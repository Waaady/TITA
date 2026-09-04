# TITA — Autonomous Navigation and Indoor Mapping

Bachelor thesis project on the **TITA** wheeled-bipedal robot
([Direct Drive Tech](https://en.directdrive.com/TITA)).

Two capabilities are built on top of the stock platform:

1. **Object detection** — a YOLOX detector on the onboard Jetson, lifted into 3D
   and fed to the navigation stack as dynamic obstacles / semantic targets.
2. **Indoor mapping** — SLAM from the onboard sensors, producing a 2D occupancy
   grid for Nav2 plus a 3D map for the thesis evaluation.

> Status: **architecture scaffold**. Folders, dependency manifests and the
> module contracts are in place; no implementation yet.

---

## Platform facts that shaped this layout

| | |
|---|---|
| Robot | TITA, 8-DOF wheeled biped, 8x quasi-direct-drive, 120 Nm peak |
| Onboard compute | NVIDIA Jetson Orin NX 16 GB (~100 TOPS) |
| OS / middleware | Ubuntu 22.04, JetPack 6.0, **ROS 2 Humble** |
| Onboard sensing | stereo (binocular) cameras, SPAD ToF, ultrasonic |
| Vendor SDK | [TITA-SDK-ROS2](https://github.com/DDTRobot/TITA-SDK-ROS2) |
| Simulation | Gazebo and Webots via `TITA_ROS2_Control_Sim` |

**The single most important integration detail:** the DDT SDK does *not* accept
`geometry_msgs/Twist`. It consumes
`tita_locomotion_interfaces/msg/LocomotionCmd` on `command/user/command`.
Nav2 emits `cmd_vel`. Everything in between lives in
[src/tita_locomotion_bridge/](src/tita_locomotion_bridge/) — that package is the
seam between "standard ROS navigation" and "this specific robot", and keeping it
isolated is what lets the rest of the stack be developed and tested in
simulation.

---

## Repository layout

The repository root **is** the colcon workspace root — `src/` holds ROS 2
packages; `build/`, `install/` and `log/` are generated and gitignored.

```
.
├── src/                     ROS 2 packages (our own) — the runtime system
│   ├── tita_bringup_thesis/     top-level launch: which nodes run where
│   ├── tita_description_thesis/ URDF/xacro for added sensors + mounts
│   ├── tita_interfaces_thesis/  our own msg/srv/action definitions
│   ├── tita_sensors/            sensor drivers, sync, calibration
│   ├── tita_perception/         YOLOX inference node, tracking, 3D projection
│   ├── tita_mapping/            SLAM configuration and map lifecycle
│   ├── tita_navigation/         Nav2 params, costmaps, behavior trees
│   ├── tita_locomotion_bridge/  cmd_vel -> LocomotionCmd  (vendor seam)
│   └── tita_teleop_safety/      manual override and e-stop
│
├── external/                upstream sources via `vcs import` (not committed)
├── perception/              OFFLINE ML: dataset prep, training, eval, export
├── models/                  weights: checkpoints / onnx / tensorrt engines
├── data/                    datasets, rosbags, saved maps (payload gitignored)
├── sim/                     Gazebo worlds and Webots scenes for the thesis
├── foxglove/                committed Foxglove layouts + bridge configuration
├── docs/                    architecture, ADRs, hardware notes, experiment logs
├── notebooks/               evaluation and plotting for the thesis
├── scripts/                 helper scripts (record, replay, deploy, benchmark)
├── tests/                   tests for the non-ROS Python code in perception/
├── docker/                  reproducible dev containers (x86 + Jetson/aarch64)
└── thesis/                  the written thesis (LaTeX)
```

### Why `perception/` is separate from `src/tita_perception/`

This split is deliberate and is the usual industrial arrangement:

- **`perception/`** never runs on the robot. It is plain Python: dataset
  conversion, YOLOX training, mAP evaluation, ONNX/TensorRT export. It needs a
  GPU workstation and a full PyTorch stack.
- **`src/tita_perception/`** is the ROS 2 node. It loads an *exported* artifact
  from `models/` and does nothing else — no training code, and no torch
  dependency at all on the robot if the TensorRT path is used.

Mixing the two is the most common way these projects become undeployable: the
node ends up importing training utilities and the Jetson image balloons. The
handoff between the two halves is a versioned artifact in `models/`, described
in [models/README.md](models/README.md).

---

## Setup

### 1. System packages (Ubuntu 22.04)

```bash
sudo apt install ros-humble-desktop python3-colcon-common-extensions \
                 python3-vcstool python3-rosdep git-lfs

# Navigation, SLAM and perception glue — all from apt, never from pip:
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup \
                 ros-humble-slam-toolbox ros-humble-rtabmap-ros \
                 ros-humble-robot-localization \
                 ros-humble-depthimage-to-laserscan \
                 ros-humble-vision-msgs ros-humble-vision-opencv \
                 ros-humble-image-pipeline ros-humble-tf2-tools \
                 ros-humble-rosbag2-storage-mcap \
                 ros-humble-foxglove-bridge \
                 ros-humble-compressed-image-transport
```

Visualisation is done with **Foxglove**, not RViz — see [foxglove/README.md](foxglove/README.md)
for the workflow and why. RViz stays available for quick local checks.

### 2. Upstream sources

```bash
git lfs install
vcs import external < tita.repos
```

### 3. Python environment

```bash
python3 -m venv --system-site-packages .venv   # --system-site-packages is required
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e external/YOLOX
```

On the robot use `requirements-jetson.txt` instead — see the header comment in
that file for why plain PyPI wheels are the wrong choice on aarch64.

### 4. Build

```bash
rosdep install --from-paths src external --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

---

## Conventions

- **Language**: code, comments and docs in English; the written thesis in
  `thesis/` may be German.
- **Namespacing**: all our topics live under the robot namespace, so a second
  TITA or a simulated one can share the network without collisions.
- **Frames**: REP-105 (`map` -> `odom` -> `base_link` -> sensor frames). Do not
  invent frame names; sensor frames are declared in `tita_description_thesis`
  and nowhere else.
- **Parameters**: no magic numbers in code. Every tunable goes into the owning
  package's `config/*.yaml` and is declared as a ROS parameter.
- **Decisions**: anything you would have to re-argue in the thesis defence gets
  a short ADR in [docs/adr/](docs/adr/) — detector choice, SLAM backend, sensor
  selection, coordinate conventions.

---

## Open decisions

Recorded here so they are not lost; each becomes an ADR once decided.

| # | Decision | Notes |
|---|---|---|
| 1 | Detector: YOLOX vs. RT-DETR vs. Ultralytics YOLO | YOLOX is **Apache-2.0**; Ultralytics is **AGPL-3.0**, which can be awkward for a published thesis. YOLOX also has a first-class TensorRT export path. Scaffolded for YOLOX, kept swappable behind `detectors/`. |
| 2 | SLAM backend | `slam_toolbox` (2D, needs a laser scan — derivable from ToF/stereo via `depthimage_to_laserscan`) vs. `rtabmap` (RGB-D/stereo, gives a 2D grid *and* a 3D map). RTAB-Map is the better fit for stereo-only indoor mapping. |
| 3 | Additional LiDAR? | Onboard sensing is stereo + SPAD ToF only. A Livox Mid-360 or similar would make mapping far more robust and would enable FAST-LIO2. Hardware/budget question. |
| 4 | Inference runtime | PyTorch (simplest) vs. ONNX Runtime vs. **TensorRT** (fastest on Orin, but the engine is device- and version-locked). Benchmarking all three is itself a good thesis result. |
| 5 | License for this repo | No `LICENSE` file yet — check your university's policy before publishing. |

---

## Next steps

The scaffold intentionally stops before code. In order:

1. Add `package.xml` plus `setup.py`/`CMakeLists.txt` to each package in `src/` —
   that is what turns these folders into real ROS 2 packages.
2. Bring up the vendor SDK unmodified and record a rosbag of every sensor topic
   (`scripts/`, output into `data/bags/`). Everything downstream can then be
   developed offline against that bag.
3. Implement `tita_locomotion_bridge` and verify teleop through it.
4. Mapping before detection: a working `map` -> `odom` transform is a
   prerequisite for projecting detections into 3D.
