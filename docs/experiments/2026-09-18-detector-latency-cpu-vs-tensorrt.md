# Detector latency on the Orin: CPU vs. TensorRT

**Date:** 2026-09-18
**Question:** Can YOLOX-s run on TITA's Jetson fast enough for navigation, and
what does moving it from CPU to GPU buy?
**Commit:** `b11a32c` + uncommitted TensorRT backend (`yolox_tensorrt.py`,
`build_engine.sh`) — commit hash to be filled in once committed.

## Setup

| | |
|---|---|
| Robot | TITA, Jetson Orin NX 16 GB, JetPack 6.0 (L4T r36.3), CUDA 12.2, TensorRT 8.6.2 |
| Power mode | MAXN (`nvpmodel -m 0`), `jetson_clocks` applied before the TensorRT run |
| Model | YOLOX-s, official COCO weights, 640x640 input |
| Camera | `perception/camera/image/left`, 960x600 `bgr8`, live, ~36–42 Hz |
| Node | `detector_node`, `frame_buffer: latest`, single worker thread |
| Scene | lab, robot stationary then driven by remote; people walking through |
| Visualisation | none (no Foxglove bridge running) |

Numbers are from the node's own log (`inference` = detector.detect() only,
including pre/post-processing on the CPU; `dropped` = frames discarded by the
latest-frame buffer).

## Results

### CPU — ONNX Runtime 1.23.2, `CPUExecutionProvider`

```
seq  700: inference 1332 ms  wait 117 ms  dropped 579 total
seq 1600: inference 1060 ms  wait  45 ms  dropped 1320 total
```

- Inference **1.0–1.3 s per frame** (steady state, not warm-up).
- Frames reaching the node: 700 in 128 s ≈ **5.5 Hz** — the executor thread
  is starved by the inference thread; DDS drops most frames before Python
  sees them.
- Processed ≈ 1 frame/s, ≈ 83 % of received frames dropped on top.
- Not navigation-grade: at 1 m/s the robot has moved a metre before a
  detection arrives.

### GPU — TensorRT 8.6 FP16 engine, native backend (pycuda)

`trtexec` at build time: **GPU compute 7.23 ms mean** (min 6.73, max 8.28),
throughput 137.9 qps, H2D 0.29 ms, D2H 0.19 ms. Engine 21 MB, build ~10 min.

Node, live:

```
seq    0: inference 36 ms  (warm-up)
seq  100: inference 19 ms  wait 1 ms   dropped 6 total
seq 1000: inference 18 ms  wait 10 ms  dropped 44 total
seq 2100: inference 16 ms  wait 1 ms   dropped 86 total
```

- Inference **15–23 ms per frame**, typically 18 ms.
- Frames reaching the node: 2100 in 61 s ≈ **34 Hz** — close to the camera rate.
- Dropped **86 of 2100 ≈ 4 %**, attributable to camera jitter (frame gaps
  measured 12–74 ms on 2026-09-04): two frames inside one 18 ms window lose one.
- Detection latency ≈ 20 ms end to end.

### Summary

| | CPU ONNX | GPU TensorRT FP16 | factor |
|---|---|---|---|
| inference per frame | ~1100 ms | ~18 ms | ~60× |
| pure GPU compute (trtexec) | — | 7.2 ms | 150× vs CPU inference |
| frames reaching the node | ~5.5 Hz | ~34 Hz | 6× |
| frames dropped | ~83 % | ~4 % | |

Of the 18 ms, ~7 ms is GPU; the remaining ~11 ms is CPU-side letterbox,
host↔device copies, decode and NMS. The GPU is no longer the bottleneck;
headroom is ~55 fps against a 42 Hz camera.

## Conclusions

1. CPU inference of YOLOX-s on the Orin is a plumbing test, not a deployment
   option. This was expected; the number makes it concrete.
2. TensorRT FP16 makes YOLOX-s comfortably real-time with no model shrinking
   — the full 640-px model and its accuracy are kept. `yolox_tiny`/`nano`
   remain an option for freeing CPU for SLAM, not a necessity.
3. Remaining per-frame cost is CPU-side. If it ever matters: move letterbox
   to the GPU, or reduce the `cv_bridge` conversion in the subscriber
   callback (currently every received frame is converted, even ones that
   will be dropped).

## Not yet done

- ONNX-vs-TensorRT equivalence test (`test_onnx_and_tensorrt_backends_agree`)
  has not been run on the robot — pytest not installed there. Should be, so
  the FP16 rounding claim is verified rather than assumed.
- Detection *quality* was not evaluated in this run — only speed. The
  `person` counts on the moving bag per model (s / tiny / nano) are a
  separate experiment.
- Clock stability: trtexec reported 5.7 % variance in GPU compute time;
  `jetson_clocks` was applied but not verified with `tegrastats`.

## What had to be installed to get here

Not part of TITA as delivered — see `requirements-jetson.txt` and the
deploy guide: `python3-libnvinfer`, `libnvinfer-bin`, `cuda-nvcc-12-2`,
`cuda-profiler-api-12-2`, `libcurand-dev-12-2`, then `pycuda` from source.
