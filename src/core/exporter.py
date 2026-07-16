from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from .document import BackgroundParams, Slice
from .transparency import apply_transparency


class ExportFormat(str, Enum):
    PNG = "png"
    WEBP = "webp"
    JPEG = "jpeg"
    BMP = "bmp"

    @property
    def supports_alpha(self) -> bool:
        return self in (ExportFormat.PNG, ExportFormat.WEBP)

    @property
    def extension(self) -> str:
        return {ExportFormat.JPEG: "jpg"}.get(self, self.value)


class ConflictPolicy(str, Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"


@dataclass
class ExportResult:
    path: str
    skipped: bool = False
    message: str = ""


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def _coerce_format(fmt: ExportFormat | str) -> ExportFormat:
    if isinstance(fmt, ExportFormat):
        return fmt
    return ExportFormat(str(fmt))


def _coerce_conflict(conflict: ConflictPolicy | str) -> ConflictPolicy:
    if isinstance(conflict, ConflictPolicy):
        return conflict
    return ConflictPolicy(str(conflict))


def _pil_format_name(fmt: ExportFormat) -> str:
    if fmt == ExportFormat.JPEG:
        return "JPEG"
    if fmt == ExportFormat.WEBP:
        return "WEBP"
    if fmt == ExportFormat.BMP:
        return "BMP"
    return "PNG"


def export_slices(
    image_rgba: np.ndarray,
    slices: List[Slice],
    out_dir: str,
    fmt: ExportFormat | str,
    background: BackgroundParams,
    conflict: ConflictPolicy | str = ConflictPolicy.RENAME,
    only_export_flagged: bool = True,
    jpeg_quality: int = 92,
) -> List[ExportResult]:
    fmt = _coerce_format(fmt)
    conflict = _coerce_conflict(conflict)
    out_path = Path(out_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    results: List[ExportResult] = []

    for sl in slices:
        if only_export_flagged and not sl.export:
            continue
        safe_name = _safe_filename(sl.name)
        rgba = apply_transparency(image_rgba, background, sl.rect)
        if rgba.size == 0:
            results.append(ExportResult("", skipped=True, message=f"{sl.name}: empty"))
            continue

        if not fmt.supports_alpha:
            # Composite on white for opaque formats
            rgb = rgba[:, :, :3].astype(np.float32)
            a = rgba[:, :, 3:4].astype(np.float32) / 255.0
            comp = (rgb * a + 255.0 * (1.0 - a)).astype(np.uint8)
            pil = Image.fromarray(np.ascontiguousarray(comp), mode="RGB")
        else:
            pil = Image.fromarray(np.ascontiguousarray(rgba), mode="RGBA")

        dest = out_path / f"{safe_name}.{fmt.extension}"
        if dest.exists():
            if conflict == ConflictPolicy.SKIP:
                results.append(ExportResult(str(dest), skipped=True, message="exists"))
                continue
            if conflict == ConflictPolicy.RENAME:
                dest = _unique_path(dest)

        save_kwargs = {}
        if fmt == ExportFormat.JPEG:
            save_kwargs["quality"] = jpeg_quality
        elif fmt == ExportFormat.WEBP:
            save_kwargs["lossless"] = True
            save_kwargs["quality"] = 90

        try:
            pil.save(str(dest), format=_pil_format_name(fmt), **save_kwargs)
            if not dest.is_file() or dest.stat().st_size <= 0:
                results.append(
                    ExportResult(str(dest), skipped=True, message="write failed")
                )
                continue
            results.append(ExportResult(str(dest)))
        except Exception as e:
            results.append(ExportResult(str(dest), skipped=True, message=str(e)))

    return results


def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if c in bad else c for c in (name or "").strip())
    cleaned = cleaned.rstrip(". ")
    return cleaned or "slice"
