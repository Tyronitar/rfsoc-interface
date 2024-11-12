from PySide6.QtWidgets import QWidget, QMainWindow, QApplication
from PySide6.QtCore import Qt
from rfsocinterface.ui.telescope_control_ui import Ui_TelescopeControlWidget as Ui_TelescopeControlWidget
from kidpy import kidpy

class StopMotion(Exception):
    """Exception for handling pressing of the stop button."""
    def __init__(self, *args):
        super().__init__(*args)

class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self):
        pass

class TelescopeControlWidget(QWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""
    def __init__(self, kpy: kidpy, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)
        self.kpy = kpy
        self.ctrl = TelescopeMotorController()
    
    def update_ui(self):
        # TODO: Update the values to show current position etc.
        pass


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
