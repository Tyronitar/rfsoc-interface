# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'controller.ui'
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
from PySide6.QtWidgets import (QApplication, QButtonGroup, QGridLayout, QPushButton,
    QSizePolicy, QWidget)
from . import icons_rc

class Ui_Controller(object):
    def setupUi(self, Controller):
        if not Controller.objectName():
            Controller.setObjectName(u"Controller")
        Controller.resize(216, 204)
        Controller.setMinimumSize(QSize(200, 200))
        self.gridLayout = QGridLayout(Controller)
        self.gridLayout.setObjectName(u"gridLayout")
        self.down_pushButton = QPushButton(Controller)
        self.buttonGroup = QButtonGroup(Controller)
        self.buttonGroup.setObjectName(u"buttonGroup")
        self.buttonGroup.addButton(self.down_pushButton)
        self.down_pushButton.setObjectName(u"down_pushButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.down_pushButton.sizePolicy().hasHeightForWidth())
        self.down_pushButton.setSizePolicy(sizePolicy)
        self.down_pushButton.setMinimumSize(QSize(30, 30))
        icon = QIcon()
        icon.addFile(u":/icons/down.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.down_pushButton.setIcon(icon)
        self.down_pushButton.setIconSize(QSize(50, 50))

        self.gridLayout.addWidget(self.down_pushButton, 3, 1, 1, 1, Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop)

        self.left_pushButton = QPushButton(Controller)
        self.buttonGroup.addButton(self.left_pushButton)
        self.left_pushButton.setObjectName(u"left_pushButton")
        sizePolicy.setHeightForWidth(self.left_pushButton.sizePolicy().hasHeightForWidth())
        self.left_pushButton.setSizePolicy(sizePolicy)
        self.left_pushButton.setMinimumSize(QSize(30, 30))
        icon1 = QIcon()
        icon1.addFile(u":/icons/left.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.left_pushButton.setIcon(icon1)
        self.left_pushButton.setIconSize(QSize(50, 50))

        self.gridLayout.addWidget(self.left_pushButton, 2, 0, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.right_pushButton = QPushButton(Controller)
        self.buttonGroup.addButton(self.right_pushButton)
        self.right_pushButton.setObjectName(u"right_pushButton")
        sizePolicy.setHeightForWidth(self.right_pushButton.sizePolicy().hasHeightForWidth())
        self.right_pushButton.setSizePolicy(sizePolicy)
        self.right_pushButton.setMinimumSize(QSize(30, 30))
        icon2 = QIcon()
        icon2.addFile(u":/icons/right.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.right_pushButton.setIcon(icon2)
        self.right_pushButton.setIconSize(QSize(50, 50))

        self.gridLayout.addWidget(self.right_pushButton, 2, 2, 1, 1, Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

        self.up_pushButton = QPushButton(Controller)
        self.buttonGroup.addButton(self.up_pushButton)
        self.up_pushButton.setObjectName(u"up_pushButton")
        sizePolicy.setHeightForWidth(self.up_pushButton.sizePolicy().hasHeightForWidth())
        self.up_pushButton.setSizePolicy(sizePolicy)
        self.up_pushButton.setMinimumSize(QSize(30, 30))
        icon3 = QIcon()
        icon3.addFile(u":/icons/up.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.up_pushButton.setIcon(icon3)
        self.up_pushButton.setIconSize(QSize(50, 50))

        self.gridLayout.addWidget(self.up_pushButton, 1, 1, 1, 1, Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignBottom)


        self.retranslateUi(Controller)

        QMetaObject.connectSlotsByName(Controller)
    # setupUi

    def retranslateUi(self, Controller):
        Controller.setWindowTitle(QCoreApplication.translate("Controller", u"Form", None))
        self.down_pushButton.setText("")
        self.left_pushButton.setText("")
        self.right_pushButton.setText("")
        self.up_pushButton.setText("")
    # retranslateUi

