"""Pre- and post-processing shared by every YOLOX backend.

This is the single place where YOLOX's input contract lives. It must match
the training pipeline exactly (``yolox.data.data_augment.preproc``):

* letterbox to the network size, image anchored **top-left**, padding value
  114, ``cv2.INTER_LINEAR``;
* **BGR** channel order (YOLOX trains on ``cv2.imread`` output), CHW layout;
* **no normalisation** - raw 0..255 float32. Dividing by 255 or subtracting
  the ImageNet mean silently destroys accuracy.

Both backends produce the same ``(N, 5 + num_classes)`` tensor per image:
``[cx, cy, w, h, objectness, cls_0 .. cls_k]``. The PyTorch model decodes the
grid offsets itself (``decode_in_inference=True``); the official ONNX export
does not, so :func:`decode_outputs` is applied there first.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from .base import Detection

YOLOX_STRIDES = (8, 16, 32)


def letterbox(image_bgr: np.ndarray, input_size: tuple[int, int]) -> tuple[np.ndarray, float]:
    """Resize + pad ``image_bgr`` into a ``(3, H, W)`` float32 tensor.

    Returns the tensor and the scale factor ``r`` needed to map network
    coordinates back to the original image (``orig = net / r``).
    """
    h_in, w_in = input_size
    padded = np.full((h_in, w_in, 3), 114, dtype=np.uint8)
    r = min(h_in / image_bgr.shape[0], w_in / image_bgr.shape[1])
    new_w = int(image_bgr.shape[1] * r)
    new_h = int(image_bgr.shape[0] * r)
    resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    padded[:new_h, :new_w] = resized
    tensor = np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32)
    return tensor, r


def make_grids(input_size: tuple[int, int], strides: Sequence[int] = YOLOX_STRIDES):
    """Anchor-point grid and per-point stride for the concatenated head
    output, in the order YOLOX emits them (stride 8, then 16, then 32)."""
    grids, expanded = [], []
    for s in strides:
        hs, ws = input_size[0] // s, input_size[1] // s
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grid = np.stack((xv, yv), axis=2).reshape(-1, 2)
        grids.append(grid)
        expanded.append(np.full((grid.shape[0], 1), s))
    return (
        np.concatenate(grids, axis=0).astype(np.float32),
        np.concatenate(expanded, axis=0).astype(np.float32),
    )


def decode_outputs(raw: np.ndarray, input_size: tuple[int, int]) -> np.ndarray:
    """Turn raw head output ``(N, 5+C)`` into decoded ``[cx, cy, w, h, ...]``
    in network-input pixels. Mirrors ``yolox.utils.demo_utils.demo_postprocess``."""
    grids, strides = make_grids(input_size)
    if raw.shape[0] != grids.shape[0]:
        raise ValueError(
            f"output has {raw.shape[0]} anchor points, expected {grids.shape[0]} "
            f"for input size {input_size} - wrong input_size for this model?"
        )
    out = raw.copy()
    out[:, :2] = (out[:, :2] + grids) * strides
    out[:, 2:4] = np.exp(out[:, 2:4]) * strides
    return out


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> np.ndarray:
    """Greedy NMS over ``boxes`` (xyxy). Returns kept indices, best first."""
    if boxes.shape[0] == 0:
        return np.empty(0, dtype=np.int64)
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_threshold]
    return np.asarray(keep, dtype=np.int64)


def postprocess(
    decoded: np.ndarray,
    scale: float,
    image_shape: tuple[int, int],
    conf_threshold: float,
    nms_threshold: float,
    class_whitelist: Sequence[int] | None = None,
) -> list[Detection]:
    """Decoded ``(N, 5+C)`` output -> thresholded, NMS'd detections in
    original-image pixel coordinates.

    NMS is class-aware (a chair overlapping a person suppresses neither),
    implemented with the usual coordinate-offset trick. Each anchor point
    contributes only its best class, as in YOLOX's own ``postprocess``.
    """
    if decoded.shape[0] == 0:
        return []
    obj = decoded[:, 4]
    cls_scores = decoded[:, 5:]
    cls_ids = cls_scores.argmax(axis=1)
    cls_conf = cls_scores[np.arange(decoded.shape[0]), cls_ids]
    score = obj * cls_conf

    mask = score >= conf_threshold
    if class_whitelist is not None:
        mask &= np.isin(cls_ids, np.asarray(list(class_whitelist)))
    if not mask.any():
        return []

    boxes_cxcywh = decoded[mask, :4]
    obj, cls_conf, score, cls_ids = obj[mask], cls_conf[mask], score[mask], cls_ids[mask]

    boxes = np.empty_like(boxes_cxcywh)
    boxes[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
    boxes[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
    boxes[:, 2] = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
    boxes[:, 3] = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2
    boxes /= scale

    # Offset boxes per class so one NMS pass is class-aware.
    offset = cls_ids[:, None].astype(np.float32) * (max(image_shape) * 2.0)
    keep = nms(boxes + offset, score, nms_threshold)

    h, w = image_shape
    detections = []
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        detections.append(
            Detection(
                class_id=int(cls_ids[i]),
                score=float(score[i]),
                obj_conf=float(obj[i]),
                cls_conf=float(cls_conf[i]),
                x1=float(np.clip(x1, 0, w)),
                y1=float(np.clip(y1, 0, h)),
                x2=float(np.clip(x2, 0, w)),
                y2=float(np.clip(y2, 0, h)),
            )
        )
    return detections
