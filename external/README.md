# `external/` — upstream sources

Populated by `vcs import`, **not committed**:

```bash
vcs import external < tita.repos     # from the repo root
vcs pull external                    # update everything
vcs export external > frozen.repos   # freeze exact commits
```

Contains the DDT/TITA vendor packages (SDK, URDF, simulation, manual) and YOLOX.

## Do not edit anything in here

If upstream code needs a change, the options in order of preference are:

1. Configure or extend it from one of our own packages in `src/`.
2. Fork the upstream repo, change it there, and point `tita.repos` at your fork.
3. Keep a patch file in `docs/` and apply it as an explicit build step.

Editing in place means the change is invisible to git, lost on the next
`vcs pull`, and impossible to describe accurately in the thesis.

## Pin before submitting

Every entry in `tita.repos` currently tracks a branch. Before the results in the
thesis are final, run `vcs export external` and replace the branch names with
the exact commit hashes. Otherwise an upstream push can change your robot's
behaviour between writing a chapter and defending it, with nothing in your own
history to explain it.
