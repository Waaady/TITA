"""Minimal reader for the OMG CDR encoding used by ROS 2 (rmw_fastrtps,
rmw_cyclonedds) inside rosbag2 files.

Only what ROS 2 messages need is implemented: little-endian primitives,
strings, fixed arrays and sequences, with CDR's natural alignment rules.
Alignment is relative to the start of the payload, i.e. the byte right after
the 4-byte encapsulation header.
"""

from __future__ import annotations

import struct

_ENCAPSULATION_HEADER_LEN = 4
_CDR_LE = 0x0001
_CDR_BE = 0x0000


class CdrError(ValueError):
    """Malformed CDR payload."""


class CdrReader:
    """Sequential reader over one serialized ROS 2 message."""

    def __init__(self, data: bytes) -> None:
        if len(data) < _ENCAPSULATION_HEADER_LEN:
            raise CdrError("payload shorter than the CDR encapsulation header")
        kind = struct.unpack_from(">H", data, 0)[0]
        if kind == _CDR_LE:
            self._endian = "<"
        elif kind == _CDR_BE:
            self._endian = ">"
        else:
            raise CdrError(f"unsupported CDR encapsulation kind 0x{kind:04x}")
        self._data = data
        self._pos = _ENCAPSULATION_HEADER_LEN

    # -- internals ---------------------------------------------------------

    def _align(self, size: int) -> None:
        # Alignment is counted from the start of the payload, not the buffer.
        rel = self._pos - _ENCAPSULATION_HEADER_LEN
        self._pos += (-rel) % size

    def _unpack(self, fmt: str, size: int):
        self._align(size)
        if self._pos + size > len(self._data):
            raise CdrError("read past end of CDR payload")
        value = struct.unpack_from(self._endian + fmt, self._data, self._pos)[0]
        self._pos += size
        return value

    # -- primitives --------------------------------------------------------

    def bool(self) -> bool:
        return bool(self._unpack("B", 1))

    def uint8(self) -> int:
        return self._unpack("B", 1)

    def int32(self) -> int:
        return self._unpack("i", 4)

    def uint32(self) -> int:
        return self._unpack("I", 4)

    def float64(self) -> float:
        return self._unpack("d", 8)

    def string(self) -> str:
        # uint32 length (includes the trailing NUL), then the bytes.
        length = self.uint32()
        if length == 0:
            return ""
        end = self._pos + length
        if end > len(self._data):
            raise CdrError("string runs past end of CDR payload")
        raw = self._data[self._pos : end - 1]  # strip NUL terminator
        self._pos = end
        return raw.decode("utf-8", errors="replace")

    # -- aggregates --------------------------------------------------------

    def float64_array(self, count: int) -> list[float]:
        """Fixed-size ``float64[N]`` array."""
        return [self.float64() for _ in range(count)]

    def float64_sequence(self) -> list[float]:
        """Unbounded ``float64[]`` sequence."""
        return self.float64_array(self.uint32())

    def uint8_sequence(self) -> memoryview:
        """Unbounded ``uint8[]`` sequence, returned without copying."""
        length = self.uint32()
        end = self._pos + length
        if end > len(self._data):
            raise CdrError("byte sequence runs past end of CDR payload")
        view = memoryview(self._data)[self._pos : end]
        self._pos = end
        return view

    @property
    def remaining(self) -> int:
        return len(self._data) - self._pos
