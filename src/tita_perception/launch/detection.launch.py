"""Start detector_node under the robot's namespace.

    ros2 launch tita_perception detection.launch.py namespace:=/tita3037072
    ros2 launch tita_perception detection.launch.py namespace:=/tita3037072 use_sim_time:=true   # bag replay
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share = Path(get_package_share_directory("tita_perception"))
    return LaunchDescription(
        [
            # The namespace is the robot's serial number - never hardcoded.
            DeclareLaunchArgument("namespace", description="robot namespace, e.g. /tita3037072"),
            DeclareLaunchArgument("params_file", default_value=str(share / "config" / "detector_node.yaml")),
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            Node(
                package="tita_perception",
                executable="detector_node",
                namespace=LaunchConfiguration("namespace"),
                parameters=[
                    LaunchConfiguration("params_file"),
                    {"use_sim_time": LaunchConfiguration("use_sim_time")},
                ],
                output="screen",
            ),
        ]
    )
