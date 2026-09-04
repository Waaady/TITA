# Architecture Decision Records

A short document per significant decision, written when the decision is made.

The purpose is specific to a thesis: in the defence you will be asked *why* you
chose YOLOX over alternatives, why RTAB-Map over `slam_toolbox`, why detections
enter the costmap the way they do. An ADR written at the time captures the
reasoning while you still remember the alternatives you rejected. Reconstructing
it six months later produces a worse answer.

## Format

One file per decision, numbered and never renumbered:
`0001-object-detector-choice.md`.

```markdown
# 0001. Object detector choice

Date: 2026-09-11
Status: accepted        # proposed | accepted | superseded by 00XX

## Context
What forced a decision. Constraints: Orin NX latency budget, licensing,
available training data, deadline.

## Options considered
YOLOX / RT-DETR / Ultralytics YOLO — with the trade-off that mattered for each.

## Decision
What was chosen.

## Consequences
What this makes easy, what it makes hard, and what would have to change to
revisit it.
```

## Rules

- Immutable. A decision that changes gets a **new** ADR that supersedes the old
  one; the old file stays. The history of why you changed your mind is itself
  worth writing about.
- Short. Half a page. An ADR nobody writes because it feels like an essay is
  worth nothing.
- Only for decisions that were genuinely open. Using ROS 2 Humble is not a
  decision — the platform dictates it.

## Expected first ADRs

1. Object detector choice (YOLOX vs. alternatives, incl. licensing)
2. SLAM backend (RTAB-Map vs. `slam_toolbox`)
3. Inference runtime (PyTorch vs. ONNX Runtime vs. TensorRT)
4. Whether to add a 3D LiDAR
5. How detections reach the navigation stack (costmap layer vs. behaviour)
6. Odometry fusion strategy for a balancing wheeled biped
