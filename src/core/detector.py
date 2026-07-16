from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from .document import DetectParams, Slice, BackgroundParams
from .transparency import make_foreground_mask, resolve_bg_color


def _merge_rects(rects: List[Tuple[int, int, int, int]], gap: int) -> List[Tuple[int, int, int, int]]:
    if gap <= 0 or len(rects) <= 1:
        return rects

    boxes = [list(r) for r in rects]
    merged = True
    while merged:
        merged = False
        out: List[List[int]] = []
        used = [False] * len(boxes)
        for i in range(len(boxes)):
            if used[i]:
                continue
            x, y, w, h = boxes[i]
            x2, y2 = x + w, y + h
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                bx, by, bw, bh = boxes[j]
                bx2, by2 = bx + bw, by + bh
                if not (x2 + gap < bx or bx2 + gap < x or y2 + gap < by or by2 + gap < y):
                    nx = min(x, bx)
                    ny = min(y, by)
                    nx2 = max(x2, bx2)
                    ny2 = max(y2, by2)
                    x, y, x2, y2 = nx, ny, nx2, ny2
                    w, h = x2 - x, y2 - y
                    used[j] = True
                    merged = True
            out.append([x, y, w, h])
            used[i] = True
        boxes = out
    return [(b[0], b[1], b[2], b[3]) for b in boxes]


def detect_slices(
    image_rgba: np.ndarray,
    detect: DetectParams,
    background: BackgroundParams,
    name_prefix: str = "slice",
) -> List[Slice]:
    bg = resolve_bg_color(image_rgba, background)
    tol = detect.tolerance if detect.tolerance > 0 else background.tolerance
    mask = make_foreground_mask(image_rgba, bg, tol)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    rects: List[Tuple[int, int, int, int]] = []
    for i in range(1, num):
        x, y, w, h, area = stats[i]
        if area < detect.min_area:
            continue
        pad = detect.padding
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(image_rgba.shape[1], x + w + pad)
        y1 = min(image_rgba.shape[0], y + h + pad)
        rects.append((x0, y0, x1 - x0, y1 - y0))

    rects = _merge_rects(rects, detect.merge_gap)
    # Left-to-right, then top-to-bottom
    rects.sort(key=lambda r: (r[1] // 20, r[0]))

    slices: List[Slice] = []
    for i, (x, y, w, h) in enumerate(rects, start=1):
        slices.append(
            Slice(x=x, y=y, w=w, h=h, name=f"{name_prefix}_{i:02d}", export=True)
        )
    return slices


def hover_candidate(
    image_rgba: np.ndarray,
    px: int,
    py: int,
    detect: DetectParams,
    background: BackgroundParams,
) -> Optional[Tuple[int, int, int, int]]:
    """Return bounding box of connected component under cursor, or None."""
    h, w = image_rgba.shape[:2]
    if px < 0 or py < 0 or px >= w or py >= h:
        return None

    bg = resolve_bg_color(image_rgba, background)
    tol = detect.tolerance if detect.tolerance > 0 else background.tolerance
    mask = make_foreground_mask(image_rgba, bg, tol)

    if mask[py, px] == 0:
        # Search nearby foreground
        rad = 12
        y0, y1 = max(0, py - rad), min(h, py + rad + 1)
        x0, x1 = max(0, px - rad), min(w, px + rad + 1)
        region = mask[y0:y1, x0:x1]
        ys, xs = np.where(region > 0)
        if len(xs) == 0:
            return None
        # nearest foreground pixel
        dy = ys + y0 - py
        dx = xs + x0 - px
        idx = int(np.argmin(dx * dx + dy * dy))
        px = int(xs[idx] + x0)
        py = int(ys[idx] + y0)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    label = int(labels[py, px])
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
