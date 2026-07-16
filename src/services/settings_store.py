from __future__ import annotations

from typing import List

from PySide6.QtCore import QSettings


class SettingsStore:
    def __init__(self) -> None:
        self._s = QSettings("ImageToolkit", "ImageToolkit")

    def recent_files(self) -> List[str]:
        return list(self._s.value("recent", [], list))

    def add_recent(self, path: str) -> None:
        items = [p for p in self.recent_files() if p != path]
        items.insert(0, path)
        self._s.setValue("recent", items[:12])

    def last_export_dir(self) -> str:
        return str(self._s.value("export_dir", "", str))

    def set_last_export_dir(self, path: str) -> None:
        self._s.setValue("export_dir", path)

    def last_open_dir(self) -> str:
        return str(self._s.value("open_dir", "", str))

    def set_last_open_dir(self, path: str) -> None:
        self._s.setValue("open_dir", path)

    def window_geometry(self) -> bytes | None:
        v = self._s.value("geometry")
        return bytes(v) if v is not None else None

    def set_window_geometry(self, data: bytes) -> None:
        self._s.setValue("geometry", data)

    def window_state(self) -> bytes | None:
        v = self._s.value("windowState")
        return bytes(v) if v is not None else None

    def set_window_state(self, data: bytes) -> None:
        self._s.setValue("windowState", data)
