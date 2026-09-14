"""Plain-Python equivalents of the ROS 2 message types we read from bags.

Field order and types mirror the ``.msg`` definitions exactly - CDR is
positional, so any deviation silently misreads the payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .cdr import CdrError, CdrReader

# sensor_msgs/Image encodings we know how to turn into a BGR numpy image,
# with their channel count. Anything else is rejected loudly.
_CHANNELS = {
    "bgr8": 3,
    "rgb8": 3,
    "bgra8": 4,
    "rgba8": 4,
    "mono8": 1,
    "8UC1": 1,
    "8UC3": 3,
}


@dataclass(frozen=True)
class Header:
    """std_msgs/Header."""

    stamp_ns: int
    frame_id: str


@dataclass(frozen=True)
class Image:
    """sensor_msgs/Image, with the pixel payload as a numpy view."""

    header: Header
    height: int
    width: int
    encoding: str
    is_bigendian: bool
    step: int
    data: np.ndarray  # (height, width, channels) or (height, width)

    def to_bgr(self) -> np.ndarray:
        """The image as a contiguous, writeable 3-channel BGR array (what
        YOLOX and OpenCV expect). Always a copy: ``data`` is a read-only view
        into the bag payload."""
        import cv2  # local import keeps this module importable without OpenCV

        enc = self.encoding
        if enc in ("bgr8", "8UC3"):
            return np.array(self.data, copy=True, order="C")
        if enc == "rgb8":
            return cv2.cvtColor(self.data, cv2.COLOR_RGB2BGR)
        if enc == "bgra8":
            return cv2.cvtColor(self.data, cv2.COLOR_BGRA2BGR)
        if enc == "rgba8":
            return cv2.cvtColor(self.data, cv2.COLOR_RGBA2BGR)
        if enc in ("mono8", "8UC1"):
            return cv2.cvtColor(self.data, cv2.COLOR_GRAY2BGR)
        raise ValueError(f"no BGR conversion for encoding {enc!r}")


@dataclass(frozen=True)
class RegionOfInterest:
    """sensor_msgs/RegionOfInterest."""

    x_offset: int
    y_offset: int
    height: int
    width: int
    do_rectify: bool


@dataclass(frozen=True)
class CameraInfo:
    """sensor_msgs/CameraInfo."""

    header: Header
    height: int
    width: int
    distortion_model: str
    d: list[float] = field(default_factory=list)
    k: np.ndarray = field(default_factory=lambda: np.eye(3))  # 3x3 intrinsics
    r: np.ndarray = field(default_factory=lambda: np.eye(3))  # 3x3 rectification
    p: np.ndarray = field(default_factory=lambda: np.zeros((3, 4)))  # 3x4 projection
    binning_x: int = 0
    binning_y: int = 0
    roi: Optional[RegionOfInterest] = None

    @property
    def fx(self) -> float:
        return float(self.k[0, 0])

    @property
    def fy(self) -> float:
        return float(self.k[1, 1])

    @property
    def cx(self) -> float:
        return float(self.k[0, 2])

    @property
    def cy(self) -> float:
        return float(self.k[1, 2])


def _read_header(r: CdrReader) -> Header:
    sec = r.int32()
    nanosec = r.uint32()
    frame_id = r.string()
    return Header(stamp_ns=sec * 1_000_000_000 + nanosec, frame_id=frame_id)


def decode_image(payload: bytes) -> Image:
    """Decode a CDR-serialized ``sensor_msgs/msg/Image``."""
    r = CdrReader(payload)
    header = _read_header(r)
    height = r.uint32()
    width = r.uint32()
    encoding = r.string()
    is_bigendian = bool(r.uint8())
    step = r.uint32()
    raw = r.uint8_sequence()

    channels = _CHANNELS.get(encoding)
    if channels is None:
        raise CdrError(f"unsupported image encoding {encoding!r}")
    expected = height * step
    if len(raw) != expected:
        raise CdrError(
            f"image payload has {len(raw)} bytes, expected height*step = {expected}"
        )

    arr = np.frombuffer(raw, dtype=np.uint8).reshape(height, step)
    arr = arr[:, : width * channels]
    if channels > 1:
        arr = arr.reshape(height, width, channels)
    return Image(header, height, width, encoding, is_bigendian, step, arr)


def decode_camera_info(payload: bytes) -> CameraInfo:
    """Decode a CDR-serialized ``sensor_msgs/msg/CameraInfo``."""
    r = CdrReader(payload)
    header = _read_header(r)
    height = r.uint32()
    width = r.uint32()
    distortion_model = r.string()
    d = r.float64_sequence()
    k = np.array(r.float64_array(9), dtype=np.float64).reshape(3, 3)
    rect = np.array(r.float64_array(9), dtype=np.float64).reshape(3, 3)
    p = np.array(r.float64_array(12), dtype=np.float64).reshape(3, 4)
    binning_x = r.uint32()
    binning_y = r.uint32()
    roi = RegionOfInterest(
        x_offset=r.uint32(),
        y_offset=r.uint32(),
        height=r.uint32(),
        width=r.uint32(),
        do_rectify=r.bool(),
    )
    return CameraInfo(
        header, height, width, distortion_model, d, k, rect, p, binning_x, binning_y, roi
    )
