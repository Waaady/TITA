# `tita_interfaces_thesis` — custom interfaces

Message, service and action definitions owned by this project. Nothing else —
no nodes, no logic, minimal dependencies. Every package downstream depends on
this one, so anything heavy added here is inherited by everything.

## Rule: prefer standard messages

Before adding a definition here, check whether a standard one already fits:

- `vision_msgs/Detection2DArray`, `Detection3DArray` — object detections. Use
  these; do not invent a bounding-box message.
- `nav_msgs/OccupancyGrid`, `Path`, `Odometry` — mapping and navigation.
- `sensor_msgs/*` — anything a sensor produces.

Standard messages mean RViz, Nav2 and `rosbag2` tooling work without adapters.
A custom message is justified when the concept genuinely does not exist
upstream — for example a posture command for a wheeled biped, or a mapping
session state.

## Layout

- `msg/` — data.
- `srv/` — request/response, for things that complete quickly.
- `action/` — long-running goals with feedback and cancellation (a mapping
  sweep, a "go to and inspect" behaviour).

## Versioning

Once a message is recorded into a bag in `data/bags/`, changing its definition
makes those bags unreadable. Before the first real experiment, freeze the
interfaces; after that, add fields rather than changing them, and note any
breaking change in `docs/adr/`.
