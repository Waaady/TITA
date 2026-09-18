"""YOLOX via TensorRT, natively - the Jetson deployment path.

Runs a serialised engine that was built **on the same device** from the
official ONNX export (``scripts/build_engine.sh``). Engines are locked to one
GPU and one TensorRT version, so they are never committed and never copied
between machines.

Written against the **TensorRT 8.6** Python API (JetPack 6.0). TensorRT 10
renamed the binding calls (``get_tensor_name``, ``execute_async_v3``); code
from tutorials targeting 10 will not run here and vice versa.

Pre- and post-processing are shared with the other backends through
:mod:`yolox_common` - the engine sees exactly the tensor the ONNX model
sees, so results should match ONNX within FP16 rounding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import numpy as np

from .base import Detection, Detector
from .coco_classes import COCO_CLASSES
from .yolox_common import decode_outputs, letterbox, postprocess


class YoloxTensorRTDetector(Detector):
    def __init__(
        self,
        engine_path: Union[str, Path],
        input_size: tuple[int, int] = (640, 640),
        conf_threshold: float = 0.3,
        nms_threshold: float = 0.45,
        class_names: Sequence[str] = COCO_CLASSES,
        class_whitelist: Sequence[int] | None = None,
        decoded_output: bool = False,
        device: str = "cuda",  # accepted for config symmetry; TensorRT always runs on the GPU
    ) -> None:
        """
        decoded_output: False for an engine built from the official YOLOX
            ONNX export (raw grid offsets, decoded here); True if the model
            was exported with ``--decode_in_inference``.
        """
        self._engine_path = Path(engine_path)
        # File check before the library imports, so "you forgot to build the
        # engine" is reported even on a machine without TensorRT.
        if not self._engine_path.is_file():
            raise FileNotFoundError(
                f"{self._engine_path} - TensorRT engines are built on the robot: scripts/build_engine.sh"
            )
        import pycuda.driver as cuda
        import tensorrt as trt

        self._cuda = cuda
        self._input_size = tuple(input_size)
        self._conf = conf_threshold
        self._nms = nms_threshold
        self._class_names = tuple(class_names)
        self._whitelist = list(class_whitelist) if class_whitelist else None
        self._decoded = decoded_output
        self.trt_version = trt.__version__

        # One CUDA context, pushed/popped around every use so the detector
        # can be built in one thread (the node's constructor) and run in
        # another (the pipeline worker).
        cuda.init()
        self._ctx = cuda.Device(0).make_context()
        try:
            self._load(trt, cuda)
        finally:
            self._ctx.pop()

    def _load(self, trt, cuda) -> None:
        logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(logger)  # must outlive the engine
        self._engine = self._runtime.deserialize_cuda_engine(self._engine_path.read_bytes())
        if self._engine is None:
            raise RuntimeError(
                f"could not deserialise {self._engine_path.name}: built on another device or "
                f"TensorRT version? Rebuild it here (scripts/build_engine.sh)."
            )
        self._exec = self._engine.create_execution_context()

        inputs, outputs = [], []
        self._bindings: list[int] = []
        for i in range(self._engine.num_bindings):
            shape = tuple(self._engine.get_binding_shape(i))
            if any(d < 0 for d in shape):
                raise ValueError(
                    f"binding {self._engine.get_binding_name(i)} has a dynamic shape {shape}; "
                    f"build the engine with a fixed input (the official export is static)"
                )
            dtype = trt.nptype(self._engine.get_binding_dtype(i))
            host = cuda.pagelocked_empty(trt.volume(shape), dtype)
            dev = cuda.mem_alloc(host.nbytes)
            self._bindings.append(int(dev))
            (inputs if self._engine.binding_is_input(i) else outputs).append((shape, host, dev))
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError(f"expected 1 input and 1 output binding, got {len(inputs)}/{len(outputs)}")
        (self._in_shape, self._in_host, self._in_dev), = inputs
        (self._out_shape, self._out_host, self._out_dev), = outputs
        self._stream = cuda.Stream()

        # The engine's input size is baked in at build time; the config must agree.
        if tuple(self._in_shape[-2:]) != self._input_size:
            raise ValueError(
                f"engine expects {self._in_shape[-2:]} but input_size is {self._input_size}; "
                f"rebuild the engine or fix detector.input_size"
            )
        n_out = self._out_shape[-1]
        if n_out != 5 + len(self._class_names):
            raise ValueError(f"engine outputs {n_out - 5} classes but {len(self._class_names)} class names given")

    # -- Detector ----------------------------------------------------------

    @property
    def class_names(self) -> Sequence[str]:
        return self._class_names

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        tensor, scale = letterbox(image_bgr, self._input_size)
        self._ctx.push()
        try:
            np.copyto(self._in_host, tensor.ravel(), casting="same_kind")  # float32 -> engine dtype
            self._cuda.memcpy_htod_async(self._in_dev, self._in_host, self._stream)
            self._exec.execute_async_v2(bindings=self._bindings, stream_handle=self._stream.handle)
            self._cuda.memcpy_dtoh_async(self._out_host, self._out_dev, self._stream)
            self._stream.synchronize()
        finally:
            self._ctx.pop()
        raw = self._out_host.reshape(self._out_shape)[0].astype(np.float32, copy=False)
        decoded = raw if self._decoded else decode_outputs(raw, self._input_size)
        return postprocess(
            decoded, scale, image_bgr.shape[:2], self._conf, self._nms, self._whitelist
        )

    def close(self) -> None:
        ctx = getattr(self, "_ctx", None)
        if ctx is not None:
            ctx.detach()
            self._ctx = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001 - interpreter shutdown, nothing useful to do
            pass

    def __repr__(self) -> str:
        return (
            f"YoloxTensorRTDetector({self._engine_path.name}, {self._input_size}, "
            f"trt={self.trt_version}, in={self._in_host.dtype}, out={self._out_host.dtype})"
        )
