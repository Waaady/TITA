"""Chronological access to a rosbag2 sqlite3 (``.db3``) file.

rosbag2's sqlite3 storage has three tables that matter:

    topics   (id, name, type, serialization_format, offered_qos_profiles)
    messages (id, topic_id, timestamp, data)

``messages.timestamp`` is the *receive* time on the recording machine, in
nanoseconds since epoch, and is indexed. Messages are yielded ordered by it.
The sensor's own capture time is inside each message header (``stamp_ns``)
and is what downstream code should use for anything time-related.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Union

from .ros_messages import CameraInfo, Image, decode_camera_info, decode_image

IMAGE_TYPE = "sensor_msgs/msg/Image"
CAMERA_INFO_TYPE = "sensor_msgs/msg/CameraInfo"


@dataclass(frozen=True)
class TopicInfo:
    id: int
    name: str
    type: str
    message_count: int


class Rosbag2SqliteReader:
    """Read-only reader for one ``.db3`` file. Not thread-safe; open one
    reader per thread."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        # Read-only URI so a stray write can never corrupt a recording.
        self._con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        self._topics = self._load_topics()

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "Rosbag2SqliteReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- topics ------------------------------------------------------------

    def _load_topics(self) -> list[TopicInfo]:
        rows = self._con.execute(
            "SELECT t.id, t.name, t.type, COUNT(m.id) "
            "FROM topics t LEFT JOIN messages m ON m.topic_id = t.id "
            "GROUP BY t.id ORDER BY t.id"
        ).fetchall()
        return [TopicInfo(*row) for row in rows]

    @property
    def topics(self) -> list[TopicInfo]:
        return list(self._topics)

    def find_topic(self, name_suffix: str, type_name: Optional[str] = None) -> TopicInfo:
        """Find a topic by the end of its name, so callers never need the
        robot namespace (``/tita3037072/...``) - it differs per robot."""
        matches = [
            t
            for t in self._topics
            if t.name.endswith(name_suffix) and (type_name is None or t.type == type_name)
        ]
        if not matches:
            raise KeyError(
                f"no topic ending in {name_suffix!r}"
                + (f" of type {type_name}" if type_name else "")
                + f" in {self.path.name}; available: {[t.name for t in self._topics]}"
            )
        if len(matches) > 1:
            raise KeyError(f"ambiguous suffix {name_suffix!r}: {[t.name for t in matches]}")
        return matches[0]

    def find_topics_by_type(self, type_name: str) -> list[TopicInfo]:
        return [t for t in self._topics if t.type == type_name]

    # -- messages ----------------------------------------------------------

    def raw_messages(self, topic: TopicInfo) -> Iterator[tuple[int, bytes]]:
        """Yield ``(receive_timestamp_ns, cdr_payload)`` in chronological order."""
        cur = self._con.execute(
            "SELECT timestamp, data FROM messages WHERE topic_id = ? ORDER BY timestamp ASC",
            (topic.id,),
        )
        for ts, data in cur:
            yield ts, data

    def images(self, topic: TopicInfo) -> Iterator[tuple[int, Image]]:
        """Yield ``(receive_timestamp_ns, Image)`` chronologically."""
        if topic.type != IMAGE_TYPE:
            raise TypeError(f"{topic.name} is {topic.type}, not {IMAGE_TYPE}")
        for ts, data in self.raw_messages(topic):
            yield ts, decode_image(data)

    def first_camera_info(self, topic: TopicInfo) -> Optional[CameraInfo]:
        """The first CameraInfo on ``topic``, or None if the topic is empty.

        Calibration does not change during a recording and CameraInfo is
        published far slower than images on TITA (~9 Hz vs ~42 Hz), so the
        first message is cached and reused instead of being synchronised
        with every frame.
        """
        if topic.type != CAMERA_INFO_TYPE:
            raise TypeError(f"{topic.name} is {topic.type}, not {CAMERA_INFO_TYPE}")
        row = self._con.execute(
            "SELECT data FROM messages WHERE topic_id = ? ORDER BY timestamp ASC LIMIT 1",
            (topic.id,),
        ).fetchone()
        return decode_camera_info(row[0]) if row else None

    def time_range(self, topic: TopicInfo) -> tuple[int, int]:
        """(first, last) receive timestamp in ns for a topic."""
        row = self._con.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM messages WHERE topic_id = ?",
            (topic.id,),
        ).fetchone()
        return int(row[0]), int(row[1])
