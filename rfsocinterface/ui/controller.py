from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt

from rfsocinterface.ui.controller_ui import Ui_Controller

class Controller(QWidget, Ui_Controller):
    """Widget for Handling directional input"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
