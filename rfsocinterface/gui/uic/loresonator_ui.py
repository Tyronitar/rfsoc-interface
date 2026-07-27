# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loresonator.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QDialog,
    QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

from rfsocinterface.gui.widgets.canvas import ResonatorCanvas
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

        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.new_freq_label = QLabel(Dialog)
        self.new_freq_label.setObjectName(u"new_freq_label")

        self.gridLayout.addWidget(self.new_freq_label, 1, 0, 1, 1)

        self.onres_radioButton = QRadioButton(Dialog)
        self.resonance_buttonGroup = QButtonGroup(Dialog)
        self.resonance_buttonGroup.setObjectName(u"resonance_buttonGroup")
        self.resonance_buttonGroup.addButton(self.onres_radioButton)
        self.onres_radioButton.setObjectName(u"onres_radioButton")

        self.gridLayout.addWidget(self.onres_radioButton, 4, 0, 1, 1)

        self.depth_value_label = QLabel(Dialog)
        self.depth_value_label.setObjectName(u"depth_value_label")

        self.gridLayout.addWidget(self.depth_value_label, 3, 1, 1, 1)

        self.delta_value_label = QLabel(Dialog)
        self.delta_value_label.setObjectName(u"delta_value_label")

        self.gridLayout.addWidget(self.delta_value_label, 2, 1, 1, 1)

        self.old_freq_label = QLabel(Dialog)
        self.old_freq_label.setObjectName(u"old_freq_label")

        self.gridLayout.addWidget(self.old_freq_label, 0, 0, 1, 1)

        self.delta_label = QLabel(Dialog)
        self.delta_label.setObjectName(u"delta_label")

        self.gridLayout.addWidget(self.delta_label, 2, 0, 1, 1)

        self.offres_radioButton = QRadioButton(Dialog)
        self.resonance_buttonGroup.addButton(self.offres_radioButton)
        self.offres_radioButton.setObjectName(u"offres_radioButton")

        self.gridLayout.addWidget(self.offres_radioButton, 4, 1, 1, 1)

        self.depth_label = QLabel(Dialog)
        self.depth_label.setObjectName(u"depth_label")

        self.gridLayout.addWidget(self.depth_label, 3, 0, 1, 1)

        self.old_freq_value_label = QLabel(Dialog)
        self.old_freq_value_label.setObjectName(u"old_freq_value_label")

        self.gridLayout.addWidget(self.old_freq_value_label, 0, 1, 1, 1)

        self.bad_res_radioButton = QRadioButton(Dialog)
        self.resonance_buttonGroup.addButton(self.bad_res_radioButton)
        self.bad_res_radioButton.setObjectName(u"bad_res_radioButton")

        self.gridLayout.addWidget(self.bad_res_radioButton, 4, 3, 1, 1)

        self.collided_res_radioButton = QRadioButton(Dialog)
        self.resonance_buttonGroup.addButton(self.collided_res_radioButton)
        self.collided_res_radioButton.setObjectName(u"collided_res_radioButton")

        self.gridLayout.addWidget(self.collided_res_radioButton, 4, 2, 1, 1)

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


        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 1, 1, 3)


        self.verticalLayout_2.addLayout(self.gridLayout)

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
        self.new_freq_label.setText(QCoreApplication.translate("Dialog", u"New Frequency (MHz):", None))
        self.onres_radioButton.setText(QCoreApplication.translate("Dialog", u"On Resonance", None))
        self.depth_value_label.setText("")
        self.delta_value_label.setText("")
        self.old_freq_label.setText(QCoreApplication.translate("Dialog", u"Old Frequency (MHz):", None))
        self.delta_label.setText(QCoreApplication.translate("Dialog", u"\u0394f (KHz):", None))
        self.offres_radioButton.setText(QCoreApplication.translate("Dialog", u"Off Resonance", None))
        self.depth_label.setText(QCoreApplication.translate("Dialog", u"Resonance Depth:", None))
        self.old_freq_value_label.setText("")
        self.bad_res_radioButton.setText(QCoreApplication.translate("Dialog", u"Bad Resonance", None))
        self.collided_res_radioButton.setText(QCoreApplication.translate("Dialog", u"Collided Resonance", None))
        self.refit_pushButton.setText(QCoreApplication.translate("Dialog", u"Refit", None))
    # retranslateUi

