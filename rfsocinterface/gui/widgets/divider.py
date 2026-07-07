"""Straight-line dividers for organizing the GUI."""

from PySide6.QtWidgets import QFrame, QSizePolicy


class HLine(QFrame):
    """Horizontal dividing line."""

    def __init__(self):
        """Initialize an HLine."""
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)


class VLine(QFrame):
    """Vertical dividing line."""

    def __init__(self):
        """Initialize a VLine."""
        super().__init__()
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
