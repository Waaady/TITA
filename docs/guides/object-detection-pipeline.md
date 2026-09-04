# Walkthrough: live object detection on TITA

Step by step, from an empty workspace to YOLOX running on the robot.

Written for someone new to ROS 2. Each step says what you are doing, **how you
know it worked**, and what usually goes wrong. Do not skip ahead — every step
exists because the next one is much harder to debug without it.

## The idea in one picture

```
  camera image ──▶ YOLOX ──▶ 2D boxes ──┐
                                         ├──▶ 3D object positions ──▶ navigation
  point cloud ───────────────────────────┘
```

Two things to note before starting:

- **Only the left camera is used for detection.** Detection needs one image.
  The second camera exists to measure distance, and TITA already computes that
  for you and publishes it as `perception/camera/point_cloud`. Running the
  detector on both images doubles the cost for nothing.
- **The detector runs on the robot's Jetson, not on your laptop.** A raw camera
  image is ~2.7 MB; at 60 Hz that is far more than WiFi can carry. Only the
  results (a few hundred bytes) travel over the network.

---

## Phase 0 — Prerequisites

Before anything else, confirm the basics work.

```bash
ssh robot@<address>                       # see docs/hardware/robot-access.md
ros2 node list
ros2 topic hz /tita3037072/perception/camera/image/left
```

**Done when:** `ros2 topic hz` reports a steady rate (roughly 60 Hz).

**If it reports nothing:** the camera is not publishing. Either the SDK is not
running, or nothing has started the camera. Fix this now — everything below
assumes real image data. A topic showing up in `ros2 topic list` does *not*
mean data is flowing; only `ros2 topic hz` proves that.

Remember the namespace `/tita3037072` is this robot's serial number. Never
hardcode it — pass it as a launch argument.

---

## Phase 1 — Record a bag

A *bag* is a recording of all sensor data that can be replayed exactly. This is
the single most valuable thing you will produce in this phase, because a bag can
be replayed a hundred times identically and a physical experiment cannot.

### Where a bag comes from

Three things are easy to confuse:

| | What it is | Its job |
|---|---|---|
| **rosbag2** (`ros2 bag record`) | built into ROS 2 | **records** — the camcorder |
| **MCAP** | a file format | **stores** — like MP4 for video |
| **Foxglove** | an application | **plays back** — the video player |

`ros2 bag record` is an ordinary ROS node. It subscribes to topics like any
other node and writes what arrives to a file. **Foxglove is not involved in
recording at all.** MCAP was designed by Foxglove and is now a standard rosbag2
storage backend, which is why Foxglove can open the file directly — convenient,
but not required. `ros2 bag play` works just as well.

You run the recording **on the robot**, over SSH. Recording from your laptop
would pull all image data across WiFi, which is exactly the bandwidth problem
described above.

### Check disk space first

Raw images are big: ~2.7 MB per frame at 60 Hz is roughly **160 MB per second**,
so three minutes would be about 29 GB — plus the point cloud. That can fill the
Jetson's disk.

```bash
df -h
```

Two ways to keep it manageable, and you should use both:

- **Compress** with `--storage-preset-profile zstd_fast`.
- **Record short clips.** 30 seconds is plenty for phases 3–6. Record a longer
  run later, once you know the pipeline works and what you actually need.

> **Do not use `--compression-mode file` with MCAP.** It produces a `.mcap.zstd`
> file that **Foxglove cannot open** — you would have to decompress it first,
> which defeats the drag-and-drop workflow. The `zstd_fast` preset compresses
> *inside* the MCAP file instead, chunk by chunk, so the result stays a valid
> `.mcap`.
>
> `zstd_fast` rather than `zstd_small` on purpose: the SDK is running on the same
> Orin, and the stronger setting costs noticeably more CPU while recording. The
> size difference is modest; dropped frames are not.

### Record

Start `tmux` first so the recording survives a WiFi dropout:

```bash
tmux new -s rec
timeout -s INT 30 ros2 bag record \
  --storage mcap \
  --storage-preset-profile zstd_fast \
  -o indoor_run_01 \
  /tita3037072/perception/camera/image/left \
  /tita3037072/perception/camera/info/left \
  /tita3037072/perception/camera/point_cloud \
  /tf /tf_static
```

Drive the robot through the room past the objects you care about.

`ros2 bag record` has no built-in duration limit. `timeout -s INT 30` sends the
same signal as `Ctrl+C` after 30 seconds, so the file is closed cleanly. Pressing
`Ctrl+C` yourself does exactly the same thing.

The 30 seconds start immediately — have the robot moving, or you record half a
minute of standing still.

Check the result before recording more:

```bash
du -sh indoor_run_01
ros2 bag info indoor_run_01
```

**Always include `/tf` and `/tf_static`.** A bag without them cannot be used for
the 3D work in phase 7, and you will not want to re-record.

### Copy it to your laptop

The file is on the Jetson. From your laptop:

```powershell
scp -r robot@<address>:~/indoor_run_01 C:\Users\const\Documents\TITA\data\bags\
```

Rename it by date and scenario: `2026-09-11_lab_corridor_01`. Note the
calibration and software commit that were active — a bag whose provenance is
unknown cannot support a claim in the thesis.

**Done when:** `ros2 bag info <bag>` lists all five topics with a plausible
message count.

---

## Phase 2 — Replay the bag on your laptop

From here on you work offline. No robot needed.

```bash
ros2 bag play data/bags/<bag>          # terminal 1
ros2 topic hz /tita3037072/perception/camera/image/left   # terminal 2
```

Then open the `.mcap` file directly in Foxglove and look at the images. See
[`foxglove/README.md`](../../foxglove/README.md).

**Done when:** you can see the recorded camera images in Foxglove and scrub
through the timeline.

You now have a reproducible test fixture. Every change from here on can be
tested against exactly the same input.

---

## Phase 3 — A node that only receives images

Do not add YOLOX yet. Write the smallest possible node in
[`src/tita_perception/`](../../src/tita_perception/) that subscribes to the
image topic and prints the image dimensions.

This step exists to isolate the one mistake that costs beginners a full day.

### The QoS trap

QoS ("quality of service") decides *how* messages are delivered. Think of post:

- **RELIABLE** — registered mail. Redelivered until it arrives.
- **BEST_EFFORT** — a postcard. Arrives or does not, never resent.

Cameras send postcards: at 60 Hz a lost frame does not matter. But a subscriber
uses RELIABLE **by default**. Publisher and subscriber then do not match, and
you receive **nothing at all** — no error, no warning, no callback. The node
runs, the topic exists, and nothing happens.

Use the sensor QoS profile (`qos_profile_sensor_data` in `rclpy`).

### Converting the image

A ROS image is not a normal image. `cv_bridge` converts it into a NumPy array,
which is what OpenCV and YOLOX work with.

**Done when:** replaying the bag makes your node print image dimensions at a
steady rate.

**Only continue once this works.** Debugging QoS *and* a neural network at the
same time is miserable.

---

## Phase 4 — YOLOX on single images, without ROS

Still no ROS. Export a handful of frames from the bag to `.png` and run YOLOX on
them in a plain Python script in [`perception/`](../../perception/), starting
from the pretrained COCO weights.

Look at the output images. Are the boxes in sensible places?

### Two silent mistakes to check here

**Channel order.** There is `rgb8` and `bgr8` — red and blue swapped. Check what
TITA publishes. Swapped channels produce no error, just worse detections.

**Normalisation.** Most networks rescale pixel values to 0–1. **YOLOX by default
does not.** If you normalise "as usual", you get garbage. Whatever preprocessing
you use here must later be reproduced exactly in the ROS node.

**Done when:** you have output images with correct boxes and you have written
down your exact preprocessing steps.

---

## Phase 5 — Put the two halves together

Now extend the node from Phase 3 with the detector from Phase 4. Run it against
the replayed bag.

### Always take the newest frame

If the camera delivers 60 frames per second and YOLOX manages 30, frames pile up
in a queue and you end up detecting on images that are two seconds old. On a
robot moving at 3 m/s that is six metres wrong.

Set the queue depth to **1** and deliberately drop frames. An up-to-date
detection at 15 Hz is worth more to navigation than a stale one at 60 Hz.

You do not need 60 Hz. Throttling to 10–15 Hz saves a lot of compute.

**Done when:** the node produces detections continuously while the bag replays,
without falling behind.

---

## Phase 6 — Publish results and see them in Foxglove

Publish detections as `vision_msgs/Detection2DArray`. Use this standard message
rather than inventing your own — Foxglove and Nav2 understand it directly.

For visualisation, do **not** draw boxes into the image and republish it. Send
`foxglove_msgs/ImageAnnotations` instead: you send only coordinates and Foxglove
draws the rectangles over the image itself. Re-encoding JPEGs costs the Jetson
real frames per second.

Save the layout to [`foxglove/layouts/detection.json`](../../foxglove/layouts/).

**Done when:** boxes appear over the live image in Foxglove.

---

## Phase 7 — From 2D to 3D

A box in the image is not yet a position in the room. Combine the detection with
`perception/camera/point_cloud` to get the distance, then transform it into the
`map` frame using TF.

This is where most of the real error comes from — document your assumptions, they
belong in the thesis.

**Prerequisite:** a working `map` → `odom` transform, i.e. mapping has to run
first. Build the map before the 3D detection.

**Done when:** you publish `vision_msgs/Detection3DArray` and the markers appear
in the right place in Foxglove's 3D panel.

---

## Phase 8 — Onto the robot

Only now does the code move to the Jetson.

1. Export the model: PyTorch → ONNX → TensorRT. TensorRT is NVIDIA's optimiser;
   it compiles the network for this specific chip.
2. **Build the TensorRT engine on the robot.** An engine built on your
   workstation's GPU will not load on the Jetson. See
   [`models/README.md`](../../models/README.md).
3. Verify the exported model still produces the same output as PyTorch on a
   fixed test image. This catches the most common deployment failure.

**Done when:** the detector runs live on the robot and you can see the results
in Foxglove from your laptop.

Note: TITA publishes no compressed image topics. To watch images live over WiFi
you must start `image_transport republish` yourself — raw images will saturate
the link, and you will blame your node for what is actually the network.

---

## Phase 9 — Measure, for the thesis

Now the part that produces results worth writing about.

Benchmark all three inference paths on the Orin — PyTorch, ONNX Runtime,
TensorRT — measuring latency and throughput. Evaluate detection quality (mAP) on
your own annotated data.

Measure with visualisation **switched off**. Streaming to Foxglove costs Orin CPU
and would make your latency numbers wrong.

Record every run in [`docs/experiments/`](../experiments/): date, commit hash,
model artifact, bag used, result.

---

## Order of work, summarised

| Phase | You are proving |
|---|---|
| 0 | Data actually flows |
| 1–2 | You have a reproducible recording |
| 3 | ROS plumbing works (QoS!) |
| 4 | The detector works |
| 5 | Both together, fast enough |
| 6 | You can see what is happening |
| 7 | Detections have a position in the room |
| 8 | It runs on the robot |
| 9 | You have numbers to write up |

The pattern throughout: **isolate one unknown at a time.** Every phase is easy to
debug on its own and very hard to debug in combination with the next one.
