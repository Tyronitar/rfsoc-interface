# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'channel_settings.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialogButtonBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QToolButton, QWidget)

from rfsocinterface.gui.widgets.file_select import FileSelectWidget
from rfsocinterface.gui.widgets.lineedit import ClickableLineEdit
from . import icons_rc

class Ui_ChannelSettingsWidget(object):
    def setupUi(self, ChannelSettingsWidget):
        if not ChannelSettingsWidget.objectName():
            ChannelSettingsWidget.setObjectName(u"ChannelSettingsWidget")
        ChannelSettingsWidget.resize(650, 425)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ChannelSettingsWidget.sizePolicy().hasHeightForWidth())
        ChannelSettingsWidget.setSizePolicy(sizePolicy)
        ChannelSettingsWidget.setMinimumSize(QSize(650, 0))
        self.gridLayout = QGridLayout(ChannelSettingsWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.buttonBox = QDialogButtonBox(ChannelSettingsWidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Reset|QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttonBox.setCenterButtons(False)

        self.gridLayout.addWidget(self.buttonBox, 6, 0, 1, 2, Qt.AlignmentFlag.AlignBottom)

        self.ethernet_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.ethernet_GroupBox.setObjectName(u"ethernet_GroupBox")
        self.eth_gridLayout = QGridLayout(self.ethernet_GroupBox)
        self.eth_gridLayout.setObjectName(u"eth_gridLayout")
        self.eth_dest_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_dest_error_label.setObjectName(u"eth_dest_error_label")
        self.eth_dest_error_label.setWordWrap(True)

        self.eth_gridLayout.addWidget(self.eth_dest_error_label, 3, 1, 1, 1)

        self.eth_port_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_port_error_label.setObjectName(u"eth_port_error_label")

        self.eth_gridLayout.addWidget(self.eth_port_error_label, 7, 1, 1, 1)

        self.eth_mac_label = QLabel(self.ethernet_GroupBox)
        self.eth_mac_label.setObjectName(u"eth_mac_label")

        self.eth_gridLayout.addWidget(self.eth_mac_label, 4, 0, 1, 1)

        self.eth_port_label = QLabel(self.ethernet_GroupBox)
        self.eth_port_label.setObjectName(u"eth_port_label")

        self.eth_gridLayout.addWidget(self.eth_port_label, 6, 0, 1, 1)

        self.eth_port_lineEdit = ClickableLineEdit(self.ethernet_GroupBox)
        self.eth_port_lineEdit.setObjectName(u"eth_port_lineEdit")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.eth_port_lineEdit.sizePolicy().hasHeightForWidth())
        self.eth_port_lineEdit.setSizePolicy(sizePolicy1)

        self.eth_gridLayout.addWidget(self.eth_port_lineEdit, 6, 1, 1, 1)

        self.eth_dest_label = QLabel(self.ethernet_GroupBox)
        self.eth_dest_label.setObjectName(u"eth_dest_label")

        self.eth_gridLayout.addWidget(self.eth_dest_label, 2, 0, 1, 1)

        self.eth_mac_lineEdit = ClickableLineEdit(self.ethernet_GroupBox)
        self.eth_mac_lineEdit.setObjectName(u"eth_mac_lineEdit")
        sizePolicy1.setHeightForWidth(self.eth_mac_lineEdit.sizePolicy().hasHeightForWidth())
        self.eth_mac_lineEdit.setSizePolicy(sizePolicy1)

        self.eth_gridLayout.addWidget(self.eth_mac_lineEdit, 4, 1, 1, 1)

        self.eth_source_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_source_error_label.setObjectName(u"eth_source_error_label")
        self.eth_source_error_label.setWordWrap(True)

        self.eth_gridLayout.addWidget(self.eth_source_error_label, 1, 1, 1, 1)

        self.eth_pushButton = QPushButton(self.ethernet_GroupBox)
        self.eth_pushButton.setObjectName(u"eth_pushButton")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.eth_pushButton.sizePolicy().hasHeightForWidth())
        self.eth_pushButton.setSizePolicy(sizePolicy2)
        self.eth_pushButton.setMinimumSize(QSize(0, 24))

        self.eth_gridLayout.addWidget(self.eth_pushButton, 8, 1, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.eth_source_label = QLabel(self.ethernet_GroupBox)
        self.eth_source_label.setObjectName(u"eth_source_label")

        self.eth_gridLayout.addWidget(self.eth_source_label, 0, 0, 1, 1)

        self.eth_dest_lineEdit = ClickableLineEdit(self.ethernet_GroupBox)
        self.eth_dest_lineEdit.setObjectName(u"eth_dest_lineEdit")
        sizePolicy1.setHeightForWidth(self.eth_dest_lineEdit.sizePolicy().hasHeightForWidth())
        self.eth_dest_lineEdit.setSizePolicy(sizePolicy1)

        self.eth_gridLayout.addWidget(self.eth_dest_lineEdit, 2, 1, 1, 1)

        self.eth_source_lineEdit = ClickableLineEdit(self.ethernet_GroupBox)
        self.eth_source_lineEdit.setObjectName(u"eth_source_lineEdit")
        sizePolicy1.setHeightForWidth(self.eth_source_lineEdit.sizePolicy().hasHeightForWidth())
        self.eth_source_lineEdit.setSizePolicy(sizePolicy1)

        self.eth_gridLayout.addWidget(self.eth_source_lineEdit, 0, 1, 1, 1)

        self.eth_mac_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_mac_error_label.setObjectName(u"eth_mac_error_label")
        self.eth_mac_error_label.setWordWrap(True)

        self.eth_gridLayout.addWidget(self.eth_mac_error_label, 5, 1, 1, 1)


        self.gridLayout.addWidget(self.ethernet_GroupBox, 5, 0, 1, 1)

        self.if_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.if_GroupBox.setObjectName(u"if_GroupBox")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.if_GroupBox.sizePolicy().hasHeightForWidth())
        self.if_GroupBox.setSizePolicy(sizePolicy3)
        self.if_GroupBox.setMaximumSize(QSize(215, 16777215))
        self.if_gridLayout = QGridLayout(self.if_GroupBox)
        self.if_gridLayout.setObjectName(u"if_gridLayout")
        self.rfin_error_label = QLabel(self.if_GroupBox)
        self.rfin_error_label.setObjectName(u"rfin_error_label")

        self.if_gridLayout.addWidget(self.rfin_error_label, 3, 1, 1, 1)

        self.rfout_error_label = QLabel(self.if_GroupBox)
        self.rfout_error_label.setObjectName(u"rfout_error_label")
        sizePolicy.setHeightForWidth(self.rfout_error_label.sizePolicy().hasHeightForWidth())
        self.rfout_error_label.setSizePolicy(sizePolicy)
        self.rfout_error_label.setWordWrap(True)

        self.if_gridLayout.addWidget(self.rfout_error_label, 1, 1, 1, 1)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.rfin_lineEdit = ClickableLineEdit(self.if_GroupBox)
        self.rfin_lineEdit.setObjectName(u"rfin_lineEdit")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfin_lineEdit.setSizePolicy(sizePolicy4)
        self.rfin_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_3.addWidget(self.rfin_lineEdit)

        self.rfin_uploadToolButton = QToolButton(self.if_GroupBox)
        self.rfin_uploadToolButton.setObjectName(u"rfin_uploadToolButton")
        self.rfin_uploadToolButton.setEnabled(True)
        sizePolicy2.setHeightForWidth(self.rfin_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfin_uploadToolButton.setSizePolicy(sizePolicy2)
        self.rfin_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.rfin_uploadToolButton.setIcon(icon)

        self.horizontalLayout_3.addWidget(self.rfin_uploadToolButton)


        self.if_gridLayout.addLayout(self.horizontalLayout_3, 2, 1, 1, 1)

        self.rfinLabel = QLabel(self.if_GroupBox)
        self.rfinLabel.setObjectName(u"rfinLabel")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.rfinLabel.sizePolicy().hasHeightForWidth())
        self.rfinLabel.setSizePolicy(sizePolicy5)

        self.if_gridLayout.addWidget(self.rfinLabel, 2, 0, 1, 1)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.rfout_lineEdit = ClickableLineEdit(self.if_GroupBox)
        self.rfout_lineEdit.setObjectName(u"rfout_lineEdit")
        sizePolicy4.setHeightForWidth(self.rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfout_lineEdit.setSizePolicy(sizePolicy4)
        self.rfout_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_2.addWidget(self.rfout_lineEdit)

        self.rfout_uploadToolButton = QToolButton(self.if_GroupBox)
        self.rfout_uploadToolButton.setObjectName(u"rfout_uploadToolButton")
        self.rfout_uploadToolButton.setEnabled(True)
        sizePolicy2.setHeightForWidth(self.rfout_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfout_uploadToolButton.setSizePolicy(sizePolicy2)
        self.rfout_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.rfout_uploadToolButton.setBaseSize(QSize(25, 25))
        self.rfout_uploadToolButton.setIcon(icon)
        self.rfout_uploadToolButton.setArrowType(Qt.ArrowType.NoArrow)

        self.horizontalLayout_2.addWidget(self.rfout_uploadToolButton)


        self.if_gridLayout.addLayout(self.horizontalLayout_2, 0, 1, 1, 1)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.lo_freq_lineEdit = ClickableLineEdit(self.if_GroupBox)
        self.lo_freq_lineEdit.setObjectName(u"lo_freq_lineEdit")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.lo_freq_lineEdit.sizePolicy().hasHeightForWidth())
        self.lo_freq_lineEdit.setSizePolicy(sizePolicy6)
        self.lo_freq_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_4.addWidget(self.lo_freq_lineEdit)

        self.lo_freq_uploadToolButton = QToolButton(self.if_GroupBox)
        self.lo_freq_uploadToolButton.setObjectName(u"lo_freq_uploadToolButton")
        self.lo_freq_uploadToolButton.setEnabled(True)
        sizePolicy2.setHeightForWidth(self.lo_freq_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.lo_freq_uploadToolButton.setSizePolicy(sizePolicy2)
        self.lo_freq_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.lo_freq_uploadToolButton.setIcon(icon)

        self.horizontalLayout_4.addWidget(self.lo_freq_uploadToolButton)


        self.if_gridLayout.addLayout(self.horizontalLayout_4, 4, 1, 1, 1)

        self.lo_freq_label = QLabel(self.if_GroupBox)
        self.lo_freq_label.setObjectName(u"lo_freq_label")
        sizePolicy5.setHeightForWidth(self.lo_freq_label.sizePolicy().hasHeightForWidth())
        self.lo_freq_label.setSizePolicy(sizePolicy5)

        self.if_gridLayout.addWidget(self.lo_freq_label, 4, 0, 1, 1)

        self.rfoutLabel = QLabel(self.if_GroupBox)
        self.rfoutLabel.setObjectName(u"rfoutLabel")
        sizePolicy5.setHeightForWidth(self.rfoutLabel.sizePolicy().hasHeightForWidth())
        self.rfoutLabel.setSizePolicy(sizePolicy5)

        self.if_gridLayout.addWidget(self.rfoutLabel, 0, 0, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.if_gridLayout.addItem(self.verticalSpacer, 5, 1, 1, 1)


        self.gridLayout.addWidget(self.if_GroupBox, 5, 1, 1, 1)

        self.resonator_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.resonator_GroupBox.setObjectName(u"resonator_GroupBox")
        sizePolicy3.setHeightForWidth(self.resonator_GroupBox.sizePolicy().hasHeightForWidth())
        self.resonator_GroupBox.setSizePolicy(sizePolicy3)
        self.resonator_GroupBox.setMinimumSize(QSize(400, 0))
        self.resonator_gridLayout = QGridLayout(self.resonator_GroupBox)
        self.resonator_gridLayout.setObjectName(u"resonator_gridLayout")
        self.params_fileSelectWidget = FileSelectWidget(self.resonator_GroupBox)
        self.params_fileSelectWidget.setObjectName(u"params_fileSelectWidget")

        self.resonator_gridLayout.addWidget(self.params_fileSelectWidget, 0, 0, 1, 2)

        self.upload_params_pushButton = QPushButton(self.resonator_GroupBox)
        self.upload_params_pushButton.setObjectName(u"upload_params_pushButton")
        sizePolicy2.setHeightForWidth(self.upload_params_pushButton.sizePolicy().hasHeightForWidth())
        self.upload_params_pushButton.setSizePolicy(sizePolicy2)
        self.upload_params_pushButton.setIcon(icon)

        self.resonator_gridLayout.addWidget(self.upload_params_pushButton, 1, 1, 1, 1, Qt.AlignmentFlag.AlignRight)


        self.gridLayout.addWidget(self.resonator_GroupBox, 1, 0, 1, 2)


        self.retranslateUi(ChannelSettingsWidget)

        QMetaObject.connectSlotsByName(ChannelSettingsWidget)
    # setupUi

    def retranslateUi(self, ChannelSettingsWidget):
        ChannelSettingsWidget.setWindowTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Form", None))
        self.ethernet_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Ethernet Settings", None))
        self.eth_dest_error_label.setText("")
        self.eth_port_error_label.setText("")
        self.eth_mac_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination MAC address:", None))
        self.eth_port_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Port:", None))
        self.eth_port_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.eth_dest_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination IP address:", None))
        self.eth_mac_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"XX:XX:XX:XX:XX:XX", None))
        self.eth_source_error_label.setText("")
        self.eth_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Configure Hardware", None))
        self.eth_source_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Source IP address:", None))
        self.eth_dest_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"255.255.255.255", None))
        self.eth_source_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"255.255.255.255", None))
        self.eth_mac_error_label.setText("")
        self.if_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"IF Settings", None))
        self.rfin_error_label.setText("")
        self.rfout_error_label.setText("")
        self.rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0.0", None))
        self.rfin_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.rfinLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfin (dB):", None))
        self.rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0.0", None))
        self.rfout_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.lo_freq_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"400", None))
        self.lo_freq_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.lo_freq_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"LO freq (MHz):", None))
        self.rfoutLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfout (dB):", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Resonator Settings", None))
        self.upload_params_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload parameters to RFSoC", None))
    # retranslateUi

