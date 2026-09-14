"""Build the pipeline from ``config/detector.yaml``.

Shared by the offline bag script and the ROS node so both read the same
file the same way - there is exactly one place where a config key is
turned into an object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import yaml

from ..bag.ros_messages import CameraInfo
from ..detectors import build_detector
from ..tracking import IouTracker
from .detection_pipeline import DetectionPipeline
from .frame_buffer import FrameBuffer, make_frame_buffer


def load_config(path: Union[str, Path]) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def build_pipeline(
    cfg: dict[str, Any],
    models_root: Union[str, Path],
    camera_info: Optional[CameraInfo] = None,
    warmup: bool = True,
) -> DetectionPipeline:
    """Detector (warmed up), tracker and pipeline from the ``detector``,
    ``tracking`` and ``pipeline`` sections."""
    detector = build_detector(cfg["detector"], models_root=models_root)
    if warmup:
        detector.warmup()

    trk = cfg["tracking"]
    tracker = None
    if trk.get("enabled", True):
        tracker = IouTracker(
            iou_threshold=trk["iou_threshold"],
            max_misses=trk["max_misses"],
            smoothing=trk["smoothing"],
            same_class_only=trk["same_class_only"],
        )

    pipe = cfg["pipeline"]
    return DetectionPipeline(
        detector,
        tracker=tracker,
        camera_info=camera_info,
        dynamic_classes=pipe["dynamic_classes"],
        undistort_angles=pipe["undistort_angles"],
        border_margin_px=pipe["border_margin_px"],
    )


def build_buffer(cfg: dict[str, Any]) -> FrameBuffer:
    pipe = cfg["pipeline"]
    return make_frame_buffer(pipe["frame_buffer"], pipe.get("queue_size", 8))
