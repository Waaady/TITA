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
