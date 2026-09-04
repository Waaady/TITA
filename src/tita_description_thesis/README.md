# `tita_description_thesis` — robot description extensions

The vendor URDF lives in `external/TITA_Description` and is **not** modified.
This package extends it with the hardware added for the thesis and is the
**single source of truth for frame names**.

## Contents

- `urdf/` — xacro macros for added sensors and their mounts, plus a top-level
  xacro that includes the vendor description and attaches them.
- `meshes/` — visual and collision meshes for brackets and mounts (LFS-tracked).
- `config/` — joint limits or overrides that belong to the description.

## Why not fork the vendor URDF

Because it will be updated. Including it and layering on top keeps
`vcs pull external` from turning into a merge conflict every time DDT ships a
fix, and it keeps a clear line in the thesis between the platform as delivered
and the modifications that are your contribution.

## Frames

Follow REP-105 and REP-103:

```
map -> odom -> base_link -> <sensor>_link -> <sensor>_optical_frame
```

Camera frames need both a `_link` (x forward, z up) and an `_optical_frame`
(z forward, x right). Publishing detections in the wrong one of the two produces
results that look almost right, which is worse than obviously wrong.

Every frame name used anywhere in `src/` must be traceable to a joint declared
here. If a node hardcodes a frame string that does not appear in this package,
that is a bug.
