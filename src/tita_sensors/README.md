# `tita_sensors` — sensor bringup, synchronisation, calibration

The foundation layer. Everything above assumes data from here is calibrated,
correctly timestamped, and published in a declared TF frame. When perception or
mapping behaves strangely, suspect this package first.

## Scope

- Bringing up the onboard sensors (stereo cameras, SPAD ToF, ultrasonic, IMU)
  and any sensor added for the thesis.
- Rectification and stereo processing (`image_pipeline`).
- Time synchronisation between streams (`message_filters`, approximate or exact
  time policies).
- Storing and publishing calibration results.

## `calibration/`

Intrinsics, stereo extrinsics, and the sensor-to-`base_link` transforms.

These are **per-robot measurements**, not code. Commit them with the date and
the robot serial in the filename, and never overwrite an old calibration —
results in the thesis are only interpretable if you can say which calibration
produced them.

Extrinsics measured by hand belong in
[`tita_description_thesis`](../tita_description_thesis/) as URDF joints;
extrinsics obtained from a calibration procedure belong here, with the
description referencing them. Keeping one source of truth per transform avoids
the classic bug where two slightly different mount transforms coexist.

## Timestamping

The most common source of hard-to-diagnose SLAM and projection failure is a
timestamp problem, not an algorithm problem. Check early:

- Are all sensors on the same clock? `use_sim_time` must be consistent across
  every node when replaying bags.
- Is the driver stamping at capture time or at publish time? The difference is
  tens of milliseconds, which at 3 m/s is centimetres of error.
- Is the transport dropping frames? Check `ros2 topic hz` against the datasheet
  rate, not against what looks plausible.
