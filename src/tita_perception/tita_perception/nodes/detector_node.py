"""ROS 2 node: camera image -> YOLOX -> vision_msgs/Detection2DArray.

Thin wrapper around :class:`DetectionPipeline`. The image callback only
drops the frame into the buffer (microseconds); a worker thread runs the
detector and publishes. So the ROS executor is never blocked by inference,
and the newest-frame policy from ``frame_buffer.py`` decides what gets
detected when the detector is slower than the camera.

Parameters (config/detector_node.yaml): everything ROS-specific. The
detector/pipeline/tracking settings come from ``config_file`` (the same
``detector.yaml`` the offline script uses) so there is one source of truth.

    ros2 run tita_perception detector_node --ros-args -r __ns:=/tita3037072 \
        --params-file src/tita_perception/config/detector_node.yaml
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo as CameraInfoMsg
from sensor_msgs.msg import Image as ImageMsg
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from ..bag.ros_messages import CameraInfo, Header
from ..pipeline import Frame, FrameResult, build_buffer, build_pipeline, load_config


def _stamp_ns(msg) -> int:
    return msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec


def camera_info_from_msg(msg: CameraInfoMsg) -> CameraInfo:
    """sensor_msgs/CameraInfo -> the plain dataclass the pipeline uses."""
    return CameraInfo(
        header=Header(stamp_ns=_stamp_ns(msg), frame_id=msg.header.frame_id),
        height=msg.height,
        width=msg.width,
        distortion_model=msg.distortion_model,
        d=list(msg.d),
        k=np.array(msg.k, dtype=np.float64).reshape(3, 3),
        r=np.array(msg.r, dtype=np.float64).reshape(3, 3),
        p=np.array(msg.p, dtype=np.float64).reshape(3, 4),
    )


def detections_to_msg(result: FrameResult) -> Detection2DArray:
    """FrameResult -> Detection2DArray. Stamp and frame are the *image's*,
    so a consumer can look up TF at the right time.

    Only what the standard message can carry: box, label, score, track id.
    Bearing, foot point, scale rate etc. need an own message in
    tita_interfaces_thesis (not written yet).
    """
    out = Detection2DArray()
    out.header.stamp.sec = result.stamp_ns // 1_000_000_000
    out.header.stamp.nanosec = result.stamp_ns % 1_000_000_000
    out.header.frame_id = result.frame_id
    for obs in result.detections:
        det = Detection2D()
        det.header = out.header
        det.id = str(obs.track.track_id) if obs.track else ""
        det.bbox.center.position.x = obs.center_xy[0]
        det.bbox.center.position.y = obs.center_xy[1]
        det.bbox.size_x = obs.width_px
        det.bbox.size_y = obs.height_px
        hyp = ObjectHypothesisWithPose()
        hyp.hypothesis.class_id = obs.label
        hyp.hypothesis.score = obs.score
        det.results.append(hyp)
        out.detections.append(det)
    return out


class DetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("detector_node")
        # "" means "use the default" - ROS parameters cannot be null.
        self.declare_parameter("config_file", "")  # "" -> share/tita_perception/config/detector.yaml
        self.declare_parameter("models_root", "")  # "" -> <cwd>/models (run from the workspace root)
        self.declare_parameter("image_topic", "perception/camera/image/left")
        self.declare_parameter("camera_info_topic", "perception/camera/info/left")
        self.declare_parameter("detections_topic", "perception/detections")
        self.declare_parameter("publish_debug_image", False)
        self.declare_parameter("debug_image_topic", "perception/detections/image")

        p = lambda name: self.get_parameter(name).value  # noqa: E731
        share = Path(get_package_share_directory("tita_perception"))
        cfg = load_config(p("config_file") or share / "config" / "detector.yaml")
        models_root = Path(p("models_root") or Path.cwd() / "models")

        self._pipeline = build_pipeline(cfg, models_root)
        self._buffer = build_buffer(cfg)
        self._bridge = CvBridge()
        self._seq = 0
        self.get_logger().info(f"detector: {self._pipeline.detector!r}")

        self._pub = self.create_publisher(Detection2DArray, p("detections_topic"), 10)
        self._debug_pub = None
        if p("publish_debug_image"):
            self._debug_pub = self.create_publisher(ImageMsg, p("debug_image_topic"), 1)

        # Cameras publish BEST_EFFORT; the default RELIABLE subscriber would
        # silently receive nothing. Depth 1: the middleware keeps only the
        # newest message while the callback runs.
        self.create_subscription(ImageMsg, p("image_topic"), self._on_image, qos_profile_sensor_data)
        self._info_sub = self.create_subscription(
            CameraInfoMsg, p("camera_info_topic"), self._on_camera_info, qos_profile_sensor_data
        )

        self._worker = threading.Thread(target=self._run, name="detector-worker", daemon=True)
        self._worker.start()

    # -- callbacks (executor thread) ---------------------------------------

    def _on_camera_info(self, msg: CameraInfoMsg) -> None:
        # Calibration does not change: take the first one and unsubscribe.
        self._pipeline.set_camera_info(camera_info_from_msg(msg))
        self.destroy_subscription(self._info_sub)
        self.get_logger().info(f"camera info received ({msg.width}x{msg.height}, {msg.distortion_model})")

    def _on_image(self, msg: ImageMsg) -> None:
        image = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        self._buffer.put(
            Frame(
                seq=self._seq,
                stamp_ns=_stamp_ns(msg),
                recv_ns=self.get_clock().now().nanoseconds,
                frame_id=msg.header.frame_id,
                image=image,
            )
        )
        self._seq += 1

    # -- worker thread -----------------------------------------------------

    def _run(self) -> None:
        self._pipeline.run(self._buffer, self._publish)

    def _publish(self, result: FrameResult, frame: Frame) -> None:
        msg = detections_to_msg(result)
        self._pub.publish(msg)
        if self._debug_pub is not None:
            from ..visualization import draw_result

            img_msg = self._bridge.cv2_to_imgmsg(draw_result(frame.image, result), encoding="bgr8")
            img_msg.header = msg.header
            self._debug_pub.publish(img_msg)
        if result.frame_seq % 100 == 0:
            self.get_logger().info(
                f"seq {result.frame_seq}: {len(result.detections)} det, "
                f"inference {result.inference_ms:.0f} ms, wait {result.queue_wait_ms:.0f} ms, "
                f"dropped {result.dropped_total} total"
            )

    def destroy_node(self) -> None:
        self._buffer.close()  # lets the worker's run() return
        self._worker.join(timeout=5.0)
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
