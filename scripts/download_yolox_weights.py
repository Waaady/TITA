#!/usr/bin/env python3
"""Fetch pretrained COCO YOLOX artifacts from the upstream GitHub release
into models/ (which is gitignored).

    python scripts/download_yolox_weights.py            # yolox_s .pth + .onnx
    python scripts/download_yolox_weights.py yolox_tiny yolox_nano

The .pth feeds the torch backend, the .onnx the ONNX Runtime backend. Both
come from the same release, so they are the same weights - which is what
makes them useful for checking the two backends against each other.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"
MODELS = ("yolox_nano", "yolox_tiny", "yolox_s", "yolox_m", "yolox_l", "yolox_x")


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"exists   {dest.relative_to(REPO_ROOT)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"download {url}")

    def report(blocks: int, block_size: int, total: int) -> None:
        if total > 0 and sys.stdout.isatty():
            done = min(blocks * block_size, total)
            sys.stdout.write(f"\r         {done / 1e6:6.1f} / {total / 1e6:.1f} MB")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, tmp, reporthook=report)
    sys.stdout.write("\n")
    tmp.replace(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()[:16]
    print(f"saved    {dest.relative_to(REPO_ROOT)}  sha256:{digest}...")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("models", nargs="*", metavar="MODEL", help=f"one of {', '.join(MODELS)}; default: yolox_s")
    p.add_argument("--only", choices=["pth", "onnx"], help="fetch just one format")
    args = p.parse_args()
    for name in args.models or ["yolox_s"]:
        if name not in MODELS:
            p.error(f"unknown model {name!r}; choose from {', '.join(MODELS)}")
        if args.only != "onnx":
            download(f"{RELEASE}/{name}.pth", REPO_ROOT / "models" / "checkpoints" / f"{name}.pth")
        if args.only != "pth":
            download(f"{RELEASE}/{name}.onnx", REPO_ROOT / "models" / "onnx" / f"{name}.onnx")


if __name__ == "__main__":
    main()
