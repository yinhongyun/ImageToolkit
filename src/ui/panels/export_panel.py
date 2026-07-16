from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QComboBox,
    QLabel,
    QFileDialog,
    QFormLayout,
)

from core.exporter import ExportFormat, ConflictPolicy


class ExportPanel(QWidget):
    exportSelected = Signal()
    exportAll = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("导出")
        form = QFormLayout(box)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择导出目录…")
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(36)
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(btn_browse)
        form.addRow("目录", path_row)

        self.fmt = QComboBox()
        self.fmt.addItem("PNG（透明，推荐）", ExportFormat.PNG)
        self.fmt.addItem("WebP（透明）", ExportFormat.WEBP)
        self.fmt.addItem("JPEG（无透明）", ExportFormat.JPEG)
        self.fmt.addItem("BMP（无透明）", ExportFormat.BMP)
        form.addRow("格式", self.fmt)

        self.conflict = QComboBox()
        self.conflict.addItem("自动重命名", ConflictPolicy.RENAME)
        self.conflict.addItem("覆盖", ConflictPolicy.OVERWRITE)
        self.conflict.addItem("跳过已存在", ConflictPolicy.SKIP)
        form.addRow("重名时", self.conflict)

        hint = QLabel("JPEG/BMP 会铺白底后保存")
        hint.setObjectName("HintLabel")
        form.addRow(hint)

        row = QHBoxLayout()
        self.btn_sel = QPushButton("导出选中/勾选")
        self.btn_sel.setObjectName("PrimaryButton")
        self.btn_all = QPushButton("导出全部")
        row.addWidget(self.btn_sel)
        row.addWidget(self.btn_all)
        form.addRow(row)

        layout.addWidget(box)
        self.btn_sel.clicked.connect(self.exportSelected.emit)
        self.btn_all.clicked.connect(self.exportAll.emit)
        self.fmt.currentIndexChanged.connect(self._on_fmt)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择导出目录", self.path_edit.text())
        if d:
            self.path_edit.setText(d)

    def _on_fmt(self) -> None:
        fmt: ExportFormat = self.fmt.currentData()
        if not fmt.supports_alpha:
            self.fmt.setToolTip("该格式不支持透明通道，将合成到白底")
        else:
            self.fmt.setToolTip("")

    def export_dir(self) -> str:
        return self.path_edit.text().strip()

    def set_export_dir(self, path: str) -> None:
        self.path_edit.setText(path)

    def format(self) -> ExportFormat:
        # PySide stores str-Enum as plain str in QVariant — coerce back
        data = self.fmt.currentData()
        if isinstance(data, ExportFormat):
            return data
        if data is None:
            return ExportFormat.PNG
        try:
            return ExportFormat(str(data))
        except ValueError:
            return ExportFormat.PNG

    def conflict_policy(self) -> ConflictPolicy:
        data = self.conflict.currentData()
        if isinstance(data, ConflictPolicy):
            return data
        if data is None:
            return ConflictPolicy.RENAME
        try:
            return ConflictPolicy(str(data))
        except ValueError:
            return ConflictPolicy.RENAME
