"""Message conversions of detector_node. Needs a sourced ROS 2 environment
(vision_msgs, sensor_msgs); skipped elsewhere."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rclpy")
pytest.importorskip("vision_msgs")

from sensor_msgs.msg import CameraInfo as CameraInfoMsg  # noqa: E402

from tita_perception.nodes.detector_node import camera_info_from_msg, detections_to_msg  # noqa: E402
from tita_perception.pipeline.results import FrameResult, ObstacleObservation, TrackInfo  # noqa: E402


def test_camera_info_from_msg():
    msg = CameraInfoMsg()
    msg.header.frame_id = "left_img_raw"
    msg.header.stamp.sec, msg.header.stamp.nanosec = 12, 34
    msg.width, msg.height = 960, 600
    msg.distortion_model = "rational_polynomial"
    msg.d = [0.1] * 8
    msg.k = [479.0, 0.0, 480.0, 0.0, 479.0, 298.0, 0.0, 0.0, 1.0]
    msg.r = list(np.eye(3).ravel())
    msg.p = [479.0, 0.0, 480.0, 0.0, 0.0, 479.0, 298.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    info = camera_info_from_msg(msg)
    assert (info.fx, info.cx, info.cy) == (479.0, 480.0, 298.0)
    assert info.header.stamp_ns == 12_000_000_034
    assert info.p.shape == (3, 4) and len(info.d) == 8


def test_detections_to_msg_keeps_image_stamp_and_track_id():
    obs = ObstacleObservation(
        class_id=0, label="person", score=0.9, obj_conf=0.95, cls_conf=0.95, is_dynamic=True,
        bbox_xyxy=[100, 50, 160, 250], bbox_norm=[0, 0, 0, 0], center_xy=[130.0, 150.0],
        foot_xy=[130.0, 250.0], width_px=60.0, height_px=200.0, area_frac=0.02, touches_border=False,
        bearing_rad=None, foot_elevation_rad=None,
        track=TrackInfo(7, True, 3, 3, 0.1, None, None, None, None),
    )
    result = FrameResult(
        frame_seq=1, stamp_ns=5_000_000_123, recv_ns=0, frame_id="cam", image_width=960, image_height=600,
        processed_wall_ns=0, queue_wait_ms=0, inference_ms=0, total_ms=0, dropped_since_last=0,
        dropped_total=0, detections=[obs],
    )
    msg = detections_to_msg(result)
    assert (msg.header.stamp.sec, msg.header.stamp.nanosec, msg.header.frame_id) == (5, 123, "cam")
    det = msg.detections[0]
    assert det.id == "7"
    assert (det.bbox.center.position.x, det.bbox.center.position.y) == (130.0, 150.0)
    assert (det.bbox.size_x, det.bbox.size_y) == (60.0, 200.0)
    assert det.results[0].hypothesis.class_id == "person"
    assert det.results[0].hypothesis.score == pytest.approx(0.9)
