# Project status

**Last updated: 2026-09-04**

A living document. Update it whenever something is verified, decided, or ruled
out — it is the first thing to read when picking the project back up.

---

## Where the project stands

| Area | State |
|---|---|
| Repository scaffold | **Done.** Folders, dependency manifests, module contracts. |
| ROS 2 packages | **Not started.** No `package.xml` / `setup.py` yet, so `colcon build` has nothing to build. |
| Robot access | **Working.** SSH, topics inspected, first bag recorded. |
| Object detection | Walkthrough phases 0–1 done. See [guides/object-detection-pipeline.md](guides/object-detection-pipeline.md). |
| Mapping | Not started. |
| Git | **Nothing committed yet.** Everything is still untracked in the working tree. |

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

### Recordings

| Bag | Duration | Contents | Size |
|---|---|---|---|
| `indoor_run_01` | 14.5 s | 470 images, 136 CameraInfo, 1155 tf, 1 tf_static | 777 MB |

Recorded with the robot **stationary**. Sufficient for walkthrough phases 3–6;
phase 7 and mapping will need a moving recording.

Data rate ≈ **53 MB/s** uncompressed. Budget ~3.2 GB per minute of recording.

---

## Open questions

Ordered by how much they affect the thesis.

| # | Question | How to settle it |
|---|---|---|
| 1 | Why is `camera/point_cloud` not published? | Find what should produce it in the SDK. Blocks phase 7. |
| 2 | Is `command/manager/cmd_twist` an input or the command manager's output? | `ros2 topic info /tita3037072/command/manager/cmd_twist --verbose` — decides whether the locomotion bridge is a converter or just a remap. |
| 3 | Is a TITA Tower physically attached? | `ros2 topic hz /tower/mapping/odometry`. If yes, there is a LiDAR and the mapping chapter changes shape. See [hardware/topic-map.md](hardware/topic-map.md). |
| 4 | Which node publishes the camera images? | `ros2 topic info /tita3037072/perception/camera/image/left --verbose`. No camera driver node appeared in `ros2 node list`, which is odd — and the answer probably also explains question 1. |
| 5 | Actual sensor part numbers and manufacturers | Not yet determined. Topic names give only functional roles. Needs `dmesg`, `/dev/v4l/by-id/`, `/sys/bus/i2c/devices/`, device tree. Needed for the hardware chapter. |

---

## Next steps

1. Copy `indoor_run_01` to `data/bags/` and open it in Foxglove — walkthrough
   phase 2.
2. Write the frame-extraction script (bag → PNG) in `perception/` — the first
   real code of the project, and the start of phase 4.
3. Minimal image subscriber node (phase 3), watching out for the QoS trap.
4. Commit. Nothing is in git yet.

---

## Decisions still open

Tracked in the root [README](../README.md) under *Open decisions*; each becomes
an ADR in [adr/](adr/) once settled. Detector choice, SLAM backend, inference
runtime, LiDAR, repository licence.
