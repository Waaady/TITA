# `src/` — ROS 2 packages

Colcon workspace source space. Only **our own** packages live here; upstream
code is pulled into `external/` via `vcs import` and is never committed.

## Dependency direction

Packages depend downwards only. If you find yourself wanting an upwards
dependency, the thing you need probably belongs in `tita_interfaces_thesis`.

```
              tita_bringup_thesis          (launch only, depends on everything)
                       |
      +----------------+----------------+-------------------+
      |                |                |                   |
tita_navigation   tita_perception   tita_mapping    tita_teleop_safety
      |                |                |                   |
      +----------------+----------------+-------------------+
                       |                                    |
                 tita_sensors                     tita_locomotion_bridge
                       |                                    |
              tita_description_thesis              (vendor SDK, external/)
                       |
              tita_interfaces_thesis
```

## Package roles

| Package | Build type | Role |
|---|---|---|
| `tita_interfaces_thesis` | `ament_cmake` | msg/srv/action definitions. No logic — interface packages must stay dependency-light or they poison everything downstream. |
| `tita_description_thesis` | `ament_cmake` | URDF/xacro for sensors we add and their mounting transforms. The single source of truth for frame names. |
| `tita_sensors` | `ament_cmake` | Driver bringup, time synchronisation, camera calibration. Everything above this assumes calibrated, timestamped, correctly framed data. |
| `tita_perception` | `ament_python` | YOLOX inference, tracking, 2D-to-3D projection. |
| `tita_mapping` | `ament_cmake` | SLAM configuration, map saving/loading, localisation mode. |
| `tita_navigation` | `ament_cmake` | Nav2 parameters, costmap layers, behavior trees. |
| `tita_locomotion_bridge` | `ament_cmake` (C++) | `cmd_vel` -> `LocomotionCmd`. C++ because it sits in the control loop. |
| `tita_teleop_safety` | `ament_cmake` | Manual override, deadman, e-stop. Must be able to preempt everything above it. |
| `tita_bringup_thesis` | `ament_cmake` | Launch files and composition only. No nodes of its own. |

## Conventions

- One responsibility per package. If a package needs a "utils" module shared
  with another package, that is a sign the boundary is wrong.
- Parameters in `config/*.yaml`, declared with descriptors and validated on
  startup. Nodes must fail loudly on a missing parameter, not fall back to a
  default that silently changes behaviour.
- Launch files are per-package (`launch/`) and composed in
  `tita_bringup_thesis`; a package's own launch file must be runnable on its
  own for debugging.
- Every package gets a `test/` directory. `colcon test` should stay green.
