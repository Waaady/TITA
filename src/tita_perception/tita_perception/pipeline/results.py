"""What the detection pipeline emits per frame.

This is the contract towards later components (approach / path-intrusion
classification, 3D projection, costmap). Everything a consumer might need
to judge *"is this thing coming towards me"* without re-running the
detector is included, but the judgement itself is **not** made here.

Coordinates are pixels of the original camera image unless stated
otherwise; angles follow :mod:`tita_perception.geometry` (bearing positive
right, elevation positive down, camera optical frame).

Two record modes when serialising (``to_dict``):

``minimal`` (default)
    What a consumer needs to *act* on a detection and nothing else: when and
    from which camera, what, how sure, can it move, which track, where in
    the image, and the two angles. Track identity is flattened into the
    detection. Everything left out is either derivable from these fields
    plus the camera geometry, or is telemetry about the detector rather
    than about the scene.

``expanded``
    Every field of every dataclass, nested as declared. For benchmarking
    (per-frame timing, drop counts), threshold analysis (``obj_conf`` /
    ``cls_conf``) and re-deriving geometry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

RecordMode = Literal["minimal", "expanded"]
RECORD_MODES: tuple[str, ...] = ("minimal", "expanded")


def _check_mode(mode: str) -> None:
    if mode not in RECORD_MODES:
        raise ValueError(f"unknown record mode {mode!r}, expected one of {RECORD_MODES}")


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

    def to_dict(self, mode: RecordMode = "minimal") -> dict[str, Any]:
        _check_mode(mode)
        if mode == "expanded":
            return asdict(self)
        track = self.track
        return {
            "label": self.label,
            "score": self.score,
            "is_dynamic": self.is_dynamic,
            "track_id": track.track_id if track else None,
            "confirmed": track.confirmed if track else False,
            "bbox_xyxy": self.bbox_xyxy,
            "bearing_rad": self.bearing_rad,
            "foot_elevation_rad": self.foot_elevation_rad,
        }


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

    def to_dict(self, mode: RecordMode = "minimal") -> dict[str, Any]:
        _check_mode(mode)
        if mode == "expanded":
            return asdict(self)
        return {
            "frame_seq": self.frame_seq,
            "stamp_ns": self.stamp_ns,
            "frame_id": self.frame_id,
            "detections": [o.to_dict(mode) for o in self.detections],
        }
