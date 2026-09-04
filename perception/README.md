# `perception/` — offline machine learning

Everything about the detector that does **not** run on the robot: dataset
preparation, training, evaluation, and export. Runs on a GPU workstation.

The product of this directory is a versioned artifact in
[`models/`](../models/), which is the only thing
[`src/tita_perception`](../src/tita_perception/) ever consumes. Nothing here is
imported by the ROS node.

## Layout

| Directory | Contents |
|---|---|
| `datasets/` | Dataset definitions, class maps, split logic, converters into COCO format. The class list is a thesis decision — record it here and in an ADR. Actual images live in `data/`, never here. |
| `configs/` | YOLOX experiment files (`exp` classes) and any training hyperparameters. One file per experiment, named so it can be cited in the thesis. |
| `training/` | Training entry points and schedules. |
| `evaluation/` | mAP, per-class metrics, confusion matrices, latency benchmarks. Outputs feed the plots in `notebooks/`. |
| `export/` | Checkpoint -> ONNX -> TensorRT engine. Also the place to verify that the exported model still matches the PyTorch model numerically. |

## YOLOX

Installed from source, not PyPI (the `yolox` package on PyPI is unrelated):

```bash
vcs import external < tita.repos      # from the repo root
pip install -e external/YOLOX
```

Apache-2.0, anchor-free, with a maintained ONNX and TensorRT export path — which
is why it is the default here rather than Ultralytics YOLO (AGPL-3.0, which
constrains how a published thesis can be licensed). The detector interface in
`src/tita_perception/detectors/` is deliberately backend-agnostic so this can be
re-evaluated without touching the robot code.

Reasonable starting point: `yolox-s` or `yolox-tiny` at 640x640, fine-tuned from
COCO weights on your own indoor data. Start from `yolox-nano` if the latency
budget on the Orin turns out to be tight.

## Reproducibility

Each training run must be reproducible from what is committed here: config file,
dataset version, seed, and the upstream commit pinned in `tita.repos`. A number
in the thesis that cannot be regenerated is a number that will be questioned in
the defence.

Log every run to TensorBoard and keep the run directory name consistent between
`models/checkpoints/`, `evaluation/` outputs, and the thesis text.
