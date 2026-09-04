# `notebooks/` — analysis and thesis figures

Jupyter notebooks for evaluating results and producing the figures that go into
the thesis. Exploration and plotting only.

## Rules

- **Notebooks are not the pipeline.** Anything that has to run twice belongs in
  `perception/` or `scripts/` as a proper module. A notebook that trains a model
  is a result you cannot reproduce.
- **Strip output before committing.** `nbstripout` is in `requirements-dev.txt`;
  install it as a pre-commit hook. Notebook outputs make diffs unreadable and
  can quietly add megabytes of embedded images to the repo.
- Number them in reading order: `01_dataset_statistics.ipynb`,
  `02_detector_evaluation.ipynb`, `03_slam_trajectory_error.ipynb`.
- Notebooks read from `data/` and `models/` and write figures to
  `docs/images/`. They should never write into `data/processed/`.

## Plot style

Set a consistent style once and reuse it for every figure. Match the thesis
document: same font family, same figure width as the text column, vector output
(PDF or SVG) rather than PNG. Figures that are consistent across a thesis look
considered; ones that are not are noticed.
