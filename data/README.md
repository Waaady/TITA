# `data/` — datasets, recordings, maps

Structure is committed, payload is not. Everything here is either large,
regenerable, or specific to one physical experiment.

| Directory | Contents |
|---|---|
| `raw/` | Untouched source data: exported images, downloaded datasets, raw annotation dumps. **Never edited in place** — treat it as read-only. |
| `interim/` | Intermediate products: extracted frames, filtered subsets, partial annotations. Disposable. |
| `processed/` | Training-ready data, COCO-format JSON, fixed train/val/test splits. Small manifest files (`*.json`, `*.yaml`) *are* tracked so splits stay reproducible. |
| `bags/` | `rosbag2` recordings from the robot. The most valuable thing in the repo — you can rerun a bag, you cannot rerun an experiment. |
| `maps/` | Saved occupancy grids (`.pgm` + `.yaml`) and 3D maps from mapping runs. |

## rosbags

Record early and record everything. A bag containing all sensor topics plus TF
lets perception, mapping and navigation be developed entirely offline, and lets
you rerun a parameter change against exactly the same input.

- Prefer **MCAP** storage (`--storage mcap`) over the default sqlite3: better
  compression, much better tooling, and it is Foxglove's native format — an
  MCAP bag opens by drag-and-drop, with no conversion step. See
  [`../foxglove/README.md`](../foxglove/README.md).
- Always include `/tf` and `/tf_static`. A bag without TF is nearly useless.
- Name bags `YYYY-MM-DD_location_scenario`, e.g. `2026-09-11_lab_corridor_walk`.
- Note the calibration and software commit that were active for each recording.
  A bag whose provenance is unknown cannot support a claim in the thesis.

## Splits

Fix the train/val/test split once and commit the manifest. Re-splitting between
experiments silently invalidates every comparison you have already made, and it
is the kind of mistake that is very hard to notice after the fact.
