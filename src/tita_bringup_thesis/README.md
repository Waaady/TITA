# `tita_bringup_thesis` — system composition

Launch files only. This package owns the answer to "which nodes run, with which
parameters, on which machine". It contains no nodes of its own.

## Planned launch files

| File | Purpose |
|---|---|
| `robot.launch.py` | Everything that runs on the Jetson: sensors, locomotion bridge, perception, safety. |
| `mapping.launch.py` | Robot plus SLAM in mapping mode. Used to build a map. |
| `navigation.launch.py` | Robot plus localisation plus Nav2. The autonomy demo. |
| `sim.launch.py` | The same stack against Gazebo or Webots, with `use_sim_time:=true`. |
| `replay.launch.py` | Perception and mapping against a recorded bag, no hardware. |
| `foxglove.launch.py` | `foxglove_bridge` with the topic whitelist from [`foxglove/config/`](../../foxglove/config/). Kept separate so it can be left out of experiment runs — streaming everything costs Orin CPU and distorts latency measurements. |

## Distributed operation

Not everything has to run on the robot. Heavy visualisation (RViz), logging and
offline analysis belong on the workstation; the Jetson's 100 TOPS are for
inference. Keep `ROS_DOMAIN_ID` and the DDS configuration in `config/` so the
split is reproducible rather than tribal knowledge.

## Rules

- Every launch file must declare `use_sim_time` and pass it down consistently.
  Mixed clock sources are the single most common cause of "TF extrapolation
  into the future" errors.
- Parameters come from the owning package's `config/`, overridden here only when
  a specific composition needs a different value — do not copy whole parameter
  files.
- Each launch file should be runnable on its own and should fail with a clear
  message if a prerequisite (map file, model artifact, robot connection) is
  missing.
