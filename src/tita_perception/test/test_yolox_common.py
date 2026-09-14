"""Preprocessing parity and post-processing correctness for YOLOX."""

from __future__ import annotations

import numpy as np
import pytest

from tita_perception.detectors.yolox_common import (
    YOLOX_STRIDES,
    decode_outputs,
    letterbox,
    make_grids,
    nms,
    postprocess,
)


def test_letterbox_matches_upstream_preproc_contract():
    img = np.zeros((600, 960, 3), dtype=np.uint8)
    img[..., 0] = 10  # B
    img[..., 1] = 20  # G
    img[..., 2] = 30  # R
    tensor, r = letterbox(img, (640, 640))
    assert tensor.shape == (3, 640, 640) and tensor.dtype == np.float32
    assert r == pytest.approx(640 / 960)
    # image anchored top-left, channel order preserved (BGR), no normalisation
    assert tensor[:, 0, 0].tolist() == [10.0, 20.0, 30.0]
    # padding below the resized image is 114 in all channels
    assert tensor[:, 639, 0].tolist() == [114.0, 114.0, 114.0]
    assert tensor[:, 399, 639].tolist() == [10.0, 20.0, 30.0]
    assert tensor[:, 400, 0].tolist() == [114.0, 114.0, 114.0]


def test_letterbox_matches_upstream_when_available():
    yolox = pytest.importorskip("yolox.data.data_augment")
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (600, 960, 3), dtype=np.uint8)
    ours, r_ours = letterbox(img, (640, 640))
    theirs, r_theirs = yolox.preproc(img, (640, 640))
    assert r_ours == pytest.approx(r_theirs)
    np.testing.assert_array_equal(ours, theirs)


def test_grids_cover_all_strides():
    grids, strides = make_grids((640, 640))
    expected = sum((640 // s) ** 2 for s in YOLOX_STRIDES)
    assert grids.shape == (expected, 2)
    assert strides.shape == (expected, 1)
    assert set(np.unique(strides)) == set(YOLOX_STRIDES)


def test_decode_outputs_reference_implementation():
    """Compare against a direct transcription of yolox.utils.demo_postprocess."""
    input_size = (320, 320)
    n = sum((320 // s) ** 2 for s in YOLOX_STRIDES)
    rng = np.random.default_rng(2)
    raw = rng.normal(size=(n, 85)).astype(np.float32)

    grids_ref, strides_ref = [], []
    for s in YOLOX_STRIDES:
        h, w = 320 // s, 320 // s
        xv, yv = np.meshgrid(np.arange(w), np.arange(h))
        grids_ref.append(np.stack((xv, yv), 2).reshape(1, -1, 2))
        strides_ref.append(np.full((1, h * w, 1), s))
    grids_ref = np.concatenate(grids_ref, 1)
    strides_ref = np.concatenate(strides_ref, 1)
    ref = raw[None].copy()
    ref[..., :2] = (ref[..., :2] + grids_ref) * strides_ref
    ref[..., 2:4] = np.exp(ref[..., 2:4]) * strides_ref

    np.testing.assert_allclose(decode_outputs(raw, input_size), ref[0], rtol=1e-6)
    with pytest.raises(ValueError):
        decode_outputs(raw, (640, 640))


def test_nms_suppresses_overlapping_lower_scores_only():
    boxes = np.array(
        [[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60], [0, 0, 10, 10]], dtype=np.float32
    )
    scores = np.array([0.9, 0.8, 0.7, 0.95], dtype=np.float32)
    keep = nms(boxes, scores, 0.5).tolist()
    assert keep == [3, 2]
    assert nms(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), 0.5).size == 0


def test_postprocess_thresholds_scales_and_is_class_aware():
    # decoded rows: cx, cy, w, h, obj, cls0, cls1 in *network* pixels
    scale = 0.5  # net = orig * 0.5  -> orig = net / 0.5
    decoded = np.array(
        [
            [100, 100, 40, 40, 0.9, 0.9, 0.1],  # class 0, score .81
            [100, 100, 40, 40, 0.9, 0.1, 0.9],  # class 1, same box -> kept (class-aware)
            [102, 102, 40, 40, 0.8, 0.8, 0.1],  # class 0, overlaps first -> suppressed
            [300, 300, 20, 20, 0.5, 0.5, 0.2],  # score .25 -> below threshold
            [310, 315, 30, 30, 0.9, 0.2, 0.9],  # class 1 -> box clipped to image edge
        ],
        dtype=np.float32,
    )
    dets = postprocess(decoded, scale, image_shape=(600, 640), conf_threshold=0.3, nms_threshold=0.5)
    assert len(dets) == 3
    assert sorted(d.class_id for d in dets) == [0, 1, 1]
    assert all(d.score == pytest.approx(0.81) for d in dets)
    first = next(d for d in dets if d.class_id == 0)
    assert (first.x1, first.y1, first.x2, first.y2) == (160.0, 160.0, 240.0, 240.0)
    clipped = max(dets, key=lambda d: d.x2)
    assert clipped.x2 <= 640 and clipped.y2 <= 600

    only_cls0 = postprocess(decoded, scale, (600, 640), 0.3, 0.5, class_whitelist=[0])
    assert [d.class_id for d in only_cls0] == [0]
    assert postprocess(np.zeros((0, 7), np.float32), scale, (600, 640), 0.3, 0.5) == []
