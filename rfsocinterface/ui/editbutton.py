from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QLabel, QSizePolicy, QGridLayout, QSpacerItem, QToolButton, QPushButton
from PySide6.QtCore import QPropertyAnimation, Qt, QRect, QSize
from PySide6.QtGui import QDoubleValidator, QIcon

class ResonatorEditButton(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setLayout(QGridLayout(self))
        self.layout().addItem(
            QSpacerItem(
                20,
                40,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            ),
            0,
            0
        )
        self.layout().addItem(
            QSpacerItem(
                40,
                20,
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Expanding,
            ),
            1,
            1
        )

        self.edit_toolButton = QToolButton(self)
        self.edit_toolButton.setObjectName(u"edit_toolButton")
        self.edit_toolButton.setGeometry(QRect(750, 10, 27, 26))
        self.edit_toolButton.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.edit_toolButton.setAutoFillBackground(False)
        icon = QIcon()
        icon.addFile(u":/icons/edit.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.edit_toolButton.setIcon(icon)
        self.edit_toolButton.setIconSize(QSize(20, 20))

        self.layout().addWidget(self.edit_toolButton, 0, 1)
        self.setStyleSheet('QWidget {background-color: transparent}')