# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'initialization.ui'
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QGroupBox, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget)

from rfsocinterface.channel_settings import ChannelSettingsWidget

class Ui_InitializationTabWidget(object):
    def setupUi(self, InitializationTabWidget):
        if not InitializationTabWidget.objectName():
            InitializationTabWidget.setObjectName(u"InitializationTabWidget")
        InitializationTabWidget.resize(504, 430)
        self.gridLayout = QGridLayout(InitializationTabWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.scrollArea = QScrollArea(InitializationTabWidget)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setAutoFillBackground(True)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 484, 410))
        self.scrollAreaWidgetContents.setAutoFillBackground(True)
        self.verticalLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.channel1_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.channel1_groupBox.setObjectName(u"channel1_groupBox")
        self.verticalLayout_2 = QVBoxLayout(self.channel1_groupBox)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.channel1_settings_widget = ChannelSettingsWidget(self.channel1_groupBox)
        self.channel1_settings_widget.setObjectName(u"channel1_settings_widget")

        self.verticalLayout_2.addWidget(self.channel1_settings_widget)


        self.verticalLayout.addWidget(self.channel1_groupBox)

        self.channel2_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.channel2_groupBox.setObjectName(u"channel2_groupBox")
        self.verticalLayout_4 = QVBoxLayout(self.channel2_groupBox)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.channel2_settings_widget = ChannelSettingsWidget(self.channel2_groupBox)
        self.channel2_settings_widget.setObjectName(u"channel2_settings_widget")

        self.verticalLayout_4.addWidget(self.channel2_settings_widget)


        self.verticalLayout.addWidget(self.channel2_groupBox)

        self.channel3_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.channel3_groupBox.setObjectName(u"channel3_groupBox")
        self.verticalLayout_5 = QVBoxLayout(self.channel3_groupBox)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.channel3_settings_widget = ChannelSettingsWidget(self.channel3_groupBox)
        self.channel3_settings_widget.setObjectName(u"channel3_settings_widget")

        self.verticalLayout_5.addWidget(self.channel3_settings_widget)


        self.verticalLayout.addWidget(self.channel3_groupBox)

        self.channel4_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.channel4_groupBox.setObjectName(u"channel4_groupBox")
        self.verticalLayout_6 = QVBoxLayout(self.channel4_groupBox)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.channel4_settings_widget = ChannelSettingsWidget(self.channel4_groupBox)
        self.channel4_settings_widget.setObjectName(u"channel4_settings_widget")

        self.verticalLayout_6.addWidget(self.channel4_settings_widget)


        self.verticalLayout.addWidget(self.channel4_groupBox)

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.gridLayout.addWidget(self.scrollArea, 4, 0, 1, 1)


        self.retranslateUi(InitializationTabWidget)

        QMetaObject.connectSlotsByName(InitializationTabWidget)
    # setupUi

    def retranslateUi(self, InitializationTabWidget):
        InitializationTabWidget.setWindowTitle(QCoreApplication.translate("InitializationTabWidget", u"Form", None))
        self.channel1_groupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Channel 1", None))
        self.channel2_groupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Channel 2", None))
        self.channel3_groupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Channel 3", None))
        self.channel4_groupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Channel 4", None))
    # retranslateUi

