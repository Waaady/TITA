# `docker/` — reproducible environments

Optional but strongly worth it for a thesis: the environment is part of the
result. "It worked on my laptop in March" is not reproducible, and a broken
system-wide Python install two weeks before the deadline is a bad day.

## Planned images

| Image | Base | Purpose |
|---|---|---|
| `Dockerfile.dev` | `ros:humble` (amd64) | Workstation development, simulation, RViz. |
| `Dockerfile.train` | `pytorch/pytorch` + CUDA | YOLOX training and export. |
| `Dockerfile.jetson` | `dustynv/ros:humble-*` (arm64, L4T) | On-robot deployment. |

Plus a `compose.yaml` wiring up X11 forwarding, GPU access (`--gpus all` /
`--runtime nvidia`), the workspace mount, and host networking for DDS discovery.

## Notes

- Host networking is the simple choice for ROS 2 discovery. Bridge networking
  works but needs explicit DDS configuration and will cost an afternoon.
- Do not build inside the image and also mount the workspace over the build
  output — mount the source, build in the container, and keep `build/` and
  `install/` out of the mount or in a named volume.
- The Jetson image must be built for arm64. Cross-building from x86 works with
  `qemu`/`buildx` but is slow; building on the robot is usually simpler.
- Pin base image tags. `ros:humble` moves.
