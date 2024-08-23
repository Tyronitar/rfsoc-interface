"""Main entry point for the rfsocinterface package."""

from rfsocinterface.loconfig import LOConfigWindow
from PySide6.QtWidgets import QApplication

if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()