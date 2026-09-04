# `docs/` — project documentation

Written material that supports the code. The thesis text itself lives in
[`thesis/`](../thesis/); this is the working documentation you draw on while
writing it.

| Directory | Contents |
|---|---|
| `adr/` | Architecture Decision Records — see [adr/README.md](adr/README.md). |
| `architecture/` | System diagrams, node/topic graphs, TF trees, data flow. |
| `hardware/` | Sensor datasheets, wiring, mounting, robot serial and configuration, network setup. |
| `experiments/` | One file per experiment: date, setup, parameters, commit hash, bag name, result. |
| `images/` | Figures used by the docs (LFS-tracked). |

## Experiment log

The highest-value directory here, and the one most likely to be neglected.
Write the entry *while* running the experiment, not afterwards.

A usable entry answers: what question was this run supposed to answer, what was
the setup, which commit and which model artifact, which bag was recorded, what
happened, and what you concluded. Two months later, the difference between a
result you can defend and a number you cannot explain is whether this file
exists.

## Diagrams

Prefer text-based diagrams (Mermaid, PlantUML) committed as source over exported
images — they diff, they can be reviewed, and they can be regenerated at thesis
resolution. Keep the rendered versions in `images/` for inclusion in the text.

Worth having early:

- The ROS node/topic graph for the full autonomy stack.
- The TF tree.
- The data flow from camera through detector to costmap.
