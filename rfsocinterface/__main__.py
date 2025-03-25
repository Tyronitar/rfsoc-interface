"""Main entry point for the rfsocinterface package."""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QScreen
from rfsocinterface.gui.main_window import MainWindow

def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())

if __name__ == '__main__':
    app = QApplication()
    screen = app.primaryScreen()

    # w = MainWindow("settings.toml")
    w = MainWindow()
    w.setScreen(screen)
    move_to_center(w, screen)
    w.show()

    app.exec()
