"""Custom scroll area widgets."""

from typing import override

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QScrollArea


class ExpandingScrollArea(QScrollArea):
    """Scroll area that grows with its contents until constrained."""

    @override
    def sizeHint(self) -> QSize:
        widget = self.widget()
        if widget is None:
            return super().sizeHint()

        content_size = widget.sizeHint()

        frame = 2 * self.frameWidth()

        return QSize(
            content_size.width() + frame,
            content_size.height() + frame,
        )
