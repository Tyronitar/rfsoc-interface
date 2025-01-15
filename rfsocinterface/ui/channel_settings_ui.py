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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QToolButton,
    QWidget)

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.lineedit import ClickableLineEdit
from . import icons_rc

class Ui_ChannelSettingsWidget(object):
    def setupUi(self, ChannelSettingsWidget):
        if not ChannelSettingsWidget.objectName():
            ChannelSettingsWidget.setObjectName(u"ChannelSettingsWidget")
        ChannelSettingsWidget.resize(530, 346)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ChannelSettingsWidget.sizePolicy().hasHeightForWidth())
        ChannelSettingsWidget.setSizePolicy(sizePolicy)
        self.gridLayout = QGridLayout(ChannelSettingsWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.buttonBox = QDialogButtonBox(ChannelSettingsWidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttonBox.setCenterButtons(False)

        self.gridLayout.addWidget(self.buttonBox, 6, 0, 1, 2, Qt.AlignmentFlag.AlignBottom)

        self.ethernet_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.ethernet_GroupBox.setObjectName(u"ethernet_GroupBox")
        self.gridLayout_2 = QGridLayout(self.ethernet_GroupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.eth_source_label = QLabel(self.ethernet_GroupBox)
        self.eth_source_label.setObjectName(u"eth_source_label")

        self.gridLayout_2.addWidget(self.eth_source_label, 0, 0, 1, 1)

        self.eth_source_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_source_lineEdit.setObjectName(u"eth_source_lineEdit")

        self.gridLayout_2.addWidget(self.eth_source_lineEdit, 0, 1, 1, 1)

        self.eth_dest_label = QLabel(self.ethernet_GroupBox)
        self.eth_dest_label.setObjectName(u"eth_dest_label")

        self.gridLayout_2.addWidget(self.eth_dest_label, 1, 0, 1, 1)

        self.eth_dest_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_dest_lineEdit.setObjectName(u"eth_dest_lineEdit")

        self.gridLayout_2.addWidget(self.eth_dest_lineEdit, 1, 1, 1, 1)

        self.eth_mac_label = QLabel(self.ethernet_GroupBox)
        self.eth_mac_label.setObjectName(u"eth_mac_label")

        self.gridLayout_2.addWidget(self.eth_mac_label, 2, 0, 1, 1)

        self.eth_mac_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_mac_lineEdit.setObjectName(u"eth_mac_lineEdit")

        self.gridLayout_2.addWidget(self.eth_mac_lineEdit, 2, 1, 1, 1)

        self.eth_port_label = QLabel(self.ethernet_GroupBox)
        self.eth_port_label.setObjectName(u"eth_port_label")

        self.gridLayout_2.addWidget(self.eth_port_label, 3, 0, 1, 1)

        self.eth_port_lineEdit = QLineEdit(self.ethernet_GroupBox)
        self.eth_port_lineEdit.setObjectName(u"eth_port_lineEdit")

        self.gridLayout_2.addWidget(self.eth_port_lineEdit, 3, 1, 1, 1)

        self.eth_pushButton = QPushButton(self.ethernet_GroupBox)
        self.eth_pushButton.setObjectName(u"eth_pushButton")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.eth_pushButton.sizePolicy().hasHeightForWidth())
        self.eth_pushButton.setSizePolicy(sizePolicy1)

        self.gridLayout_2.addWidget(self.eth_pushButton, 4, 1, 1, 1, Qt.AlignmentFlag.AlignRight)


        self.gridLayout.addWidget(self.ethernet_GroupBox, 5, 0, 1, 2)

        self.attenuation_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.attenuation_GroupBox.setObjectName(u"attenuation_GroupBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.attenuation_GroupBox.sizePolicy().hasHeightForWidth())
        self.attenuation_GroupBox.setSizePolicy(sizePolicy2)
        self.formLayout_4 = QFormLayout(self.attenuation_GroupBox)
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.rfoutLabel = QLabel(self.attenuation_GroupBox)
        self.rfoutLabel.setObjectName(u"rfoutLabel")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.rfoutLabel.sizePolicy().hasHeightForWidth())
        self.rfoutLabel.setSizePolicy(sizePolicy3)

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.rfoutLabel)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.rfout_lineEdit = ClickableLineEdit(self.attenuation_GroupBox)
        self.rfout_lineEdit.setObjectName(u"rfout_lineEdit")
        sizePolicy1.setHeightForWidth(self.rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfout_lineEdit.setSizePolicy(sizePolicy1)
        self.rfout_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_2.addWidget(self.rfout_lineEdit)

        self.rfout_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfout_uploadToolButton.setObjectName(u"rfout_uploadToolButton")
        self.rfout_uploadToolButton.setEnabled(False)
        sizePolicy1.setHeightForWidth(self.rfout_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfout_uploadToolButton.setSizePolicy(sizePolicy1)
        self.rfout_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.rfout_uploadToolButton.setIcon(icon)
        self.rfout_uploadToolButton.setArrowType(Qt.ArrowType.NoArrow)

        self.horizontalLayout_2.addWidget(self.rfout_uploadToolButton)


        self.formLayout_4.setLayout(0, QFormLayout.FieldRole, self.horizontalLayout_2)

        self.rfinLabel = QLabel(self.attenuation_GroupBox)
        self.rfinLabel.setObjectName(u"rfinLabel")
        sizePolicy3.setHeightForWidth(self.rfinLabel.sizePolicy().hasHeightForWidth())
        self.rfinLabel.setSizePolicy(sizePolicy3)

        self.formLayout_4.setWidget(1, QFormLayout.LabelRole, self.rfinLabel)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.rfin_lineEdit = ClickableLineEdit(self.attenuation_GroupBox)
        self.rfin_lineEdit.setObjectName(u"rfin_lineEdit")
        sizePolicy1.setHeightForWidth(self.rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfin_lineEdit.setSizePolicy(sizePolicy1)
        self.rfin_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_3.addWidget(self.rfin_lineEdit)

        self.rfin_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfin_uploadToolButton.setObjectName(u"rfin_uploadToolButton")
        self.rfin_uploadToolButton.setEnabled(False)
        sizePolicy1.setHeightForWidth(self.rfin_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfin_uploadToolButton.setSizePolicy(sizePolicy1)
        self.rfin_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.rfin_uploadToolButton.setIcon(icon)

        self.horizontalLayout_3.addWidget(self.rfin_uploadToolButton)


        self.formLayout_4.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout_3)

        self.lo_freq_label = QLabel(self.attenuation_GroupBox)
        self.lo_freq_label.setObjectName(u"lo_freq_label")
        sizePolicy3.setHeightForWidth(self.lo_freq_label.sizePolicy().hasHeightForWidth())
        self.lo_freq_label.setSizePolicy(sizePolicy3)

        self.formLayout_4.setWidget(2, QFormLayout.LabelRole, self.lo_freq_label)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.lo_freq_lineEdit = ClickableLineEdit(self.attenuation_GroupBox)
        self.lo_freq_lineEdit.setObjectName(u"lo_freq_lineEdit")
        sizePolicy1.setHeightForWidth(self.lo_freq_lineEdit.sizePolicy().hasHeightForWidth())
        self.lo_freq_lineEdit.setSizePolicy(sizePolicy1)
        self.lo_freq_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_4.addWidget(self.lo_freq_lineEdit)

        self.lo_freq_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.lo_freq_uploadToolButton.setObjectName(u"lo_freq_uploadToolButton")
        self.lo_freq_uploadToolButton.setEnabled(False)
        sizePolicy1.setHeightForWidth(self.lo_freq_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.lo_freq_uploadToolButton.setSizePolicy(sizePolicy1)
        self.lo_freq_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.lo_freq_uploadToolButton.setIcon(icon)

        self.horizontalLayout_4.addWidget(self.lo_freq_uploadToolButton)


        self.formLayout_4.setLayout(2, QFormLayout.FieldRole, self.horizontalLayout_4)


        self.gridLayout.addWidget(self.attenuation_GroupBox, 1, 1, 1, 1)

        self.resonator_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.resonator_GroupBox.setObjectName(u"resonator_GroupBox")
        self.formLayout_2 = QFormLayout(self.resonator_GroupBox)
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.tone_list_label = QLabel(self.resonator_GroupBox)
        self.tone_list_label.setObjectName(u"tone_list_label")
        self.tone_list_label.setMinimumSize(QSize(0, 0))
        self.tone_list_label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.tone_list_label)

        self.tone_list_file_upload_widget = FileUploadWidget(self.resonator_GroupBox)
        self.tone_list_file_upload_widget.setObjectName(u"tone_list_file_upload_widget")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.tone_list_file_upload_widget.sizePolicy().hasHeightForWidth())
        self.tone_list_file_upload_widget.setSizePolicy(sizePolicy4)

        self.formLayout_2.setWidget(0, QFormLayout.FieldRole, self.tone_list_file_upload_widget)

        self.tone_power_label = QLabel(self.resonator_GroupBox)
        self.tone_power_label.setObjectName(u"tone_power_label")
        self.tone_power_label.setMinimumSize(QSize(0, 0))

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.tone_power_label)

        self.tone_power_file_upload_widget = FileUploadWidget(self.resonator_GroupBox)
        self.tone_power_file_upload_widget.setObjectName(u"tone_power_file_upload_widget")
        sizePolicy4.setHeightForWidth(self.tone_power_file_upload_widget.sizePolicy().hasHeightForWidth())
        self.tone_power_file_upload_widget.setSizePolicy(sizePolicy4)

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.tone_power_file_upload_widget)

        self.chanmask_label = QLabel(self.resonator_GroupBox)
        self.chanmask_label.setObjectName(u"chanmask_label")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.chanmask_label)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.chanmask_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.chanmask_lineEdit.setObjectName(u"chanmask_lineEdit")

        self.horizontalLayout.addWidget(self.chanmask_lineEdit)

        self.chanmask_pushButton = QPushButton(self.resonator_GroupBox)
        self.chanmask_pushButton.setObjectName(u"chanmask_pushButton")

        self.horizontalLayout.addWidget(self.chanmask_pushButton)


        self.formLayout_2.setLayout(2, QFormLayout.FieldRole, self.horizontalLayout)


        self.gridLayout.addWidget(self.resonator_GroupBox, 1, 0, 1, 1)


        self.retranslateUi(ChannelSettingsWidget)

        QMetaObject.connectSlotsByName(ChannelSettingsWidget)
    # setupUi

    def retranslateUi(self, ChannelSettingsWidget):
        ChannelSettingsWidget.setWindowTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Form", None))
        self.ethernet_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Ethernet Settings", None))
        self.eth_source_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Source IP address:", None))
        self.eth_dest_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination IP address:", None))
        self.eth_mac_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destimation MAC address:", None))
        self.eth_port_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Port:", None))
        self.eth_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Configure Hardware", None))
        self.attenuation_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"IF Settings", None))
        self.rfoutLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfout:", None))
        self.rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfout_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.rfinLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfin:", None))
        self.rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfin_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.lo_freq_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"LO freq (KHz):", None))
        self.lo_freq_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"4e6", None))
        self.lo_freq_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Resonator Settings", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("ChannelSettingsWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("ChannelSettingsWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone list file:", None))
        self.tone_power_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone power file:", None))
        self.chanmask_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Channel mask:", None))
        self.chanmask_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Browse...", None))
    # retranslateUi

