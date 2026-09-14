# `tita_perception` — object detection on the robot

**Runtime only.** No training code, no dataset code. This package loads an
exported artifact produced by [`perception/`](../../perception/) and turns
camera images into 3D obstacles.

## Pipeline

```
  /camera/left/image_raw ─┐
  /camera/.../camera_info ┤
                          ▼
                    detector node          detectors/       (YOLOX -> boxes)
                          │  vision_msgs/Detection2DArray
                          ▼
                    tracker node           tracking/        (ID association)
                          │  Detection2DArray with stable IDs
                          ▼
                   projection node         projection/      (2D -> 3D)
                          │  vision_msgs/Detection3DArray
                          ▼
            costmap layer / semantic map consumers
```

## Sub-modules

| Directory | Contents |
|---|---|
| `detectors/` | One class per backend behind a common `Detector` interface: `predict(image) -> boxes`. Planned: `YoloxTensorRTDetector`, `YoloxOnnxDetector`, `YoloxTorchDetector`. Swapping backends must be a config change, not a code change. |
| `tracking/` | Frame-to-frame association so a detection has a stable identity. ByteTrack or a simple IoU+Kalman tracker. Needed before anything can reason about "the same person moved". |
| `projection/` | Lifts 2D boxes to 3D using stereo depth / the SPAD ToF plus `camera_info` and TF. This is where most of the real error comes from — document the assumptions. |

## Interfaces

- **Subscribes**: rectified image + `sensor_msgs/CameraInfo`, depth or disparity,
  TF.
- **Publishes**: `vision_msgs/Detection3DArray`, plus an annotated debug image
  on a separate topic that is **off by default** (encoding and publishing JPEGs
  costs real frames per second on the Orin).
- **Parameters**: model path, input resolution, confidence and NMS thresholds,
  class whitelist, target frame. All in `config/`.

## Notes

- Preprocessing in the node must match training exactly — the same letterbox,
  the same channel order, the same normalisation. Silent mismatches here cost
  accuracy without ever raising an error, and they are painful to debug from
  mAP numbers alone. Consider asserting on a fixed test image at startup.
- Benchmark with the debug image publisher disabled; otherwise you are
  benchmarking image compression.

---

## What exists today (2026-09-13)

The pure-Python part of the pipeline is implemented and tested against the
`2026-09-04_lab_moving_01` recording. The ROS node itself is not written yet;
everything below runs without ROS, on Windows or Linux.

```
tita_perception/
├── bag/            rosbag2 sqlite3 reader + CDR decoding of Image / CameraInfo (no ROS needed)
├── detectors/      Detector interface, YoloxOnnxDetector, YoloxTorchDetector, shared pre/postprocessing
├── pipeline/       Frame, LatestFrameSlot / FrameQueue, BagFrameSource, DetectionPipeline, FrameResult
├── tracking/       IouTracker (stable ids + image-plane motion)
├── geometry.py     pixel -> bearing / elevation from CameraInfo
└── visualization.py  debug overlay (off by default, costs fps)
config/detector.yaml   every tunable
test/                  pytest; `pytest src/tita_perception/test`
```

### Running it

```bash
python scripts/download_yolox_weights.py                       # once: yolox_s .pth + .onnx into models/
python scripts/run_detection_on_bag.py data/bags/<bag>          # ONNX, config defaults
python scripts/run_detection_on_bag.py data/bags/<bag> --backend torch --device cuda --show
python scripts/run_detection_on_bag.py data/bags/<bag> --buffer all --speed 0   # offline: every frame
```

Output: one JSON line per processed frame in `data/interim/detections/`.

### Staleness policy — always the newest frame

`pipeline.frame_buffer: latest` is a one-element mailbox between the frame
source and the detector. A new frame *replaces* an unprocessed one; the
detector therefore never works on an image older than the newest available,
and every skipped frame is counted (`dropped_since_last`, `dropped_total`,
`queue_wait_ms` in the output). On the robot this is what keeps an obstacle
report from arriving after the robot has reached the obstacle. `all` is a
bounded FIFO with back-pressure for offline evaluation where every frame
matters.

Measured on the workstation (960x600 frames, ~36 Hz in the bag, YOLOX-s 640):

| backend | device | inference | frames processed |
|---|---|---|---|
| ONNX Runtime | CPU | ~40 ms | 606 / 973 (367 dropped, still real-time) |
| ONNX Runtime | CUDA (RTX 5080) | ~8 ms | 973 / 973 |
| PyTorch | CUDA (RTX 5080) | ~10 ms | 968 / 973 |

### Output contract (`FrameResult` / `ObstacleObservation`)

Per frame: `frame_seq`, `stamp_ns` (sensor time), `recv_ns`, `frame_id`,
image size, `queue_wait_ms`, `inference_ms`, `total_ms`, drop counters.

Per detection:

| field | meaning |
|---|---|
| `class_id`, `label`, `score`, `obj_conf`, `cls_conf` | what; `score = obj * cls` |
| `is_dynamic` | class is in `pipeline.dynamic_classes` (person, dog, ...) |
| `bbox_xyxy`, `bbox_norm`, `center_xy`, `width_px`, `height_px`, `area_frac` | where in the image |
| `foot_xy` | bottom-centre of the box: ground contact point, the input for a ground-plane range estimate |
| `touches_border` | box clipped by the image edge, size/foot unreliable |
| `bearing_rad` | horizontal angle of the box centre, **positive = right** (camera optical frame) |
| `foot_elevation_rad` | vertical angle of the foot point, **positive = down** |
| `track.track_id`, `confirmed`, `hits`, `age_frames`, `duration_s` | identity over time |
| `track.velocity_px_s` | box-centre velocity in the image |
| `track.bearing_rate_rad_s` | d(bearing)/dt — a target on a collision course keeps a constant bearing (rate ~ 0) while growing |
| `track.scale_rate_per_s` | relative growth of box size per second; > 0 means getting closer |
| `track.height_rate_px_s` | same for box height (more robust for people than area) |

The *decision* whether a tracked object is approaching or entering the path
is deliberately **not** made here — that is a separate component consuming
this record.

Angles use the `rational_polynomial` distortion model from CameraInfo
(`pipeline.undistort_angles: true`) because `image/left` is the raw,
strongly barrel-distorted image (~118° horizontal FOV). Verified on the
2026-09-04 recording; the pinhole-only bearing is off by up to 14° at the edge.

### Preprocessing contract (do not change without retraining)

Letterbox to 640x640 anchored top-left, pad 114, `INTER_LINEAR`, **BGR**,
CHW, float32 **0..255 without normalisation**. `test_yolox_common.py` checks
this against upstream `yolox.data.data_augment.preproc` byte for byte, and
`test_pipeline.py` checks that the ONNX and PyTorch backends agree on a real
frame — the export-equivalence test from `tests/README.md`.

### ROS 2 node (written 2026-09-14, not yet run — needs a ROS 2 machine)

`tita_perception/nodes/detector_node.py`: image callback -> `LatestFrameSlot`,
worker thread runs `DetectionPipeline.run`, publishes `vision_msgs/Detection2DArray`
(stamp = image stamp, `id` = track id). CameraInfo is taken once and the
subscription dropped. ROS-only parameters in `config/detector_node.yaml`;
detector settings come from `detector.yaml` via `config_file`.

```bash
colcon build --symlink-install && source install/setup.bash
ros2 bag play data/bags/<bag> --clock                          # terminal 1
ros2 launch tita_perception detection.launch.py namespace:=/tita3037072 use_sim_time:=true
ros2 topic hz /tita3037072/perception/detections               # terminal 3
```

Run `ros2 launch` from the workspace root, or set `models_root`.

### Not done yet

- Running the node on the Jetson / against `ros2 bag play`.
- An own message in `tita_interfaces_thesis` for bearing, foot point, scale
  rate etc. — `Detection2DArray` carries only box, label, score, track id.
- TensorRT backend (build the engine on the Orin from `models/onnx/`).
- Tracker is a greedy IoU matcher; swap for ByteTrack when needed, keeping
  the `TrackInfo` fields.
- 2D → 3D projection (blocked: `camera/point_cloud` has no publisher).
