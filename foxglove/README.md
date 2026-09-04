# `foxglove/` — visualisation

Foxglove is the primary visualisation and debugging tool for this project. It
replaces the usual RViz + rqt combination for three reasons that matter here:

1. It runs on your Windows laptop and talks to the Jetson over WebSocket. RViz
   over the network needs a full ROS installation on the viewing machine and a
   working DDS discovery across the WLAN — both are painful.
2. It opens the MCAP bags in [`../data/bags/`](../data/bags/) natively, with a
   scrubbable timeline. Debugging a mapping run by scrubbing back and forth
   through the recording is far more effective than rerunning the robot.
3. Layouts are JSON and can be committed, so a figure in the thesis can be
   regenerated exactly.

## Contents

| Directory | Contents |
|---|---|
| `layouts/` | Exported Foxglove layouts (`.json`). Commit them — a layout is part of how a result was produced. |
| `config/` | `foxglove_bridge` parameters, notably the topic whitelist. |

## The two modes

### Live — robot running

On the Jetson:

```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

In Foxglove: *Open connection* -> `ws://<jetson-ip>:8765`.

### Offline — replaying a recording

Record with MCAP storage (see [`../data/README.md`](../data/README.md)), then
just drag the `.mcap` file into Foxglove. No ROS, no bridge, no robot. This is
where most of the perception and SLAM debugging should happen.

## Bandwidth: the thing that will bite you

Two stereo cameras plus point clouds over WLAN will saturate the link, the
bridge will lag behind, and you will conclude that your node is slow when it is
actually the transport. Before blaming any algorithm:

- **Whitelist topics** in the bridge rather than subscribing to everything.
  `foxglove_bridge` takes a `topic_whitelist` regex parameter; keep the list in
  `config/` per use case (mapping vs. detection debugging).
- **Use compressed image transport.** Send `.../compressed`, never raw images,
  over the network.
- **Downsample point clouds** for visualisation. You do not need every point to
  see whether the map looks right.
- Remember that visualisation load lands on the Orin's CPU, competing with
  inference. A latency number measured while streaming everything to Foxglove is
  not the number that belongs in the thesis.

## Layouts worth building

| Layout | Panels | Used for |
|---|---|---|
| `mapping.json` | 3D (TF, point cloud, occupancy grid), Plot (odometry drift), Log | Building and checking maps |
| `detection.json` | Image with detection overlay, 3D with `Detection3DArray` markers, Plot (inference latency) | Tuning the detector and its 3D projection |
| `locomotion.json` | Plot: commanded `cmd_vel` vs. measured odometry velocity, side by side | Validating [`tita_locomotion_bridge`](../src/tita_locomotion_bridge/) — the fastest way to catch a sign or unit error |
| `navigation.json` | 3D (costmaps, global/local plan), State transitions (Nav2 behavior tree), Log | Debugging why the robot chose a path |

The `locomotion.json` one is worth building first. Plotting commanded against
measured velocity immediately exposes the inverted-yaw and wrong-unit bugs that
are otherwise discovered by watching the robot drive into a wall.

## Uploading to a Foxglove project

Only needed for sharing runs with a supervisor. The official tool is
[`foxglove-cli`](https://github.com/foxglove/foxglove-cli). It is an operational
tool, not a project dependency — it belongs in [`../scripts/`](../scripts/) and
must **not** go into `requirements.txt`.

The API token is a secret: keep it in the gitignored `.env`, never in a script
or a layout file.
