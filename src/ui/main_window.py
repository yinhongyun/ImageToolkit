from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction, QKeySequence, QDragEnterEvent, QDropEvent, QImage
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QToolBar,
    QFileDialog,
    QMessageBox,
    QLabel,
    QStatusBar,
    QApplication,
)

from core.commands import CommandStack
from core.detector import detect_slices
from core.document import Document
from core.exporter import export_slices
from core.project_io import (
    open_image_as_document,
    open_rgba_as_document,
    persist_rgba_png,
    save_project,
    load_project,
)
from services.settings_store import SettingsStore
from ui.canvas_view import CanvasView, ToolMode
from ui.panels.tool_panel import ToolPanel
from ui.panels.slice_panel import SlicePanel
from ui.panels.export_panel import ExportPanel


IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;所有文件 (*.*)"
PROJECT_FILTER = "ImageToolkit 工程 (*.itk);;所有文件 (*.*)"


class DetectWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, doc: Document) -> None:
        super().__init__()
        self._doc = doc

    def run(self) -> None:
        try:
            slices = detect_slices(
                self._doc.image_rgba,
                self._doc.detect,
                self._doc.background,
                name_prefix=self._doc.name_prefix,
            )
            self.finished.emit(slices)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ImageToolkit")
        self.resize(1400, 860)
        self.setAcceptDrops(True)

        self.settings = SettingsStore()
        self.doc: Optional[Document] = None
        self.commands = CommandStack()
        self._thread: Optional[QThread] = None
        self._live_geo_pending = False

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._connect()
        self._restore_window()
        self._set_actions_enabled(False)
        self.statusBar().showMessage("就绪 — 打开 / 拖入 / Ctrl+V 粘贴图片")

        export_dir = self.settings.last_export_dir()
        if export_dir:
            self.export_panel.set_export_dir(export_dir)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("CentralRoot")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.tool_panel = ToolPanel()
        self.tool_panel.setMinimumWidth(220)
        self.tool_panel.setMaximumWidth(300)

        self.canvas = CanvasView()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.slice_panel = SlicePanel()
        self.export_panel = ExportPanel()
        rl.addWidget(self.slice_panel, stretch=1)
        rl.addWidget(self.export_panel)
        right.setMinimumWidth(280)
        right.setMaximumWidth(420)

        splitter.addWidget(self.tool_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 860, 320])

        sb = QStatusBar()
        self.setStatusBar(sb)
        self._coord_label = QLabel("")
        self._zoom_label = QLabel("100%")
        self._count_label = QLabel("")
        sb.addPermanentWidget(self._coord_label)
        sb.addPermanentWidget(self._zoom_label)
        sb.addPermanentWidget(self._count_label)

    def _build_menus(self) -> None:
        m_file = self.menuBar().addMenu("文件")
        self.act_open = QAction("打开图片…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_proj = QAction("打开工程…", self)
        self.act_save_proj = QAction("保存工程", self)
        self.act_save_proj.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save_proj_as = QAction("工程另存为…", self)
        self.act_export = QAction("导出…", self)
        self.act_export.setShortcut("Ctrl+E")
        self.act_quit = QAction("退出", self)
        self.act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_paste = QAction("粘贴图片", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        m_file.addAction(self.act_open)
        m_file.addAction(self.act_paste)
        m_file.addAction(self.act_open_proj)
        m_file.addSeparator()
        m_file.addAction(self.act_save_proj)
        m_file.addAction(self.act_save_proj_as)
        m_file.addSeparator()
        self._recent_menu = m_file.addMenu("最近打开")
        m_file.addSeparator()
        m_file.addAction(self.act_export)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)
        self._rebuild_recent_menu()

        m_edit = self.menuBar().addMenu("编辑")
        self.act_undo = QAction("撤销", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_redo = QAction("重做", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_detect = QAction("自动识别", self)
        self.act_detect.setShortcut("A")
        self.act_delete = QAction("删除切片", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        m_edit.addAction(self.act_paste)
        m_edit.addSeparator()
        m_edit.addAction(self.act_detect)
        m_edit.addAction(self.act_delete)

        m_view = self.menuBar().addMenu("视图")
        self.act_fit = QAction("适应窗口", self)
        self.act_fit.setShortcut("Ctrl+0")
        self.act_100 = QAction("实际像素", self)
        self.act_100.setShortcut("Ctrl+1")
        m_view.addAction(self.act_fit)
        m_view.addAction(self.act_100)

        m_help = self.menuBar().addMenu("帮助")
        act_about = QAction("关于 ImageToolkit", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.act_open)
        tb.addAction(self.act_paste)
        tb.addAction(self.act_detect)
        tb.addSeparator()
        self.act_tool_select = QAction("选择", self)
        self.act_tool_select.setCheckable(True)
        self.act_tool_select.setChecked(True)
        self.act_tool_select.setShortcut("V")
        self.act_tool_draw = QAction("画框", self)
        self.act_tool_draw.setCheckable(True)
        self.act_tool_draw.setShortcut("R")
        tb.addAction(self.act_tool_select)
        tb.addAction(self.act_tool_draw)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_export)

    def _connect(self) -> None:
        self.act_open.triggered.connect(self.open_image_dialog)
        self.act_paste.triggered.connect(self.paste_image)
        self.act_open_proj.triggered.connect(self.open_project_dialog)
        self.act_save_proj.triggered.connect(self.save_project)
        self.act_save_proj_as.triggered.connect(self.save_project_as)
        self.act_export.triggered.connect(lambda: self.do_export(selected_only=True))
        self.act_quit.triggered.connect(self.close)
        self.act_undo.triggered.connect(self.undo)
        self.act_redo.triggered.connect(self.redo)
        self.act_detect.triggered.connect(self.run_detect)
        self.act_delete.triggered.connect(self.delete_selected)
        self.act_fit.triggered.connect(self.canvas.fit_view)
        self.act_100.triggered.connect(lambda: self.canvas.set_zoom(1.0))

        self.act_tool_select.triggered.connect(lambda: self._set_tool(ToolMode.SELECT))
        self.act_tool_draw.triggered.connect(lambda: self._set_tool(ToolMode.DRAW))

        self.tool_panel.toolChanged.connect(self._set_tool)
        self.tool_panel.redetectRequested.connect(self.run_detect)
        self.tool_panel.paramsChanged.connect(self._sync_params)
        self.tool_panel.previewFlagsChanged.connect(self._sync_preview_flags)

        self.canvas.sliceSelected.connect(self._on_canvas_select)
        self.canvas.slicesChanged.connect(self._on_slices_changed)
        self.canvas.sliceGeometryLive.connect(self._on_slice_geometry_live)
        self.canvas.statusMessage.connect(self.statusBar().showMessage)
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.canvas.requestSnapshot.connect(self._snapshot)

        self.slice_panel.selectionChanged.connect(self.canvas.set_selected)
        self.slice_panel.sliceEdited.connect(self._on_slice_panel_edited)
        self.slice_panel.deleteRequested.connect(self.delete_selected)

        self.export_panel.exportSelected.connect(lambda: self.do_export(selected_only=True))
        self.export_panel.exportAll.connect(lambda: self.do_export(selected_only=False))

    def _set_tool(self, tool: ToolMode) -> None:
        self.canvas.set_tool(tool)
        self.act_tool_select.setChecked(tool == ToolMode.SELECT)
        self.act_tool_draw.setChecked(tool == ToolMode.DRAW)
        if tool == ToolMode.SELECT:
            self.tool_panel.radio_select.setChecked(True)
        else:
            self.tool_panel.radio_draw.setChecked(True)

    def _set_actions_enabled(self, on: bool) -> None:
        for a in (
            self.act_save_proj,
            self.act_save_proj_as,
            self.act_export,
            self.act_detect,
            self.act_delete,
            self.act_fit,
            self.act_100,
            self.act_tool_select,
            self.act_tool_draw,
        ):
            a.setEnabled(on)
        self.tool_panel.setEnabled(on)
        self.slice_panel.setEnabled(on)
        self.export_panel.setEnabled(on)

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        for path in self.settings.recent_files():
            act = QAction(path, self)
            act.triggered.connect(lambda checked=False, p=path: self.open_path(p))
            self._recent_menu.addAction(act)
        if not self.settings.recent_files():
            empty = QAction("（空）", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)

    # ----- document lifecycle -----
    def _confirm_discard(self) -> bool:
        if self.doc and self.doc.dirty:
            r = QMessageBox.question(
                self,
                "未保存的更改",
                "当前工作有未保存更改，是否继续？\n（可先保存为 .itk 工程）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return r == QMessageBox.StandardButton.Yes
        return True

    def open_image_dialog(self) -> None:
        start = self.settings.last_open_dir() or ""
        path, _ = QFileDialog.getOpenFileName(self, "打开图片", start, IMAGE_FILTER)
        if path:
            self.open_path(path)

    def open_project_dialog(self) -> None:
        start = self.settings.last_open_dir() or ""
        path, _ = QFileDialog.getOpenFileName(self, "打开工程", start, PROJECT_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if not self._confirm_discard():
            return
        try:
            p = Path(path)
            if p.suffix.lower() == ".itk":
                doc = load_project(path)
            else:
                doc = open_image_as_document(path)
            self._load_document(doc)
            self.settings.add_recent(str(p.resolve()))
            self.settings.set_last_open_dir(str(p.parent))
            self._rebuild_recent_menu()
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))

    def _load_document(self, doc: Document) -> None:
        self.doc = doc
        self.commands.clear()
        self.canvas.set_document(doc)
        self.slice_panel.set_document(doc)
        self.tool_panel.load_from_doc(doc)
        self._set_actions_enabled(True)
        self._update_title()
        self._update_count()
        self.statusBar().showMessage(
            f"已打开 {Path(doc.image_path).name if doc.image_path else ''} — 点「自动识别」或用手动画框"
        )

    def save_project(self) -> None:
        if not self.doc:
            return
        if self.doc.project_path:
            try:
                self.tool_panel.read_detect_into(self.doc)
                save_project(self.doc, self.doc.project_path)
                self._update_title()
                self.statusBar().showMessage(f"已保存 {self.doc.project_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
        else:
            self.save_project_as()

    def save_project_as(self) -> None:
        if not self.doc:
            return
        start = self.doc.project_path or (self.settings.last_open_dir() or "")
        path, _ = QFileDialog.getSaveFileName(self, "工程另存为", start, PROJECT_FILTER)
        if not path:
            return
        if not path.lower().endswith(".itk"):
            path += ".itk"
        try:
            self.tool_panel.read_detect_into(self.doc)
            save_project(self.doc, path)
            self.settings.add_recent(path)
            self._rebuild_recent_menu()
            self._update_title()
            self.statusBar().showMessage(f"已保存 {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _update_title(self) -> None:
        name = "ImageToolkit"
        if self.doc and self.doc.image_path:
            base = Path(self.doc.image_path).name
            mark = " *" if self.doc.dirty else ""
            proj = f" — {Path(self.doc.project_path).name}" if self.doc.project_path else ""
            name = f"{base}{mark}{proj} — ImageToolkit"
        self.setWindowTitle(name)

    # ----- detect / edit -----
    def _sync_params(self) -> None:
        if self.doc:
            self.tool_panel.read_detect_into(self.doc)
            self.canvas.invalidate_detect_cache()
            self.slice_panel.refresh_preview()

    def _sync_preview_flags(self) -> None:
        self.canvas.set_show_boxes(self.tool_panel.chk_boxes.isChecked())
        self.canvas.set_show_labels(self.tool_panel.chk_labels.isChecked())

    def paste_image(self) -> None:
        clip = QApplication.clipboard()
        md = clip.mimeData()
        qimg: Optional[QImage] = None
        if md and md.hasImage():
            img = clip.image()
            if isinstance(img, QImage) and not img.isNull():
                qimg = img
            else:
                pix = clip.pixmap()
                if pix and not pix.isNull():
                    qimg = pix.toImage()
        if qimg is None or qimg.isNull():
            # Also accept file path copied from explorer
            if md and md.hasUrls():
                for url in md.urls():
                    path = url.toLocalFile()
                    if path and Path(path).is_file():
                        self.open_path(path)
                        return
            self.statusBar().showMessage("剪贴板里没有图片")
            return
        if not self._confirm_discard():
            return
        try:
            rgba = self._qimage_to_rgba(qimg)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_dir = Path(tempfile.gettempdir()) / "ImageToolkit"
            tmp_path = tmp_dir / f"paste_{stamp}.png"
            persist_rgba_png(rgba, str(tmp_path))
            doc = open_rgba_as_document(rgba, name_prefix="paste", image_path=str(tmp_path))
            self._load_document(doc)
            self.statusBar().showMessage(f"已粘贴图片 {qimg.width()}×{qimg.height()} — 可点「自动识别」")
        except Exception as e:
            QMessageBox.critical(self, "粘贴失败", str(e))

    @staticmethod
    def _qimage_to_rgba(qimg: QImage) -> np.ndarray:
        img = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        ptr = img.constBits()
        buf = np.frombuffer(ptr, dtype=np.uint8, count=bpl * h).reshape(h, bpl)
        rgba = np.ascontiguousarray(buf[:, : w * 4].reshape(h, w, 4))
        return rgba.copy()

    def _snapshot(self) -> None:
        if self.doc:
            self.commands.push(self.doc)
            self._refresh_undo_actions()

    def run_detect(self) -> None:
        if not self.doc or not self.doc.has_image:
            return
        self.tool_panel.read_detect_into(self.doc)
        self.statusBar().showMessage("正在识别…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._snapshot()
        try:
            slices = detect_slices(
                self.doc.image_rgba,
                self.doc.detect,
                self.doc.background,
                name_prefix=self.doc.name_prefix,
            )
            self.doc.slices = slices
            self.doc.dirty = True
            self.canvas.set_document(self.doc)
            self.slice_panel.set_document(self.doc)
            self._update_title()
            self._update_count()
            if not slices:
                self.statusBar().showMessage("未找到可拆区域 — 尝试增大背景容差，或改用手动画框")
                QMessageBox.information(
                    self,
                    "未识别到内容",
                    "没有找到足够大的前景区域。\n\n建议：增大「背景容差」，降低「最小面积」，或使用「手动画框」。",
                )
            else:
                self.statusBar().showMessage(f"识别完成：{len(slices)} 个切片")
                self.canvas.set_selected(slices[0].id)
                self.slice_panel.select_id(slices[0].id)
        except Exception as e:
            QMessageBox.critical(self, "识别失败", str(e))
        finally:
            QApplication.restoreOverrideCursor()
            self._refresh_undo_actions()

    def delete_selected(self) -> None:
        if not self.doc:
            return
        ids = self.slice_panel.selected_ids()
        if not ids and self.canvas.selected_id():
            ids = [self.canvas.selected_id()]
        if not ids:
            return
        self._snapshot()
        for sid in ids:
            self.doc.remove_slice(sid)
        self.canvas.set_selected("")
        self.canvas.update()
        self.slice_panel.refresh_list(keep_selection=False)
        self._update_title()
        self._update_count()
        self._refresh_undo_actions()

    def undo(self) -> None:
        if self.doc and self.commands.undo(self.doc):
            self.canvas.set_document(self.doc)
            self.canvas.set_selected(self.canvas.selected_id())
            self.slice_panel.set_document(self.doc)
            self._update_title()
            self._update_count()
            self._refresh_undo_actions()

    def redo(self) -> None:
        if self.doc and self.commands.redo(self.doc):
            self.canvas.set_document(self.doc)
            self.slice_panel.set_document(self.doc)
            self._update_title()
            self._update_count()
            self._refresh_undo_actions()

    def _refresh_undo_actions(self) -> None:
        self.act_undo.setEnabled(self.commands.can_undo())
        self.act_redo.setEnabled(self.commands.can_redo())

    def _on_canvas_select(self, slice_id: str) -> None:
        if slice_id:
            self.slice_panel.select_id(slice_id)
        self._update_count()

    def _on_slices_changed(self) -> None:
        self.slice_panel.refresh_list(keep_selection=True)
        self.slice_panel.refresh_preview()
        self._update_title()
        self._update_count()
        self._refresh_undo_actions()

    def _on_slice_geometry_live(self) -> None:
        # Throttle spin updates while dragging; skip list/preview rebuild
        if self._live_geo_pending:
            return
        self._live_geo_pending = True

        def _flush() -> None:
            self._live_geo_pending = False
            self.slice_panel.sync_geometry_from_doc()

        from PySide6.QtCore import QTimer

        QTimer.singleShot(50, _flush)

    def _on_slice_panel_edited(self) -> None:
        self.canvas.update()
        self._update_title()
        self._update_count()

    def _on_cursor(self, x: int, y: int) -> None:
        if self.doc and self.doc.has_image:
            if 0 <= x < self.doc.width and 0 <= y < self.doc.height:
                self._coord_label.setText(f"({x}, {y})")
            else:
                self._coord_label.setText("")
        self._zoom_label.setText(f"{int(self.canvas.zoom() * 100)}%")

    def _update_count(self) -> None:
        n = len(self.doc.slices) if self.doc else 0
        self._count_label.setText(f"{n} 个切片" if n else "")

    # ----- export -----
    def do_export(self, selected_only: bool) -> None:
        if not self.doc or not self.doc.has_image:
            return
        if not self.doc.slices:
            QMessageBox.information(self, "导出", "还没有切片。请先自动识别或手动画框。")
            return

        out_dir = self.export_panel.export_dir()
        if not out_dir:
            out_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
            if not out_dir:
                return
            self.export_panel.set_export_dir(out_dir)

        out_dir = str(Path(out_dir).expanduser().resolve())
        self.export_panel.set_export_dir(out_dir)

        self.tool_panel.read_detect_into(self.doc)
        fmt = self.export_panel.format()
        conflict = self.export_panel.conflict_policy()

        if selected_only:
            ids = set(self.slice_panel.selected_ids())
            if ids:
                slices = [s for s in self.doc.slices if s.id in ids]
            else:
                slices = [s for s in self.doc.slices if s.export]
        else:
            slices = list(self.doc.slices)

        if not slices:
            QMessageBox.information(
                self,
                "导出",
                "没有可导出的切片。\n请在列表中勾选，或选中要导出的项，或点「导出全部」。",
            )
            return

        if not fmt.supports_alpha:
            r = QMessageBox.question(
                self,
                "格式提示",
                f"{fmt.value.upper()} 不支持透明，将铺白底导出。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        try:
            results = export_slices(
                self.doc.image_rgba,
                slices,
                out_dir,
                fmt,
                self.doc.background,
                conflict=conflict,
                only_export_flagged=False,
            )
            self.settings.set_last_export_dir(out_dir)
            written = [r for r in results if not r.skipped]
            skipped = [r for r in results if r.skipped]
            if not written:
                detail = "\n".join(f"- {r.message or r.path}" for r in skipped) or "未知原因"
                QMessageBox.warning(self, "导出失败", f"没有成功写出任何文件。\n\n{detail}")
                return

            msg = f"已导出 {len(written)} 个文件到\n{out_dir}"
            if skipped:
                msg += f"\n跳过 {len(skipped)} 个"
            box = QMessageBox(self)
            box.setWindowTitle("导出完成")
            box.setText(msg)
            open_btn = box.addButton("打开文件夹", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == open_btn:
                os.startfile(out_dir)  # noqa: S606 — Windows
            self.statusBar().showMessage(f"导出完成：{len(written)} 个文件 → {out_dir}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ----- drag drop -----
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        urls = e.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.open_path(path)

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self.settings.set_window_geometry(bytes(self.saveGeometry()))
        self.settings.set_window_state(bytes(self.saveState()))
        super().closeEvent(event)

    def _restore_window(self) -> None:
        geo = self.settings.window_geometry()
        if geo:
            self.restoreGeometry(geo)
        st = self.settings.window_state()
        if st:
            self.restoreState(st)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "关于 ImageToolkit",
            "ImageToolkit\n\n"
            "本地图片拆分工具：自动/手动拆图、边缘预览、背景透明、多格式导出。\n"
            "工程文件扩展名：.itk\n\n"
            "快捷键：Ctrl+V 粘贴 · A 自动识别 · V 选择 · R 画框 · Ctrl+E 导出 · 空格拖动画布 · C 隐藏边框",
        )
