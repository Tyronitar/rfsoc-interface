# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'imaging.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QGridLayout, QGroupBox, QLabel, QPushButton,
    QSizePolicy, QWidget)

from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from rfsocinterface.gui.widgets.save_location import SaveLocationWidget

class Ui_ImagingWidget(object):
    def setupUi(self, ImagingWidget):
        if not ImagingWidget.objectName():
            ImagingWidget.setObjectName(u"ImagingWidget")
        ImagingWidget.resize(201, 189)
        self.gridLayout = QGridLayout(ImagingWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(9, 9, 9, 9)
        self.pushButton = QPushButton(ImagingWidget)
        self.pushButton.setObjectName(u"pushButton")

        self.gridLayout.addWidget(self.pushButton, 7, 1, 1, 1)

        self.channel_comboBox = CheckableComboBox(ImagingWidget)
        self.channel_comboBox.setObjectName(u"channel_comboBox")

        self.gridLayout.addWidget(self.channel_comboBox, 0, 1, 1, 1)

        self.show_checkBox = QCheckBox(ImagingWidget)
        self.show_checkBox.setObjectName(u"show_checkBox")

        self.gridLayout.addWidget(self.show_checkBox, 5, 0, 1, 1)

        self.dither_groupBox = QGroupBox(ImagingWidget)
        self.dither_groupBox.setObjectName(u"dither_groupBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.dither_groupBox.sizePolicy().hasHeightForWidth())
        self.dither_groupBox.setSizePolicy(sizePolicy)
        self.gridLayout_2 = QGridLayout(self.dither_groupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.dither_label = QLabel(self.dither_groupBox)
        self.dither_label.setObjectName(u"dither_label")

        self.gridLayout_2.addWidget(self.dither_label, 0, 0, 1, 1)

        self.dither_comboBox = QComboBox(self.dither_groupBox)
        self.dither_comboBox.setObjectName(u"dither_comboBox")

        self.gridLayout_2.addWidget(self.dither_comboBox, 0, 1, 1, 1)

        self.dither_line = QFrame(self.dither_groupBox)
        self.dither_line.setObjectName(u"dither_line")
        self.dither_line.setFrameShape(QFrame.Shape.HLine)
        self.dither_line.setFrameShadow(QFrame.Shadow.Sunken)

        self.gridLayout_2.addWidget(self.dither_line, 1, 0, 1, 2)


        self.gridLayout.addWidget(self.dither_groupBox, 2, 0, 1, 2)

        self.channels_label = QLabel(ImagingWidget)
        self.channels_label.setObjectName(u"channels_label")

        self.gridLayout.addWidget(self.channels_label, 0, 0, 1, 1)

        self.save_location_widget = SaveLocationWidget(ImagingWidget)
        self.save_location_widget.setObjectName(u"save_location_widget")
        sizePolicy.setHeightForWidth(self.save_location_widget.sizePolicy().hasHeightForWidth())
        self.save_location_widget.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.save_location_widget, 1, 0, 1, 2)


        self.retranslateUi(ImagingWidget)

        QMetaObject.connectSlotsByName(ImagingWidget)
    # setupUi

    def retranslateUi(self, ImagingWidget):
        ImagingWidget.setWindowTitle(QCoreApplication.translate("ImagingWidget", u"Form", None))
        self.pushButton.setText(QCoreApplication.translate("ImagingWidget", u"Start", None))
        self.show_checkBox.setText(QCoreApplication.translate("ImagingWidget", u"Show image", None))
        self.dither_groupBox.setTitle(QCoreApplication.translate("ImagingWidget", u"Dithering", None))
        self.dither_label.setText(QCoreApplication.translate("ImagingWidget", u"Dither pattern:", None))
        self.channels_label.setText(QCoreApplication.translate("ImagingWidget", u"Channels:", None))
    # retranslateUi

