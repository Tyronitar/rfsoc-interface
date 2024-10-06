# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'lodiagnostics.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDialog,
    QDialogButtonBox, QSizePolicy, QVBoxLayout, QWidget)

from rfsocinterface.ui.canvas import DiagnosticsCanvas

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"Dialog")
        Dialog.resize(800, 600)
        self.verticalLayout_2 = QVBoxLayout(Dialog)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.flagged_checkBox = QCheckBox(Dialog)
        self.flagged_checkBox.setObjectName(u"flagged_checkBox")

        self.verticalLayout_2.addWidget(self.flagged_checkBox)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.canvas = DiagnosticsCanvas(Dialog)
        self.canvas.setObjectName(u"canvas")

        self.verticalLayout.addWidget(self.canvas)


        self.verticalLayout_2.addLayout(self.verticalLayout)

        self.buttonBox = QDialogButtonBox(Dialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)

        self.verticalLayout_2.addWidget(self.buttonBox)


        self.retranslateUi(Dialog)

        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("Dialog", u"LO Sweep Diagnostics", None))
        self.flagged_checkBox.setText(QCoreApplication.translate("Dialog", u"Only Show Flagged Resonators", None))
    # retranslateUi

