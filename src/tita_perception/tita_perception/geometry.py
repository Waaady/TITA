"""Pixel -> viewing-direction conversions from ``CameraInfo``.

Conventions (REP-103 optical frame): z forward along the optical axis,
x right, y down. Angles are therefore

* ``bearing``   - horizontal angle, **positive to the right** of the optical
                  axis (image x increasing);
* ``elevation`` - vertical angle, **positive downward** (image y increasing).

For a ground-standing object, the elevation of its *foot point* (bottom of
the box) is what a later stage combines with the camera height to estimate
range without depth data. This module only produces the angles; the range
estimate belongs to the projection stage.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .bag.ros_messages import CameraInfo


class PixelToAngle:
    def __init__(self, camera_info: CameraInfo, undistort: bool = False) -> None:
        """
        undistort: apply the CameraInfo distortion model (``d``) before
            computing angles. Use True for raw images (TITA's ``image/left``
            is raw: strong barrel distortion, CameraInfo frame ``left_img_raw``)
            and False for a rectified topic - undistorting twice is worse
            than not at all.
        """
        self.fx, self.fy = camera_info.fx, camera_info.fy
        self.cx, self.cy = camera_info.cx, camera_info.cy
        if self.fx <= 0 or self.fy <= 0:
            raise ValueError("CameraInfo has no valid focal length (K is empty?)")
        self._undistort = undistort and any(abs(v) > 0 for v in camera_info.d)
        self._k = np.asarray(camera_info.k, dtype=np.float64)
        self._d = np.asarray(camera_info.d, dtype=np.float64)
        self.image_size = (camera_info.width, camera_info.height)

    def normalized(self, u: float, v: float) -> tuple[float, float]:
        """Pixel -> normalised image coordinates (x/z, y/z)."""
        if self._undistort:
            import cv2

            pt = np.array([[[u, v]]], dtype=np.float64)
            x, y = cv2.undistortPoints(pt, self._k, self._d)[0, 0]
            return float(x), float(y)
        return (u - self.cx) / self.fx, (v - self.cy) / self.fy

    def bearing(self, u: float, v: Optional[float] = None) -> float:
        """Horizontal angle [rad] of pixel column ``u``; positive = right."""
        x, _ = self.normalized(u, self.cy if v is None else v)
        return math.atan(x)

    def elevation(self, v: float, u: Optional[float] = None) -> float:
        """Vertical angle [rad] of pixel row ``v``; positive = down."""
        _, y = self.normalized(self.cx if u is None else u, v)
        return math.atan(y)

    def bearing_rate(self, u: float, du_dt: float) -> float:
        """d(bearing)/dt [rad/s] for a pixel moving at ``du_dt`` px/s
        (pinhole approximation)."""
        x = (u - self.cx) / self.fx
        return (du_dt / self.fx) / (1.0 + x * x)
