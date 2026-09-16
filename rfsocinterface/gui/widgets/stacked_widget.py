"""StackedWidget that changes size to its current widget."""

from typing import override

from PySide6.QtWidgets import QStackedWidget


class ResizingStackedWidget(QStackedWidget):
    """QStackedWidget that changes size to its current widget."""

    @override
    def sizeHint(self):
        return self.currentWidget().sizeHint()

    @override
    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint()
