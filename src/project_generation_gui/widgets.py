from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel
from qtpy.QtCore import Signal
from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import QPlainTextEdit, QTreeWidget, QTreeWidgetItem


class TextEditor(QPlainTextEdit):
    document_text_changed = Signal(str)

    def __init__(self, path: Path, text: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.setPlainText(text)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.textChanged.connect(lambda: self.document_text_changed.emit(self.toPlainText()))
class ObjectTree(QTreeWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Value"])
        self.setAlternatingRowColors(True)

    def set_value(self, value: Any) -> None:
        self.clear()
        self._append(self.invisibleRootItem(), "root", value)
        self.expandToDepth(1)

    def _append(self, parent: QTreeWidgetItem, name: str, value: Any) -> None:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="python", by_alias=True)
        elif is_dataclass(value) and not isinstance(value, type):
            value = {field.name: getattr(value, field.name) for field in fields(value)}

        if isinstance(value, Mapping):
            item = QTreeWidgetItem([name, f"{{{len(value)}}}"])
            parent.addChild(item)
            for key, child in value.items():
                self._append(item, str(key), child)
        elif isinstance(value, (list, tuple)):
            item = QTreeWidgetItem([name, f"[{len(value)}]"])
            parent.addChild(item)
            for index, child in enumerate(value):
                self._append(item, f"[{index}]", child)
        else:
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, UUID):
                value = str(value)
            parent.addChild(QTreeWidgetItem([name, "" if value is None else str(value)]))
