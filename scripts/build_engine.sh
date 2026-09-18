#!/usr/bin/env bash
# Build a TensorRT engine from an ONNX model - ON THE ROBOT.
#
#   bash scripts/build_engine.sh              # yolox_s, fp16
#   bash scripts/build_engine.sh yolox_tiny   # another model
#   bash scripts/build_engine.sh yolox_s fp32 # full precision, for comparison
#
# Engines are locked to the GPU and TensorRT version they were built with.
# They are gitignored; what makes a result reproducible is the ONNX file plus
# this command. Rebuild after any JetPack update.
#
# Takes a few minutes on the Orin. trtexec prints a throughput benchmark at
# the end - that number is a free first measurement. Run `sudo jetson_clocks`
# beforehand so it is not distorted by clock scaling.
set -euo pipefail

MODEL=${1:-yolox_s}
PRECISION=${2:-fp16}
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TRTEXEC=${TRTEXEC:-/usr/src/tensorrt/bin/trtexec}

ONNX="$REPO_ROOT/models/onnx/$MODEL.onnx"
OUT="$REPO_ROOT/models/tensorrt/${MODEL}_${PRECISION}.engine"

[[ -f "$ONNX" ]] || { echo "missing $ONNX - run: python3 scripts/download_yolox_weights.py $MODEL" >&2; exit 1; }
[[ -x "$TRTEXEC" ]] || { echo "trtexec not found at $TRTEXEC - sudo apt install libnvinfer-bin" >&2; exit 1; }

case "$PRECISION" in
  fp16) PREC_ARGS=(--fp16) ;;
  fp32) PREC_ARGS=() ;;
  *) echo "precision must be fp16 or fp32, got '$PRECISION'" >&2; exit 1 ;;
esac

mkdir -p "$(dirname "$OUT")"
echo "building $OUT from $ONNX ($PRECISION) ..."
"$TRTEXEC" --onnx="$ONNX" --saveEngine="$OUT" "${PREC_ARGS[@]}" 2>&1 | tee "$OUT.log"

echo
echo "engine: $OUT ($(du -h "$OUT" | cut -f1))"
echo "log:    $OUT.log   (throughput numbers near the end)"
echo "now set detector.backend: tensorrt in src/tita_perception/config/detector.yaml"
