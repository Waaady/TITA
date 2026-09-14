"""IoU tracker motion estimates and CameraInfo angle conventions."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tita_perception.bag.ros_messages import CameraInfo, Header
from tita_perception.detectors.base import Detection
from tita_perception.geometry import PixelToAngle
from tita_perception.tracking import IouTracker, iou_matrix


def det(x1, y1, x2, y2, cls=0, score=0.9) -> Detection:
    return Detection(class_id=cls, score=score, obj_conf=score, cls_conf=1.0, x1=x1, y1=y1, x2=x2, y2=y2)


NS = 1_000_000_000


def test_iou_matrix():
    a = np.array([[0, 0, 10, 10]], np.float32)
    b = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [20, 20, 30, 30]], np.float32)
    np.testing.assert_allclose(iou_matrix(a, b)[0], [1.0, 1 / 3, 0.0], atol=1e-6)
    assert iou_matrix(np.zeros((0, 4)), b).shape == (0, 3)


def test_track_id_is_stable_and_velocity_has_right_sign():
    trk = IouTracker(iou_threshold=0.3, max_misses=2, smoothing=1.0)
    t0 = trk.update([det(100, 100, 200, 300)], 0)[0]
    assert t0.track_id == 1 and not t0.confirmed and t0.velocity_px_s is None
    
    # 0.1 s later, moved 10 px right and grown by 20 %
    t1 = trk.update([det(110, 100, 230, 340)], NS // 10)[0]
    assert t1.track_id == 1 and t1.confirmed and t1.hits == 2
    vx, vy = t1.velocity_px_s
    assert vx == pytest.approx((170 - 150) / 0.1)
    assert vy == pytest.approx((220 - 200) / 0.1)
    assert t1.scale_rate_per_s == pytest.approx((1.2 - 1.0) / 0.1)
    assert t1.height_rate_px_s == pytest.approx((240 - 200) / 0.1)
    assert t1.duration_s == pytest.approx(0.1)


def test_new_object_gets_new_id_and_lost_track_expires():
    trk = IouTracker(iou_threshold=0.3, max_misses=1)
    a = trk.update([det(0, 0, 50, 50)], 0)[0]
    b = trk.update([det(500, 500, 550, 550)], NS)[0]
    assert (a.track_id, b.track_id) == (1, 2)
    assert len(trk.tracks) == 2  # a missed once, still alive
    trk.update([], 2 * NS)
    assert [t.track_id for t in trk.tracks] == [2]  # a exceeded max_misses, b at the limit
    trk.update([], 3 * NS)
    assert trk.tracks == []
    c = trk.update([det(0, 0, 50, 50)], 4 * NS)[0]
    assert c.track_id == 3  # ids are never reused


def test_greedy_matching_prefers_best_overlap_and_respects_class_option():
    trk = IouTracker(iou_threshold=0.1, same_class_only=True)
    trk.update([det(0, 0, 100, 100, cls=0)], 0)
    same_box_other_class = trk.update([det(0, 0, 100, 100, cls=1)], NS // 10)[0]
    assert same_box_other_class.track_id == 2

    trk = IouTracker(iou_threshold=0.1)
    trk.update([det(0, 0, 100, 100), det(200, 0, 300, 100)], 0)
    out = trk.update([det(205, 0, 305, 100), det(2, 0, 102, 100)], NS // 10)
    assert [t.track_id for t in out] == [2, 1]


def _camera_info(fx=500.0, fy=500.0, cx=320.0, cy=240.0, d=None) -> CameraInfo:
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    return CameraInfo(Header(0, "cam"), 480, 640, "plumb_bob", d or [], k)


def test_bearing_and_elevation_conventions():
    ang = PixelToAngle(_camera_info())
    assert ang.bearing(320) == pytest.approx(0.0)
    assert ang.bearing(320 + 500) == pytest.approx(math.pi / 4)  # right => positive
    assert ang.bearing(320 - 500) == pytest.approx(-math.pi / 4)
    assert ang.elevation(240 + 500) == pytest.approx(math.pi / 4)  # down => positive
    # bearing rate: 500 px/s at the principal point == 1 rad/s
    assert ang.bearing_rate(320, 500) == pytest.approx(1.0)
    assert ang.bearing_rate(820, 500) == pytest.approx(0.5)


def test_undistort_flag_is_a_noop_without_distortion():
    ang = PixelToAngle(_camera_info(d=[0, 0, 0, 0, 0]), undistort=True)
    assert ang.bearing(820) == pytest.approx(math.pi / 4)


def test_invalid_intrinsics_rejected():
    with pytest.raises(ValueError):
        PixelToAngle(_camera_info(fx=0.0))
