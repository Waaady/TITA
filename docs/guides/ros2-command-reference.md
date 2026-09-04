# ROS 2 command reference

The commands actually used on this project, with what they are good for and the
traps that come with them. Not a complete ROS 2 reference — a working one.

Unless stated otherwise these run **on the robot**, over SSH.

---

## Finding out what exists

```bash
ros2 node list                 # which programs are running
ros2 topic list                # which channels exist
ros2 topic list -t             # ...with message types
```

**Trap:** a topic appears in `ros2 topic list` if it has a publisher **or** a
subscriber. Its presence does **not** mean data is flowing. This project has a
concrete example: `perception/camera/point_cloud` is listed, but nothing
publishes it — only `obstacle_detector_node` sits there waiting.

`ros2 node list` can also be incomplete depending on what is running at the
moment. Do not treat either list as the whole truth.

---

## Finding out what is real

```bash
ros2 topic hz /tita3037072/perception/camera/image/left
```

Measures the actual message rate. **This is the honest test** — if a sensor is
dead, this is where you find out. `Ctrl+C` to stop.

A `WARNING: topic ... does not appear to be published yet` at the start is
normal; it is printed before the first message arrives.

Reading the output: `average rate` is the mean, but look at `min` and `max` too.
On this robot the images average ~42 Hz while individual gaps range from 12 ms to
74 ms — i.e. they arrive irregularly. That jitter is why a detector node must
always take the newest frame instead of assuming a steady tick.

```bash
ros2 topic info /tita3037072/perception/camera/point_cloud --verbose
```

The single most useful diagnostic command. It reports:

- **`Publisher count`** — zero means nobody is sending. Case closed.
- **`Subscription count`** and the subscribing node names.
- **The QoS profile** of each endpoint.

The QoS part matters more than it looks. A publisher using `BEST_EFFORT` and a
subscriber using `RELIABLE` will **never connect**, even with a matching topic
name and type — and neither side reports an error. When a subscription silently
receives nothing, check this first.

```bash
ros2 topic echo /tita3037072/system/status --once
```

Prints one message and exits. `--once` matters: without it, a camera topic will
flood your terminal.

Note this robot's diagnostics live on `system/status`, **not** on the usual
`/diagnostics`.

---

## Recording

```bash
timeout -s INT 60 ros2 bag record -o indoor_run_02 \
  /tita3037072/perception/camera/image/left \
  /tita3037072/perception/camera/info/left \
  /tf /tf_static
```

Piece by piece:

| Part | Why |
|---|---|
| `timeout -s INT 60` | `ros2 bag record` has no duration limit of its own. This sends the same signal as `Ctrl+C` after 60 s, so the file closes cleanly. |
| `-o <name>` | Output directory. Must not already exist. |
| topic list | Explicit is better than `-a` (record everything), which will fill the disk. |

**Always record `/tf` and `/tf_static`.** Without them the bag is useless for
anything involving 3D or coordinate frames, and you cannot add them afterwards.

**Watch the output.** rosbag2 prints a `Subscribed to topic '...'` line for every
topic it actually finds. A topic you listed but that does not appear in those
lines was **not recorded** — that is how the missing point cloud was discovered
here.

**Check the space first** (`df -h ~`). Raw images are large: ~53 MB/s on this
robot, so roughly 3.2 GB per minute.

### MCAP vs. sqlite3

The default storage is `sqlite3`, producing a `.db3` file. Foxglove opens those,
as long as the message types are ROS standard ones.

If `ros-humble-rosbag2-storage-mcap` is installed, prefer MCAP:

```bash
ros2 bag record --storage mcap --storage-preset-profile zstd_fast -o run ...
```

**Do not use `--compression-mode file` with MCAP.** It produces `.mcap.zstd`,
which Foxglove cannot open. `--storage-preset-profile zstd_fast` compresses
*inside* the file instead and keeps it readable.

---

## Inspecting and replaying a bag

```bash
ros2 bag info indoor_run_01
```

Check three things: the duration, that **every** expected topic is listed, and
that each has a message count greater than zero.

```bash
ros2 bag play data/bags/indoor_run_01
ros2 bag play data/bags/indoor_run_01 --loop     # repeat forever
ros2 bag play data/bags/indoor_run_01 -r 0.5     # half speed
```

Replaying publishes the recorded messages onto the same topics as if the robot
were running. This is how development happens: a bag is reproducible, a physical
experiment is not.

```bash
ros2 bag convert -i old_bag -o convert.yaml       # e.g. db3 -> mcap
```

---

## Frames

```bash
ros2 run tf2_tools view_frames
```

Produces a PDF of the complete transform tree. Run it when you need to know how
sensor frames relate to `base_link` and `map`.

---

## Parameters

```bash
ros2 param list                     # all nodes and their parameters
ros2 param dump /<node>             # one node's parameters as YAML
ros2 param get /<node> <name>
```

Driver nodes often expose the sensor model, serial number or firmware version
here — one of the few ROS-side routes to actual hardware identity.

---

## Running things

```bash
ros2 run <package> <executable>
ros2 launch <package> <launch_file>
ros2 launch tita_bringup sdk_launch.py     # the TITA SDK
```

`ros2 run` starts one node; `ros2 launch` starts a whole configured set.

Note: launching the TITA SDK is not sufficient on its own. The robot only accepts
API commands after you bring it to standing with the remote controller and select
**use-sdk mode**.

---

## Companion commands (not ROS)

Used constantly alongside the above.

| Command | Purpose |
|---|---|
| `ssh robot@<address>` | Connect. Everything typed afterwards runs **on the robot**. |
| `exit` or `Ctrl+D` | Disconnect. `Enter ~ .` forces it if the session hangs. |
| `scp -r robot@<addr>:~/bag C:\...\data\bags\` | Copy files. Runs **on the laptop**, not inside the SSH session. |
| `df -h ~` | Free disk space — before every recording. |
| `du -sh <dir>` | How big did that get? |
| `nohup <cmd> > log 2>&1 &` | Keep a command running after logout, without tmux. |
| `sqlite3 bag_0.db3 ".tables"` | A `.db3` bag is an ordinary SQLite database — you can look inside it. |

**Which machine am I on?** Look at the prompt: `robot@...$` is the robot,
`PS C:\...>` is your laptop. Or ask: `whoami`, `hostname`, `pwd`.

---

## The three traps worth memorising

1. **QoS mismatch** — subscriber gets nothing, no error. Cameras publish
   `BEST_EFFORT`; a default subscriber is `RELIABLE`. Use the sensor QoS profile.
2. **Topic exists ≠ data flows** — always confirm with `ros2 topic hz`.
3. **Namespace is per robot** — `/tita3037072` is this robot's serial. Pass it as
   a launch argument, never hardcode it.
