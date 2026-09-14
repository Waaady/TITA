"""Draw pipeline results onto a frame for eyeballing. Debug only - never on
the robot's hot path (encoding images costs real frames per second)."""

from __future__ import annotations

import cv2
import numpy as np

from .pipeline.results import FrameResult

_DYNAMIC_COLOR = (0, 0, 255)  # BGR red
_STATIC_COLOR = (0, 200, 0)


def draw_result(image_bgr: np.ndarray, result: FrameResult) -> np.ndarray:
    """Return a copy of ``image_bgr`` with boxes, labels, track ids and the
    frame's timing overlaid."""
    out = image_bgr.copy()
    for obs in result.detections:
        x1, y1, x2, y2 = (int(round(v)) for v in obs.bbox_xyxy)
        color = _DYNAMIC_COLOR if obs.is_dynamic else _STATIC_COLOR
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        text = f"{obs.label} {obs.score:.2f}"
        if obs.track is not None:
            text = f"#{obs.track.track_id} " + text
            if obs.track.scale_rate_per_s is not None:
                text += f" s{obs.track.scale_rate_per_s:+.2f}/s"
        if obs.bearing_rad is not None:
            text += f" {np.degrees(obs.bearing_rad):+.0f}deg"
        cv2.putText(out, text, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        fx, fy = (int(round(v)) for v in obs.foot_xy)
        cv2.circle(out, (fx, fy), 3, color, -1)

    hud = (
        f"seq {result.frame_seq}  inf {result.inference_ms:.0f} ms  "
        f"wait {result.queue_wait_ms:.0f} ms  dropped {result.dropped_since_last} "
        f"(total {result.dropped_total})"
    )
    # Bottom-left so it never covers a label of a box touching the top edge.
    org = (8, out.shape[0] - 10)
    cv2.putText(out, hud, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(out, hud, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    return out
