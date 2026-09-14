"""Feed frames from a rosbag2 ``.db3`` file into a :class:`FrameBuffer`,
paced like the original camera.

Runs in its own thread so the detector thread sees exactly what it would see
on the robot: frames arriving at camera rate whether or not it is ready.
With ``speed=0`` the bag is pushed as fast as it can be read (offline mode).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional, Union

from ..bag import CAMERA_INFO_TYPE, IMAGE_TYPE, CameraInfo, Rosbag2SqliteReader
from .frame import Frame
from .frame_buffer import FrameBuffer


class BagFrameSource:
    def __init__(
        self,
        bag_path: Union[str, Path],
        buffer: FrameBuffer,
        image_topic_suffix: str = "perception/camera/image/left",
        camera_info_topic_suffix: Optional[str] = "perception/camera/info/left",
        speed: float = 1.0,
        max_frames: Optional[int] = None,
    ) -> None:
        """
        speed: 1.0 replays at the recorded rate (by header stamps), 2.0 at
            twice that, 0 as fast as possible.
        """
        self._path = Path(bag_path)
        self._buffer = buffer
        self._speed = float(speed)
        self._max_frames = max_frames
        self._image_suffix = image_topic_suffix
        self._info_suffix = camera_info_topic_suffix
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.frames_read = 0
        self.error: Optional[BaseException] = None

        # Resolve topics and calibration up front so failures are immediate.
        with Rosbag2SqliteReader(self._path) as reader:
            self.image_topic = reader.find_topic(image_topic_suffix, IMAGE_TYPE)
            self.camera_info: Optional[CameraInfo] = None
            if camera_info_topic_suffix:
                try:
                    info_topic = reader.find_topic(camera_info_topic_suffix, CAMERA_INFO_TYPE)
                    self.camera_info = reader.first_camera_info(info_topic)
                except KeyError:
                    self.camera_info = None
            self.total_frames = self.image_topic.message_count

    # -- thread control ----------------------------------------------------

    def start(self) -> "BagFrameSource":
        self._thread = threading.Thread(target=self._run, name="bag-frame-source", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # -- producer loop -----------------------------------------------------

    def _run(self) -> None:
        try:
            # sqlite connections are per-thread, so open our own here.
            with Rosbag2SqliteReader(self._path) as reader:
                first_stamp: Optional[int] = None
                t_start = time.perf_counter()
                for seq, (recv_ns, image) in enumerate(reader.images(self.image_topic)):
                    if self._stop.is_set():
                        break
                    if self._max_frames is not None and seq >= self._max_frames:
                        break
                    stamp = image.header.stamp_ns
                    if self._speed > 0:
                        if first_stamp is None:
                            first_stamp = stamp
                        due = t_start + (stamp - first_stamp) / 1e9 / self._speed
                        delay = due - time.perf_counter()
                        if delay > 0:
                            time.sleep(delay)
                    self._buffer.put(
                        Frame(
                            seq=seq,
                            stamp_ns=stamp,
                            recv_ns=recv_ns,
                            frame_id=image.header.frame_id,
                            image=image.to_bgr(),
                        )
                    )
                    self.frames_read += 1
        except BaseException as exc:  # noqa: BLE001 - surfaced to the consumer via .error
            self.error = exc
        finally:
            self._buffer.close()
