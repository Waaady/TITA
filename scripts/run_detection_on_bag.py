#!/usr/bin/env python3
"""Run the YOLOX detection pipeline on a rosbag2 ``.db3`` recording.

Replays the bag's left camera images at recorded speed through the same
buffer/detector/tracker chain that will later sit behind the ROS node, and
writes one JSON line per processed frame.

    python scripts/run_detection_on_bag.py data/bags/2026-09-04_lab_moving_01
    python scripts/run_detection_on_bag.py <bag> --mode expanded            # every field
    python scripts/run_detection_on_bag.py <bag> --backend torch --device cuda --show
    python scripts/run_detection_on_bag.py <bag> --buffer all --speed 0   # every frame, offline

Record modes (--mode):
    minimal   what a consumer needs to act on a detection: frame stamp/id,
              label, score, is_dynamic, track id, bbox, bearing, foot
              elevation. Default.
    expanded  every field of FrameResult, nested as declared, including
              per-frame timing and the full track state. For benchmarking
              and geometry re-derivation.

Output goes to data/interim/detections/<bag>_<backend>_<mode>.jsonl by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
# Make the package importable without installing it, so this works straight
# from a checkout. `pip install -e src/tita_perception` makes this redundant.
sys.path.insert(0, str(REPO_ROOT / "src" / "tita_perception"))

from tita_perception.pipeline import (  # noqa: E402
    RECORD_MODES,
    BagFrameSource,
    Frame,
    FrameResult,
    build_buffer,
    build_pipeline,
    load_config,
)

DEFAULT_CONFIG = REPO_ROOT / "src" / "tita_perception" / "config" / "detector.yaml"

# (cli attribute, config section, key) - applied only when the flag was given.
CONFIG_OVERRIDES = (
    ("backend", "detector", "backend"),
    ("device", "detector", "device"),
    ("conf", "detector", "conf_threshold"),
    ("buffer", "pipeline", "frame_buffer"),
    ("speed", "bag", "speed"),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bag", type=Path, help=".db3 file or the bag directory")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--mode", choices=RECORD_MODES, default="minimal", help="fields written per record")
    p.add_argument("--backend", choices=["onnx", "torch"], help="override detector.backend")
    p.add_argument("--device", help="override detector.device (cpu | cuda | tensorrt)")
    p.add_argument("--conf", type=float, help="override detector.conf_threshold")
    p.add_argument("--buffer", choices=["latest", "all"], help="override pipeline.frame_buffer")
    p.add_argument("--speed", type=float, help="override bag.speed (0 = as fast as possible)")
    p.add_argument("--max-frames", type=int, help="stop after this many source frames")
    p.add_argument("--no-track", action="store_true", help="disable the tracker")
    p.add_argument("--output", type=Path, help="JSONL output path")
    p.add_argument("--show", action="store_true", help="live window with boxes (debug only)")
    p.add_argument("--save-video", type=Path, help="write annotated frames to an .mp4")
    p.add_argument("--quiet", action="store_true", help="no per-frame console output")
    return p.parse_args()


def apply_overrides(cfg: dict, args: argparse.Namespace) -> None:
    for attr, section, key in CONFIG_OVERRIDES:
        value = getattr(args, attr)
        if value is not None:
            cfg[section][key] = value
    if args.no_track:
        cfg["tracking"]["enabled"] = False


def resolve_bag(path: Path) -> Path:
    """Accept either the .db3 file or the bag directory containing it."""
    if path.is_file():
        return path
    if path.is_dir():
        db3 = sorted(path.glob("*.db3"))
        if len(db3) == 1:
            return db3[0]
        if not db3:
            sys.exit(f"no .db3 file in {path}")
        sys.exit(f"{path} holds several .db3 files, pass one explicitly: {[p.name for p in db3]}")
    sys.exit(f"bag not found: {path}")


def default_output(bag_path: Path, backend: str, mode: str) -> Path:
    bag_name = bag_path.parent.name if bag_path.parent != REPO_ROOT else bag_path.stem
    return REPO_ROOT / "data" / "interim" / "detections" / f"{bag_name}_{backend}_{mode}.jsonl"


def describe_camera(source: BagFrameSource) -> str:
    ci = source.camera_info
    if ci is None:
        return "warning: no CameraInfo in bag - bearing angles will be null"
    return (
        f"camera: {ci.width}x{ci.height} fx={ci.fx:.1f} fy={ci.fy:.1f} "
        f"cx={ci.cx:.1f} cy={ci.cy:.1f} model={ci.distortion_model}"
    )


def describe_frame(result: FrameResult, total_frames: int) -> str:
    labels = ", ".join(
        f"{'#%d ' % o.track.track_id if o.track else ''}{o.label} {o.score:.2f}" for o in result.detections
    )
    return (
        f"[{result.frame_seq:4d}/{total_frames}] inf {result.inference_ms:5.1f} ms  "
        f"wait {result.queue_wait_ms:5.1f} ms  drop {result.dropped_since_last:2d}  "
        f"{len(result.detections)} det: {labels}"
    )


class Visualizer:
    """Optional live window and/or .mp4 of annotated frames. Owns the cv2
    import so the headless path never loads it."""

    def __init__(self, show: bool, video_path: Optional[Path], realtime: bool, on_quit: Callable[[], None]):
        import cv2

        from tita_perception.visualization import draw_result

        self._cv2, self._draw = cv2, draw_result
        self._show, self._video_path, self._realtime, self._on_quit = show, video_path, realtime, on_quit
        self._writer = None

    def __call__(self, result: FrameResult, frame: Frame) -> None:
        canvas = self._draw(frame.image, result)
        if self._video_path:
            if self._writer is None:
                self._video_path.parent.mkdir(parents=True, exist_ok=True)
                # Real-time replay -> nominal 30 fps; as-fast-as-possible -> the detector's own pace.
                fps = 30.0 if self._realtime else 1000.0 / max(result.inference_ms, 1.0)
                self._writer = self._cv2.VideoWriter(
                    str(self._video_path), self._cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame.width, frame.height)
                )
            self._writer.write(canvas)
        if self._show:
            self._cv2.imshow("tita_perception", canvas)
            if self._cv2.waitKey(1) & 0xFF == ord("q"):
                self._on_quit()

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
        if self._show:
            self._cv2.destroyAllWindows()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    apply_overrides(cfg, args)
    det_cfg, pipe_cfg, bag_cfg = cfg["detector"], cfg["pipeline"], cfg["bag"]

    bag_path = resolve_bag(args.bag)
    out_path = args.output or default_output(bag_path, det_cfg["backend"], args.mode)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # -- build ---------------------------------------------------------------
    buffer = build_buffer(cfg)
    source = BagFrameSource(
        bag_path,
        buffer,
        image_topic_suffix=bag_cfg["image_topic_suffix"],
        camera_info_topic_suffix=bag_cfg.get("camera_info_topic_suffix"),
        speed=bag_cfg["speed"],
        max_frames=args.max_frames,
    )
    print(describe_camera(source))

    t0 = time.perf_counter()
    pipeline = build_pipeline(cfg, REPO_ROOT / "models", camera_info=source.camera_info)
    print(f"detector: {pipeline.detector!r}  (loaded + warm in {time.perf_counter() - t0:.1f} s)")

    viz = None
    if args.show or args.save_video:
        viz = Visualizer(args.show, args.save_video, realtime=bag_cfg["speed"] != 0, on_quit=source.stop)

    # -- run -----------------------------------------------------------------
    stats = {"frames": 0, "inference_ms": 0.0, "wait_ms": 0.0, "detections": 0}

    with out_path.open("w", encoding="utf-8") as out_file:

        def sink(result: FrameResult, frame: Frame) -> None:
            out_file.write(json.dumps(result.to_dict(args.mode)) + "\n")
            stats["frames"] += 1
            stats["inference_ms"] += result.inference_ms
            stats["wait_ms"] += result.queue_wait_ms
            stats["detections"] += len(result.detections)
            if not args.quiet:
                print(describe_frame(result, source.total_frames))
            if viz:
                viz(result, frame)

        print(f"bag: {bag_path}  ({source.total_frames} frames on {source.image_topic.name})")
        print(f"buffer: {pipe_cfg['frame_buffer']}  speed: x{bag_cfg['speed']}  mode: {args.mode}  -> {out_path}")
        t_run = time.perf_counter()
        source.start()
        try:
            pipeline.run(buffer, sink)
        except KeyboardInterrupt:
            source.stop()
        finally:
            source.join(5.0)
            if viz:
                viz.close()
    if source.error:
        raise source.error

    elapsed = time.perf_counter() - t_run
    n = max(stats["frames"], 1)
    print(
        f"\nprocessed {stats['frames']} of {source.frames_read} frames in {elapsed:.1f} s "
        f"({stats['frames'] / elapsed:.1f} fps), dropped {buffer.dropped_total}, "
        f"mean inference {stats['inference_ms'] / n:.1f} ms, mean wait {stats['wait_ms'] / n:.1f} ms, "
        f"{stats['detections']} detections -> {out_path}"
    )


if __name__ == "__main__":
    main()
