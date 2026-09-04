# `scripts/` — operational helpers

Small utilities that are run by hand, not part of the ROS graph. Kept out of
`src/` so they do not become accidental dependencies of the runtime system.

Anticipated:

| Script | Purpose |
|---|---|
| `record_bag.sh` | Record the standard topic set with MCAP storage and a consistent name. |
| `replay_bag.sh` | Replay with `use_sim_time` and the right clock setup. |
| `deploy_to_robot.sh` | rsync the workspace to the Jetson and rebuild. |
| `build_engine.sh` | ONNX -> TensorRT **on the robot** (engines are device-locked). |
| `benchmark_inference.py` | Latency and throughput per backend on the Orin. |
| `extract_frames.py` | Bag -> images for annotation. |

## Conventions

- `set -euo pipefail` in every shell script. A deploy script that keeps going
  after a failed build is worse than one that crashes.
- No hardcoded paths or IP addresses — take them from arguments or a `.env`
  that is gitignored.
- Anything run repeatedly during experiments belongs here rather than in shell
  history. When a command's exact form matters for reproducing a result, the
  script *is* the documentation.
