"""Various bespoke tool buttons."""
from PySide6.QtWidgets import QToolButton


class RoundedToolButton(QToolButton):
    """A tool button with rounded corners."""
    def __init__(
        self,
        size: int=25,
        radius_fraction: float=0.25,
        background_color: str='#efefef',
        pressed_color: str='#b8b8b8',
        border_color: str='#767676',
        parent=None,
        **kwargs,
    ):
        super().__init__(parent=parent, **kwargs)

        self.setFixedSize(size, size)
        radius = int(size * radius_fraction)
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {background_color};
                border-radius: {radius}px;
                border: 2px solid {border_color};
            }}
            QToolButton:pressed {{
                background-color: {pressed_color};
            }}
        """)


class CircularToolButton(RoundedToolButton):
    """A tool button shaped like a circle."""
    def __init__(
        self,
        size: int=25,
        background_color: str='#efefef',
        pressed_color: str='#b8b8b8',
        border_color: str='#767676',
        parent=None,
        **kwargs,
    ):
        super().__init__(size, radius_fraction=0.5, background_color=background_color, pressed_color=pressed_color, border_color=border_color, parent=parent, **kwargs)
