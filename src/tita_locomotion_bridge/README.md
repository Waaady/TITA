# `tita_locomotion_bridge` — the vendor seam

Translates standard ROS navigation output into what the TITA SDK actually
accepts. This is the only package in `src/` that is allowed to depend on
`tita_locomotion_interfaces` from the vendor SDK. Isolating it here means the
whole rest of the stack can be developed and tested against simulation or bags
without the real robot.

## The mismatch

| | |
|---|---|
| Nav2 produces | `geometry_msgs/Twist` on `cmd_vel` |
| TITA consumes | `tita_locomotion_interfaces/msg/LocomotionCmd` on `command/user/command` (frame `cmd`) |

A wheeled biped also has state that a differential-drive `Twist` cannot express:
stand/crouch height, body pitch and roll, jump, and the transition between
balancing and quadruped-style modes. Those are commanded through this package
too, not smuggled into `Twist` fields.

## Responsibilities

- `cmd_vel` -> `LocomotionCmd` conversion, including unit and sign conventions.
  Verify the sign of yaw against the actual robot before trusting anything.
- Velocity, acceleration and jerk limiting. TITA does 3–5 m/s with the API
  unlocked; Nav2's default limits are not appropriate for a 24 kg machine that
  can move that fast indoors.
- Command timeout / watchdog: if the planner stops publishing, the robot must
  stop, not coast on the last command.
- Posture and mode commands (stand height, pitch), exposed as services or as
  messages from `tita_interfaces_thesis`.
- Passing through the e-stop from `tita_teleop_safety` with priority over
  everything else.

## Why C++

It sits in the control path with a hard latency budget. Also, the vendor
interfaces are C++-first.

## Testing

Test the conversion as a pure function first — given a `Twist`, assert on the
resulting `LocomotionCmd`. That test needs no robot and no ROS graph, and it
catches the sign and unit errors that are otherwise found by watching the robot
drive into a wall.
