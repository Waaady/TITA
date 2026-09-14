"""What the detection pipeline emits per frame.

This is the contract towards later components (approach / path-intrusion
classification, 3D projection, costmap). Everything a consumer might need
to judge *"is this thing coming towards me"* without re-running the
detector is included, but the judgement itself is **not** made here.

Coordinates are pixels of the original camera image unless stated
otherwise; angles follow :mod:`tita_perception.geometry` (bearing positive
right, elevation positive down, camera optical frame).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class TrackInfo:
    """Identity and image-plane motion of the object across frames."""

    track_id: int
    confirmed: bool  # seen in >= 2 frames; single-frame tracks are often noise
    hits: int
    age_frames: int
    duration_s: float  # time between first and latest sighting
    velocity_px_s: Optional[list[float]]  # box centre [vx, vy]; None on first sighting
    bearing_rate_rad_s: Optional[float]  # d(bearing)/dt; ~0 => on a collision course or static
    scale_rate_per_s: Optional[float]  # relative growth of box size; > 0 => getting closer
    height_rate_px_s: Optional[float]


@dataclass
class ObstacleObservation:
    """One detected object in one frame."""

    # -- what ----------------------------------------------------------------
    class_id: int
    label: str
    score: float  # objectness * class confidence
    obj_conf: float
    cls_conf: float
    is_dynamic: bool  # class can move by itself (person, dog, ...)
    # -- where (image) -------------------------------------------------------
    bbox_xyxy: list[float]  # [x1, y1, x2, y2] px
    bbox_norm: list[float]  # same, divided by image width/height (0..1)
    center_xy: list[float]  # box centre px
    foot_xy: list[float]  # bottom-centre px: ground contact for range estimation
    width_px: float
    height_px: float
    area_frac: float  # box area / image area - crude proximity proxy
    touches_border: bool  # box clipped by the image edge => size/foot unreliable
    # -- where (angles, from CameraInfo; None if no calibration) -------------
    bearing_rad: Optional[float]  # of box centre
    foot_elevation_rad: Optional[float]  # of foot point
    # -- identity over time --------------------------------------------------
    track: Optional[TrackInfo]


@dataclass
class FrameResult:
    """Everything produced for one processed frame."""

    frame_seq: int
    stamp_ns: int  # sensor capture time (message header)
    recv_ns: int  # receive time at the recorder / node
    frame_id: str  # TF frame of the camera
    image_width: int
    image_height: int
    # -- timing / staleness -------------------------------------------------
    processed_wall_ns: int  # wall clock when inference finished
    queue_wait_ms: float  # how long the frame waited for the detector
    inference_ms: float  # detector.detect() only
    total_ms: float  # wait + inference + tracking + packaging
    dropped_since_last: int  # frames discarded because this one was newer
    dropped_total: int
    # -- content ------------------------------------------------------------
    detections: list[ObstacleObservation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
