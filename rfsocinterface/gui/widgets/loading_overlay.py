"""Code for a loading overlay."""

from typing import override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.gui.widgets.spinner import (
    STANDARD_STICKY_SPINNER_SETTINGS,
    StickyWaitingSpinner,
)
from rfsocinterface.gui.widgets.tool_buttons import RoundedToolButton


class LoadingOverlay(QWidget):
    """An overlay to display over the GUI while a slow action is performed."""

    finished = Signal()

    def __init__(self, parent=None):
        """Initialize a LoadingOverlay."""
        super().__init__(parent=parent)

        self._cancelled = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.fillcolor = QColor(0, 0, 0, 150)

        layout = QVBoxLayout(self)

        self.close_button = RoundedToolButton(parent=self)
        close_icon = QIcon()
        close_icon.addFile(
            ':/icons/close.svg', QSize(14, 14), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.close_button.setIcon(close_icon)
        self.close_button.clicked.connect(self.cancel)

        self.spinner = StickyWaitingSpinner(
            parent=self, center_on_parent=False, **STANDARD_STICKY_SPINNER_SETTINGS
        )
        label_font = QFont('Arial', 20, QFont.Weight.Medium)
        self.label = QLabel('Loading...', parent=self)
        self.label.setFont(label_font)
        self.label.setStyleSheet('color: white')
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self.setLayout(layout)
        self.hide()

    def text(self) -> str:
        """Return the text in the overlay's label."""
        return self.label.text()

    def set_text(self, text: str):
        """Set the text in the overlay's label."""
        self.label.setText(text)

    def _update_position(self):
        """Move the overlay to be on top of its parent."""
        self.resize(self.parent().size())
        self.move(0, 0)

    def cancel(self):
        """Cancel the active task."""
        self._cancelled = True
        self.stop()

    def start(self):
        """Start the loading animation."""
        if self.parentWidget():
            self._update_position()
            self.spinner.start()
            self.show()

    def stop(self):
        """Stop the loading animation."""
        self.spinner.stop()
        self.hide()
        self.finished.emit()

    @override
    def paintEvent(self, event):
        self._update_position()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.fillcolor)
