"""Start detector_node under the robot's namespace.

    ros2 launch tita_perception detection.launch.py namespace:=/tita3037072
    ros2 launch tita_perception detection.launch.py namespace:=/tita3037072 use_sim_time:=true   # bag replay
    ros2 launch tita_perception detection.launch.py namespace:=/tita3037072 detector_config:=detector_jetson.yaml  # TensorRT

detector_config names a file in share/tita_perception/config/ (detector.yaml
= ONNX on CPU, works anywhere; detector_jetson.yaml = TensorRT, robot only).
An absolute path is accepted as-is.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_node(context, *args, **kwargs):
    share = Path(get_package_share_directory("tita_perception"))
    config = Path(LaunchConfiguration("detector_config").perform(context))
    if not config.is_absolute():
        config = share / "config" / config
    return [
        Node(
            package="tita_perception",
            executable="detector_node",
            namespace=LaunchConfiguration("namespace"),
            parameters=[
                LaunchConfiguration("params_file"),
                {
                    "config_file": str(config),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                },
            ],
            output="screen",
        )
    ]


def generate_launch_description() -> LaunchDescription:
    share = Path(get_package_share_directory("tita_perception"))
    return LaunchDescription(
        [
            # The namespace is the robot's serial number - never hardcoded.
            DeclareLaunchArgument("namespace", description="robot namespace, e.g. /tita3037072"),
            DeclareLaunchArgument("params_file", default_value=str(share / "config" / "detector_node.yaml")),
            DeclareLaunchArgument(
                "detector_config",
                default_value="detector.yaml",
                description="detector/pipeline config in share/config/, or an absolute path",
            ),
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            # OpaqueFunction: the config path has to be resolved at launch time,
            # after the argument value is known.
            OpaqueFunction(function=_launch_node),
        ]
    )
