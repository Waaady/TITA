"""Reading rosbag2 sqlite3 (``.db3``) recordings without a ROS installation.

Only the message types we need are decoded (``sensor_msgs/Image``,
``sensor_msgs/CameraInfo``). Plain Python + numpy, so the same code runs on
a Windows workstation, in CI, and on the robot.
"""

from .bag_reader import CAMERA_INFO_TYPE, IMAGE_TYPE, Rosbag2SqliteReader, TopicInfo
from .ros_messages import CameraInfo, Header, Image, decode_camera_info, decode_image

__all__ = [
    "CAMERA_INFO_TYPE",
    "IMAGE_TYPE",
    "CameraInfo",
    "Header",
    "Image",
    "Rosbag2SqliteReader",
    "TopicInfo",
    "decode_camera_info",
    "decode_image",
]
