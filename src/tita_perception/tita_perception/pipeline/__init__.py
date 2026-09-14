"""Frame flow: source -> buffer (drop policy) -> detector -> tracker -> results."""

from .bag_source import BagFrameSource
from .detection_pipeline import DetectionPipeline
from .frame import Frame
from .frame_buffer import FrameBuffer, FrameQueue, LatestFrameSlot, make_frame_buffer
from .results import FrameResult, ObstacleObservation, TrackInfo

__all__ = [
    "BagFrameSource",
    "DetectionPipeline",
    "Frame",
    "FrameBuffer",
    "FrameQueue",
    "FrameResult",
    "LatestFrameSlot",
    "ObstacleObservation",
    "TrackInfo",
    "make_frame_buffer",
]
