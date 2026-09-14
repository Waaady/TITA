#!/usr/bin/env python3
"""Run the YOLOX detection pipeline on a rosbag2 ``.db3`` recording.

Replays the bag's left camera images at recorded speed through the same
buffer/detector/tracker chain that will later sit behind the ROS node, and
writes one JSON line per processed frame.

    python scripts/run_detection_on_bag.py data/bags/2026-09-04_lab_moving_01
    python scripts/run_detection_on_bag.py <bag> --backend torch --device cuda --show
    python scripts/run_detection_on_bag.py <bag> --buffer all --speed 0   # every frame, offline

Output goes to data/interim/detections/<bag>_<backend>.jsonl by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
# Make the package importable without installing it, so this works straight
# from a checkout. `pip install -e src/tita_perception` makes this redundant.
sys.path.insert(0, str(REPO_ROOT / "src" / "tita_perception"))

from tita_perception.detectors import build_detector  # noqa: E402
from tita_perception.pipeline import BagFrameSource, DetectionPipeline, make_frame_buffer  # noqa: E402
from tita_perception.tracking import IouTracker  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "src" / "tita_perception" / "config" / "detector.yaml"


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bag", type=Path, help=".db3 file or the bag directory")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
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


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    det_cfg, pipe_cfg = cfg["detector"], cfg["pipeline"]
    trk_cfg, bag_cfg = cfg["tracking"], cfg["bag"]

    if args.backend:
        det_cfg["backend"] = args.backend
    if args.device:
        det_cfg["device"] = args.device
    if args.conf is not None:
        det_cfg["conf_threshold"] = args.conf
    if args.buffer:
        pipe_cfg["frame_buffer"] = args.buffer
    if args.speed is not None:
        bag_cfg["speed"] = args.speed

    bag_path = resolve_bag(args.bag)
    bag_name = bag_path.parent.name if bag_path.parent != REPO_ROOT else bag_path.stem
    out_path = args.output or (
        REPO_ROOT / "data" / "interim" / "detections" / f"{bag_name}_{det_cfg['backend']}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # -- build ---------------------------------------------------------------
    t0 = time.perf_counter()
    detector = build_detector(det_cfg, models_root=REPO_ROOT / "models")
    detector.warmup()
    print(f"detector: {detector!r}  (loaded + warm in {time.perf_counter() - t0:.1f} s)")

    buffer = make_frame_buffer(pipe_cfg["frame_buffer"], pipe_cfg.get("queue_size", 8))
    source = BagFrameSource(
        bag_path,
        buffer,
        image_topic_suffix=bag_cfg["image_topic_suffix"],
        camera_info_topic_suffix=bag_cfg.get("camera_info_topic_suffix"),
        speed=bag_cfg["speed"],
        max_frames=args.max_frames,
    )
    if source.camera_info is None:
        print("warning: no CameraInfo in bag - bearing angles will be null")
    else:
        ci = source.camera_info
        print(f"camera: {ci.width}x{ci.height} fx={ci.fx:.1f} fy={ci.fy:.1f} cx={ci.cx:.1f} cy={ci.cy:.1f} "
              f"model={ci.distortion_model}")

    tracker = None
    if trk_cfg.get("enabled", True) and not args.no_track:
        tracker = IouTracker(
            iou_threshold=trk_cfg["iou_threshold"],
            max_misses=trk_cfg["max_misses"],
            smoothing=trk_cfg["smoothing"],
            same_class_only=trk_cfg["same_class_only"],
        )
    pipeline = DetectionPipeline(
        detector,
        tracker=tracker,
        camera_info=source.camera_info,
        dynamic_classes=pipe_cfg["dynamic_classes"],
        undistort_angles=pipe_cfg["undistort_angles"],
        border_margin_px=pipe_cfg["border_margin_px"],
    )

    # -- sinks ---------------------------------------------------------------
    writer = None
    if args.show or args.save_video:
        import cv2

        from tita_perception.visualization import draw_result

    out_file = out_path.open("w", encoding="utf-8")
    stats = {"frames": 0, "inference_ms": 0.0, "wait_ms": 0.0, "detections": 0}

    def sink(result, frame):
        nonlocal writer
        out_file.write(json.dumps(result.to_dict()) + "\n")
        stats["frames"] += 1
        stats["inference_ms"] += result.inference_ms
        stats["wait_ms"] += result.queue_wait_ms
        stats["detections"] += len(result.detections)
        if not args.quiet:
            labels = ", ".join(
                f"{'#%d ' % o.track.track_id if o.track else ''}{o.label} {o.score:.2f}"
                for o in result.detections
            )
            print(
                f"[{result.frame_seq:4d}/{source.total_frames}] inf {result.inference_ms:5.1f} ms  "
                f"wait {result.queue_wait_ms:5.1f} ms  drop {result.dropped_since_last:2d}  "
                f"{len(result.detections)} det: {labels}"
            )
        if args.show or args.save_video:
            canvas = draw_result(frame.image, result)
            if args.save_video:
                if writer is None:
                    args.save_video.parent.mkdir(parents=True, exist_ok=True)
                    fps = 1000.0 / max(result.inference_ms, 1.0) if bag_cfg["speed"] == 0 else 30.0
                    writer = cv2.VideoWriter(
                        str(args.save_video), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                        (frame.width, frame.height),
                    )
                writer.write(canvas)
            if args.show:
                cv2.imshow("tita_perception", canvas)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    source.stop()

    # -- run -----------------------------------------------------------------
    print(f"bag: {bag_path}  ({source.total_frames} frames on {source.image_topic.name})")
    print(f"buffer: {pipe_cfg['frame_buffer']}  speed: x{bag_cfg['speed']}  -> {out_path}")
    t_run = time.perf_counter()
    source.start()
    try:
        pipeline.run(buffer, sink)
    except KeyboardInterrupt:
        source.stop()
    finally:
        source.join(5.0)
        out_file.close()
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()
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
