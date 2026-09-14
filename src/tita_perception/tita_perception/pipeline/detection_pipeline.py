"""frame buffer -> detector -> tracker -> :class:`FrameResult`.

The consumer side of the pipeline. It is source-agnostic: a bag replay
thread or (later) a ROS subscription callback puts :class:`Frame` objects
into the buffer; :meth:`DetectionPipeline.run` drains it. :meth:`process`
is the synchronous core and can be called directly from a ROS callback.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, Optional

from ..detectors.base import Detection, Detector
from ..detectors.coco_classes import DEFAULT_DYNAMIC_CLASSES
from ..geometry import PixelToAngle
from ..tracking import IouTracker, TrackState
from ..bag.ros_messages import CameraInfo
from .frame import Frame
from .frame_buffer import FrameBuffer
from .results import FrameResult, ObstacleObservation, TrackInfo

ResultSink = Callable[[FrameResult, Frame], None]
"""Receives each result together with the frame it was computed from (the
frame is only needed for visualisation and is never retained by the
pipeline)."""


class DetectionPipeline:
    def __init__(
        self,
        detector: Detector,
        tracker: Optional[IouTracker] = None,
        camera_info: Optional[CameraInfo] = None,
        dynamic_classes: Iterable[str] = DEFAULT_DYNAMIC_CLASSES,
        undistort_angles: bool = False,
        border_margin_px: int = 2,
    ) -> None:
        self._detector = detector
        self._tracker = tracker
        self._undistort = undistort_angles
        self._angles: Optional[PixelToAngle] = None
        if camera_info is not None:
            self.set_camera_info(camera_info)
        self._dynamic = frozenset(dynamic_classes)
        self._border = border_margin_px
        self.frames_processed = 0

    @property
    def detector(self) -> Detector:
        return self._detector

    def set_camera_info(self, camera_info: CameraInfo) -> None:
        """Enable bearing/elevation output. May be called after construction -
        on the robot CameraInfo arrives on its own topic, later than the
        first image."""
        self._angles = PixelToAngle(camera_info, self._undistort)

    # -- threaded consumer -------------------------------------------------

    def run(
        self,
        buffer: FrameBuffer,
        sink: ResultSink,
        stop: Optional[threading.Event] = None,
        poll_s: float = 0.5,
    ) -> None:
        """Consume ``buffer`` until it is closed and drained (or ``stop`` is
        set), passing each :class:`FrameResult` to ``sink``."""
        while stop is None or not stop.is_set():
            item = buffer.get(timeout=poll_s)
            if item is None:
                if buffer.closed:
                    break
                continue
            frame, dropped = item
            sink(self.process(frame, dropped, buffer.dropped_total), frame)

    # -- synchronous core --------------------------------------------------

    def process(self, frame: Frame, dropped_since_last: int = 0, dropped_total: int = 0) -> FrameResult:
        t_pick = time.perf_counter()
        queue_wait_ms = (t_pick - frame.enqueued_at) * 1e3

        detections = self._detector.detect(frame.image)
        t_inf = time.perf_counter()

        tracks: list[Optional[TrackState]]
        if self._tracker is not None:
            tracks = self._tracker.update(detections, frame.stamp_ns)
        else:
            tracks = [None] * len(detections)

        observations = [
            self._observation(d, t, frame.width, frame.height) for d, t in zip(detections, tracks)
        ]
        t_end = time.perf_counter()
        self.frames_processed += 1
        return FrameResult(
            frame_seq=frame.seq,
            stamp_ns=frame.stamp_ns,
            recv_ns=frame.recv_ns,
            frame_id=frame.frame_id,
            image_width=frame.width,
            image_height=frame.height,
            processed_wall_ns=time.time_ns(),
            queue_wait_ms=queue_wait_ms,
            inference_ms=(t_inf - t_pick) * 1e3,
            total_ms=(t_end - frame.enqueued_at) * 1e3,
            dropped_since_last=dropped_since_last,
            dropped_total=dropped_total,
            detections=observations,
        )

    # -- packaging ---------------------------------------------------------

    def _observation(
        self, det: Detection, track: Optional[TrackState], width: int, height: int
    ) -> ObstacleObservation:
        label = self._detector.label(det.class_id)
        cx, cy = det.center
        foot = (cx, det.y2)
        m = self._border
        touches_border = det.x1 <= m or det.y1 <= m or det.x2 >= width - m or det.y2 >= height - m

        bearing = foot_elev = None
        if self._angles is not None:
            bearing = self._angles.bearing(cx, cy)
            foot_elev = self._angles.elevation(foot[1], foot[0])

        track_info = None
        if track is not None:
            bearing_rate = None
            if self._angles is not None and track.velocity_px_s is not None:
                bearing_rate = self._angles.bearing_rate(cx, track.velocity_px_s[0])
            track_info = TrackInfo(
                track_id=track.track_id,
                confirmed=track.confirmed,
                hits=track.hits,
                age_frames=track.age,
                duration_s=track.duration_s,
                velocity_px_s=list(track.velocity_px_s) if track.velocity_px_s else None,
                bearing_rate_rad_s=bearing_rate,
                scale_rate_per_s=track.scale_rate_per_s,
                height_rate_px_s=track.height_rate_px_s,
            )

        return ObstacleObservation(
            class_id=det.class_id,
            label=label,
            score=det.score,
            obj_conf=det.obj_conf,
            cls_conf=det.cls_conf,
            is_dynamic=label in self._dynamic,
            bbox_xyxy=[det.x1, det.y1, det.x2, det.y2],
            bbox_norm=[det.x1 / width, det.y1 / height, det.x2 / width, det.y2 / height],
            center_xy=[cx, cy],
            foot_xy=[foot[0], foot[1]],
            width_px=det.width,
            height_px=det.height,
            area_frac=det.area / float(width * height),
            touches_border=touches_border,
            bearing_rad=bearing,
            foot_elevation_rad=foot_elev,
            track=track_info,
        )
