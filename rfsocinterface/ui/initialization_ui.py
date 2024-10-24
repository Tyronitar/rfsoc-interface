# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'initialization.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
    QScrollArea, QSizePolicy, QSpacerItem, QToolButton,
    QVBoxLayout, QWidget)

class Ui_InitializationTabWidget(object):
    def setupUi(self, InitializationTabWidget):
        if not InitializationTabWidget.objectName():
            InitializationTabWidget.setObjectName(u"InitializationTabWidget")
        InitializationTabWidget.resize(504, 430)
        self.gridLayout = QGridLayout(InitializationTabWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.scrollArea = QScrollArea(InitializationTabWidget)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setAutoFillBackground(True)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 484, 358))
        self.scrollAreaWidgetContents.setAutoFillBackground(True)
        self.verticalLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.gridLayout.addWidget(self.scrollArea, 4, 0, 1, 1)

        self.frame = QFrame(InitializationTabWidget)
        self.frame.setObjectName(u"frame")
        self.frame.setFrameShape(QFrame.Shape.Panel)
        self.frame.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout = QHBoxLayout(self.frame)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.add_toolButton = QToolButton(self.frame)
        self.add_toolButton.setObjectName(u"add_toolButton")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
        self.add_toolButton.setIcon(icon)
        self.add_toolButton.setIconSize(QSize(20, 20))
        self.add_toolButton.setAutoRaise(True)

        self.horizontalLayout.addWidget(self.add_toolButton)

        self.delete_toolButton = QToolButton(self.frame)
        self.delete_toolButton.setObjectName(u"delete_toolButton")
        icon1 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListRemove))
        self.delete_toolButton.setIcon(icon1)
        self.delete_toolButton.setIconSize(QSize(20, 20))
        self.delete_toolButton.setAutoRaise(True)

        self.horizontalLayout.addWidget(self.delete_toolButton)


        self.gridLayout.addWidget(self.frame, 5, 0, 1, 1)


        self.retranslateUi(InitializationTabWidget)

        QMetaObject.connectSlotsByName(InitializationTabWidget)
    # setupUi

    def retranslateUi(self, InitializationTabWidget):
        InitializationTabWidget.setWindowTitle(QCoreApplication.translate("InitializationTabWidget", u"Form", None))
        self.add_toolButton.setText(QCoreApplication.translate("InitializationTabWidget", u"...", None))
        self.delete_toolButton.setText(QCoreApplication.translate("InitializationTabWidget", u"...", None))
    # retranslateUi

