"""YOLOX via ONNX Runtime.

Works on the workstation (CPU or CUDA) and on the Jetson. Needs no torch at
inference time; on Windows the CUDA/cuDNN DLLs are borrowed from the torch
cu128 wheel through ``onnxruntime.preload_dlls()`` if no CUDA toolkit is on
the PATH (see requirements.txt).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import numpy as np

from .base import Detection, Detector
from .coco_classes import COCO_CLASSES
from .yolox_common import decode_outputs, letterbox, postprocess

_PROVIDER_ALIASES = {
    "cpu": ["CPUExecutionProvider"],
    "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "tensorrt": ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
}


class YoloxOnnxDetector(Detector):
    def __init__(
        self,
        model_path: Union[str, Path],
        input_size: tuple[int, int] = (640, 640),
        conf_threshold: float = 0.3,
        nms_threshold: float = 0.45,
        device: str = "cpu",
        class_names: Sequence[str] = COCO_CLASSES,
        class_whitelist: Sequence[int] | None = None,
        decoded_output: bool = False,
        num_threads: int | None = None,
    ) -> None:
        """
        decoded_output: False for the official YOLOX ONNX export (raw grid
            offsets, decoded here); True if the model was exported with
            ``--decode_in_inference``.
        """
        import onnxruntime as ort

        self._model_path = Path(model_path)
        if not self._model_path.is_file():
            raise FileNotFoundError(self._model_path)
        self._input_size = tuple(input_size)
        self._conf = conf_threshold
        self._nms = nms_threshold
        self._class_names = tuple(class_names)
        self._whitelist = list(class_whitelist) if class_whitelist else None
        self._decoded = decoded_output

        providers = _PROVIDER_ALIASES.get(device.lower())
        if providers is None:
            raise ValueError(f"unknown device {device!r}; use one of {list(_PROVIDER_ALIASES)}")
        if device.lower() != "cpu":
            # ORT >= 1.21: locate CUDA/cuDNN DLLs from pip packages or torch.
            preload = getattr(ort, "preload_dlls", None)
            if preload is not None:
                try:
                    preload()
                except Exception:  # noqa: BLE001 - best effort, ORT reports the real error
                    pass

        opts = ort.SessionOptions()
        if num_threads:
            opts.intra_op_num_threads = num_threads
        self._session = ort.InferenceSession(str(self._model_path), opts, providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self.active_providers = self._session.get_providers()

        n_out = self._session.get_outputs()[0].shape[-1]
        if isinstance(n_out, int) and n_out != 5 + len(self._class_names):
            raise ValueError(
                f"model outputs {n_out - 5} classes but {len(self._class_names)} class names given"
            )

    # -- Detector ----------------------------------------------------------

    @property
    def class_names(self) -> Sequence[str]:
        return self._class_names

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        tensor, scale = letterbox(image_bgr, self._input_size)
        raw = self._session.run(None, {self._input_name: tensor[None]})[0][0]
        decoded = raw if self._decoded else decode_outputs(raw, self._input_size)
        return postprocess(
            decoded, scale, image_bgr.shape[:2], self._conf, self._nms, self._whitelist
        )

    def __repr__(self) -> str:
        return (
            f"YoloxOnnxDetector({self._model_path.name}, {self._input_size}, "
            f"providers={self.active_providers})"
        )
