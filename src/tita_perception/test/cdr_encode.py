"""Tiny CDR *encoder* used only by the tests to build synthetic
sensor_msgs payloads, so the decoder is checked against an independent
implementation of the same alignment rules."""

from __future__ import annotations

import struct

import numpy as np


class CdrWriter:
    def __init__(self) -> None:
        self._buf = bytearray(b"\x00\x01\x00\x00")  # CDR_LE encapsulation

    def _align(self, size: int) -> None:
        rel = len(self._buf) - 4
        self._buf.extend(b"\x00" * ((-rel) % size))

    def _pack(self, fmt: str, size: int, value) -> "CdrWriter":
        self._align(size)
        self._buf.extend(struct.pack("<" + fmt, value))
        return self

    def uint8(self, v: int) -> "CdrWriter":
        return self._pack("B", 1, v)

    def int32(self, v: int) -> "CdrWriter":
        return self._pack("i", 4, v)

    def uint32(self, v: int) -> "CdrWriter":
        return self._pack("I", 4, v)

    def float64(self, v: float) -> "CdrWriter":
        return self._pack("d", 8, v)

    def string(self, s: str) -> "CdrWriter":
        raw = s.encode("utf-8") + b"\x00"
        self.uint32(len(raw))
        self._buf.extend(raw)
        return self

    def float64_seq(self, values) -> "CdrWriter":
        self.uint32(len(values))
        for v in values:
            self.float64(v)
        return self

    def float64_array(self, values) -> "CdrWriter":
        for v in values:
            self.float64(v)
        return self

    def bytes_seq(self, data: bytes) -> "CdrWriter":
        self.uint32(len(data))
        self._buf.extend(data)
        return self

    def header(self, stamp_ns: int, frame_id: str) -> "CdrWriter":
        return self.int32(stamp_ns // 1_000_000_000).uint32(stamp_ns % 1_000_000_000).string(frame_id)

    def bytes(self) -> bytes:
        return bytes(self._buf)


def encode_image(
    pixels: np.ndarray, encoding: str, stamp_ns: int = 1_700_000_000_123_456_789, frame_id: str = "cam"
) -> bytes:
    h, w = pixels.shape[:2]
    ch = 1 if pixels.ndim == 2 else pixels.shape[2]
    return (
        CdrWriter()
        .header(stamp_ns, frame_id)
        .uint32(h)
        .uint32(w)
        .string(encoding)
        .uint8(0)
        .uint32(w * ch)
        .bytes_seq(np.ascontiguousarray(pixels).tobytes())
        .bytes()
    )


def encode_camera_info(
    width: int, height: int, k, d, stamp_ns: int = 1_700_000_000_000_000_000, frame_id: str = "cam"
) -> bytes:
    w = CdrWriter().header(stamp_ns, frame_id).uint32(height).uint32(width).string("plumb_bob")
    w.float64_seq(d).float64_array(np.asarray(k).ravel()).float64_array(np.eye(3).ravel())
    p = np.zeros((3, 4))
    p[:, :3] = np.asarray(k)
    w.float64_array(p.ravel()).uint32(0).uint32(0)
    w.uint32(0).uint32(0).uint32(0).uint32(0).uint8(0)  # RegionOfInterest
    return w.bytes()
