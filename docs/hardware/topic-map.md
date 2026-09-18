# TITA topic map

Captured from the real robot (`ros2 node list`, `ros2 topic list -t`), cross-checked
against the official manual
(<https://tita-development-manual-uc.readthedocs.io/zh-cn/latest/>, Chinese only).

**Robot namespace: `/tita3037072`** — derived from the robot's serial number. It
is not stable across machines: never hardcode it. Take it from a launch
argument or the `ROBOT_NAMESPACE` environment variable.

## Sensors

| Topic (under `/tita3037072`) | Type | Hardware | Rate |
|---|---|---|---|
| `perception/camera/image/left` | `sensor_msgs/Image` | stereo camera, colour, **960x600 `bgr8`** | 60 Hz documented, **~42 Hz measured** |
| `perception/camera/image/right` | `sensor_msgs/Image` | stereo camera, colour | |
| `perception/camera/info/{left,right}` | `sensor_msgs/CameraInfo` | stereo calibration | **~9.4 Hz measured** — 4x slower than images |
| `perception/camera/point_cloud` | `sensor_msgs/PointCloud2` | stereo depth | **no publisher** — see below |
| `perception/devices/face_point` | `sensor_msgs/PointCloud2` | **front-facing SPAD ToF** (manual) | |
| `perception/devices/neck_point` | `sensor_msgs/PointCloud2` | **neck-mounted SPAD ToF** (manual) | |
| `perception/devices/ultrawave` | `sensor_msgs/Range` | ultrasonic | |
| `perception/obstacle/point` | `sensor_msgs/PointCloud2` | obstacle sensor | |
| `perception/obstacle/distance_data` | `std_msgs/Float64` | obstacle distance | |
| `perception/detector/angle_data` | `std_msgs/Float64` | **slope detector** — incline angle, *not* object detection | |
| `imu_sensor_broadcaster/imu` | `sensor_msgs/Imu` | body IMU | |
| `joint_states` | `sensor_msgs/JointState` | 8 joints + wheels | |
| `chassis/odometry` | `nav_msgs/Odometry` | wheel/leg odometry | |
| `system/battery/{left,right}` | `sensor_msgs/BatteryState` | two hot-swap packs | |
| `system/status` | `diagnostic_msgs/DiagnosticArray` | **this is the diagnostics topic** — there is no `/diagnostics` | |

The "Hardware" column gives **functional roles**, translated from the manual.
Actual manufacturer, model and serial numbers are **not** obtainable from
topic names and have not yet been determined — see
[../status.md](../status.md), open question 5.

Naming trap: `perception/detector/angle_data` is a **slope detector**
(坡度检测), nothing to do with our object detector.

### Camera details (measured from the 2026-09-04 bag)

- `image/left` is **raw, not rectified**: `rational_polynomial` distortion,
  8 coefficients, fx ≈ fy ≈ 479, principal point ≈ (479, 298), strong barrel
  distortion, ~118° horizontal FOV after undistortion. Frame
  `tita3037072/left_camera` on the image, `left_img_raw` on the CameraInfo.
- The manual claims the images are undistorted. **They are not.** Any angle or
  3D work must undistort first; a pinhole-only bearing is 14° off at the edge.
- CameraInfo `P` has a non-zero Tx (−71 → baseline ≈ 0.15 m if that is fx·b) —
  odd for the *left* camera of a stereo pair. Unverified.

### `point_cloud` has no publisher

`ros2 topic info --verbose` on 2026-09-04: `Publisher count: 0`,
`Subscription count: 1` — the subscriber is `obstacle_detector_node`
(`/tita3037072`, QoS RELIABLE), which sits waiting for data that never
arrives. The stereo depth computation is not running. DDT's own obstacle
detection is therefore non-functional as delivered.

Consequence for us: no depth from the vendor stack. Routes around it are
RTAB-Map's stereo mode (consumes left+right directly) or running
`stereo_image_proc` ourselves.

Note the subscriber's **RELIABLE** QoS — unusual for a point cloud. If a
publisher ever appears with BEST_EFFORT, the two will not connect.

## Command path

| Topic | Type | Role |
|---|---|---|
| `command/user/command` | `tita_locomotion_interfaces/LocomotionCmd` | the SDK entry point documented in the quickstart |
| `command/active/command` | `tita_locomotion_interfaces/LocomotionCmd` | active command source |
| `command/passive/command` | `tita_locomotion_interfaces/LocomotionCmd` | passive command source |
| `command/teleop/command` | `sensor_msgs/Joy` | remote controller |
| `command/manager/cmd_twist` | **`geometry_msgs/Twist`** | manual: "chassis motion **final** control command" |
| `command/manager/cmd_pose` | `geometry_msgs/PoseStamped` | |
| `command/manager/cmd_key` | `std_msgs/String` | |
| `locomotion/body/fsm_mode` | `std_msgs/String` | FSM state — read this to know whether the robot accepts SDK commands |

`command_manager_node` merges the active and passive command sources into one
output. **`cmd_twist` is plain `geometry_msgs/Twist`**, which is what Nav2
emits — so the conversion work in
[`tita_locomotion_bridge`](../../src/tita_locomotion_bridge/) may be far smaller
than originally assumed.

### Resolved 2026-09-18: `cmd_twist` is an **output** — never publish to it

`ros2 topic info --verbose` on the robot:

```
Publisher:    command_manager_node   (/tita3037072)   RELIABLE
Subscription: hw_broadcaster_node    (/tita3037072)   RELIABLE
```

`command_manager_node` *writes* `cmd_twist`; `hw_broadcaster_node` (the
hardware layer) reads it. Publishing there from our side would put two
publishers on one topic fighting each other. **Off limits.**

Consequence: the input path is the documented one, `command/user/command`
with `tita_locomotion_interfaces/LocomotionCmd`. The
[`tita_locomotion_bridge`](../../src/tita_locomotion_bridge/) is therefore a
**message converter** (Twist → LocomotionCmd), not a remap. Risk R2 in
[../risks.md](../risks.md) is narrowed to "implement the converter and prove
it moves the robot"; the architecture question is closed.

```
Nav2 ─Twist─▶ tita_locomotion_bridge ─LocomotionCmd─▶ command/user/command
                                                            │
                                                   command_manager_node
                                                            │ cmd_twist
                                                   hw_broadcaster_node ─▶ motors
```

Next read-only steps: `ros2 interface show tita_locomotion_interfaces/msg/LocomotionCmd`
(the fields the bridge must fill) and `ros2 topic info .../command/user/command --verbose`
(confirm `command_manager_node` subscribes there).

`hw_broadcaster_node` did not appear in the 2026-09-04 node list either —
further confirmation that list was partial.

## TITA Tower

`tower_msgs_bridge_node` is running and these topics exist:

| Topic | Type |
|---|---|
| `/tita3037072/tower/map_point` | `sensor_msgs/PointCloud2` |
| `/tita3037072/tower/odometry` | `nav_msgs/Odometry` |
| `/tower/mapping/cloud_colored` | `sensor_msgs/PointCloud2` |
| `/tower/mapping/odometry` | `nav_msgs/Odometry` |
| `/tower/navigation/cmd_vel` | `geometry_msgs/Twist` |

Per the manual, the **Tower is a sensor module containing a LiDAR, stereo
cameras, an IMU and RTK/GNSS**, and it produces a coloured 3D map plus
high-precision odometry. If one is physically attached to this robot, it changes
the mapping chapter substantially — it may already provide the SLAM that this
thesis was going to build.

**But the Tower's own sensor topics (`/tower/lidar/points`, `/tower/imu/data`)
are absent from the topic list.** That suggests the bridge node runs
unconditionally while no Tower is attached or powered. Verify:

```bash
ros2 topic info /tower/mapping/odometry --verbose   # any publishers?
ros2 topic hz /tower/mapping/odometry               # anything actually flowing?
```

Note also that the `/tower/*` topics sit at the **root**, outside the robot
namespace, while everything else is namespaced. Anything we write that consumes
them has to account for that asymmetry.

## Nodes seen

`ros2 node list` on 2026-09-04 (SDK state at the time unknown):

```
/tita3037072/battery_device_node
/tita3037072/command_manager_node
/tita3037072/robot_state_publisher
/tita3037072/teleop_command_node
/tita3037072/temperature_controller_node
/tita3037072/tower_msgs_bridge_node
/tita3037072/transform_listener_impl_...
```

Later, `obstacle_detector_node` was also seen (as the point-cloud subscriber)
but was not in this list. **No camera driver node and no `controller_manager`
appeared**, although their topics did. The list is therefore not the whole
truth — either it was captured in a partial SDK state, or those publishers
run as composed nodes inside another process. Which node publishes the camera
images is still open (status.md question 4).

## Missing / to check

- No LiDAR topic outside the Tower — consistent with stereo + ToF only.
- Some sensors run over **CANFD**, not ROS (see `TITA_CAN_Interface` upstream).
  A sensor absent from `ros2 topic list` is not necessarily absent from the robot.
- A topic appears in `ros2 topic list` if it has a publisher **or** a subscriber.
  Confirm real data with `ros2 topic hz` before assuming a sensor works.
