from PySide6.QtWidgets import QWidget, QMainWindow, QApplication
from PySide6.QtCore import Qt
from rfsocinterface.ui.telescope_control_ui import Ui_MainWindow as Ui_TelescopeWindow

class TelescopeControlWindow(QMainWindow, Ui_TelescopeWindow):
    """Window for controlling telescope motion."""
    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)


if __name__ == '__main__':
    app = QApplication()

    win = TelescopeControlWindow()
    win.show()
    app.exec()
