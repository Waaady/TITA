"""End-to-end pipeline behaviour with a fake detector: staleness handling,
result packaging, and the ONNX backend against the real model if present."""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Sequence

import numpy as np
import pytest

from tita_perception.bag.ros_messages import CameraInfo, Header
from tita_perception.detectors import COCO_CLASSES, build_detector
from tita_perception.detectors.base import Detection, Detector
from tita_perception.pipeline import DetectionPipeline, Frame, FrameQueue, LatestFrameSlot
from tita_perception.tracking import IouTracker

REPO_ROOT = Path(__file__).resolve().parents[3]
ONNX_MODEL = REPO_ROOT / "models" / "onnx" / "yolox_s.onnx"


class FakeDetector(Detector):
    """Returns a person box that walks right by 5 px per frame seq; takes
    ``delay`` seconds per call to simulate a slow backend."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls: list[int] = []

    @property
    def class_names(self) -> Sequence[str]:
        return COCO_CLASSES

    @property
    def input_size(self) -> tuple[int, int]:
        return (32, 32)

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        seq = int(image_bgr[0, 0, 0])
        self.calls.append(seq)
        time.sleep(self.delay)
        x = 100 + 5 * seq
        return [
            Detection(0, 0.9, 0.95, 0.947, x, 50, x + 60, 250),  # person
            Detection(56, 0.6, 0.8, 0.75, 0, 300, 120, 600),  # chair touching left border
        ]


def _frame(seq: int, w: int = 960, h: int = 600) -> Frame:
    img = np.zeros((h, w, 3), np.uint8)
    img[0, 0, 0] = seq
    return Frame(seq=seq, stamp_ns=seq * 25_000_000, recv_ns=seq * 25_000_000 + 5, frame_id="cam", image=img)


def _camera_info() -> CameraInfo:
    k = np.array([[480.0, 0, 480.0], [0, 480.0, 300.0], [0, 0, 1]])
    return CameraInfo(Header(0, "cam"), 600, 960, "plumb_bob", [0.0] * 5, k)


def test_process_packages_everything_downstream_needs():
    pipe = DetectionPipeline(FakeDetector(), tracker=IouTracker(smoothing=1.0), camera_info=_camera_info())
    r0 = pipe.process(_frame(0))
    r1 = pipe.process(_frame(1), dropped_since_last=3, dropped_total=3)

    assert (r1.frame_seq, r1.stamp_ns, r1.recv_ns, r1.frame_id) == (1, 25_000_000, 25_000_005, "cam")
    assert (r1.image_width, r1.image_height) == (960, 600)
    assert r1.dropped_since_last == 3 and r1.dropped_total == 3
    assert r1.inference_ms >= 0 and r1.total_ms >= r1.inference_ms

    person, chair = r1.detections
    assert person.label == "person" and person.is_dynamic and person.class_id == 0
    assert chair.label == "chair" and not chair.is_dynamic and chair.touches_border
    assert not person.touches_border
    assert person.bbox_xyxy == [105, 50, 165, 250]
    assert person.bbox_norm == pytest.approx([105 / 960, 50 / 600, 165 / 960, 250 / 600])
    assert person.center_xy == [135.0, 150.0] and person.foot_xy == [135.0, 250.0]
    assert person.area_frac == pytest.approx(60 * 200 / (960 * 600))
    assert person.bearing_rad == pytest.approx(math.atan((135 - 480) / 480))
    assert person.foot_elevation_rad == pytest.approx(math.atan((250 - 300) / 480))

    # tracking: same id as in frame 0, moved 5 px in 25 ms => 200 px/s right
    assert r0.detections[0].track.track_id == person.track.track_id
    assert person.track.confirmed and person.track.hits == 2
    assert person.track.velocity_px_s == pytest.approx([200.0, 0.0])
    assert person.track.scale_rate_per_s == pytest.approx(0.0)
    assert person.track.bearing_rate_rad_s > 0
    assert r0.detections[0].track.velocity_px_s is None

    d = r1.to_dict("expanded")
    assert d["detections"][0]["track"]["track_id"] == person.track.track_id
    import json

    json.dumps(d)  # must be serialisable as-is


def test_minimal_record_is_the_default_and_flattens_track():
    pipe = DetectionPipeline(FakeDetector(), tracker=IouTracker(smoothing=1.0), camera_info=_camera_info())
    pipe.process(_frame(0))
    r1 = pipe.process(_frame(1), dropped_since_last=3, dropped_total=3)
    person = r1.detections[0]

    d = r1.to_dict()
    assert d == r1.to_dict("minimal")
    assert set(d) == {"frame_seq", "stamp_ns", "frame_id", "detections"}
    assert (d["frame_seq"], d["stamp_ns"], d["frame_id"]) == (1, 25_000_000, "cam")

    p = d["detections"][0]
    assert set(p) == {
        "label", "score", "is_dynamic", "track_id", "confirmed", "bbox_xyxy", "bearing_rad", "foot_elevation_rad"
    }
    assert p["label"] == "person" and p["is_dynamic"]
    assert p["track_id"] == person.track.track_id and p["confirmed"]
    assert p["bbox_xyxy"] == person.bbox_xyxy
    assert p["bearing_rad"] == pytest.approx(person.bearing_rad)
    assert p["foot_elevation_rad"] == pytest.approx(person.foot_elevation_rad)

    with pytest.raises(ValueError):
        r1.to_dict("verbose")


def test_minimal_record_without_tracker_has_null_identity():
    r = DetectionPipeline(FakeDetector()).process(_frame(0))
    p = r.to_dict()["detections"][0]
    assert p["track_id"] is None and p["confirmed"] is False


def test_without_camera_info_and_tracker_fields_are_none():
    r = DetectionPipeline(FakeDetector()).process(_frame(0))
    obs = r.detections[0]
    assert obs.bearing_rad is None and obs.foot_elevation_rad is None and obs.track is None


def test_slow_detector_with_latest_slot_skips_stale_frames():
    detector = FakeDetector(delay=0.03)
    pipe = DetectionPipeline(detector)
    slot = LatestFrameSlot()
    results = []
    n = 20

    def producer():
        for i in range(n):
            slot.put(_frame(i))
            time.sleep(0.005)
        slot.close()

    t = threading.Thread(target=producer)
    t.start()
    pipe.run(slot, lambda res, frame: results.append(res))
    t.join()

    seqs = [r.frame_seq for r in results]
    assert seqs == sorted(seqs) and seqs[-1] == n - 1
    assert len(seqs) < n
    assert sum(r.dropped_since_last for r in results) == slot.dropped_total == n - len(seqs)
    assert results[-1].dropped_total == slot.dropped_total
    assert detector.calls == seqs


def test_slow_detector_with_queue_processes_every_frame():
    pipe = DetectionPipeline(FakeDetector(delay=0.005))
    q = FrameQueue(maxsize=2)
    results = []
    n = 12

    def producer():
        for i in range(n):
            q.put(_frame(i))
        q.close()

    t = threading.Thread(target=producer)
    t.start()
    pipe.run(q, lambda res, frame: results.append(res))
    t.join()
    assert [r.frame_seq for r in results] == list(range(n))
    assert all(r.dropped_since_last == 0 for r in results)


def test_run_stops_on_event():
    pipe = DetectionPipeline(FakeDetector())
    slot = LatestFrameSlot()
    stop = threading.Event()
    stop.set()
    pipe.run(slot, lambda res, frame: None, stop=stop, poll_s=0.01)  # returns immediately


@pytest.mark.skipif(not ONNX_MODEL.exists(), reason="yolox_s.onnx not downloaded")
def test_onnx_backend_detects_synthetic_person_free_image_without_crashing():
    det = build_detector(
        {"backend": "onnx", "device": "cpu", "conf_threshold": 0.3, "onnx": {"model_path": "onnx/yolox_s.onnx"}},
        models_root=REPO_ROOT / "models",
    )
    assert det.input_size == (640, 640) and len(det.class_names) == 80
    out = det.detect(np.full((600, 960, 3), 114, np.uint8))
    assert isinstance(out, list)
    for d in out:
        assert 0 <= d.x1 <= d.x2 <= 960 and 0 <= d.y1 <= d.y2 <= 600


@pytest.mark.skipif(
    not (ONNX_MODEL.exists() and (REPO_ROOT / "models" / "checkpoints" / "yolox_s.pth").exists()),
    reason="both yolox_s artifacts needed",
)
def test_onnx_and_torch_backends_agree():
    """Export equivalence: same weights through two runtimes must give the
    same boxes (within float tolerance) on a real frame."""
    pytest.importorskip("torch")
    pytest.importorskip("yolox")
    from tita_perception.bag import Rosbag2SqliteReader

    bag = REPO_ROOT / "data" / "bags" / "2026-09-04_lab_moving_01" / "indoor_run_03_0.db3"
    if bag.exists():
        with Rosbag2SqliteReader(bag) as r:
            _, img = next(r.images(r.find_topic("perception/camera/image/left")))
            image = img.to_bgr()
    else:
        rng = np.random.default_rng(0)
        image = rng.integers(0, 255, (600, 960, 3), dtype=np.uint8)

    common = {"device": "cpu", "conf_threshold": 0.3, "nms_threshold": 0.45}
    onnx = build_detector({"backend": "onnx", "onnx": {"model_path": "onnx/yolox_s.onnx"}, **common}, REPO_ROOT / "models")
    torch_ = build_detector(
        {"backend": "torch", "torch": {"checkpoint_path": "checkpoints/yolox_s.pth", "exp_name": "yolox-s"}, **common},
        REPO_ROOT / "models",
    )
    a = sorted(onnx.detect(image), key=lambda d: (d.class_id, d.x1))
    b = sorted(torch_.detect(image), key=lambda d: (d.class_id, d.x1))
    assert [d.class_id for d in a] == [d.class_id for d in b]
    for da, db in zip(a, b):
        assert da.score == pytest.approx(db.score, abs=2e-2)
        np.testing.assert_allclose(da.xyxy, db.xyxy, atol=2.0)


def test_tensorrt_backend_reports_missing_engine_before_needing_the_library(tmp_path):
    """The factory wires up backend 'tensorrt', and a forgotten engine build
    is a FileNotFoundError naming the path - checked before importing
    tensorrt, so this runs on machines without it."""
    cfg = {"backend": "tensorrt", "tensorrt": {"engine_path": "tensorrt/nope.engine"}}
    with pytest.raises(FileNotFoundError, match="nope.engine"):
        build_detector(cfg, tmp_path)


TRT_ENGINE = REPO_ROOT / "models" / "tensorrt" / "yolox_s_fp16.engine"


@pytest.mark.skipif(not (ONNX_MODEL.exists() and TRT_ENGINE.exists()), reason="needs onnx model + built engine")
def test_onnx_and_tensorrt_backends_agree():
    """Engine equivalence: an FP16 engine built from the ONNX file must give
    the same boxes on a real frame, within FP16 rounding. Only runs on the
    robot, where the engine exists."""
    pytest.importorskip("tensorrt")
    pytest.importorskip("pycuda")
    from tita_perception.bag import Rosbag2SqliteReader

    bag = REPO_ROOT / "data" / "bags" / "2026-09-04_lab_moving_01" / "indoor_run_03_0.db3"
    if bag.exists():
        with Rosbag2SqliteReader(bag) as r:
            _, img = next(r.images(r.find_topic("perception/camera/image/left")))
            image = img.to_bgr()
    else:
        rng = np.random.default_rng(0)
        image = rng.integers(0, 255, (600, 960, 3), dtype=np.uint8)

    common = {"conf_threshold": 0.3, "nms_threshold": 0.45}
    onnx = build_detector(
        {"backend": "onnx", "device": "cpu", "onnx": {"model_path": "onnx/yolox_s.onnx"}, **common},
        REPO_ROOT / "models",
    )
    trt = build_detector(
        {"backend": "tensorrt", "tensorrt": {"engine_path": "tensorrt/yolox_s_fp16.engine"}, **common},
        REPO_ROOT / "models",
    )
    a = sorted(onnx.detect(image), key=lambda d: (d.class_id, d.x1))
    b = sorted(trt.detect(image), key=lambda d: (d.class_id, d.x1))
    assert [d.class_id for d in a] == [d.class_id for d in b]
    for da, db in zip(a, b):
        assert da.score == pytest.approx(db.score, abs=5e-2)  # FP16: a little looser than torch-vs-onnx
        np.testing.assert_allclose(da.xyxy, db.xyxy, atol=3.0)
    trt.close()
