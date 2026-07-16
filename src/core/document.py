from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
import uuid

import numpy as np


Rect = Tuple[int, int, int, int]  # x, y, w, h


SLICE_COLORS = [
    (80, 200, 220),
    (220, 170, 80),
    (160, 140, 240),
    (120, 210, 140),
    (240, 130, 150),
    (100, 180, 255),
]


@dataclass
class DetectParams:
    tolerance: int = 28
    min_area: int = 400
    padding: int = 4
    merge_gap: int = 0


@dataclass
class BackgroundParams:
    color: Optional[Tuple[int, int, int]] = None  # RGB; None = auto
    tolerance: int = 28
    mode: str = "colorkey"  # colorkey | edge_fill


@dataclass
class Slice:
    x: int
    y: int
    w: int
    h: int
    name: str
    export: bool = True
    locked: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def rect(self) -> Rect:
        return self.x, self.y, self.w, self.h

    def set_rect(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = int(x), int(y), max(1, int(w)), max(1, int(h))

    def clamp_to(self, width: int, height: int) -> None:
        self.x = max(0, min(self.x, width - 1))
        self.y = max(0, min(self.y, height - 1))
        self.w = max(1, min(self.w, width - self.x))
        self.h = max(1, min(self.h, height - self.y))

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Slice":
        return Slice(
            x=int(data["x"]),
            y=int(data["y"]),
            w=int(data["w"]),
            h=int(data["h"]),
            name=str(data.get("name", "slice")),
            export=bool(data.get("export", True)),
            locked=bool(data.get("locked", False)),
            id=str(data.get("id", uuid.uuid4().hex[:10])),
        )


@dataclass
class Document:
    image_path: Optional[str] = None
    image_rgba: Optional[np.ndarray] = None  # HxWx4 uint8 RGB(A)
    slices: List[Slice] = field(default_factory=list)
    detect: DetectParams = field(default_factory=DetectParams)
    background: BackgroundParams = field(default_factory=BackgroundParams)
    dirty: bool = False
    project_path: Optional[str] = None
    name_prefix: str = "slice"

    @property
    def width(self) -> int:
        return 0 if self.image_rgba is None else int(self.image_rgba.shape[1])

    @property
    def height(self) -> int:
        return 0 if self.image_rgba is None else int(self.image_rgba.shape[0])

    @property
    def has_image(self) -> bool:
        return self.image_rgba is not None

    def clear_slices(self) -> None:
        self.slices.clear()
        self.dirty = True

    def add_slice(self, sl: Slice) -> None:
        if self.has_image:
            sl.clamp_to(self.width, self.height)
        self.slices.append(sl)
        self.dirty = True

    def remove_slice(self, slice_id: str) -> Optional[Slice]:
        for i, s in enumerate(self.slices):
            if s.id == slice_id:
                self.dirty = True
                return self.slices.pop(i)
        return None

    def find_slice(self, slice_id: str) -> Optional[Slice]:
        for s in self.slices:
            if s.id == slice_id:
                return s
        return None

    def next_name(self) -> str:
        n = 1
        existing = {s.name for s in self.slices}
        while f"{self.name_prefix}_{n:02d}" in existing:
            n += 1
        return f"{self.name_prefix}_{n:02d}"

    def color_for_index(self, index: int) -> Tuple[int, int, int]:
        return SLICE_COLORS[index % len(SLICE_COLORS)]
