from __future__ import annotations

from copy import deepcopy
from typing import List, Optional

from .document import Document, Slice


class CommandStack:
    def __init__(self, limit: int = 80) -> None:
        self._undo: List[List[Slice]] = []
        self._redo: List[List[Slice]] = []
        self._limit = limit

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, doc: Document) -> None:
        self._undo.append(deepcopy(doc.slices))
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, doc: Document) -> bool:
        if not self._undo:
            return False
        self._redo.append(deepcopy(doc.slices))
        doc.slices = self._undo.pop()
        doc.dirty = True
        return True

    def redo(self, doc: Document) -> bool:
        if not self._redo:
            return False
        self._undo.append(deepcopy(doc.slices))
        doc.slices = self._redo.pop()
        doc.dirty = True
        return True
