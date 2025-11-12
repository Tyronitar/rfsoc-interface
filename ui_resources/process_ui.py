# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'process.ui'
##
## Created by: Qt User Interface Compiler version 6.8.1
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QPushButton,
    QSizePolicy, QWidget)

class Ui_ProcessingWidget(object):
    def setupUi(self, ProcessingWidget):
        if not ProcessingWidget.objectName():
            ProcessingWidget.setObjectName(u"ProcessingWidget")
        ProcessingWidget.resize(306, 43)
        self.horizontalLayout = QHBoxLayout(ProcessingWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.checkBox = QCheckBox(ProcessingWidget)
        self.checkBox.setObjectName(u"checkBox")
        self.checkBox.setChecked(True)

        self.horizontalLayout.addWidget(self.checkBox)

        self.pushButton = QPushButton(ProcessingWidget)
        self.pushButton.setObjectName(u"pushButton")

        self.horizontalLayout.addWidget(self.pushButton)


        self.retranslateUi(ProcessingWidget)
        self.checkBox.clicked["bool"].connect(self.pushButton.setVisible)

        QMetaObject.connectSlotsByName(ProcessingWidget)
    # setupUi

    def retranslateUi(self, ProcessingWidget):
        ProcessingWidget.setWindowTitle(QCoreApplication.translate("ProcessingWidget", u"Form", None))
        self.checkBox.setText(QCoreApplication.translate("ProcessingWidget", u"Process data?", None))
        self.pushButton.setText(QCoreApplication.translate("ProcessingWidget", u"Configure Processing...", None))
    # retranslateUi

