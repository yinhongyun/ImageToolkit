from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor, QImage, QPixmap
from PySide6.QtWidgets import QLabel

import numpy as np


def make_checkerboard(w: int, h: int, cell: int = 8) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    c1, c2 = QColor(50, 50, 50), QColor(70, 70, 70)
    for y in range(h):
        for x in range(w):
            img.setPixelColor(x, y, c1 if ((x // cell) + (y // cell)) % 2 == 0 else c2)
    return img


def rgba_to_qimage(rgba: np.ndarray) -> QImage:
    h, w = rgba.shape[:2]
    if rgba.shape[2] == 3:
        rgb = np.ascontiguousarray(rgba)
        return QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
    arr = np.ascontiguousarray(rgba)
    return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def composite_on_checker(rgba: np.ndarray, cell: int = 8) -> QImage:
    h, w = rgba.shape[:2]
    base = make_checkerboard(w, h, cell)
    overlay = rgba_to_qimage(rgba)
    painter = QPainter(base)
    painter.drawImage(0, 0, overlay)
    painter.end()
    return base


class PreviewLabel(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#1e1e1e; border:1px solid #3a3a3a; border-radius:4px;")
        self.setText("无预览")

    def set_rgba(self, rgba: np.ndarray | None) -> None:
        if rgba is None or rgba.size == 0:
            self.clear()
            self.setText("无预览")
            return
        qimg = composite_on_checker(rgba)
        pix = QPixmap.fromImage(qimg)
        self.setPixmap(
            pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.pixmap() and not self.pixmap().isNull():
            # keep aspect on resize via stored? skip for simplicity
            pass
