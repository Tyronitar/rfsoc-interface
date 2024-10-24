# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'file_upload.ui'
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
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLineEdit, QPushButton,
    QSizePolicy, QToolButton, QWidget)
from . import icons_rc

class Ui_FileUploadWidget(object):
    def setupUi(self, FileUploadWidget):
        if not FileUploadWidget.objectName():
            FileUploadWidget.setObjectName(u"FileUploadWidget")
        FileUploadWidget.resize(260, 42)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(FileUploadWidget.sizePolicy().hasHeightForWidth())
        FileUploadWidget.setSizePolicy(sizePolicy)
        FileUploadWidget.setMinimumSize(QSize(0, 0))
        self.horizontalLayout = QHBoxLayout(FileUploadWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.lineEdit = QLineEdit(FileUploadWidget)
        self.lineEdit.setObjectName(u"lineEdit")

        self.horizontalLayout.addWidget(self.lineEdit)

        self.pushButton = QPushButton(FileUploadWidget)
        self.pushButton.setObjectName(u"pushButton")

        self.horizontalLayout.addWidget(self.pushButton)

        self.toolButton = QToolButton(FileUploadWidget)
        self.toolButton.setObjectName(u"toolButton")
        self.toolButton.setEnabled(False)
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.toolButton.setIcon(icon)

        self.horizontalLayout.addWidget(self.toolButton)


        self.retranslateUi(FileUploadWidget)

        QMetaObject.connectSlotsByName(FileUploadWidget)
    # setupUi

    def retranslateUi(self, FileUploadWidget):
        FileUploadWidget.setWindowTitle(QCoreApplication.translate("FileUploadWidget", u"Form", None))
        self.pushButton.setText(QCoreApplication.translate("FileUploadWidget", u"Browse...", None))
        self.toolButton.setText(QCoreApplication.translate("FileUploadWidget", u"...", None))
    # retranslateUi

