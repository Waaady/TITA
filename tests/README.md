# `tests/` — tests for the offline Python code

`pytest` tests for [`perception/`](../perception/) — dataset conversion, split
logic, export correctness, metric computation.

Tests for ROS 2 packages do **not** live here. They live in each package's own
`test/` directory and are run by `colcon test`, because they need the ament
test harness.

```bash
pytest tests/          # this directory
colcon test            # everything in src/
```

## Worth testing

Not everything, but these repay the effort:

- **Dataset conversion.** An off-by-one in a COCO category id or a flipped
  bounding-box coordinate convention silently degrades training. It shows up as
  a disappointing mAP, weeks later, with no error message.
- **Export equivalence.** After ONNX or TensorRT export, assert that the
  exported model's output matches PyTorch's on a fixed input within tolerance.
  This catches the single most common deployment failure.
- **Preprocessing parity.** The letterbox, channel order and normalisation used
  at inference must match training. Test them against a stored reference tensor.
- **Metric computation.** If you compute mAP yourself rather than through
  `pycocotools`, test it against a known case. A wrong metric invalidates every
  number in the thesis.

Skip testing plotting code and one-off analysis.
