# `tita_mapping` — indoor SLAM

Builds and maintains the map of the environment. Two operating modes, and the
distinction matters for the thesis evaluation:

- **Mapping mode** — SLAM is running, the map is being built and refined.
- **Localisation mode** — a previously saved map is loaded and only the pose is
  estimated. This is what autonomous navigation runs in.

## Backend

Undecided; see the ADR in [`docs/adr/`](../../docs/adr/). Two candidates, both
available from apt on Humble:

| | `slam_toolbox` | `rtabmap_ros` |
|---|---|---|
| Input | 2D `LaserScan` | RGB-D / stereo + odometry |
| Output | 2D occupancy grid | 2D grid **and** 3D point cloud / mesh |
| Fit for TITA | needs `depthimage_to_laserscan` to fake a scan from ToF/stereo | native fit for the onboard stereo cameras |
| Loop closure | scan matching, very solid indoors | visual bag-of-words |

RTAB-Map is the more natural fit given TITA has no 2D LiDAR, and it produces the
3D map that makes for a much better thesis chapter. `slam_toolbox` is the safer
fallback and a good baseline to compare against — that comparison is itself a
result worth writing up.

## Prerequisite: odometry

SLAM quality is bounded by odometry quality. TITA is a wheeled biped, so its
wheel odometry drifts hard during balancing and any pitching motion. Plan on
fusing wheel odometry with the IMU in `robot_localization` (an EKF publishing
`odom` -> `base_link`) *before* tuning any SLAM parameters. Doing it in the
other order wastes a lot of time.

## Layout

- `config/` — backend parameters, EKF configuration, map-saver settings.
- `launch/` — `mapping.launch.py` and `localization.launch.py`, kept separate.
- `rviz/` — visualisation presets for mapping runs.
- `maps/` — small reference maps that belong to the repo. Full recorded maps
  from experiments go to `data/maps/` instead.

## Evaluation

Trajectory error against ground truth goes through `evo` (in
`requirements.txt`). Record every mapping run as a rosbag into `data/bags/` so
runs can be replayed and compared after parameter changes — you cannot rerun a
physical experiment, but you can rerun the bag a hundred times.
