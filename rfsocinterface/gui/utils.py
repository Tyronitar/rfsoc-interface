"""General utils for GUI code."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMainWindow

# Useful Aliases
tr = QCoreApplication.translate


DATA_ROUTINE_FUNCTION_WIDGET_ARGS = {}


def move_to_center(win: QMainWindow, screen: QScreen):
    """Move a window to the center of the screen."""
    win.move(screen.geometry().center() - win.geometry().center())
