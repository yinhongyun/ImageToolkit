from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QFormLayout,
    QLabel,
    QCheckBox,
)

from core.document import Document
from core.transparency import apply_transparency
from ui.widgets.checkerboard import PreviewLabel


class SlicePanel(QWidget):
    selectionChanged = Signal(str)
    sliceEdited = Signal()
    deleteRequested = Signal()
    renameRequested = Signal(str, str)  # id, name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanel")
        self._doc: Optional[Document] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        lst = QGroupBox("切片列表")
        ll = QVBoxLayout(lst)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        ll.addWidget(self.list)
        row = QHBoxLayout()
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("DangerButton")
        self.btn_all = QPushButton("全选导出")
        self.btn_none = QPushButton("全不选")
        row.addWidget(self.btn_del)
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_none)
        ll.addLayout(row)
        layout.addWidget(lst, stretch=2)

        props = QGroupBox("当前切片")
        form = QFormLayout(props)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("名称")
        form.addRow("名称", self.name_edit)
        self.spin_x = QSpinBox()
        self.spin_y = QSpinBox()
        self.spin_w = QSpinBox()
        self.spin_h = QSpinBox()
        for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            s.setRange(0, 100000)
        form.addRow("X", self.spin_x)
        form.addRow("Y", self.spin_y)
        form.addRow("宽", self.spin_w)
        form.addRow("高", self.spin_h)
        self.chk_export = QCheckBox("导出此项")
        self.chk_export.setChecked(True)
        self.chk_lock = QCheckBox("锁定（不可拖拽）")
        form.addRow(self.chk_export)
        form.addRow(self.chk_lock)
        layout.addWidget(props)

        prev = QGroupBox("透明预览")
        pl = QVBoxLayout(prev)
        self.preview = PreviewLabel()
        self.preview.setMinimumHeight(160)
        pl.addWidget(self.preview)
        hint = QLabel("与导出使用相同去底参数")
        hint.setObjectName("HintLabel")
        pl.addWidget(hint)
        layout.addWidget(prev, stretch=1)

        self.list.itemSelectionChanged.connect(self._on_list_sel)
        self.list.itemChanged.connect(self._on_item_changed)
        self.btn_del.clicked.connect(self.deleteRequested.emit)
        self.btn_all.clicked.connect(lambda: self._set_all_export(True))
        self.btn_none.clicked.connect(lambda: self._set_all_export(False))
        self.name_edit.editingFinished.connect(self._apply_props)
        for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            s.valueChanged.connect(self._apply_props)
        self.chk_export.toggled.connect(self._apply_props)
        self.chk_lock.toggled.connect(self._apply_props)

    def set_document(self, doc: Optional[Document]) -> None:
        self._doc = doc
        self.refresh_list()

    def refresh_list(self, keep_selection: bool = True) -> None:
        sel = self.selected_ids() if keep_selection else []
        self._updating = True
        self.list.clear()
        if not self._doc:
            self._updating = False
            self._clear_props()
            return
        for i, sl in enumerate(self._doc.slices):
            item = QListWidgetItem(f"{sl.name}  ({sl.w}×{sl.h})")
            item.setData(Qt.ItemDataRole.UserRole, sl.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if sl.export else Qt.CheckState.Unchecked)
            c = self._doc.color_for_index(i)
            item.setForeground(QBrush(QColor(*c)))
            self.list.addItem(item)
            if sl.id in sel:
                item.setSelected(True)
        self._updating = False
        if not sel and self.list.count():
            self.list.setCurrentRow(0)
        self._sync_props_from_selection()
        self.refresh_preview()

    def selected_ids(self) -> list:
        ids = []
        for item in self.list.selectedItems():
            ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def select_id(self, slice_id: str) -> None:
        self._updating = True
        self.list.clearSelection()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == slice_id:
                item.setSelected(True)
                self.list.setCurrentItem(item)
                break
        self._updating = False
        self._sync_props_from_selection()
        self.refresh_preview()

    def _on_list_sel(self) -> None:
        if self._updating:
            return
        ids = self.selected_ids()
        self.selectionChanged.emit(ids[0] if ids else "")
        self._sync_props_from_selection()
        self.refresh_preview()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating or not self._doc:
            return
        sl = self._doc.find_slice(item.data(Qt.ItemDataRole.UserRole))
        if sl:
            sl.export = item.checkState() == Qt.CheckState.Checked
            self._doc.dirty = True
            self.sliceEdited.emit()

    def _set_all_export(self, on: bool) -> None:
        if not self._doc:
            return
        for sl in self._doc.slices:
            sl.export = on
        self._doc.dirty = True
        self.refresh_list()
        self.sliceEdited.emit()

    def _clear_props(self) -> None:
        self._updating = True
        self.name_edit.clear()
        for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            s.setValue(0)
        self.preview.set_rgba(None)
        self._updating = False

    def _sync_props_from_selection(self) -> None:
        if not self._doc:
            self._clear_props()
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            self._updating = True
            self.name_edit.setEnabled(False)
            for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
                s.setEnabled(False)
            self._updating = False
            return
        sl = self._doc.find_slice(ids[0])
        if not sl:
            return
        self._updating = True
        self.name_edit.setEnabled(True)
        for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            s.setEnabled(not sl.locked)
        self.name_edit.setText(sl.name)
        self.spin_x.setValue(sl.x)
        self.spin_y.setValue(sl.y)
        self.spin_w.setValue(sl.w)
        self.spin_h.setValue(sl.h)
        self.chk_export.setChecked(sl.export)
        self.chk_lock.setChecked(sl.locked)
        self._updating = False

    def sync_geometry_from_doc(self) -> None:
        """Lightweight update while dragging — spins only, no list/preview rebuild."""
        if not self._doc or self._updating:
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        sl = self._doc.find_slice(ids[0])
        if not sl:
            return
        self._updating = True
        self.spin_x.setValue(sl.x)
        self.spin_y.setValue(sl.y)
        self.spin_w.setValue(sl.w)
        self.spin_h.setValue(sl.h)
        self._updating = False

    def _apply_props(self) -> None:
        if self._updating or not self._doc:
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        sl = self._doc.find_slice(ids[0])
        if not sl:
            return
        new_name = self.name_edit.text().strip() or sl.name
        if new_name != sl.name:
            sl.name = new_name
        if not sl.locked:
            sl.set_rect(self.spin_x.value(), self.spin_y.value(), self.spin_w.value(), self.spin_h.value())
            sl.clamp_to(self._doc.width, self._doc.height)
        sl.export = self.chk_export.isChecked()
        sl.locked = self.chk_lock.isChecked()
        self._doc.dirty = True
        self.sliceEdited.emit()
        # refresh list text without losing selection
        self.refresh_list(keep_selection=True)

    def refresh_preview(self) -> None:
        if not self._doc or not self._doc.has_image:
            self.preview.set_rgba(None)
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            self.preview.set_rgba(None)
            return
        sl = self._doc.find_slice(ids[0])
        if not sl:
            self.preview.set_rgba(None)
            return
        rgba = apply_transparency(self._doc.image_rgba, self._doc.background, sl.rect)
        self.preview.set_rgba(rgba)
