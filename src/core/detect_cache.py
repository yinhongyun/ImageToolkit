from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from .document import BackgroundParams, DetectParams
from .transparency import make_foreground_mask, resolve_bg_color


class DetectCache:
    """Cache foreground mask + connected components for fast hover lookup."""

    def __init__(self) -> None:
        self._key: Optional[tuple] = None
        self._labels: Optional[np.ndarray] = None
        self._stats: Optional[np.ndarray] = None
        self._shape: Optional[Tuple[int, int]] = None

    def invalidate(self) -> None:
        self._key = None
        self._labels = None
        self._stats = None
        self._shape = None

    def _make_key(
        self,
        image_rgba: np.ndarray,
        detect: DetectParams,
        background: BackgroundParams,
    ) -> tuple:
        bg = resolve_bg_color(image_rgba, background)
        tol = detect.tolerance if detect.tolerance > 0 else background.tolerance
        # identity by buffer pointer + shape + params (doc replaces array on open)
        return (
            id(image_rgba),
            image_rgba.shape,
            int(tol),
            int(detect.min_area),
            int(detect.padding),
            tuple(bg),
            background.mode,
        )

    def ensure(
        self,
        image_rgba: np.ndarray,
        detect: DetectParams,
        background: BackgroundParams,
    ) -> None:
        key = self._make_key(image_rgba, detect, background)
        if key == self._key and self._labels is not None:
            return
        bg = resolve_bg_color(image_rgba, background)
        tol = detect.tolerance if detect.tolerance > 0 else background.tolerance
        mask = make_foreground_mask(image_rgba, bg, tol)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        self._labels = labels
        self._stats = stats
        self._shape = (image_rgba.shape[0], image_rgba.shape[1])
        self._key = key

    def hover_rect(
        self,
        image_rgba: np.ndarray,
        px: int,
        py: int,
        detect: DetectParams,
        background: BackgroundParams,
    ) -> Optional[Tuple[int, int, int, int]]:
        h, w = image_rgba.shape[:2]
        if px < 0 or py < 0 or px >= w or py >= h:
            return None
        self.ensure(image_rgba, detect, background)
        assert self._labels is not None and self._stats is not None
        labels = self._labels
        stats = self._stats

        label = int(labels[py, px])
        if label == 0:
            rad = 12
            y0, y1 = max(0, py - rad), min(h, py + rad + 1)
            x0, x1 = max(0, px - rad), min(w, px + rad + 1)
            region = labels[y0:y1, x0:x1]
            ys, xs = np.where(region > 0)
            if len(xs) == 0:
                return None
            dy = ys.astype(np.int32) + y0 - py
            dx = xs.astype(np.int32) + x0 - px
            idx = int(np.argmin(dx * dx + dy * dy))
            label = int(region[ys[idx], xs[idx]])
            if label == 0:
                return None

        x, y, bw, bh, area = stats[label]
        if area < max(40, detect.min_area // 4):
            return None
        pad = detect.padding
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + bw + pad)
        y1 = min(h, y + bh + pad)
        return x0, y0, x1 - x0, y1 - y0
