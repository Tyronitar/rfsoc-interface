# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loresonator.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

from rfsocinterface.ui.canvas import ResonatorCanvas
from . import icons_rc

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"Dialog")
        Dialog.resize(633, 532)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Dialog.sizePolicy().hasHeightForWidth())
        Dialog.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(Dialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.canvas = ResonatorCanvas(Dialog)
        self.canvas.setObjectName(u"canvas")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.canvas.sizePolicy().hasHeightForWidth())
        self.canvas.setSizePolicy(sizePolicy1)

        self.verticalLayout_2.addWidget(self.canvas)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.old_freq_label = QLabel(Dialog)
        self.old_freq_label.setObjectName(u"old_freq_label")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.old_freq_label)

        self.old_freq_value_label = QLabel(Dialog)
        self.old_freq_value_label.setObjectName(u"old_freq_value_label")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.old_freq_value_label)

        self.new_freq_label = QLabel(Dialog)
        self.new_freq_label.setObjectName(u"new_freq_label")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.new_freq_label)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.new_freq_lineEdit = QLineEdit(Dialog)
        self.new_freq_lineEdit.setObjectName(u"new_freq_lineEdit")
        self.new_freq_lineEdit.setMaximumSize(QSize(200, 16777215))

        self.horizontalLayout_2.addWidget(self.new_freq_lineEdit)

        self.refit_pushButton = QPushButton(Dialog)
        self.refit_pushButton.setObjectName(u"refit_pushButton")

        self.horizontalLayout_2.addWidget(self.refit_pushButton)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)


        self.formLayout.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout_2)

        self.delta_label = QLabel(Dialog)
        self.delta_label.setObjectName(u"delta_label")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.delta_label)

        self.delta_value_label = QLabel(Dialog)
        self.delta_value_label.setObjectName(u"delta_value_label")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.delta_value_label)

        self.depth_label = QLabel(Dialog)
        self.depth_label.setObjectName(u"depth_label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.depth_label)

        self.depth_value_label = QLabel(Dialog)
        self.depth_value_label.setObjectName(u"depth_value_label")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.depth_value_label)


        self.verticalLayout_2.addLayout(self.formLayout)

        self.buttonBox = QDialogButtonBox(Dialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Reset|QDialogButtonBox.StandardButton.Save)

        self.verticalLayout_2.addWidget(self.buttonBox)


        self.verticalLayout.addLayout(self.verticalLayout_2)

#if QT_CONFIG(shortcut)
        self.new_freq_label.setBuddy(self.new_freq_lineEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(Dialog)

        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("Dialog", u"Resonator", None))
        self.old_freq_label.setText(QCoreApplication.translate("Dialog", u"Old Frequency (MHz):", None))
        self.old_freq_value_label.setText("")
        self.new_freq_label.setText(QCoreApplication.translate("Dialog", u"New Frequency (MHz):", None))
        self.refit_pushButton.setText(QCoreApplication.translate("Dialog", u"Refit", None))
        self.delta_label.setText(QCoreApplication.translate("Dialog", u"\u0394f (KHz):", None))
        self.delta_value_label.setText("")
        self.depth_label.setText(QCoreApplication.translate("Dialog", u"Resonance Depth:", None))
        self.depth_value_label.setText("")
    # retranslateUi

