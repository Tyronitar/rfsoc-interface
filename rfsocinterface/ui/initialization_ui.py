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
from PySide6.QtWidgets import (QApplication, QGridLayout, QScrollArea, QSizePolicy,
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
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 484, 410))
        self.scrollAreaWidgetContents.setAutoFillBackground(True)
        self.verticalLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.gridLayout.addWidget(self.scrollArea, 4, 0, 1, 1)


        self.retranslateUi(InitializationTabWidget)

        QMetaObject.connectSlotsByName(InitializationTabWidget)
    # setupUi

    def retranslateUi(self, InitializationTabWidget):
        InitializationTabWidget.setWindowTitle(QCoreApplication.translate("InitializationTabWidget", u"Form", None))
    # retranslateUi

