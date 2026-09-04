# `models/` — trained artifacts

The handoff point between [`perception/`](../perception/) (training) and
[`src/tita_perception/`](../src/tita_perception/) (inference).

Weights are **not committed**; the directory structure is. Large binaries in git
history make the repo painful to clone and are not what a thesis repository is
for. Keep the actual files on a drive or institute storage, and record where in
`docs/`.

## Stages

```
checkpoints/*.pth  ──export──▶  onnx/*.onnx  ──trtexec──▶  tensorrt/*.engine
   (portable,                    (portable,                 (fast, and locked to
    training format)              runs anywhere)             one GPU + one
                                                             TensorRT version)
```

| Directory | Format | Portable? |
|---|---|---|
| `checkpoints/` | PyTorch `.pth` | yes |
| `onnx/` | ONNX | yes |
| `tensorrt/` | TensorRT `.engine` | **no** — rebuild on the target device |

**TensorRT engines are never committed and never copied between machines.** An
engine built on a workstation RTX card will not load on the Jetson, and an
engine built under one JetPack version may not load under the next. Build them
on the robot, from the `.onnx`, as a deployment step.

## Naming

Use a name that ties an artifact to the run that produced it and can be cited
directly in the thesis:

```
yolox_s_indoor_640_v3.pth
yolox_s_indoor_640_v3.onnx
yolox_s_indoor_640_v3_orin_trt10.engine
```

## Model card

Each artifact that produces a number in the thesis needs a short note next to
it: training config, dataset version, input resolution, class list, mAP, and
measured latency on the Orin. Without that, results become uninterpretable a
month later — and the defence is more than a month later.
