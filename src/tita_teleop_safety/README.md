# `tita_teleop_safety` — manual override and emergency stop

A 24 kg machine that moves at up to 5 m/s indoors, near people, running code
written for a thesis. This package exists so that a human can always take it
back.

## Responsibilities

- **Deadman / enable**: autonomy is only allowed while an operator actively
  holds an enable input. Releasing it stops the robot. Fail-safe, not fail-open.
- **Mode arbitration**: manual teleop always wins over autonomous `cmd_vel`.
  A single mux node decides what reaches
  [`tita_locomotion_bridge`](../tita_locomotion_bridge/) — never let two nodes
  publish to the same command topic and hope for the best.
- **E-stop**: a software stop that is honoured with priority over every other
  command path.
- **Heartbeat**: loss of the operator link stops the robot rather than leaving
  the last command running.

## Non-negotiable

The physical e-stop on the robot is the real safety device. Nothing in this
package replaces it, and nothing here is safety-rated. This is an engineering
convenience layer on top of a hardware stop that must always be within reach
during experiments.

Test the stop path first, before the first autonomous run, and re-test it after
any change to the bridge. It is worth a paragraph in the thesis methodology
section — describing the safety procedure is normal practice for robot
experiments involving people.
