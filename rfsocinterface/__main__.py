"""Main entry point for the rfsocinterface package."""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy
from PySide6.QtCore import Qt

from rfsocinterface.ui.full_ui_ui import Ui_MainWindow


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)
        self.tabWidget.currentChanged.connect(self.resize_to_current)
        # Do this to 
        self.tabWidget.setCurrentIndex(0)
        self.resize_to_current(0)
    
    def resize_to_current(self, index: int):
        for i in range(self.tabWidget.count()):
            tab = self.tabWidget.widget(i)
            if i != index:
                tab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        curr_tab = self.tabWidget.widget(index)
        curr_tab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # curr_tab.resize(curr_tab.minimumSizeHint())
        # curr_tab.adjustSize()
        # self.resize(self.minimumSizeHint())
        # self.adjustSize()


if __name__ == '__main__':
    app = QApplication()

    w = MainWindow()
    w.show()
    app.exec()
