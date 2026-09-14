"""CDR decoding and bag reading."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from tita_perception.bag import (
    CAMERA_INFO_TYPE,
    IMAGE_TYPE,
    Rosbag2SqliteReader,
    decode_camera_info,
    decode_image,
)
from tita_perception.bag.cdr import CdrError, CdrReader

from cdr_encode import encode_camera_info, encode_image

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_BAG = REPO_ROOT / "data" / "bags" / "2026-09-04_lab_moving_01" / "indoor_run_03_0.db3"


# -- CDR primitives ----------------------------------------------------------


def test_cdr_alignment_is_relative_to_payload():
    # uint8 at offset 0 of payload, then a uint32 must land at payload offset 4.
    payload = b"\x00\x01\x00\x00" + b"\x07" + b"\x00\x00\x00" + (42).to_bytes(4, "little")
    r = CdrReader(payload)
    assert r.uint8() == 7
    assert r.uint32() == 42
    assert r.remaining == 0


def test_cdr_rejects_big_endian_gracefully_and_garbage_loudly():
    with pytest.raises(CdrError):
        CdrReader(b"\x00\x09\x00\x00")
    with pytest.raises(CdrError):
        CdrReader(b"\x00")


def test_cdr_string_with_odd_length_keeps_following_field_aligned():
    from cdr_encode import CdrWriter

    payload = CdrWriter().string("abc").uint32(99).string("").float64(1.5).bytes()
    r = CdrReader(payload)
    assert r.string() == "abc"
    assert r.uint32() == 99
    assert r.string() == ""
    assert r.float64() == 1.5


# -- sensor_msgs decoding ----------------------------------------------------


@pytest.mark.parametrize("encoding,channels", [("bgr8", 3), ("rgb8", 3), ("mono8", 1), ("bgra8", 4)])
def test_decode_image_roundtrip(encoding, channels):
    rng = np.random.default_rng(0)
    shape = (7, 11) if channels == 1 else (7, 11, channels)
    pixels = rng.integers(0, 255, size=shape, dtype=np.uint8)
    img = decode_image(encode_image(pixels, encoding, stamp_ns=1_234_567_890_111, frame_id="left"))
    assert (img.height, img.width, img.encoding) == (7, 11, encoding)
    assert img.header.stamp_ns == 1_234_567_890_111
    assert img.header.frame_id == "left"
    np.testing.assert_array_equal(img.data, pixels)
    bgr = img.to_bgr()
    assert bgr.shape == (7, 11, 3) and bgr.flags.writeable and bgr.flags.c_contiguous


def test_decode_image_rgb_to_bgr_swaps_channels():
    pixels = np.zeros((2, 2, 3), dtype=np.uint8)
    pixels[..., 0] = 200  # red in rgb8
    bgr = decode_image(encode_image(pixels, "rgb8")).to_bgr()
    assert bgr[0, 0].tolist() == [0, 0, 200]


def test_decode_image_rejects_unknown_encoding_and_short_payload():
    pixels = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(CdrError):
        decode_image(encode_image(pixels, "yuv422"))
    payload = encode_image(pixels, "bgr8")
    with pytest.raises(CdrError):
        decode_image(payload[:-3])


def test_decode_camera_info_fields():
    k = [[500.0, 0.0, 320.0], [0.0, 510.0, 240.0], [0.0, 0.0, 1.0]]
    d = [0.1, -0.2, 0.001, 0.002, 0.0]
    info = decode_camera_info(encode_camera_info(640, 480, k, d, frame_id="left_cam"))
    assert (info.width, info.height) == (640, 480)
    assert info.distortion_model == "plumb_bob"
    assert info.d == d
    assert (info.fx, info.fy, info.cx, info.cy) == (500.0, 510.0, 320.0, 240.0)
    assert info.p.shape == (3, 4) and info.p[0, 0] == 500.0
    assert info.header.frame_id == "left_cam"
    assert info.roi is not None and info.roi.do_rectify is False


# -- bag reader (synthetic sqlite) --------------------------------------------


@pytest.fixture
def synthetic_bag(tmp_path: Path) -> Path:
    """A minimal rosbag2 sqlite3 file with images inserted *out of order*."""
    path = tmp_path / "synthetic_0.db3"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                            serialization_format TEXT NOT NULL, offered_qos_profiles TEXT NOT NULL);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL,
                              timestamp INTEGER NOT NULL, data BLOB NOT NULL);
        CREATE INDEX timestamp_idx ON messages (timestamp ASC);
        """
    )
    con.execute("INSERT INTO topics VALUES (1, '/tita999/perception/camera/image/left', ?, 'cdr', '')", (IMAGE_TYPE,))
    con.execute("INSERT INTO topics VALUES (2, '/tita999/perception/camera/info/left', ?, 'cdr', '')", (CAMERA_INFO_TYPE,))
    con.execute("INSERT INTO topics VALUES (3, '/tf', 'tf2_msgs/msg/TFMessage', 'cdr', '')")
    stamps = [300, 100, 200]  # deliberately unsorted receive timestamps
    for i, ts in enumerate(stamps):
        pixels = np.full((4, 6, 3), i, dtype=np.uint8)
        con.execute(
            "INSERT INTO messages(topic_id, timestamp, data) VALUES (1, ?, ?)",
            (ts, encode_image(pixels, "bgr8", stamp_ns=ts * 10)),
        )
    con.execute(
        "INSERT INTO messages(topic_id, timestamp, data) VALUES (2, 150, ?)",
        (encode_camera_info(6, 4, np.eye(3) * 2, [0.0] * 5),),
    )
    con.commit()
    con.close()
    return path


def test_reader_yields_images_in_chronological_order(synthetic_bag: Path):
    with Rosbag2SqliteReader(synthetic_bag) as reader:
        topic = reader.find_topic("perception/camera/image/left")
        assert topic.message_count == 3
        seen = [(ts, img.header.stamp_ns, int(img.data[0, 0, 0])) for ts, img in reader.images(topic)]
    assert [s[0] for s in seen] == [100, 200, 300]
    assert [s[1] for s in seen] == [1000, 2000, 3000]
    assert [s[2] for s in seen] == [1, 2, 0]  # payload order follows time, not insertion


def test_reader_topic_lookup_is_namespace_agnostic(synthetic_bag: Path):
    with Rosbag2SqliteReader(synthetic_bag) as reader:
        assert reader.find_topic("camera/image/left").name.startswith("/tita999/")
        with pytest.raises(KeyError):
            reader.find_topic("does/not/exist")
        with pytest.raises(KeyError):
            reader.find_topic("left")  # ambiguous: image/left and info/left
        info = reader.first_camera_info(reader.find_topic("camera/info/left"))
        assert info is not None and info.fx == 2.0
        assert reader.time_range(reader.find_topic("camera/image/left")) == (100, 300)


def test_reader_refuses_wrong_type(synthetic_bag: Path):
    with Rosbag2SqliteReader(synthetic_bag) as reader:
        tf = reader.find_topic("/tf")
        with pytest.raises(TypeError):
            next(reader.images(tf))


# -- real recording, if present ------------------------------------------------


@pytest.mark.skipif(not REAL_BAG.exists(), reason="recording not present on this machine")
def test_real_bag_first_frames_decode_and_are_monotonic():
    with Rosbag2SqliteReader(REAL_BAG) as reader:
        topic = reader.find_topic("perception/camera/image/left", IMAGE_TYPE)
        last = -1
        for i, (ts, img) in enumerate(reader.images(topic)):
            assert ts >= last
            last = ts
            assert img.encoding == "bgr8"
            assert img.to_bgr().shape == (img.height, img.width, 3)
            if i == 20:
                break
        info = reader.first_camera_info(reader.find_topic("perception/camera/info/left"))
        assert info is not None and info.fx > 0 and (info.width, info.height) == (img.width, img.height)
