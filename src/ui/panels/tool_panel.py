from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QLabel,
    QSlider,
    QSpinBox,
    QHBoxLayout,
    QCheckBox,
    QPushButton,
    QFormLayout,
)

from ui.canvas_view import ToolMode


class ToolPanel(QWidget):
    toolChanged = Signal(object)
    paramsChanged = Signal()
    redetectRequested = Signal()
    previewFlagsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        tools = QGroupBox("工具")
        tl = QVBoxLayout(tools)
        self._group = QButtonGroup(self)
        self.radio_select = QRadioButton("选择 / 吸附 (V)")
        self.radio_draw = QRadioButton("手动画框 (R)")
        self.radio_select.setChecked(True)
        self._group.addButton(self.radio_select)
        self._group.addButton(self.radio_draw)
        tl.addWidget(self.radio_select)
        tl.addWidget(self.radio_draw)
        hint = QLabel("选择：悬停自动框选，单击确认，拖动手柄调节")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        tl.addWidget(hint)
        layout.addWidget(tools)

        self.radio_select.toggled.connect(self._emit_tool)
        self.radio_draw.toggled.connect(self._emit_tool)

        detect = QGroupBox("检测参数")
        form = QFormLayout(detect)
        self.tol_spin = QSpinBox()
        self.tol_spin.setRange(0, 120)
        self.tol_spin.setValue(28)
        self.tol_spin.setToolTip("越大去底越多，过大会啃掉本体")
        form.addRow("背景容差", self.tol_spin)

        self.min_area = QSpinBox()
        self.min_area.setRange(10, 500000)
        self.min_area.setValue(400)
        form.addRow("最小面积", self.min_area)

        self.padding = QSpinBox()
        self.padding.setRange(0, 64)
        self.padding.setValue(4)
        form.addRow("边距 Padding", self.padding)

        self.merge_gap = QSpinBox()
        self.merge_gap.setRange(0, 80)
        self.merge_gap.setValue(0)
        form.addRow("合并间距", self.merge_gap)

        self.btn_redetect = QPushButton("重新检测")
        self.btn_redetect.setObjectName("PrimaryButton")
        form.addRow(self.btn_redetect)
        layout.addWidget(detect)

        for w in (self.tol_spin, self.min_area, self.padding, self.merge_gap):
            w.valueChanged.connect(self.paramsChanged.emit)
        self.btn_redetect.clicked.connect(self.redetectRequested.emit)

        preview = QGroupBox("预览")
        pl = QVBoxLayout(preview)
        self.chk_boxes = QCheckBox("显示切片边框")
        self.chk_boxes.setChecked(True)
        self.chk_labels = QCheckBox("显示尺寸标注")
        self.chk_labels.setChecked(True)
        self.chk_checker = QCheckBox("透明预览使用棋盘格")
        self.chk_checker.setChecked(True)
        pl.addWidget(self.chk_boxes)
        pl.addWidget(self.chk_labels)
        pl.addWidget(self.chk_checker)
        tip = QLabel("按住 C 可临时隐藏边框对比原图")
        tip.setObjectName("HintLabel")
        pl.addWidget(tip)
        layout.addWidget(preview)

        for c in (self.chk_boxes, self.chk_labels, self.chk_checker):
            c.toggled.connect(self.previewFlagsChanged.emit)

        layout.addStretch(1)

    def _emit_tool(self) -> None:
        if self.radio_select.isChecked():
            self.toolChanged.emit(ToolMode.SELECT)
        else:
            self.toolChanged.emit(ToolMode.DRAW)

    def read_detect_into(self, doc) -> None:
        doc.detect.tolerance = self.tol_spin.value()
        doc.detect.min_area = self.min_area.value()
        doc.detect.padding = self.padding.value()
        doc.detect.merge_gap = self.merge_gap.value()
        doc.background.tolerance = self.tol_spin.value()

    def load_from_doc(self, doc) -> None:
        self.tol_spin.blockSignals(True)
        self.min_area.blockSignals(True)
        self.padding.blockSignals(True)
        self.merge_gap.blockSignals(True)
        self.tol_spin.setValue(doc.detect.tolerance)
        self.min_area.setValue(doc.detect.min_area)
        self.padding.setValue(doc.detect.padding)
        self.merge_gap.setValue(doc.detect.merge_gap)
        self.tol_spin.blockSignals(False)
        self.min_area.blockSignals(False)
        self.padding.blockSignals(False)
        self.merge_gap.blockSignals(False)
