"""YOLOX via PyTorch, using the upstream ``yolox`` package from
``external/YOLOX``.

The simplest backend and the reference the others are checked against; not
what runs on the robot (see ``models/README.md`` for the export chain).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Sequence, Union

import numpy as np

from .base import Detection, Detector
from .coco_classes import COCO_CLASSES
from .yolox_common import letterbox, postprocess


class YoloxTorchDetector(Detector):
    def __init__(
        self,
        checkpoint_path: Union[str, Path],
        exp_name: str = "yolox-s",
        exp_file: Union[str, Path, None] = None,
        input_size: tuple[int, int] | None = None,
        conf_threshold: float = 0.3,
        nms_threshold: float = 0.45,
        device: str = "cpu",
        fp16: bool = False,
        class_names: Sequence[str] = COCO_CLASSES,
        class_whitelist: Sequence[int] | None = None,
    ) -> None:
        """
        exp_name / exp_file: which YOLOX experiment defines the architecture
            (``yolox-s``, ``yolox-tiny``, ... or a file from
            ``perception/configs/``). The checkpoint must match it.
        input_size: defaults to the experiment's ``test_size``.
        """
        import torch
        from yolox.exp import get_exp

        self._ckpt_path = Path(checkpoint_path)
        if not self._ckpt_path.is_file():
            raise FileNotFoundError(self._ckpt_path)

        exp = get_exp(str(exp_file) if exp_file else None, exp_name)
        if len(class_names) != exp.num_classes:
            raise ValueError(
                f"experiment has {exp.num_classes} classes but {len(class_names)} class names given"
            )
        self._input_size = tuple(input_size) if input_size else tuple(exp.test_size)
        self._conf = conf_threshold
        self._nms = nms_threshold
        self._class_names = tuple(class_names)
        self._whitelist = list(class_whitelist) if class_whitelist else None

        if device.startswith("cuda") and not torch.cuda.is_available():
            warnings.warn("CUDA requested but not available - falling back to CPU", stacklevel=2)
            device = "cpu"
        self._device = torch.device(device)
        self._fp16 = fp16 and self._device.type == "cuda"

        model = exp.get_model()
        state = self._load_state_dict(torch, self._ckpt_path)
        model.load_state_dict(state)
        model.eval()
        model.head.decode_in_inference = True  # outputs [cx, cy, w, h, obj, cls...] in input px
        model.to(self._device)
        if self._fp16:
            model.half()
        self._model = model
        self._torch = torch

    @staticmethod
    def _load_state_dict(torch, path: Path):
        # torch >= 2.6 defaults to weights_only=True, which the official
        # YOLOX checkpoints satisfy. Older training checkpoints may not.
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=True)
        except Exception:  # noqa: BLE001
            warnings.warn(
                f"{path.name}: weights_only load failed, retrying with weights_only=False "
                "(only do this for checkpoints you trust)",
                stacklevel=3,
            )
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
        return ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt

    # -- Detector ----------------------------------------------------------

    @property
    def class_names(self) -> Sequence[str]:
        return self._class_names

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        torch = self._torch
        tensor, scale = letterbox(image_bgr, self._input_size)
        x = torch.from_numpy(tensor).unsqueeze(0).to(self._device)
        if self._fp16:
            x = x.half()
        with torch.no_grad():
            out = self._model(x)
        decoded = out[0].float().cpu().numpy()
        return postprocess(
            decoded, scale, image_bgr.shape[:2], self._conf, self._nms, self._whitelist
        )

    def __repr__(self) -> str:
        return (
            f"YoloxTorchDetector({self._ckpt_path.name}, {self._input_size}, "
            f"device={self._device}, fp16={self._fp16})"
        )
