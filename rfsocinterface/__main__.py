"""Main entry point for the rfsocinterface package."""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from rfsocinterface.ui.full_ui_ui import Ui_MainWindow


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)

if __name__ == '__main__':
    app = QApplication()

    w = MainWindow()
    w.show()
    app.exec()
