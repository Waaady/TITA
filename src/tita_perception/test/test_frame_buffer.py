"""Drop-stale vs. keep-all buffer semantics."""

from __future__ import annotations

import threading
import time

import numpy as np

from tita_perception.pipeline import Frame, FrameQueue, LatestFrameSlot, make_frame_buffer


def _frame(seq: int) -> Frame:
    return Frame(seq=seq, stamp_ns=seq * 1000, recv_ns=seq * 1000, frame_id="cam", image=np.zeros((2, 2, 3), np.uint8))


def test_latest_slot_keeps_only_newest_and_counts_drops():
    slot = LatestFrameSlot()
    for i in range(5):
        slot.put(_frame(i))
    frame, dropped = slot.get(timeout=0)
    assert frame.seq == 4
    assert dropped == 4
    assert slot.dropped_total == 4
    assert slot.get(timeout=0) is None  # drained
    slot.put(_frame(5))
    frame, dropped = slot.get(timeout=0)
    assert (frame.seq, dropped) == (5, 0)


def test_latest_slot_drop_counter_resets_per_get():
    slot = LatestFrameSlot()
    slot.put(_frame(0))
    slot.put(_frame(1))
    _, dropped = slot.get(timeout=0)
    assert dropped == 1
    slot.put(_frame(2))
    frame, dropped = slot.get(timeout=0)
    assert (frame.seq, dropped) == (2, 0)
    assert slot.dropped_total == 1


def test_latest_slot_get_blocks_until_put_or_close():
    slot = LatestFrameSlot()
    got = []

    def consumer():
        got.append(slot.get(timeout=5))
        got.append(slot.get(timeout=5))

    t = threading.Thread(target=consumer)
    t.start()
    time.sleep(0.05)
    slot.put(_frame(7))
    time.sleep(0.05)
    slot.close()
    t.join(2)
    assert not t.is_alive()
    assert got[0][0].seq == 7
    assert got[1] is None
    assert slot.closed


def test_latest_slot_ignores_put_after_close():
    slot = LatestFrameSlot()
    slot.close()
    slot.put(_frame(1))
    assert slot.get(timeout=0) is None


def test_queue_never_drops_and_applies_backpressure():
    q = FrameQueue(maxsize=2)
    q.put(_frame(0))
    q.put(_frame(1))
    blocked = threading.Event()

    def producer():
        q.put(_frame(2))  # must block until the consumer takes one
        blocked.set()

    t = threading.Thread(target=producer)
    t.start()
    time.sleep(0.1)
    assert not blocked.is_set(), "put() should block while the queue is full"
    assert q.get(timeout=1)[0].seq == 0
    t.join(2)
    assert blocked.is_set()
    assert [q.get(timeout=1)[0].seq for _ in range(2)] == [1, 2]
    assert q.dropped_total == 0
    q.close()
    assert q.get(timeout=0) is None


def test_slow_consumer_sees_newest_frame_with_latest_policy():
    """The scenario that matters on the robot: the producer is faster than
    the consumer. With 'latest' the consumer must never process a frame that
    is older than one it could have had."""
    slot = LatestFrameSlot()
    n_frames = 30

    def producer():
        for i in range(n_frames):
            slot.put(_frame(i))
            time.sleep(0.002)
        slot.close()

    t = threading.Thread(target=producer)
    t.start()
    processed = []
    while (item := slot.get(timeout=1)) is not None:
        processed.append(item[0].seq)
        time.sleep(0.02)  # 10x slower than the producer
    t.join()
    assert processed == sorted(processed)
    assert processed[-1] == n_frames - 1, "the last frame must always be processed"
    assert len(processed) < n_frames
    assert slot.dropped_total == n_frames - len(processed)


def test_make_frame_buffer():
    assert isinstance(make_frame_buffer("latest"), LatestFrameSlot)
    assert isinstance(make_frame_buffer("all", 3), FrameQueue)
    try:
        make_frame_buffer("bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
