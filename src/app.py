#!/usr/bin/env python3
"""ImageToolkit entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


def _resource_root() -> Path:
    # PyInstaller extracts bundled files under sys._MEIPASS
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _load_style(app: QApplication) -> None:
    qss = _resource_root() / "resources" / "styles" / "app.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))


def main() -> int:
    # Ensure src/ is on path when launched as script
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ImageToolkit")
    app.setOrganizationName("ImageToolkit")
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    _load_style(app)

    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
