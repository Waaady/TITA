# Risk register

**Created 2026-09-04.** Review it when planning, and update the status column as
risks are retired or materialise.

The point of writing these down is not pessimism. It is that the cheap moment to
discover a blocker is month 1, not month 4 — and that a thesis which names its
risks and shows how it handled them reads better than one that pretends there
were none.

## Overview

| # | Risk | Impact | Likelihood | Status |
|---|---|---|---|---|
| R1 | Vendor SDK is a black box and partly non-functional | High | **High** | open |
| R2 | Cannot command the robot from our own code | **Critical** | Medium | **narrowed 2026-09-18** — input path known (`command/user/command`, `LocomotionCmd`); `cmd_twist` confirmed as an output, off limits. Converter not yet written, "robot moves one metre" milestone still open |
| R3 | Nav2 tuning on a balancing platform | High | High | open |
| R4 | Mapping *while* driving is harder than map-then-navigate | Medium | High | open |
| R5 | `camera/point_cloud` has no publisher | Medium | **Confirmed** | open |
| R6 | Odometry drift degrades SLAM | Medium | High | open |
| R7 | Time budget vs. learning curve | High | Medium | open |
| R8 | Loss of robot access | High | Medium | mitigated by bags |

---

## R1 — Vendor SDK is a black box and partly non-functional

**Evidence.** `obstacle_detector_node` runs and waits for
`perception/camera/point_cloud`, which nothing publishes — DDT's own obstacle
detection is therefore not working as delivered. The camera driver node and
`controller_manager` were both absent from `ros2 node list` while their topics
existed. The development manual is Chinese-only and thin; the API page does not
even enumerate topics completely.

**Why it matters.** The community is tiny — the official development manual
repository has single-digit stars. When you hit a problem there will be **no
Stack Overflow answer**. This is qualitatively different from working with a
TurtleBot, where every problem has been solved a thousand times. You are first in
line.

**Mitigation.**
- Treat [hardware/topic-map.md](hardware/topic-map.md) as the real reference and
  keep extending it — you are writing the documentation that does not exist.
- Budget time explicitly for reverse engineering. It is not wasted time; it is a
  contribution, and it belongs in the thesis.
- Open a support channel with DDT early, before you urgently need it.
- Record what you learn immediately. You will not remember why something worked.

---

## R2 — Cannot command the robot from our own code

**The critical-path risk.** Everything else is decoration if the robot cannot be
driven from a node we write.

**Settled 2026-09-18:** `command/manager/cmd_twist` is the command manager's
**output** (`command_manager_node` publishes, `hw_broadcaster_node`
subscribes). It must never be published to from our side. The input is the
documented `command/user/command` with `LocomotionCmd`, so the bridge is a
Twist → LocomotionCmd **converter**. See
[hardware/topic-map.md](hardware/topic-map.md).

Remaining unknowns:

- The exact `LocomotionCmd` fields and semantics
  (`ros2 interface show tita_locomotion_interfaces/msg/LocomotionCmd`).
- The manual says the robot only accepts API commands after a human brings it to
  standing with the **remote controller** and selects *use-sdk mode*. Whether
  that can be done programmatically, and whether it survives a restart, is
  unknown. If a person must press a button before every autonomous run, that
  constrains every experiment. `locomotion/body/fsm_mode` should show the state.

**Mitigation.** Write the converter next, with a watchdog and a hard velocity
cap from day one.

Milestone to aim for: *a node we wrote makes the robot roll one metre and stop.*
Nothing else needs to work for that. A nasty surprise here is survivable in month
1 and not in month 4. Constantin will decide when to hand over control from the
remote — e-stop in reach, clear floor, remote always able to override.

---

## R3 — Nav2 tuning on a balancing platform

Nav2 assumes the base tracks velocity commands reasonably well. A balancing
wheeled biped:

- cannot hold an exact zero velocity,
- has coupled pitch and translation dynamics (it leans to accelerate),
- changes footprint with stand height,
- may be unsafe performing the default recovery behaviours (spin in place,
  back up).

**This is where time disappears.** Controller tuning is empirical and slow.

**Mitigation.** Start in simulation, where a failed parameter costs nothing. Keep
velocity limits conservative until the watchdog and e-stop are verified on
hardware. Validate each recovery behaviour individually in a clear area before
enabling it. Consider a conservative worst-case footprint rather than a dynamic
one.

---

## R4 — Mapping while driving is harder than map-then-navigate

The stated goal is mapping *while* driving autonomously. That means SLAM runs in
mapping mode while Nav2 plans on a map that is changing underneath it — a
different and harder problem than navigating in a finished map.

**Mitigation: decouple, and stage it.**

| Stage | What | Difficulty |
|---|---|---|
| 1 | Map by teleop, then navigate autonomously in the finished map | achievable |
| 2 | SLAM running during autonomous driving | stretch goal |

Stage 1 is already a complete thesis result. Treat stage 2 as the bonus, not the
baseline, and the project stays deliverable either way.

---

## R5 — `camera/point_cloud` has no publisher

**Confirmed**, not merely suspected: `Publisher count: 0`. The stereo depth
computation is not running. This blocks phase 7 of the
[object detection walkthrough](guides/object-detection-pipeline.md) — 2D
detections cannot be given a position in the room without depth.

**Mitigation.** Two independent routes, so this is unlikely to be fatal:
- RTAB-Map can consume **stereo image pairs directly** and compute depth itself,
  so SLAM does not depend on this topic.
- `stereo_image_proc` can produce the disparity and point cloud ourselves from
  `image/left` and `image/right`, both of which do publish.

Still worth understanding *why* it is missing — the answer probably also explains
the missing camera driver node.

---

## R6 — Odometry drift degrades SLAM

Wheel odometry on a balancing robot is unreliable: the robot leans to accelerate,
so wheel rotation does not correspond to body translation, and every balance
correction adds slip. SLAM quality is bounded by odometry quality.

**Mitigation.** Fuse wheel odometry with the IMU (`robot_localization` EKF)
*before* tuning any SLAM parameters — doing it the other way round wastes a lot
of time. Consider trusting visual-inertial odometry over wheel odometry here.

Measure the drift early: drive a square, see how far from the start the robot
believes it is. That is a small, clean experiment and produces a number for the
thesis.

---

## R7 — Time budget vs. learning curve

A bachelor thesis timeline, with ROS 2, Nav2, SLAM and a deep-learning
deployment pipeline all being learned at the same time, on an unusual robot with
poor documentation.

**Mitigation.**
- Define the minimum viable demo early and protect it (see below).
- Work in the phases of the walkthrough; each one is independently testable.
- Use bags relentlessly — most work does not need the robot.
- Keep the balancing/SLAM investigation proportionate. It is a
  [secondary observation](../README.md#secondary-observation-not-the-objective),
  not the objective, and it is exactly the kind of interesting side road that
  eats a thesis.

---

## R8 — Loss of robot access

Shared lab hardware, hardware faults, other users, a battery that stops holding
charge. Recorded experiments cannot be repeated if the robot is unavailable.

**Mitigation — already in place, keep doing it.** Record bags early and often,
covering more than you currently need. A bag lets development continue with no
robot at all, and it is the only artefact of a physical run that survives.

Keep a backup of `data/bags/` outside the repository: bags are gitignored, so
**git is not backing them up**.

---

## The scope safety net

The single most effective mitigation across all of the above: **define a minimum
viable demo early and protect it.**

> TITA drives autonomously from A to B through a previously mapped corridor and
> avoids a person detected by YOLOX.

That is achievable, demonstrable, and already covers all three building blocks.
Everything beyond it — simultaneous mapping, semantic behaviours, 3D map
quality — is upside.

And a point worth remembering when something does not work: **a bachelor thesis
does not require a flawlessly working robot.** It requires a well-executed,
well-documented investigation. "I built the stack, got mapping working,
integrated Nav2, and here is a rigorous analysis of where it fails and why" is a
good thesis — sometimes better than one where everything happened to work.

That is why [experiments/](experiments/) matters more than it currently looks.
