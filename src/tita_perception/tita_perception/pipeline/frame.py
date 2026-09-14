"""The unit of work flowing through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

import numpy as np


@dataclass
class Frame:
    """One camera image plus the timestamps needed to reason about staleness.

    seq:        running index at the source (bag message index / callback count)
    stamp_ns:   sensor capture time from the message header - use this for
                anything physical (velocities, TF lookups)
    recv_ns:    when the recording machine / node received it
    frame_id:   TF frame of the camera
    image:      HxWx3 uint8 BGR
    enqueued_at: ``time.perf_counter()`` when the frame entered the buffer;
                the consumer uses it to measure how long a frame waited.
    """

    seq: int
    stamp_ns: int
    recv_ns: int
    frame_id: str
    image: np.ndarray
    enqueued_at: float = field(default_factory=time.perf_counter)

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])
