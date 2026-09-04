# `sim/` — simulation assets

Worlds and scenes for developing without the robot. DDT supports both Gazebo and
Webots through
[`TITA_ROS2_Control_Sim`](https://github.com/DDTRobot/TITA_ROS2_Control_Sim),
which is pulled into `external/`. Only assets specific to this thesis live here.

| Directory | Contents |
|---|---|
| `gazebo/worlds/` | `.sdf` worlds — the indoor environments to be mapped. |
| `gazebo/models/` | Furniture, obstacles, and the objects the detector must recognise. |
| `webots/` | `.wbt` scenes, if the Webots path is used. |

## What simulation is and is not good for

Genuinely useful here:

- Nav2 tuning, behaviour trees, recovery behaviours.
- SLAM pipeline plumbing — frames, topics, launch composition.
- Testing the locomotion bridge without risking the robot.
- Reproducible navigation experiments with exact ground truth, which is hard to
  obtain in a real room.

Not useful:

- Detector accuracy. Synthetic images do not transfer, and mAP measured in
  simulation says nothing about mAP in your lab. Train and evaluate the detector
  on real data.
- Locomotion dynamics. A balancing wheeled biped is exactly the kind of system
  where the sim-to-real gap is largest.

Be explicit in the thesis about which results are simulated and which are from
hardware. Examiners ask.

## Build a world that resembles the real room

If the mapping evaluation happens in one specific corridor or lab, model that
space approximately. It makes simulation results comparable to hardware results
instead of merely adjacent to them.
