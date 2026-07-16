from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from .document import BackgroundParams


def estimate_background(image_rgba: np.ndarray) -> Tuple[int, int, int]:
    """Estimate background color from image corners."""
    h, w = image_rgba.shape[:2]
    pts = [
        image_rgba[0, 0, :3],
        image_rgba[0, w - 1, :3],
        image_rgba[h - 1, 0, :3],
        image_rgba[h - 1, w - 1, :3],
        image_rgba[h // 2, 0, :3],
        image_rgba[h // 2, w - 1, :3],
        image_rgba[0, w // 2, :3],
        image_rgba[h - 1, w // 2, :3],
    ]
    arr = np.array(pts, dtype=np.float32)
    mean = arr.mean(axis=0)
    return int(mean[0]), int(mean[1]), int(mean[2])


def resolve_bg_color(
    image_rgba: np.ndarray, params: BackgroundParams
) -> Tuple[int, int, int]:
    if params.color is not None:
        return params.color
    return estimate_background(image_rgba)


def make_foreground_mask(
    image_rgba: np.ndarray, bg: Tuple[int, int, int], tolerance: int
) -> np.ndarray:
    rgb = image_rgba[:, :, :3].astype(np.int16)
    bg_arr = np.array(bg, dtype=np.int16)
    dist = np.abs(rgb - bg_arr).max(axis=2)
    mask = (dist > tolerance).astype(np.uint8) * 255

    # If source already has alpha, treat near-zero alpha as background.
    if image_rgba.shape[2] == 4:
        alpha = image_rgba[:, :, 3]
        mask[alpha < 8] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def apply_transparency(
    image_rgba: np.ndarray,
    params: BackgroundParams,
    rect: Optional[Tuple[int, int, int, int]] = None,
) -> np.ndarray:
    """Return RGBA crop (or full image) with background made transparent."""
    if rect is not None:
        x, y, w, h = rect
        x = max(0, x)
        y = max(0, y)
        crop = image_rgba[y : y + h, x : x + w].copy()
    else:
        crop = image_rgba.copy()

    if crop.size == 0:
        return crop

    bg = resolve_bg_color(image_rgba if rect is None else crop, params)
    tol = int(params.tolerance)

    if params.mode == "edge_fill":
        return _edge_fill_transparent(crop, bg, tol)

    rgb = crop[:, :, :3].astype(np.int16)
    bg_arr = np.array(bg, dtype=np.int16)
    dist = np.abs(rgb - bg_arr).max(axis=2)
    alpha = np.where(dist <= tol, 0, 255).astype(np.uint8)

    # Soft edge: partial transparency near threshold
    soft = (dist > tol) & (dist <= tol + 12)
    if soft.any():
        alpha = alpha.astype(np.float32)
        alpha[soft] = ((dist[soft] - tol) / 12.0 * 255.0).clip(0, 255)
        alpha = alpha.astype(np.uint8)

    out = np.dstack([crop[:, :, 0], crop[:, :, 1], crop[:, :, 2], alpha])
    return out


def _edge_fill_transparent(
    crop: np.ndarray, bg: Tuple[int, int, int], tol: int
) -> np.ndarray:
    h, w = crop.shape[:2]
    rgb = crop[:, :, :3]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flood = rgb.copy()
    lo = (tol, tol, tol)
    up = (tol, tol, tol)
    # Seed from borders
    for x in range(0, w, max(1, w // 8)):
        cv2.floodFill(flood, mask, (x, 0), (0, 0, 0), loDiff=lo, upDiff=up, flags=4 | (255 << 8))
        cv2.floodFill(flood, mask, (x, h - 1), (0, 0, 0), loDiff=lo, upDiff=up, flags=4 | (255 << 8))
    for y in range(0, h, max(1, h // 8)):
        cv2.floodFill(flood, mask, (0, y), (0, 0, 0), loDiff=lo, upDiff=up, flags=4 | (255 << 8))
        cv2.floodFill(flood, mask, (w - 1, y), (0, 0, 0), loDiff=lo, upDiff=up, flags=4 | (255 << 8))

    filled = mask[1:-1, 1:-1]
    alpha = np.where(filled > 0, 0, 255).astype(np.uint8)
    # Also remove exact bg that flood missed
    dist = np.abs(rgb.astype(np.int16) - np.array(bg, dtype=np.int16)).max(axis=2)
    alpha[dist <= tol] = 0
    return np.dstack([rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2], alpha])
