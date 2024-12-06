# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'controller.ui'
##
## Created by: Qt User Interface Compiler version 6.7.3
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
from PySide6.QtWidgets import (QApplication, QButtonGroup, QGridLayout, QSizePolicy,
    QToolButton, QWidget)
from . import icons_rc

class Ui_Controller(object):
    def setupUi(self, Controller):
        if not Controller.objectName():
            Controller.setObjectName(u"Controller")
        Controller.resize(280, 250)
        Controller.setMinimumSize(QSize(280, 250))
        self.gridLayout = QGridLayout(Controller)
        self.gridLayout.setObjectName(u"gridLayout")
        self.up_toolButton = QToolButton(Controller)
        self.buttonGroup = QButtonGroup(Controller)
        self.buttonGroup.setObjectName(u"buttonGroup")
        self.buttonGroup.addButton(self.up_toolButton)
        self.up_toolButton.setObjectName(u"up_toolButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.up_toolButton.sizePolicy().hasHeightForWidth())
        self.up_toolButton.setSizePolicy(sizePolicy)
        self.up_toolButton.setMinimumSize(QSize(30, 30))
        self.up_toolButton.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        icon = QIcon()
        icon.addFile(u":/icons/up.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.up_toolButton.setIcon(icon)
        self.up_toolButton.setIconSize(QSize(50, 50))
        self.up_toolButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.gridLayout.addWidget(self.up_toolButton, 1, 1, 1, 1)

        self.down_toolButton = QToolButton(Controller)
        self.buttonGroup.addButton(self.down_toolButton)
        self.down_toolButton.setObjectName(u"down_toolButton")
        sizePolicy.setHeightForWidth(self.down_toolButton.sizePolicy().hasHeightForWidth())
        self.down_toolButton.setSizePolicy(sizePolicy)
        self.down_toolButton.setMinimumSize(QSize(30, 30))
        icon1 = QIcon()
        icon1.addFile(u":/icons/down.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.down_toolButton.setIcon(icon1)
        self.down_toolButton.setIconSize(QSize(50, 50))
        self.down_toolButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.gridLayout.addWidget(self.down_toolButton, 3, 1, 1, 1)

        self.right_toolButton = QToolButton(Controller)
        self.buttonGroup.addButton(self.right_toolButton)
        self.right_toolButton.setObjectName(u"right_toolButton")
        sizePolicy.setHeightForWidth(self.right_toolButton.sizePolicy().hasHeightForWidth())
        self.right_toolButton.setSizePolicy(sizePolicy)
        self.right_toolButton.setMinimumSize(QSize(30, 30))
        icon2 = QIcon()
        icon2.addFile(u":/icons/right.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.right_toolButton.setIcon(icon2)
        self.right_toolButton.setIconSize(QSize(50, 50))
        self.right_toolButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.gridLayout.addWidget(self.right_toolButton, 2, 2, 1, 1)

        self.left_toolButton = QToolButton(Controller)
        self.buttonGroup.addButton(self.left_toolButton)
        self.left_toolButton.setObjectName(u"left_toolButton")
        sizePolicy.setHeightForWidth(self.left_toolButton.sizePolicy().hasHeightForWidth())
        self.left_toolButton.setSizePolicy(sizePolicy)
        self.left_toolButton.setMinimumSize(QSize(30, 30))
        self.left_toolButton.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        icon3 = QIcon()
        icon3.addFile(u":/icons/left.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.left_toolButton.setIcon(icon3)
        self.left_toolButton.setIconSize(QSize(50, 50))
        self.left_toolButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.gridLayout.addWidget(self.left_toolButton, 2, 0, 1, 1)


        self.retranslateUi(Controller)

        QMetaObject.connectSlotsByName(Controller)
    # setupUi

    def retranslateUi(self, Controller):
        Controller.setWindowTitle(QCoreApplication.translate("Controller", u"Form", None))
        self.up_toolButton.setText(QCoreApplication.translate("Controller", u"Negative ZA", None))
        self.down_toolButton.setText(QCoreApplication.translate("Controller", u"Positive ZA", None))
        self.right_toolButton.setText(QCoreApplication.translate("Controller", u"Positive AZ", None))
        self.left_toolButton.setText(QCoreApplication.translate("Controller", u"Negative AZ", None))
    # retranslateUi

