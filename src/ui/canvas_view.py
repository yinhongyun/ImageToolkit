from __future__ import annotations

from enum import Enum, auto
from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPen,
    QBrush,
    QWheelEvent,
    QMouseEvent,
    QKeyEvent,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget

from core.document import Document, Slice
from core.detect_cache import DetectCache
from ui.widgets.checkerboard import rgba_to_qimage


class ToolMode(Enum):
    SELECT = auto()
    DRAW = auto()


Handle = Optional[str]  # 'nw','n','ne','e','se','s','sw','w','move'


class CanvasView(QWidget):
    sliceSelected = Signal(str)  # id or ""
    slicesChanged = Signal()  # structure / commit — refresh list
    sliceGeometryLive = Signal()  # during drag — light UI update only
    statusMessage = Signal(str)
    cursorMoved = Signal(int, int)
    requestSnapshot = Signal()  # before mutating geometry

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 240)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._doc: Optional[Document] = None
        self._qimage: Optional[QImage] = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._tool = ToolMode.SELECT
        self._selected_id: str = ""
        self._hover_rect: Optional[Tuple[int, int, int, int]] = None
        self._show_boxes = True
        self._show_labels = True
        self._hide_overlay_temp = False
        self._space_pan = False
        self._panning = False
        self._pan_last = QPoint()
        self._drawing = False
        self._draw_start: Optional[QPoint] = None
        self._draw_current: Optional[QPoint] = None
        self._handle: Handle = None
        self._drag_origin: Optional[QPoint] = None
        self._slice_origin: Optional[Tuple[int, int, int, int]] = None
        self._snapshot_pushed = False
        self._detect_cache = DetectCache()
        self._was_dragging = False

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(80)
        self._hover_timer.timeout.connect(self._run_hover)
        self._pending_hover: Optional[Tuple[int, int]] = None

        self._coord_timer = QTimer(self)
        self._coord_timer.setSingleShot(True)
        self._coord_timer.setInterval(33)
        self._coord_timer.timeout.connect(self._emit_cursor)
        self._pending_coord: Optional[Tuple[int, int]] = None

        self._empty = True

    # ----- public API -----
    def set_document(self, doc: Optional[Document]) -> None:
        self._doc = doc
        self._selected_id = ""
        self._hover_rect = None
        self._detect_cache.invalidate()
        if doc and doc.has_image:
            self._empty = False
            self._qimage = rgba_to_qimage(doc.image_rgba)
            self.fit_view()
            # Warm cache off the critical path
            QTimer.singleShot(0, self._warm_cache)
        else:
            self._empty = True
            self._qimage = None
        self.update()

    def invalidate_detect_cache(self) -> None:
        self._detect_cache.invalidate()
        self._hover_rect = None

    def _warm_cache(self) -> None:
        if self._doc and self._doc.has_image:
            try:
                self._detect_cache.ensure(
                    self._doc.image_rgba, self._doc.detect, self._doc.background
                )
            except Exception:
                pass

    def refresh_image(self) -> None:
        if self._doc and self._doc.has_image:
            self._qimage = rgba_to_qimage(self._doc.image_rgba)
            self._detect_cache.invalidate()
            self.update()

    def set_tool(self, tool: ToolMode) -> None:
        self._tool = tool
        self._hover_rect = None
        self.update()

    def tool(self) -> ToolMode:
        return self._tool

    def set_selected(self, slice_id: str) -> None:
        self._selected_id = slice_id or ""
        self.update()

    def selected_id(self) -> str:
        return self._selected_id

    def set_show_boxes(self, on: bool) -> None:
        self._show_boxes = on
        self.update()

    def set_show_labels(self, on: bool) -> None:
        self._show_labels = on
        self.update()

    def fit_view(self) -> None:
        if not self._qimage:
            return
        mw = max(1, self.width() - 40)
        mh = max(1, self.height() - 40)
        sx = mw / self._qimage.width()
        sy = mh / self._qimage.height()
        self._scale = max(0.05, min(sx, sy, 8.0))
        self._offset = QPointF(
            (self.width() - self._qimage.width() * self._scale) / 2,
            (self.height() - self._qimage.height() * self._scale) / 2,
        )
        self.update()

    def set_zoom(self, scale: float) -> None:
        self._scale = max(0.05, min(scale, 16.0))
        self.update()

    def zoom(self) -> float:
        return self._scale

    def zoom_at(self, factor: float, anchor: QPointF) -> None:
        old = self._scale
        new = max(0.05, min(old * factor, 16.0))
        if abs(new - old) < 1e-6:
            return
        # keep anchor image point stable
        img_pt = self._screen_to_image(anchor)
        self._scale = new
        self._offset = QPointF(
            anchor.x() - img_pt.x() * self._scale,
            anchor.y() - img_pt.y() * self._scale,
        )
        self.update()

    # ----- coord transforms -----
    def _screen_to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self._offset.x()) / self._scale, (p.y() - self._offset.y()) / self._scale)

    def _image_to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(x * self._scale + self._offset.x(), y * self._scale + self._offset.y())

    def _image_rect_screen(self, x: int, y: int, w: int, h: int) -> QRectF:
        tl = self._image_to_screen(x, y)
        return QRectF(tl.x(), tl.y(), w * self._scale, h * self._scale)

    # ----- paint -----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        # Antialias overlays only when idle — faster while dragging/drawing
        interactive = self._drawing or bool(self._handle) or self._panning
        p.setRenderHint(QPainter.RenderHint.Antialiasing, not interactive)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._scale < 1.0 and not interactive)
        p.fillRect(self.rect(), QColor("#1e1e1e"))

        if self._empty or not self._qimage:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "拖入 / 粘贴 (Ctrl+V) 图片，或使用「打开」\n支持 PNG / JPG / WebP / BMP")
            return

        p.drawImage(
            QRectF(
                self._offset.x(),
                self._offset.y(),
                self._qimage.width() * self._scale,
                self._qimage.height() * self._scale,
            ),
            self._qimage,
        )

        if self._hide_overlay_temp or not self._doc:
            return

        if self._show_boxes:
            for i, sl in enumerate(self._doc.slices):
                color = self._doc.color_for_index(i)
                selected = sl.id == self._selected_id
                self._draw_slice_box(p, sl, color, selected)

        if self._hover_rect and self._tool == ToolMode.SELECT and not self._drawing:
            x, y, w, h = self._hover_rect
            rect = self._image_rect_screen(x, y, w, h)
            pen = QPen(QColor(255, 255, 255, 200), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)

        if self._drawing and self._draw_start and self._draw_current:
            r = QRectF(self._draw_start, self._draw_current).normalized()
            pen = QPen(QColor(14, 99, 156), 1.5, Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.setBrush(QColor(14, 99, 156, 40))
            p.drawRect(r)

    def _draw_slice_box(self, p: QPainter, sl: Slice, color: Tuple[int, int, int], selected: bool) -> None:
        rect = self._image_rect_screen(sl.x, sl.y, sl.w, sl.h)
        qc = QColor(*color)
        pen = QPen(qc, 2.5 if selected else 1.5)
        if not selected:
            qc.setAlpha(200)
            pen.setColor(qc)
        p.setPen(pen)
        p.setBrush(QColor(color[0], color[1], color[2], 28 if selected else 12))
        p.drawRect(rect)

        if self._show_labels:
            label = f"{sl.name}  {sl.w}×{sl.h}"
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(rect.adjusted(4, 2, -2, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, label)

        if selected and not sl.locked:
            self._draw_handles(p, rect)

    def _draw_handles(self, p: QPainter, rect: QRectF) -> None:
        hs = 7
        points = self._handle_points(rect)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#0e639c"), 1))
        for pt in points.values():
            p.drawRect(QRectF(pt.x() - hs / 2, pt.y() - hs / 2, hs, hs))

    def _handle_points(self, rect: QRectF) -> dict:
        c = rect.center()
        return {
            "nw": rect.topLeft(),
            "n": QPointF(c.x(), rect.top()),
            "ne": rect.topRight(),
            "e": QPointF(rect.right(), c.y()),
            "se": rect.bottomRight(),
            "s": QPointF(c.x(), rect.bottom()),
            "sw": rect.bottomLeft(),
            "w": QPointF(rect.left(), c.y()),
        }

    def _hit_handle(self, pos: QPointF) -> Handle:
        if not self._doc or not self._selected_id:
            return None
        sl = self._doc.find_slice(self._selected_id)
        if not sl or sl.locked:
            return None
        rect = self._image_rect_screen(sl.x, sl.y, sl.w, sl.h)
        for name, pt in self._handle_points(rect).items():
            if (pos - pt).manhattanLength() <= 10:
                return name
        if rect.adjusted(-2, -2, 2, 2).contains(pos):
            return "move"
        return None

    def _hit_slice(self, img_x: int, img_y: int) -> Optional[Slice]:
        if not self._doc:
            return None
        # topmost last
        for sl in reversed(self._doc.slices):
            if sl.x <= img_x < sl.x + sl.w and sl.y <= img_y < sl.y + sl.h:
                return sl
        return None

    # ----- mouse -----
    def mousePressEvent(self, e: QMouseEvent) -> None:
        if self._empty:
            return
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and self._space_pan):
            self._panning = True
            self._pan_last = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if e.button() != Qt.MouseButton.LeftButton:
            return

        pos = e.position()
        if self._tool == ToolMode.DRAW:
            self._drawing = True
            self._draw_start = pos.toPoint()
            self._draw_current = pos.toPoint()
            self._snapshot_pushed = False
            return

        # SELECT
        handle = self._hit_handle(pos)
        if handle:
            self._ensure_snapshot()
            self._handle = handle
            self._drag_origin = pos.toPoint()
            sl = self._doc.find_slice(self._selected_id)
            self._slice_origin = sl.rect if sl else None
            return

        img = self._screen_to_image(pos)
        ix, iy = int(img.x()), int(img.y())
        hit = self._hit_slice(ix, iy)
        if hit:
            self._selected_id = hit.id
            self.sliceSelected.emit(hit.id)
            self._ensure_snapshot()
            self._handle = "move"
            self._drag_origin = pos.toPoint()
            self._slice_origin = hit.rect
            self.update()
            return

        # click hover candidate to create
        if self._hover_rect:
            self._ensure_snapshot()
            x, y, w, h = self._hover_rect
            name = self._doc.next_name()
            sl = Slice(x=x, y=y, w=w, h=h, name=name)
            self._doc.add_slice(sl)
            self._selected_id = sl.id
            self._hover_rect = None
            self.sliceSelected.emit(sl.id)
            self.slicesChanged.emit()
            self.statusMessage.emit(f"已添加切片 {name}")
            self.update()
            return

        self._selected_id = ""
        self.sliceSelected.emit("")
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._panning:
            delta = pos.toPoint() - self._pan_last
            self._pan_last = pos.toPoint()
            self._offset += QPointF(delta)
            self.update()
            return

        if self._empty or not self._doc:
            return

        img = self._screen_to_image(pos)
        ix, iy = int(img.x()), int(img.y())
        self._pending_coord = (ix, iy)
        if not self._coord_timer.isActive():
            self._coord_timer.start()

        if self._drawing and self._draw_start:
            self._draw_current = pos.toPoint()
            self.update()
            return

        if self._handle and self._drag_origin and self._slice_origin and self._selected_id:
            sl = self._doc.find_slice(self._selected_id)
            if sl and not sl.locked:
                self._apply_handle_drag(sl, pos)
                self._was_dragging = True
                # Only repaint canvas during drag — do NOT rebuild list/preview
                self.sliceGeometryLive.emit()
                self.update()
            return

        # hover cursor (skip while interacting)
        if self._tool == ToolMode.SELECT:
            h = self._hit_handle(pos)
            if h in ("nw", "se"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif h in ("ne", "sw"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif h in ("n", "s"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif h in ("e", "w"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif h == "move":
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self._pending_hover = (ix, iy)
                self._hover_timer.start()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.MiddleButton or self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if self._drawing and self._draw_start and self._draw_current and self._doc:
            r = QRectF(self._draw_start, self._draw_current).normalized()
            self._drawing = False
            tl = self._screen_to_image(r.topLeft())
            br = self._screen_to_image(r.bottomRight())
            x = int(min(tl.x(), br.x()))
            y = int(min(tl.y(), br.y()))
            w = int(abs(br.x() - tl.x()))
            h = int(abs(br.y() - tl.y()))
            self._draw_start = None
            self._draw_current = None
            if w >= 4 and h >= 4:
                self._ensure_snapshot()
                name = self._doc.next_name()
                sl = Slice(x=x, y=y, w=w, h=h, name=name)
                self._doc.add_slice(sl)
                self._selected_id = sl.id
                self.sliceSelected.emit(sl.id)
                self.slicesChanged.emit()
                self.statusMessage.emit(f"已画框 {name}")
            self.update()
        elif self._was_dragging:
            # Commit: refresh list text / preview once
            self.slicesChanged.emit()

        self._handle = None
        self._drag_origin = None
        self._slice_origin = None
        self._snapshot_pushed = False
        self._was_dragging = False

    def wheelEvent(self, e: QWheelEvent) -> None:
        if self._empty:
            return
        delta = e.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.zoom_at(factor, e.position())
        self.statusMessage.emit(f"缩放 {int(self._scale * 100)}%")

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Space:
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif e.key() == Qt.Key.Key_C:
            self._hide_overlay_temp = True
            self.update()
        elif e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._nudge_selected(e)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Space:
            self._space_pan = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        elif e.key() == Qt.Key.Key_C:
            self._hide_overlay_temp = False
            self.update()
        else:
            super().keyReleaseEvent(e)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)

    def _ensure_snapshot(self) -> None:
        if not self._snapshot_pushed:
            self.requestSnapshot.emit()
            self._snapshot_pushed = True

    def _emit_cursor(self) -> None:
        if self._pending_coord:
            self.cursorMoved.emit(*self._pending_coord)

    def _run_hover(self) -> None:
        if not self._doc or not self._doc.has_image or self._tool != ToolMode.SELECT:
            return
        if self._handle or self._drawing or self._panning:
            return
        if not self._pending_hover:
            return
        ix, iy = self._pending_hover
        # don't show hover if already over existing slice
        if self._hit_slice(ix, iy):
            if self._hover_rect:
                self._hover_rect = None
                self.update()
            return
        rect = self._detect_cache.hover_rect(
            self._doc.image_rgba, ix, iy, self._doc.detect, self._doc.background
        )
        # avoid duplicating existing nearly-same rect
        if rect:
            for sl in self._doc.slices:
                if abs(sl.x - rect[0]) < 3 and abs(sl.y - rect[1]) < 3 and abs(sl.w - rect[2]) < 3 and abs(sl.h - rect[3]) < 3:
                    rect = None
                    break
        if rect != self._hover_rect:
            self._hover_rect = rect
            self.update()

    def _apply_handle_drag(self, sl: Slice, pos: QPointF) -> None:
        assert self._drag_origin and self._slice_origin
        ox, oy, ow, oh = self._slice_origin
        delta = (pos - QPointF(self._drag_origin)) / self._scale
        dx, dy = int(delta.x()), int(delta.y())
        x, y, w, h = ox, oy, ow, oh
        handle = self._handle
        if handle == "move":
            x, y = ox + dx, oy + dy
        else:
            if handle and "e" in handle:
                w = max(1, ow + dx)
            if handle and "w" in handle:
                x = ox + dx
                w = max(1, ow - dx)
            if handle and "s" in handle:
                h = max(1, oh + dy)
            if handle and "n" in handle:
                y = oy + dy
                h = max(1, oh - dy)
        sl.set_rect(x, y, w, h)
        sl.clamp_to(self._doc.width, self._doc.height)
        self._doc.dirty = True

    def _nudge_selected(self, e: QKeyEvent) -> None:
        if not self._doc or not self._selected_id:
            return
        sl = self._doc.find_slice(self._selected_id)
        if not sl or sl.locked:
            return
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self._ensure_snapshot()
        dx = dy = 0
        if e.key() == Qt.Key.Key_Left:
            dx = -step
        elif e.key() == Qt.Key.Key_Right:
            dx = step
        elif e.key() == Qt.Key.Key_Up:
            dy = -step
        elif e.key() == Qt.Key.Key_Down:
            dy = step
        sl.set_rect(sl.x + dx, sl.y + dy, sl.w, sl.h)
        sl.clamp_to(self._doc.width, self._doc.height)
        self._doc.dirty = True
        self.slicesChanged.emit()
        self.update()
