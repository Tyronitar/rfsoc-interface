"""Variants of the QLineEdit."""
from typing import override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QWidget


class ClickableLineEdit(QLineEdit):
    """A QLineEdit that emits signals when clicked."""
    clicked = Signal()

    def __init__(self, parent: QWidget = None):
        """Initialize a ClickableLineEdit."""
        super().__init__(parent=parent)

    @override
    def mousePressEvent(self, arg__1):
        self.clicked.emit()
        return super().mousePressEvent(arg__1)
