"""Frame flow: source -> buffer (drop policy) -> detector -> tracker -> results."""

from .bag_source import BagFrameSource
from .build import build_buffer, build_pipeline, load_config
from .detection_pipeline import DetectionPipeline
from .frame import Frame
from .frame_buffer import FrameBuffer, FrameQueue, LatestFrameSlot, make_frame_buffer
from .results import RECORD_MODES, FrameResult, ObstacleObservation, RecordMode, TrackInfo

__all__ = [
    "BagFrameSource",
    "DetectionPipeline",
    "Frame",
    "FrameBuffer",
    "FrameQueue",
    "FrameResult",
    "LatestFrameSlot",
    "ObstacleObservation",
    "RECORD_MODES",
    "RecordMode",
    "TrackInfo",
    "build_buffer",
    "build_pipeline",
    "load_config",
    "make_frame_buffer",
]
