# Deploying `tita_perception` to the robot

Step by step, from a clean commit on your laptop to the detector running
against the live camera on the Jetson. Each step ends with **how you know it
worked**. Do them in order — every step exists because the next is much harder
to debug without it.

Two terminals throughout: one PowerShell on the laptop, one SSH session on the
robot. Code blocks are marked `powershell` (laptop) or `bash` (robot).

## What travels how

| | How it gets there |
|---|---|
| `src/tita_perception/` — node, pipeline, launch, config | `git clone` / `git pull` |
| YOLOX weights | downloaded **on the robot** by `scripts/download_yolox_weights.py` (`models/` is gitignored) |
| ROS dependencies (`cv_bridge`, `vision_msgs`, …) | `rosdep` from `package.xml` |
| `onnxruntime` | `pip`, on the robot |

The first time, all four need internet **on the robot**. See step 1.

---

## 0. Laptop — everything committed and pushed

```powershell
git status          # must be clean
git push
```

**Done when:** `git status` prints nothing and `git push` reports up to date.

Anything not pushed does not exist as far as the robot is concerned.

---

## 1. Robot — get it online

TITA's AP hotspot and client WiFi are mutually exclusive. In AP mode there is
**no internet**, so `git`, `apt` and `pip` all fail.

```bash
sudo wifi-app -ap_off
sudo wifi-app -on          # Ctrl+C for the menu, enter SSID + password
```

The robot now gets an address from your router — it is no longer `10.42.0.1`.
Reconnect over SSH to the new address
([robot-access.md](../hardware/robot-access.md)).

**Done when:**
```bash
ping -c 2 github.com
```
answers.

---

## 2. Robot — first time only: rosdep

```bash
sudo rosdep init      # "already initialized" is fine
rosdep update
```

**Done when:** `rosdep update` ends without errors.

---

## 3. Robot — get the code

First time:

```bash
cd ~
git clone https://github.com/Waaady/TITA.git
cd ~/TITA
```

Every later time:

```bash
cd ~/TITA
git pull
```

**Done when:** `git log --oneline -1` shows the same commit as on the laptop.

Only `src/tita_perception/` has a `package.xml`, so colcon will build exactly
one package. The other folders in `src/` are empty scaffolds and cost nothing.

---

## 4. Robot — ROS dependencies

```bash
cd ~/TITA
sudo apt update
rosdep install --from-paths src --ignore-src -r -y
```

This reads `package.xml` and installs `ros-humble-cv-bridge`,
`ros-humble-vision-msgs` and friends.

**Done when:**
```bash
python3 -c "import rclpy, cv_bridge, vision_msgs.msg; print('ok')"
```
prints `ok`.

---

## 5. Robot — ONNX Runtime

```bash
pip3 install onnxruntime
```

**CPU build on purpose.** It proves the plumbing. The GPU build for aarch64 does
not come from PyPI — that is a later, separate step
([requirements-jetson.txt](../../requirements-jetson.txt)).

> **Never `pip install opencv-python` on the Jetson.** JetPack ships a
> CUDA-enabled `cv2`; the PyPI wheel replaces it with a CPU-only one and
> everything camera-related gets slower. `opencv-python` is listed in
> `setup.py`'s `install_requires`, so also **never run
> `pip install -e src/tita_perception` on the robot** — let colcon build it
> (step 7), which does not pull dependencies.

**Done when:**
```bash
python3 -c "import onnxruntime as o, cv2, numpy as n; print(o.__version__, cv2.__version__, n.__version__)"
```
prints three versions and numpy is `1.x`.

---

## 6. Robot — weights

```bash
cd ~/TITA
python3 scripts/download_yolox_weights.py
```

**Done when:** `ls -la models/onnx/yolox_s.onnx` shows ~35 MB.

---

## 7. Robot — build

```bash
cd ~/TITA
colcon build --symlink-install --packages-select tita_perception
source install/setup.bash
```

`--symlink-install` means later edits to the Python files take effect without
rebuilding. Config or launch changes still need a rebuild.

**Done when:**
```bash
ros2 pkg executables tita_perception
```
lists `detector_node`.

---

## 8. Robot — first run against a bag, not the camera

The node has never run before. Its first execution will surface import errors,
undeclared parameters and QoS mismatches. Meet those against reproducible data.

Check whether a bag is still on the robot:

```bash
ls ~/indoor_run_01 ~/indoor_run_02 2>/dev/null
```

If not, copy one back from the laptop (in PowerShell):

```powershell
scp -r data\bags\2026-09-04_lab_moving_01 robot@<address>:~/
```

Then, two SSH terminals:

```bash
# terminal 1
ros2 bag play ~/2026-09-04_lab_moving_01 --clock --loop
```

```bash
# terminal 2
cd ~/TITA && source install/setup.bash
ros2 launch tita_perception detection.launch.py namespace:=/tita3037072 use_sim_time:=true
```

**Launch from `~/TITA`.** `models_root` resolves relative to the current
directory; from anywhere else the node cannot find the weights.

**Done when**, in a third terminal:
```bash
ros2 topic hz /tita3037072/perception/detections
ros2 topic echo /tita3037072/perception/detections --once
```
shows a rate and a `Detection2DArray` with a `person` in it.

Typical first-run failures and what they mean:

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError` | a dependency from step 4/5 missing, or `source install/setup.bash` forgotten |
| node starts, no detections, no error | QoS mismatch — but the node already uses `qos_profile_sensor_data`, so check the topic name and namespace first |
| `FileNotFoundError: .../models/...` | not launched from `~/TITA` |
| very slow, many drops | expected on CPU — ~200 ms per frame; the latest-frame policy keeps it current |

---

## 9. Robot — live

Stop the bag replay. Make sure the SDK is running and the camera publishes:

```bash
ros2 topic hz /tita3037072/perception/camera/image/left
```

Then:

```bash
cd ~/TITA && source install/setup.bash
ros2 launch tita_perception detection.launch.py namespace:=/tita3037072
```

(`use_sim_time` defaults to false.)

**Done when:** `ros2 topic hz /tita3037072/perception/detections` reports a rate
while someone walks in front of the robot.

---

## 10. See it from the laptop

Detections are a few hundred bytes each — they cross WiFi without trouble.
Start the bridge on the robot:

```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

In Foxglove: *Open connection* → `ws://<robot-address>:8765`, add a Raw
Messages panel on `/tita3037072/perception/detections`.

Do **not** enable `publish_debug_image` for this — encoding images costs the
Orin real frames per second. Overlaying boxes on the camera image in Foxglove is
phase 6 of the [walkthrough](object-detection-pipeline.md)
(`foxglove_msgs/ImageAnnotations`).

---

## Daily loop after the first time

```powershell
# laptop
git commit -am "..." ; git push
```

```bash
# robot
cd ~/TITA && git pull && colcon build --symlink-install --packages-select tita_perception
source install/setup.bash
ros2 launch tita_perception detection.launch.py namespace:=/tita3037072
```

Or skip the round trip entirely: open `~/TITA` on the robot with **VS Code
Remote-SSH** and edit there. Close it before taking latency measurements — the
VS Code server competes with the detector for the Orin's CPU.

---

## Record what you measured

The first live run is the first real number for the thesis: mean inference
time on the Orin CPU and the drop rate at the camera's ~42 Hz. Put it in
[experiments/](../experiments/) with the commit hash, and update
[status.md](../status.md).
