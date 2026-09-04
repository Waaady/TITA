# `tita_navigation` — Nav2 configuration

Autonomous driving on top of the map from [`tita_mapping`](../tita_mapping/) and
the detections from [`tita_perception`](../tita_perception/). Configuration and
plugins, not a reimplementation of Nav2.

## Layout

- `config/` — `nav2_params.yaml` (planner, controller, costmaps, recoveries),
  split per-context if the values diverge between simulation and hardware.
- `behavior_trees/` — Nav2 BT XML. Keep the default tree until you have a
  concrete reason to change it, then document the reason in an ADR.
- `launch/` — Nav2 bringup wired to this robot's topics and frames.
- `rviz/` — presets for navigation debugging.

## Costmap layers

The interesting part for the thesis. The detections from `tita_perception`
enter the local costmap as an additional layer, so that a person or a moving
obstacle influences planning even when the static map knows nothing about it.

Design question worth writing up: should detections go into the costmap as
inflated obstacles, or should they drive a separate behaviour (stop, yield,
follow)? The costmap route is simpler and composes with the existing planner;
the behaviour route allows semantics ("yield to people, ignore chairs").

## TITA-specific caveats

- **Footprint**: a wheeled biped's footprint changes with stand height. A single
  static footprint will be wrong in at least one posture — decide whether to use
  a conservative worst-case radius or to update the footprint dynamically.
- **Kinematics**: TITA is not a differential-drive robot. Its balancing dynamics
  mean it cannot execute arbitrary velocity profiles, and it cannot hold a
  perfect zero. Controller tuning (DWB or MPPI) has to respect that; expect the
  default acceleration limits to be wrong.
- **Recovery behaviours**: spin-in-place and back-up assume a stable base.
  Validate each recovery on hardware in a clear area before enabling it.
- **Speed**: keep velocity limits low until the locomotion bridge watchdog and
  the e-stop have both been verified on hardware.
