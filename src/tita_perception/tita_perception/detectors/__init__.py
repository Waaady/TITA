"""Detector backends behind one interface.

Backends are imported lazily by :func:`build_detector` so that a machine
without torch can still use the ONNX path (and vice versa).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence, Union

from .base import Detection, Detector
from .coco_classes import COCO_CLASSES, DEFAULT_DYNAMIC_CLASSES

__all__ = [
    "COCO_CLASSES",
    "DEFAULT_DYNAMIC_CLASSES",
    "Detection",
    "Detector",
    "build_detector",
]

_COMMON_KEYS = ("input_size", "conf_threshold", "nms_threshold", "device")


def build_detector(
    config: Mapping[str, Any], models_root: Union[str, Path, None] = None
) -> Detector:
    """Construct a detector from the ``detector`` section of the YAML config.

    Layout (see ``config/detector.yaml``)::

        backend: onnx | torch
        input_size, conf_threshold, nms_threshold, device   # shared
        class_names: [...]        # optional, default COCO
        class_whitelist: [...]    # optional, by name
        onnx:  {model_path, decoded_output, num_threads}
        torch: {checkpoint_path, exp_name, exp_file, fp16}

    Relative model paths are resolved against ``models_root``.
    """
    backend = config["backend"]
    root = Path(models_root) if models_root else Path.cwd()

    common = {k: config[k] for k in _COMMON_KEYS if k in config}
    if "input_size" in common:
        common["input_size"] = tuple(common["input_size"])
    class_names: Sequence[str] = tuple(config.get("class_names") or COCO_CLASSES)
    whitelist_names = config.get("class_whitelist")
    whitelist = [class_names.index(n) for n in whitelist_names] if whitelist_names else None

    def resolve(path: Union[str, Path, None]) -> Union[Path, None]:
        if path is None:
            return None
        p = Path(path)
        return p if p.is_absolute() else root / p

    if backend == "onnx":
        from .yolox_onnx import YoloxOnnxDetector

        opts = dict(config.get("onnx") or {})
        opts["model_path"] = resolve(opts.get("model_path"))
        return YoloxOnnxDetector(
            class_names=class_names, class_whitelist=whitelist, **common, **opts
        )

    if backend == "torch":
        from .yolox_torch import YoloxTorchDetector

        opts = dict(config.get("torch") or {})
        opts["checkpoint_path"] = resolve(opts.get("checkpoint_path"))
        opts["exp_file"] = resolve(opts.get("exp_file"))
        return YoloxTorchDetector(
            class_names=class_names, class_whitelist=whitelist, **common, **opts
        )

    raise ValueError(f"unknown detector backend {backend!r}; expected 'onnx' or 'torch'")
