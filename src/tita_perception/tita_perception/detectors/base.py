"""Backend-agnostic detector interface.

Every backend (PyTorch, ONNX Runtime, TensorRT) implements :class:`Detector`
and returns the same :class:`Detection` records, so swapping backends is a
config change and nothing downstream notices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Detection:
    """One detected object, in the coordinate frame of the *original* image
    (pixels, origin top-left, x right, y down)."""

    class_id: int
    score: float  # objectness * class confidence, the number to threshold on
    obj_conf: float
    cls_conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)

    @property
    def center(self) -> tuple[float, float]:
        return (0.5 * (self.x1 + self.x2), 0.5 * (self.y1 + self.y2))

    @property
    def xyxy(self) -> np.ndarray:
        return np.array([self.x1, self.y1, self.x2, self.y2], dtype=np.float32)


class Detector(ABC):
    """``detect(image_bgr) -> list[Detection]``.

    Implementations must be deterministic given the same input and must do
    *all* of their own preprocessing, so callers hand over the raw BGR frame
    and never have to know the network's input size or normalisation.
    """

    @property
    @abstractmethod
    def class_names(self) -> Sequence[str]:
        """Index -> human-readable label."""

    @property
    @abstractmethod
    def input_size(self) -> tuple[int, int]:
        """(height, width) the network is run at."""

    @abstractmethod
    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Run the detector on one HxWx3 uint8 BGR image."""

    def warmup(self, iterations: int = 2) -> None:
        """Run a few dummy inferences so the first real frame does not pay
        for lazy initialisation (CUDA context, kernel selection, ...)."""
        h, w = self.input_size
        dummy = np.full((h, w, 3), 114, dtype=np.uint8)
        for _ in range(iterations):
            self.detect(dummy)

    def label(self, class_id: int) -> str:
        names = self.class_names
        return names[class_id] if 0 <= class_id < len(names) else f"class_{class_id}"
