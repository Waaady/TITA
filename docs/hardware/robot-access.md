# Connecting to TITA

Source: the official TITA development manual (Chinese only),
<https://tita-development-manual-uc.readthedocs.io/zh-cn/latest/> —
see *Quick Start* and *WIFI Portable Application*.

## Credentials

**Not recorded here.** This repository is public. The SSH user and password
and the hotspot password are the vendor defaults and are printed in the
manual's *Quick Start* and *WIFI Portable Application* pages linked above.

If the robot's password is ever changed from the default, it must not be
written into this repository either — keep it in the lab's own credential
store.

Set up SSH keys (below) so the password is needed once, not daily.

## Three ways in, three different addresses

The address depends on how you are physically connected. This is the part that
causes most of the confusion.

| Connection | Address | When to use |
|---|---|---|
| **USB-C cable** | `192.168.42.1` | First contact, flashing, recovery. Works with no network at all. |
| **Robot's own hotspot (AP mode)** | `10.42.0.1` | In the lab, robot driving, no infrastructure needed. |
| **Robot on your WiFi (client mode)** | assigned by your router | Normal development. The only mode where the robot has internet. |

```bash
ssh robot@192.168.42.1     # USB-C
ssh robot@10.42.0.1        # AP mode
ssh robot@<router-ip>      # client mode
```

### USB-C

The robot exposes a USB network adapter (RNDIS). On Windows it sometimes fails
to enumerate — the manual's FAQ lists reinstalling the USB network adapter
driver as the fix.

Also from the FAQ: **remove the flashing cable from the DBG port before powering
on.** Left connected, the robot boots into flashing mode and SSH will not come
up at all.

### AP mode

The robot broadcasts its own network with an SSID of the form `TITAxxxxxxx`
(suffix varies per robot). The password is the vendor default from the manual.
Join it from your laptop, then SSH to `10.42.0.1`.

### Client mode — joining your WiFi

```bash
sudo wifi-app -ap_off      # AP mode must be off first
sudo wifi-app -on          # then Ctrl+C to reach the menu, enter SSID + password
```

**AP mode and client mode are mutually exclusive.** This matters more than it
sounds: in AP mode the robot has no internet, so `apt install`, `pip install`
and `git clone` all fail. Do all installation work in client mode, then switch
to AP mode for experiments where you cannot rely on lab WiFi.

## Practical setup

### SSH keys

```bash
ssh-keygen -t ed25519                        # if you have no key yet
ssh-copy-id robot@10.42.0.1                  # or use the address you need
```

### SSH config

Put this in `~/.ssh/config` on your laptop so the three addresses become names:

```
Host tita-usb
    HostName 192.168.42.1
    User robot
Host tita-ap
    HostName 10.42.0.1
    User robot
Host tita
    HostName <ip on the lab network>
    User robot
```

Then simply `ssh tita`.

Because the same hostname can point at different addresses across modes, SSH
will complain about changed host keys when you switch. Give each mode its own
`Host` entry as above rather than fighting `known_hosts`.

### VS Code Remote-SSH

The most useful part of the setup: with the Remote-SSH extension you can open
the workspace **on the Jetson** and edit, build and debug there directly, with
a terminal that is already on the robot. That removes the sync step from the
edit-build-test loop entirely.

Note that VS Code's server process runs on the Orin and costs CPU and RAM.
Close it before taking latency measurements that go into the thesis.

## The robot shuts itself down when idle

Observed twice (2026-09-15, 2026-09-18): with the robot lying still and the
remote controller switched off or timed out, TITA powers itself off after a
while — a safety behaviour, not a fault. Both times it happened in the middle
of a package installation, once leaving `dpkg` interrupted
(`sudo dpkg --configure -a` repairs that).

For anything that takes more than a few minutes over SSH — apt installs,
`pip install pycuda`, `build_engine.sh` — **keep the remote controller on**
and touch it occasionally so it does not go to standby itself.

## Sanity checks

```bash
uname -a                    # confirms you are on the robot's Ubuntu, not your laptop
ros2 topic list             # confirms the ROS 2 graph is up
ros2 topic hz /<sensor>     # confirms sensors are actually publishing
```

## First-run checklist from the manual

The SDK quickstart, in order:

1. SSH into the robot.
2. `mkdir -p tita-sdk/src && cd tita-sdk/src`
3. Clone the SDK, `colcon build`, `source install/setup.bash`
4. `ros2 launch tita_bringup sdk_launch.py`
5. Use the **remote controller** to bring the robot to standing, then select
   **use-sdk mode**. The SDK does not take control until you do this.

Step 5 is easy to miss: launching the SDK is not enough — the robot only accepts
API commands after the mode is selected on the controller.

## What is missing on the robot as delivered

Found while deploying; all fixable once the robot is in client WiFi mode.

| Missing | Install |
|---|---|
| `git` | `sudo apt install git` |
| `rosdep` | `sudo apt install python3-rosdep` |
| `colcon` | `sudo apt install python3-colcon-common-extensions` |
| `tmux` | `sudo apt install tmux` |
| `ros-humble-rosbag2-storage-mcap` | `sudo apt install ros-humble-rosbag2-storage-mcap` |

Before any of these work, the expired ROS apt key has to be refreshed — see
[../guides/deploy-to-robot.md](../guides/deploy-to-robot.md), step 2.
