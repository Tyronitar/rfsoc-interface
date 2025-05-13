# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'lodiagnostics.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDialog,
    QDialogButtonBox, QGridLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QWidget)

from rfsocinterface.gui.widgets.canvas import DiagnosticsCanvas

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"Dialog")
        Dialog.resize(594, 517)
        self.gridLayout = QGridLayout(Dialog)
        self.gridLayout.setObjectName(u"gridLayout")
        self.save_plots_pushButton = QPushButton(Dialog)
        self.save_plots_pushButton.setObjectName(u"save_plots_pushButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.save_plots_pushButton.sizePolicy().hasHeightForWidth())
        self.save_plots_pushButton.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.save_plots_pushButton, 4, 2, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.buttonBox = QDialogButtonBox(Dialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Discard|QDialogButtonBox.StandardButton.Save)

        self.gridLayout.addWidget(self.buttonBox, 5, 0, 1, 4)

        self.canvas = DiagnosticsCanvas(Dialog)
        self.canvas.setObjectName(u"canvas")

        self.gridLayout.addWidget(self.canvas, 0, 0, 1, 4)

        self.upload_pushButton = QPushButton(Dialog)
        self.upload_pushButton.setObjectName(u"upload_pushButton")
        sizePolicy.setHeightForWidth(self.upload_pushButton.sizePolicy().hasHeightForWidth())
        self.upload_pushButton.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.upload_pushButton, 4, 0, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 4, 1, 1, 1)

        self.flagged_checkBox = QCheckBox(Dialog)
        self.flagged_checkBox.setObjectName(u"flagged_checkBox")

        self.gridLayout.addWidget(self.flagged_checkBox, 3, 2, 1, 1)

        self.median_shift_label = QLabel(Dialog)
        self.median_shift_label.setObjectName(u"median_shift_label")

        self.gridLayout.addWidget(self.median_shift_label, 3, 0, 1, 1)


        self.retranslateUi(Dialog)

        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("Dialog", u"LO Sweep Diagnostics", None))
        self.save_plots_pushButton.setText(QCoreApplication.translate("Dialog", u"Save Plots...", None))
        self.upload_pushButton.setText(QCoreApplication.translate("Dialog", u"Write updated tone list to RFSoC", None))
        self.flagged_checkBox.setText(QCoreApplication.translate("Dialog", u"Only show flagged resonators", None))
        self.median_shift_label.setText(QCoreApplication.translate("Dialog", u"Median shift (KHz): ", None))
    # retranslateUi

