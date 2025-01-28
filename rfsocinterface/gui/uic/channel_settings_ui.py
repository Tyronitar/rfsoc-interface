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
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QToolButton,
    QWidget)

from rfsocinterface.gui.widgets.lineedit import ClickableLineEdit
from . import icons_rc

class Ui_ChannelSettingsWidget(object):
    def setupUi(self, ChannelSettingsWidget):
        if not ChannelSettingsWidget.objectName():
            ChannelSettingsWidget.setObjectName(u"ChannelSettingsWidget")
        ChannelSettingsWidget.resize(650, 514)
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

        self.eth_dest_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_dest_lineEdit.setObjectName(u"eth_dest_lineEdit")

        self.eth_gridLayout.addWidget(self.eth_dest_lineEdit, 2, 1, 1, 1)

        self.eth_port_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_port_lineEdit.setObjectName(u"eth_port_lineEdit")

        self.eth_gridLayout.addWidget(self.eth_port_lineEdit, 6, 1, 1, 1)

        self.eth_dest_label = QLabel(self.ethernet_GroupBox)
        self.eth_dest_label.setObjectName(u"eth_dest_label")

        self.eth_gridLayout.addWidget(self.eth_dest_label, 2, 0, 1, 1)

        self.eth_pushButton = QPushButton(self.ethernet_GroupBox)
        self.eth_pushButton.setObjectName(u"eth_pushButton")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.eth_pushButton.sizePolicy().hasHeightForWidth())
        self.eth_pushButton.setSizePolicy(sizePolicy1)
        self.eth_pushButton.setMinimumSize(QSize(0, 24))

        self.eth_gridLayout.addWidget(self.eth_pushButton, 8, 1, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.eth_source_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_source_lineEdit.setObjectName(u"eth_source_lineEdit")

        self.eth_gridLayout.addWidget(self.eth_source_lineEdit, 0, 1, 1, 1)

        self.eth_mac_label = QLabel(self.ethernet_GroupBox)
        self.eth_mac_label.setObjectName(u"eth_mac_label")

        self.eth_gridLayout.addWidget(self.eth_mac_label, 4, 0, 1, 1)

        self.eth_source_label = QLabel(self.ethernet_GroupBox)
        self.eth_source_label.setObjectName(u"eth_source_label")

        self.eth_gridLayout.addWidget(self.eth_source_label, 0, 0, 1, 1)

        self.eth_port_label = QLabel(self.ethernet_GroupBox)
        self.eth_port_label.setObjectName(u"eth_port_label")

        self.eth_gridLayout.addWidget(self.eth_port_label, 6, 0, 1, 1)

        self.eth_mac_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_mac_lineEdit.setObjectName(u"eth_mac_lineEdit")

        self.eth_gridLayout.addWidget(self.eth_mac_lineEdit, 4, 1, 1, 1)

        self.eth_source_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_source_error_label.setObjectName(u"eth_source_error_label")
        self.eth_source_error_label.setWordWrap(True)

        self.eth_gridLayout.addWidget(self.eth_source_error_label, 1, 1, 1, 1)

        self.eth_mac_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_mac_error_label.setObjectName(u"eth_mac_error_label")
        self.eth_mac_error_label.setWordWrap(True)

        self.eth_gridLayout.addWidget(self.eth_mac_error_label, 5, 1, 1, 1)

        self.eth_port_error_label = QLabel(self.ethernet_GroupBox)
        self.eth_port_error_label.setObjectName(u"eth_port_error_label")

        self.eth_gridLayout.addWidget(self.eth_port_error_label, 7, 1, 1, 1)


        self.gridLayout.addWidget(self.ethernet_GroupBox, 5, 0, 1, 2)

        self.if_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.if_GroupBox.setObjectName(u"if_GroupBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.if_GroupBox.sizePolicy().hasHeightForWidth())
        self.if_GroupBox.setSizePolicy(sizePolicy2)
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
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfin_lineEdit.setSizePolicy(sizePolicy3)
        self.rfin_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_3.addWidget(self.rfin_lineEdit)

        self.rfin_uploadToolButton = QToolButton(self.if_GroupBox)
        self.rfin_uploadToolButton.setObjectName(u"rfin_uploadToolButton")
        self.rfin_uploadToolButton.setEnabled(True)
        sizePolicy1.setHeightForWidth(self.rfin_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfin_uploadToolButton.setSizePolicy(sizePolicy1)
        self.rfin_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.rfin_uploadToolButton.setIcon(icon)

        self.horizontalLayout_3.addWidget(self.rfin_uploadToolButton)


        self.if_gridLayout.addLayout(self.horizontalLayout_3, 2, 1, 1, 1)

        self.rfinLabel = QLabel(self.if_GroupBox)
        self.rfinLabel.setObjectName(u"rfinLabel")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.rfinLabel.sizePolicy().hasHeightForWidth())
        self.rfinLabel.setSizePolicy(sizePolicy4)

        self.if_gridLayout.addWidget(self.rfinLabel, 2, 0, 1, 1)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.rfout_lineEdit = ClickableLineEdit(self.if_GroupBox)
        self.rfout_lineEdit.setObjectName(u"rfout_lineEdit")
        sizePolicy3.setHeightForWidth(self.rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfout_lineEdit.setSizePolicy(sizePolicy3)
        self.rfout_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_2.addWidget(self.rfout_lineEdit)

        self.rfout_uploadToolButton = QToolButton(self.if_GroupBox)
        self.rfout_uploadToolButton.setObjectName(u"rfout_uploadToolButton")
        self.rfout_uploadToolButton.setEnabled(True)
        sizePolicy1.setHeightForWidth(self.rfout_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfout_uploadToolButton.setSizePolicy(sizePolicy1)
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
        sizePolicy3.setHeightForWidth(self.lo_freq_lineEdit.sizePolicy().hasHeightForWidth())
        self.lo_freq_lineEdit.setSizePolicy(sizePolicy3)
        self.lo_freq_lineEdit.setMaximumSize(QSize(16777215, 16777215))

        self.horizontalLayout_4.addWidget(self.lo_freq_lineEdit)

        self.lo_freq_uploadToolButton = QToolButton(self.if_GroupBox)
        self.lo_freq_uploadToolButton.setObjectName(u"lo_freq_uploadToolButton")
        self.lo_freq_uploadToolButton.setEnabled(True)
        sizePolicy1.setHeightForWidth(self.lo_freq_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.lo_freq_uploadToolButton.setSizePolicy(sizePolicy1)
        self.lo_freq_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.lo_freq_uploadToolButton.setIcon(icon)

        self.horizontalLayout_4.addWidget(self.lo_freq_uploadToolButton)


        self.if_gridLayout.addLayout(self.horizontalLayout_4, 4, 1, 1, 1)

        self.lo_freq_label = QLabel(self.if_GroupBox)
        self.lo_freq_label.setObjectName(u"lo_freq_label")
        sizePolicy4.setHeightForWidth(self.lo_freq_label.sizePolicy().hasHeightForWidth())
        self.lo_freq_label.setSizePolicy(sizePolicy4)

        self.if_gridLayout.addWidget(self.lo_freq_label, 4, 0, 1, 1)

        self.rfoutLabel = QLabel(self.if_GroupBox)
        self.rfoutLabel.setObjectName(u"rfoutLabel")
        sizePolicy4.setHeightForWidth(self.rfoutLabel.sizePolicy().hasHeightForWidth())
        self.rfoutLabel.setSizePolicy(sizePolicy4)

        self.if_gridLayout.addWidget(self.rfoutLabel, 0, 0, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.if_gridLayout.addItem(self.verticalSpacer, 5, 1, 1, 1)


        self.gridLayout.addWidget(self.if_GroupBox, 1, 1, 1, 1)

        self.resonator_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.resonator_GroupBox.setObjectName(u"resonator_GroupBox")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.resonator_GroupBox.sizePolicy().hasHeightForWidth())
        self.resonator_GroupBox.setSizePolicy(sizePolicy5)
        self.resonator_GroupBox.setMinimumSize(QSize(400, 0))
        self.resonator_gridLayout = QGridLayout(self.resonator_GroupBox)
        self.resonator_gridLayout.setObjectName(u"resonator_gridLayout")
        self.upload_tones_pushButton = QPushButton(self.resonator_GroupBox)
        self.upload_tones_pushButton.setObjectName(u"upload_tones_pushButton")
        sizePolicy1.setHeightForWidth(self.upload_tones_pushButton.sizePolicy().hasHeightForWidth())
        self.upload_tones_pushButton.setSizePolicy(sizePolicy1)

        self.resonator_gridLayout.addWidget(self.upload_tones_pushButton, 4, 1, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.tone_power_label = QLabel(self.resonator_GroupBox)
        self.tone_power_label.setObjectName(u"tone_power_label")
        self.tone_power_label.setMinimumSize(QSize(0, 0))

        self.resonator_gridLayout.addWidget(self.tone_power_label, 2, 0, 1, 1)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.tone_power_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.tone_power_lineEdit.setObjectName(u"tone_power_lineEdit")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.tone_power_lineEdit.sizePolicy().hasHeightForWidth())
        self.tone_power_lineEdit.setSizePolicy(sizePolicy6)

        self.horizontalLayout_5.addWidget(self.tone_power_lineEdit)

        self.tone_power_pushButton = QPushButton(self.resonator_GroupBox)
        self.tone_power_pushButton.setObjectName(u"tone_power_pushButton")
        sizePolicy1.setHeightForWidth(self.tone_power_pushButton.sizePolicy().hasHeightForWidth())
        self.tone_power_pushButton.setSizePolicy(sizePolicy1)

        self.horizontalLayout_5.addWidget(self.tone_power_pushButton)


        self.resonator_gridLayout.addLayout(self.horizontalLayout_5, 2, 1, 1, 1)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.chanmask_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.chanmask_lineEdit.setObjectName(u"chanmask_lineEdit")
        sizePolicy6.setHeightForWidth(self.chanmask_lineEdit.sizePolicy().hasHeightForWidth())
        self.chanmask_lineEdit.setSizePolicy(sizePolicy6)

        self.horizontalLayout.addWidget(self.chanmask_lineEdit)

        self.chanmask_pushButton = QPushButton(self.resonator_GroupBox)
        self.chanmask_pushButton.setObjectName(u"chanmask_pushButton")
        sizePolicy1.setHeightForWidth(self.chanmask_pushButton.sizePolicy().hasHeightForWidth())
        self.chanmask_pushButton.setSizePolicy(sizePolicy1)

        self.horizontalLayout.addWidget(self.chanmask_pushButton)


        self.resonator_gridLayout.addLayout(self.horizontalLayout, 5, 1, 1, 1)

        self.tone_list_label = QLabel(self.resonator_GroupBox)
        self.tone_list_label.setObjectName(u"tone_list_label")
        self.tone_list_label.setMinimumSize(QSize(0, 0))
        self.tone_list_label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

        self.resonator_gridLayout.addWidget(self.tone_list_label, 0, 0, 1, 1)

        self.chanmask_label = QLabel(self.resonator_GroupBox)
        self.chanmask_label.setObjectName(u"chanmask_label")

        self.resonator_gridLayout.addWidget(self.chanmask_label, 5, 0, 1, 1)

        self.tone_list_error_label = QLabel(self.resonator_GroupBox)
        self.tone_list_error_label.setObjectName(u"tone_list_error_label")

        self.resonator_gridLayout.addWidget(self.tone_list_error_label, 1, 1, 1, 1)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.tone_list_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.tone_list_lineEdit.setObjectName(u"tone_list_lineEdit")
        sizePolicy6.setHeightForWidth(self.tone_list_lineEdit.sizePolicy().hasHeightForWidth())
        self.tone_list_lineEdit.setSizePolicy(sizePolicy6)

        self.horizontalLayout_6.addWidget(self.tone_list_lineEdit)

        self.tone_list_pushButton = QPushButton(self.resonator_GroupBox)
        self.tone_list_pushButton.setObjectName(u"tone_list_pushButton")
        sizePolicy1.setHeightForWidth(self.tone_list_pushButton.sizePolicy().hasHeightForWidth())
        self.tone_list_pushButton.setSizePolicy(sizePolicy1)

        self.horizontalLayout_6.addWidget(self.tone_list_pushButton)


        self.resonator_gridLayout.addLayout(self.horizontalLayout_6, 0, 1, 1, 1)

        self.tone_power_error_label = QLabel(self.resonator_GroupBox)
        self.tone_power_error_label.setObjectName(u"tone_power_error_label")

        self.resonator_gridLayout.addWidget(self.tone_power_error_label, 3, 1, 1, 1)


        self.gridLayout.addWidget(self.resonator_GroupBox, 1, 0, 1, 1)


        self.retranslateUi(ChannelSettingsWidget)

        QMetaObject.connectSlotsByName(ChannelSettingsWidget)
    # setupUi

    def retranslateUi(self, ChannelSettingsWidget):
        ChannelSettingsWidget.setWindowTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Form", None))
        self.ethernet_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Ethernet Settings", None))
        self.eth_dest_error_label.setText("")
        self.eth_dest_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"255.255.255.255", None))
        self.eth_port_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.eth_dest_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination IP address:", None))
        self.eth_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Configure Hardware", None))
        self.eth_source_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"255.255.255.255", None))
        self.eth_mac_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination MAC address:", None))
        self.eth_source_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Source IP address:", None))
        self.eth_port_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Port:", None))
        self.eth_mac_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"XX:XX:XX:XX:XX:XX", None))
        self.eth_source_error_label.setText("")
        self.eth_mac_error_label.setText("")
        self.eth_port_error_label.setText("")
        self.if_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"IF Settings", None))
        self.rfin_error_label.setText("")
        self.rfout_error_label.setText("")
        self.rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0.0", None))
        self.rfin_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.rfinLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfin (dB):", None))
        self.rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0.0", None))
        self.rfout_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.lo_freq_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"4e6", None))
        self.lo_freq_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.lo_freq_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"LO freq (Hz):", None))
        self.rfoutLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfout (dB):", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Resonator Settings", None))
        self.upload_tones_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Tones", None))
        self.tone_power_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone power file:", None))
        self.tone_power_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"/path/to/filename.npy", None))
        self.tone_power_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Browse...", None))
        self.chanmask_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"/path/to/filename.npy", None))
        self.chanmask_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("ChannelSettingsWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("ChannelSettingsWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone list file:", None))
        self.chanmask_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Channel mask:", None))
        self.tone_list_error_label.setText("")
        self.tone_list_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"/path/to/filename.npy", None))
        self.tone_list_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Browse...", None))
        self.tone_power_error_label.setText("")
    # retranslateUi

