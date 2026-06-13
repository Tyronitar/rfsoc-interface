"""Code for a loading overlay."""

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
        return self.label.text()

    def setText(self, text: str):
        self.label.setText(text)

    def _update_position(self):
        self.resize(self.parent().size())
        self.move(0, 0)

    def cancel(self):
        self._cancelled = True
        self.stop()

    def start(self):
        if self.parentWidget():
            self._update_position()
            self.spinner.start()
            self.show()

    def stop(self):
        self.spinner.stop()
        self.hide()
        self.finished.emit()

    def paintEvent(self, event):
        self._update_position()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.fillcolor)


if __name__ == '__main__':
    from PySide6.QtWidgets import (
        QApplication,
        QGridLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QWidget,
    )

    class MainWindow(QMainWindow):
        def __init__(self, parent=None):
            super().__init__(parent)

            self.container = QWidget(parent=self)
            layout = QGridLayout(parent=self.container)
            self.label = QLabel('Lorem ipsum:', parent=self.container)
            self.lineEdit = QLineEdit(parent=self.container)
            self.push_button = QPushButton('Click me to load', parent=self.container)

            self.loading_overlay = LoadingOverlay(self)

            self.push_button.clicked.connect(self.loading_overlay.start)

            layout.addWidget(self.label, 0, 0)
            layout.addWidget(self.lineEdit, 0, 1, 1, 2)
            layout.addWidget(self.push_button, 1, 1)

            self.container.setLayout(layout)
            self.setCentralWidget(self.container)

        def toggle_loading_screen(self):
            self.loading_overlay.show()

    app = QApplication()
    win = MainWindow()
    win.show()
    app.exec()
