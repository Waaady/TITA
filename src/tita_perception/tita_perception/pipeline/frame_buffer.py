"""Hand-off between the frame producer (bag reader, ROS subscription) and
the detector, with an explicit policy for what happens when the detector is
slower than the camera.

Why this matters: the robot drives while detecting. If the camera delivers
40 frames/s and the detector manages 15, an ordinary FIFO fills up and the
detector ends up looking at images that are seconds old - by the time an
obstacle is reported, the robot has already reached it. Two policies:

:class:`LatestFrameSlot`
    A one-element mailbox. A new frame *replaces* whatever is waiting; the
    consumer always gets the newest image and every frame it could not keep
    up with is dropped and counted. This is what runs on the robot.

:class:`FrameQueue`
    A bounded FIFO whose ``put`` blocks when full, i.e. back-pressure on the
    producer. Nothing is dropped. Only for offline work where every frame of
    a recording must be processed (evaluation, extracting frames).

Both are thread-safe and share the :class:`FrameBuffer` interface so the
pipeline does not care which one it is given.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import deque
from typing import Callable, Optional

from .frame import Frame


class FrameBuffer(ABC):
    """Common interface: ``put`` from the producer thread, ``get`` from the
    consumer thread, ``close`` once the producer is done."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._closed = False

    def _wait(self, ready: Callable[[], bool], timeout: Optional[float]) -> bool:
        """Block until ``ready()`` or closed. Caller must hold the lock."""
        return self._cond.wait_for(lambda: ready() or self._closed, timeout)

    @abstractmethod
    def put(self, frame: Frame) -> None: ...

    @abstractmethod
    def get(self, timeout: Optional[float] = None) -> Optional[tuple[Frame, int]]:
        """Block for the next frame. Returns ``(frame, dropped_since_last)``
        or ``None`` when closed and drained (or on timeout)."""

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    @property
    def dropped_total(self) -> int:
        return 0


class LatestFrameSlot(FrameBuffer):
    """Keep only the newest frame; drop and count everything the consumer
    did not get to in time."""

    def __init__(self) -> None:
        super().__init__()
        self._frame: Optional[Frame] = None
        self._dropped_pending = 0
        self._dropped_total = 0

    def put(self, frame: Frame) -> None:
        with self._cond:
            if self._closed:
                return
            if self._frame is not None:
                # Consumer never picked this one up - it is stale now.
                self._dropped_pending += 1
                self._dropped_total += 1
            self._frame = frame
            self._cond.notify()

    def get(self, timeout: Optional[float] = None) -> Optional[tuple[Frame, int]]:
        with self._cond:
            self._wait(lambda: self._frame is not None, timeout)
            if self._frame is None:
                return None
            item = (self._frame, self._dropped_pending)
            self._frame, self._dropped_pending = None, 0
            return item

    @property
    def dropped_total(self) -> int:
        with self._cond:
            return self._dropped_total


class FrameQueue(FrameBuffer):
    """Bounded FIFO with back-pressure. Never drops."""

    def __init__(self, maxsize: int = 8) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        super().__init__()
        self._items: deque[Frame] = deque()
        self._maxsize = maxsize

    def put(self, frame: Frame) -> None:
        with self._cond:
            self._wait(lambda: len(self._items) < self._maxsize, None)
            if self._closed:
                return
            self._items.append(frame)
            self._cond.notify_all()

    def get(self, timeout: Optional[float] = None) -> Optional[tuple[Frame, int]]:
        with self._cond:
            self._wait(lambda: bool(self._items), timeout)
            if not self._items:
                return None
            frame = self._items.popleft()
            self._cond.notify_all()  # a blocked producer may continue
            return frame, 0


def make_frame_buffer(policy: str, queue_size: int = 8) -> FrameBuffer:
    """``"latest"`` -> :class:`LatestFrameSlot`, ``"all"`` -> :class:`FrameQueue`."""
    if policy == "latest":
        return LatestFrameSlot()
    if policy == "all":
        return FrameQueue(queue_size)
    raise ValueError(f"unknown frame buffer policy {policy!r}; expected 'latest' or 'all'")
