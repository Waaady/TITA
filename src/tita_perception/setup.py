from glob import glob

from setuptools import find_packages, setup

package_name = "tita_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test", "test.*"]),
    data_files=[
        # ament index + package.xml + config/launch, as every ament_python package.
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools", "numpy<2", "opencv-python", "pyyaml"],
    extras_require={
        "onnx": ["onnxruntime-gpu>=1.21"],
        "torch": ["torch", "torchvision"],  # + pip install -e external/YOLOX
    },
    zip_safe=True,
    maintainer="TODO",
    maintainer_email="todo@example.com",
    description="YOLOX object detection on the TITA robot.",
    license="TODO",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "detector_node = tita_perception.nodes.detector_node:main",
        ],
    },
)
