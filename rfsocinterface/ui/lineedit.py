from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QWidget

class ClickableLineEdit(QLineEdit):
    clicked = Signal()

    def __init__(self, parent: QWidget=None):
        super().__init__(parent=parent)
    
    def mousePressEvent(self, arg__1):
        self.clicked.emit()
        return super().mousePressEvent(arg__1)