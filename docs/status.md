# Project status

**Last updated: 2026-09-18**

A living document. Update it whenever something is verified, decided, or ruled
out — it is the first thing to read when picking the project back up.

---

## Goal

**Autonomous driving.** TITA navigating indoor environments on its own, and
mapping them while it drives. Object detection and SLAM are the two enabling
capabilities; they are means, not ends.

Use this as the tie-breaker when priorities are unclear: does it move the robot
closer to driving autonomously?

**Secondary, and deliberately kept secondary:** TITA balances on two wheels and
pitches constantly to stay upright, whereas SLAM is normally run on stable
platforms. The effect of that on mapping quality is worth recording as a side
result — but it must not become the main line of investigation.

---

## Where the project stands

| Area | State |
|---|---|
| Repository scaffold | **Done.** Folders, dependency manifests, module contracts. |
| ROS 2 packages | `tita_perception` **runs live on the robot** (2026-09-18). Three backends: ONNX CPU (~1100 ms/frame), and **TensorRT FP16 on the GPU: ~18 ms/frame, 4 % dropped** — see [experiments/2026-09-18-detector-latency-cpu-vs-tensorrt.md](experiments/2026-09-18-detector-latency-cpu-vs-tensorrt.md). Other packages still empty. |
| Robot access | **Working.** SSH, topics inspected, bags recorded. Repo cloned on the robot. See [work_diary/](work_diary/) for the session log. |
| Object detection | **Phases 3–5 and 8 done (2026-09-18):** node runs live on the Jetson GPU. Phase 6 (Foxglove boxes) and 7 (3D) not started. Detection *quality* on the robot not yet inspected — only speed. |
| Mapping | Not started. |
| Git | Last commit `b11a32c`. **Everything from 2026-09-18 is uncommitted** (TensorRT backend, experiment, diary, docs) — commit first next session. Config on the robot diverges from the repo (`backend: tensorrt` vs `onnx`) — see [work_diary/2026-09-18.md](work_diary/2026-09-18.md). |

---

## Verified facts about this robot

Measured on the machine, not taken from the datasheet.

### Identity and access

- **Robot namespace: `/tita3037072`** (from the serial number). Never hardcode it.
- SSH works. Credentials and the three possible addresses are in
  [hardware/robot-access.md](hardware/robot-access.md).

### What is installed — and what is not

| | State | Consequence |
|---|---|---|
| `ros-humble-rosbag2-storage-mcap` | **not installed** | Bags are recorded as `sqlite3` `.db3`, not MCAP. Foxglove still opens them (all recorded types are ROS standard messages). |
| `tmux` | **not installed** | Long-running commands die with the SSH session. Use `nohup`, or install tmux once the robot has internet. |
| `git`, `rosdep`, `colcon`, `python3-pip` | **were not installed** — installed 2026-09-15 | TITA ships a runtime-only ROS. |
| TensorRT Python binding, `trtexec`, `nvcc`, CUDA headers, `pycuda` | **were not installed** — installed 2026-09-18 | TITA ships the TensorRT/CUDA *runtime* libraries only. Package list in `requirements-jetson.txt`. |
| ROS apt signing key | **was expired** — refreshed 2026-09-15 | Until then no ROS package could be installed at all; explains the missing MCAP plugin and tmux. See [guides/deploy-to-robot.md](guides/deploy-to-robot.md) step 2. |

Installing either needs internet on the robot, which means **client WiFi mode**,
not AP mode — the two are mutually exclusive on TITA.

### Sensor data — what actually flows

| Topic (under `/tita3037072`) | State | Measured |
|---|---|---|
| `perception/camera/image/left` | **publishing** | ~42 Hz live, ~32 Hz when recording (frames dropped on write) |
| `perception/camera/info/left` | **publishing** | ~9.4 Hz — much slower than the images |
| `perception/camera/point_cloud` | **NO publisher** | `obstacle_detector_node` subscribes and waits; nothing produces it |
| `/tf` | publishing | ~80 Hz |
| `/tf_static` | publishing | once, latched |

Two consequences worth remembering:

- **CameraInfo arrives ~4x slower than images.** Do not try to synchronise them
  1:1. Cache the first `CameraInfo` and reuse it — calibration does not change.
- **The stereo depth computation is not running.** Whatever should produce
  `point_cloud` is not started. This blocks phase 7 (2D → 3D projection), but
  nothing before it.

### Camera (measured from the 2026-09-04 bag)

- `image/left` is **960x600 `bgr8`**, ~36 Hz in the bag, frame `tita3037072/left_camera`.
- CameraInfo: `rational_polynomial`, 8 coefficients, fx ≈ fy ≈ 479, principal
  point ≈ (479, 298), frame `left_img_raw`. **The image is raw, not rectified**:
  strong barrel distortion, ~118° horizontal FOV after undistortion. Any angle
  or 3D work must undistort first; the pinhole-only bearing is 14° off at the edge.
- CameraInfo `P` has a non-zero Tx (−71 → baseline ≈ 0.15 m if that is fx·b) —
  odd for the *left* camera of a stereo pair. Unverified.

### Recordings

| Bag | Duration | Contents | Size |
|---|---|---|---|
| `indoor_run_01` | 14.5 s | 470 images, 136 CameraInfo, 1155 tf, 1 tf_static | 777 MB |
| `2026-09-04_lab_moving_01` (`indoor_run_03`) | 27 s | 973 images, 266 CameraInfo, 2157 tf, 1 tf_static | 1.68 GB |

`indoor_run_01` was recorded **stationary**; `lab_moving_01` with the robot
moving through the lab and a corridor with people walking. Both are sqlite3
`.db3` (MCAP plugin not installed on the robot); `tita_perception.bag` reads
them without ROS.

Data rate ≈ **53 MB/s** uncompressed. Budget ~3.2 GB per minute of recording.

---

## Open questions

Ordered by how much they affect the thesis. The project-level risks behind these
are in [risks.md](risks.md) — in particular **R2**, whether the robot can be
commanded from our own code at all, which is on the critical path.

| # | Question | How to settle it |
|---|---|---|
| 1 | Why is `camera/point_cloud` not published? | Find what should produce it in the SDK. Blocks phase 7. |
| 2 | Is `command/manager/cmd_twist` an input or the command manager's output? | `ros2 topic info /tita3037072/command/manager/cmd_twist --verbose` — decides whether the locomotion bridge is a converter or just a remap. |
| 3 | Is a TITA Tower physically attached? | `ros2 topic hz /tower/mapping/odometry`. If yes, there is a LiDAR and the mapping chapter changes shape. See [hardware/topic-map.md](hardware/topic-map.md). |
| 4 | Which node publishes the camera images? | `ros2 topic info /tita3037072/perception/camera/image/left --verbose`. No camera driver node appeared in `ros2 node list`, which is odd — and the answer probably also explains question 1. |
| 5 | Actual sensor part numbers and manufacturers | Not yet determined. Topic names give only functional roles. Needs `dmesg`, `/dev/v4l/by-id/`, `/sys/bus/i2c/devices/`, device tree. Needed for the hardware chapter. |
| 6 | Is there a rectified image topic, and what is the stereo baseline? | `image/left` is raw (see Camera above). Check `ros2 topic list` for a `rect` topic and the right camera's CameraInfo. Matters for phase 7. |

---

## Detection pipeline — state on 2026-09-13

Implemented in `src/tita_perception/` (pure Python, no ROS), run via
`scripts/run_detection_on_bag.py`, 41 tests in `src/tita_perception/test/`.

- `.db3` → chronological frames → **one-slot latest-frame buffer** → YOLOX →
  IoU tracker → JSONL with box, label/score, foot point, bearing/elevation,
  track id, pixel velocity, bearing rate, scale rate. The approach/path
  decision is left to a later component.
- Workstation numbers (YOLOX-s 640, 960x600 input): ONNX CPU ~40 ms (drops a
  third of the frames at 36 Hz but stays current), ONNX CUDA ~8 ms, PyTorch
  CUDA ~10 ms — nothing dropped.
- ONNX and PyTorch backends agree on real frames (export-equivalence test).
- Workstation env: conda `TITA` (Python 3.10). torch had to be moved to
  **2.8.0+cu128** — the RTX 5080 (Blackwell, sm_120) is unsupported by the
  torch 2.1.2 that was pinned before. `requirements.txt` updated accordingly.

## Next steps

1. **Commit** — everything from 2026-09-18 is in the working tree only.
2. Look at one live detection: `ros2 topic echo /tita3037072/perception/detections --once`.
3. Resolve the config divergence: `config/detector_jetson.yaml` + `config_file` launch argument.
4. Run `test_onnx_and_tensorrt_backends_agree` on the robot (needs `pytest` there).
5. Phase 6: `ImageAnnotations` publisher + `foxglove_bridge` → boxes over the live image.
6. Settle the open questions below, especially the missing `point_cloud` (blocks phase 7).
   WSL/Ubuntu 22.04) against `ros2 bag play`; fix what breaks.
3. Phase 6: Foxglove `ImageAnnotations` + layout.
4. Approach / path-intrusion component consuming the `FrameResult` record.
5. Open the bags in Foxglove (phase 2) — never done, still useful for the thesis figures.
6. Settle the open questions below, especially the missing `point_cloud`.

---

## Decisions still open

Tracked in the root [README](../README.md) under *Open decisions*; each becomes
an ADR in [adr/](adr/) once settled. Detector choice, SLAM backend, inference
runtime, LiDAR, repository licence.
