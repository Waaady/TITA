"""Frame-to-frame association so a detection has a stable identity.

Greedy IoU matching with a short memory - deliberately the simplest thing
that gives downstream code what it needs: a ``track_id`` that persists while
an object stays in view, plus per-track motion in the image plane. Whether a
tracked object is *approaching* or *entering the path* is decided elsewhere;
this module only provides the raw quantities for that decision.

Replace with ByteTrack once detections are noisier or the scene busier; the
:class:`TrackState` fields are the interface to keep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from ..detectors.base import Detection


@dataclass
class TrackState:
    track_id: int
    class_id: int
    first_stamp_ns: int
    last_stamp_ns: int
    bbox: np.ndarray  # xyxy, px
    hits: int = 1  # frames in which the track was matched
    age: int = 1  # frames since creation, matched or not
    misses: int = 0  # consecutive frames without a match
    # Image-plane motion, exponentially smoothed. None until the 2nd hit.
    velocity_px_s: Optional[tuple[float, float]] = None  # centre (vx, vy)
    scale_rate_per_s: Optional[float] = None  # d(sqrt(area))/dt / sqrt(area)
    height_rate_px_s: Optional[float] = None  # d(box height)/dt
    _score_sum: float = field(default=0.0, repr=False)

    @property
    def confirmed(self) -> bool:
        return self.hits >= 2

    @property
    def duration_s(self) -> float:
        return (self.last_stamp_ns - self.first_stamp_ns) / 1e9

    @property
    def center(self) -> tuple[float, float]:
        return (0.5 * (self.bbox[0] + self.bbox[2]), 0.5 * (self.bbox[1] + self.bbox[3]))


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise IoU between two sets of xyxy boxes, shape (len(a), len(b))."""
    if a.shape[0] == 0 or b.shape[0] == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float32)
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    wh = np.clip(rb - lt, 0, None)
    inter = wh[..., 0] * wh[..., 1]
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


class IouTracker:
    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_misses: int = 5,
        smoothing: float = 0.5,
        same_class_only: bool = False,
    ) -> None:
        """
        iou_threshold: minimum overlap to associate a detection with a track.
        max_misses: frames a track survives without a detection.
        smoothing: EMA weight of the newest velocity sample (1 = no smoothing).
        same_class_only: refuse to match across classes. Off by default -
            the detector's class flickers (chair/couch) more often than two
            objects swap places.
        """
        self._iou_thr = iou_threshold
        self._max_misses = max_misses
        self._alpha = smoothing
        self._same_class = same_class_only
        self._tracks: list[TrackState] = []
        self._next_id = 1

    @property
    def tracks(self) -> list[TrackState]:
        return list(self._tracks)

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(
        self, detections: Sequence[Detection], stamp_ns: int
    ) -> list[Optional[TrackState]]:
        """Associate ``detections`` (from one frame at ``stamp_ns``) with
        existing tracks. Returns one :class:`TrackState` per detection, in
        the same order (a fresh track for unmatched detections)."""
        det_boxes = (
            np.stack([d.xyxy for d in detections]) if detections else np.zeros((0, 4), np.float32)
        )
        trk_boxes = (
            np.stack([t.bbox for t in self._tracks]) if self._tracks else np.zeros((0, 4), np.float32)
        )
        ious = iou_matrix(trk_boxes, det_boxes)
        if self._same_class:
            for ti, t in enumerate(self._tracks):
                for di, d in enumerate(detections):
                    if t.class_id != d.class_id:
                        ious[ti, di] = 0.0

        assignment: list[Optional[TrackState]] = [None] * len(detections)
        matched_tracks: set[int] = set()
        # Greedy: best IoU pair first, then next best among the unassigned.
        if ious.size:
            order = np.dstack(np.unravel_index(np.argsort(-ious, axis=None), ious.shape))[0]
            for ti, di in order:
                if ious[ti, di] < self._iou_thr:
                    break
                if ti in matched_tracks or assignment[di] is not None:
                    continue
                track = self._tracks[ti]
                self._advance(track, detections[di], stamp_ns)
                assignment[di] = track
                matched_tracks.add(ti)

        for ti, track in enumerate(self._tracks):
            if ti not in matched_tracks:
                track.age += 1
                track.misses += 1
        self._tracks = [t for t in self._tracks if t.misses <= self._max_misses]

        for di, det in enumerate(detections):
            if assignment[di] is None:
                track = TrackState(
                    track_id=self._next_id,
                    class_id=det.class_id,
                    first_stamp_ns=stamp_ns,
                    last_stamp_ns=stamp_ns,
                    bbox=det.xyxy.copy(),
                )
                self._next_id += 1
                self._tracks.append(track)
                assignment[di] = track
        return assignment

    # -- internals ---------------------------------------------------------

    def _advance(self, track: TrackState, det: Detection, stamp_ns: int) -> None:
        dt = (stamp_ns - track.last_stamp_ns) / 1e9
        if dt > 0:
            old_c = track.center
            new_c = det.center
            vx, vy = (new_c[0] - old_c[0]) / dt, (new_c[1] - old_c[1]) / dt
            old_h = float(track.bbox[3] - track.bbox[1])
            old_s = math.sqrt(max(float((track.bbox[2] - track.bbox[0]) * old_h), 1e-6))
            new_s = math.sqrt(max(det.area, 1e-6))
            scale_rate = (new_s / old_s - 1.0) / dt
            height_rate = (det.height - old_h) / dt
            track.velocity_px_s = self._ema2(track.velocity_px_s, (vx, vy))
            track.scale_rate_per_s = self._ema(track.scale_rate_per_s, scale_rate)
            track.height_rate_px_s = self._ema(track.height_rate_px_s, height_rate)
        track.bbox = det.xyxy.copy()
        track.class_id = det.class_id
        track.last_stamp_ns = stamp_ns
        track.hits += 1
        track.age += 1
        track.misses = 0

    def _ema(self, old: Optional[float], new: float) -> float:
        return new if old is None else self._alpha * new + (1 - self._alpha) * old

    def _ema2(
        self, old: Optional[tuple[float, float]], new: tuple[float, float]
    ) -> tuple[float, float]:
        if old is None:
            return new
        return (self._ema(old[0], new[0]), self._ema(old[1], new[1]))
