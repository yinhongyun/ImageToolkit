from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from .document import BackgroundParams, DetectParams, Document, Slice


PROJECT_VERSION = 1


def load_image(path: str) -> np.ndarray:
    img = Image.open(path)
    img = img.convert("RGBA")
    return np.array(img, dtype=np.uint8)


def save_project(doc: Document, path: str) -> None:
    if not doc.image_path:
        raise ValueError("工程需要源图路径才能保存")

    data: Dict[str, Any] = {
        "version": PROJECT_VERSION,
        "app": "ImageToolkit",
        "image_path": str(Path(doc.image_path).resolve()),
        "name_prefix": doc.name_prefix,
        "detect": {
            "tolerance": doc.detect.tolerance,
            "min_area": doc.detect.min_area,
            "padding": doc.detect.padding,
            "merge_gap": doc.detect.merge_gap,
        },
        "background": {
            "color": list(doc.background.color) if doc.background.color else None,
            "tolerance": doc.background.tolerance,
            "mode": doc.background.mode,
        },
        "slices": [s.to_dict() for s in doc.slices],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    doc.project_path = path
    doc.dirty = False


def load_project(path: str) -> Document:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    image_path = data.get("image_path")
    if not image_path or not Path(image_path).exists():
        raise FileNotFoundError(f"找不到源图：{image_path}")

    rgba = load_image(image_path)
    detect_d = data.get("detect", {})
    bg_d = data.get("background", {})
    color = bg_d.get("color")
    doc = Document(
        image_path=image_path,
        image_rgba=rgba,
        name_prefix=data.get("name_prefix", "slice"),
        detect=DetectParams(
            tolerance=int(detect_d.get("tolerance", 28)),
            min_area=int(detect_d.get("min_area", 400)),
            padding=int(detect_d.get("padding", 4)),
            merge_gap=int(detect_d.get("merge_gap", 0)),
        ),
        background=BackgroundParams(
            color=tuple(color) if color else None,
            tolerance=int(bg_d.get("tolerance", 28)),
            mode=str(bg_d.get("mode", "colorkey")),
        ),
        project_path=path,
        dirty=False,
    )
    doc.slices = [Slice.from_dict(s) for s in data.get("slices", [])]
    return doc


def open_image_as_document(path: str, name_prefix: Optional[str] = None) -> Document:
    rgba = load_image(path)
    prefix = name_prefix or Path(path).stem
    return Document(
        image_path=str(Path(path).resolve()),
        image_rgba=rgba,
        name_prefix=prefix,
        dirty=False,
    )


def open_rgba_as_document(
    rgba: np.ndarray,
    name_prefix: str = "paste",
    image_path: Optional[str] = None,
) -> Document:
    if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
        raise ValueError("无效的图像数据")
    if rgba.shape[2] == 3:
        alpha = np.full((*rgba.shape[:2], 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgba, alpha], axis=2)
    rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
    return Document(
        image_path=image_path,
        image_rgba=rgba,
        name_prefix=name_prefix,
        dirty=True,
    )


def persist_rgba_png(rgba: np.ndarray, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG")
    return str(Path(path).resolve())
