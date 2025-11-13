# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'data_streaming.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QWidget)

from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from rfsocinterface.gui.widgets.save_location import SaveLocationWidget

class Ui_DataStreamingWidget(object):
    def setupUi(self, DataStreamingWidget):
        if not DataStreamingWidget.objectName():
            DataStreamingWidget.setObjectName(u"DataStreamingWidget")
        DataStreamingWidget.resize(308, 187)
        self.gridLayout = QGridLayout(DataStreamingWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.routines_pushButton = QPushButton(DataStreamingWidget)
        self.routines_pushButton.setObjectName(u"routines_pushButton")

        self.gridLayout.addWidget(self.routines_pushButton, 2, 2, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 1, 0, 1, 1)

        self.groupBox = QGroupBox(DataStreamingWidget)
        self.groupBox.setObjectName(u"groupBox")
        self.gridLayout_2 = QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.duration_label = QLabel(self.groupBox)
        self.duration_label.setObjectName(u"duration_label")

        self.gridLayout_2.addWidget(self.duration_label, 1, 0, 1, 1)

        self.duration_lineEdit = QLineEdit(self.groupBox)
        self.duration_lineEdit.setObjectName(u"duration_lineEdit")

        self.gridLayout_2.addWidget(self.duration_lineEdit, 1, 1, 1, 1)

        self.save_location_widget = SaveLocationWidget(self.groupBox)
        self.save_location_widget.setObjectName(u"save_location_widget")

        self.gridLayout_2.addWidget(self.save_location_widget, 4, 0, 1, 3)

        self.channel_comboBox = CheckableComboBox(self.groupBox)
        self.channel_comboBox.setObjectName(u"channel_comboBox")

        self.gridLayout_2.addWidget(self.channel_comboBox, 0, 1, 1, 1)

        self.channels_label = QLabel(self.groupBox)
        self.channels_label.setObjectName(u"channels_label")

        self.gridLayout_2.addWidget(self.channels_label, 0, 0, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_2.addItem(self.horizontalSpacer, 0, 2, 1, 1)


        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 3)

        self.auto_process_checkBox = QCheckBox(DataStreamingWidget)
        self.auto_process_checkBox.setObjectName(u"auto_process_checkBox")
        self.auto_process_checkBox.setChecked(True)

        self.gridLayout.addWidget(self.auto_process_checkBox, 2, 0, 1, 1)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer_2, 2, 1, 1, 1)

        self.start_pushButton = QPushButton(DataStreamingWidget)
        self.start_pushButton.setObjectName(u"start_pushButton")

        self.gridLayout.addWidget(self.start_pushButton, 3, 2, 1, 1)


        self.retranslateUi(DataStreamingWidget)

        QMetaObject.connectSlotsByName(DataStreamingWidget)
    # setupUi

    def retranslateUi(self, DataStreamingWidget):
        DataStreamingWidget.setWindowTitle(QCoreApplication.translate("DataStreamingWidget", u"Form", None))
        self.routines_pushButton.setText(QCoreApplication.translate("DataStreamingWidget", u"Data Routines...", None))
        self.groupBox.setTitle(QCoreApplication.translate("DataStreamingWidget", u"Data Streaming Settings", None))
        self.duration_label.setText(QCoreApplication.translate("DataStreamingWidget", u"Duration (s):", None))
        self.duration_lineEdit.setPlaceholderText(QCoreApplication.translate("DataStreamingWidget", u"5", None))
        self.channels_label.setText(QCoreApplication.translate("DataStreamingWidget", u"Channels:", None))
        self.auto_process_checkBox.setText(QCoreApplication.translate("DataStreamingWidget", u"Auto process data", None))
        self.start_pushButton.setText(QCoreApplication.translate("DataStreamingWidget", u"Start", None))
    # retranslateUi

