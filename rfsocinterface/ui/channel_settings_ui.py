# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'channel_settings.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget)

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.section import Section
from . import icons_rc

class Ui_ChannelSettingsWidget(object):
    def setupUi(self, ChannelSettingsWidget):
        if not ChannelSettingsWidget.objectName():
            ChannelSettingsWidget.setObjectName(u"ChannelSettingsWidget")
        ChannelSettingsWidget.resize(465, 262)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ChannelSettingsWidget.sizePolicy().hasHeightForWidth())
        ChannelSettingsWidget.setSizePolicy(sizePolicy)
        self.gridLayout = QGridLayout(ChannelSettingsWidget)
        self.gridLayout.setObjectName(u"gridLayout")
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
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.tone_list_file_upload_widget.sizePolicy().hasHeightForWidth())
        self.tone_list_file_upload_widget.setSizePolicy(sizePolicy1)

        self.formLayout_2.setWidget(0, QFormLayout.FieldRole, self.tone_list_file_upload_widget)

        self.tone_power_label = QLabel(self.resonator_GroupBox)
        self.tone_power_label.setObjectName(u"tone_power_label")
        self.tone_power_label.setMinimumSize(QSize(0, 0))

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.tone_power_label)

        self.tone_power_file_upload_widget = FileUploadWidget(self.resonator_GroupBox)
        self.tone_power_file_upload_widget.setObjectName(u"tone_power_file_upload_widget")
        sizePolicy1.setHeightForWidth(self.tone_power_file_upload_widget.sizePolicy().hasHeightForWidth())
        self.tone_power_file_upload_widget.setSizePolicy(sizePolicy1)

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.tone_power_file_upload_widget)


        self.gridLayout.addWidget(self.resonator_GroupBox, 0, 0, 1, 3, Qt.AlignmentFlag.AlignTop)

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
        self.rfout_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.rfout_lineEdit.setObjectName(u"rfout_lineEdit")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfout_lineEdit.setSizePolicy(sizePolicy4)
        self.rfout_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_2.addWidget(self.rfout_lineEdit)

        self.rfout_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfout_uploadToolButton.setObjectName(u"rfout_uploadToolButton")
        self.rfout_uploadToolButton.setEnabled(False)
        sizePolicy4.setHeightForWidth(self.rfout_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfout_uploadToolButton.setSizePolicy(sizePolicy4)
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
        self.rfin_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.rfin_lineEdit.setObjectName(u"rfin_lineEdit")
        sizePolicy4.setHeightForWidth(self.rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfin_lineEdit.setSizePolicy(sizePolicy4)
        self.rfin_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_3.addWidget(self.rfin_lineEdit)

        self.rfin_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfin_uploadToolButton.setObjectName(u"rfin_uploadToolButton")
        self.rfin_uploadToolButton.setEnabled(False)
        sizePolicy4.setHeightForWidth(self.rfin_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfin_uploadToolButton.setSizePolicy(sizePolicy4)
        self.rfin_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.rfin_uploadToolButton.setIcon(icon)

        self.horizontalLayout_3.addWidget(self.rfin_uploadToolButton)


        self.formLayout_4.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout_3)


        self.gridLayout.addWidget(self.attenuation_GroupBox, 1, 2, 1, 1, Qt.AlignmentFlag.AlignTop)

        self.buttonBox = QDialogButtonBox(ChannelSettingsWidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttonBox.setCenterButtons(False)

        self.gridLayout.addWidget(self.buttonBox, 4, 0, 1, 3, Qt.AlignmentFlag.AlignBottom)

        self.udp_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.udp_GroupBox.setObjectName(u"udp_GroupBox")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.udp_GroupBox.sizePolicy().hasHeightForWidth())
        self.udp_GroupBox.setSizePolicy(sizePolicy5)
        self.verticalLayout = QVBoxLayout(self.udp_GroupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName(u"formLayout_6")
        self.udp_sourceLabel = QLabel(self.udp_GroupBox)
        self.udp_sourceLabel.setObjectName(u"udp_sourceLabel")
        sizePolicy3.setHeightForWidth(self.udp_sourceLabel.sizePolicy().hasHeightForWidth())
        self.udp_sourceLabel.setSizePolicy(sizePolicy3)

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.udp_sourceLabel)

        self.udp_sourceLineEdit = QLineEdit(self.udp_GroupBox)
        self.udp_sourceLineEdit.setObjectName(u"udp_sourceLineEdit")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.udp_sourceLineEdit.sizePolicy().hasHeightForWidth())
        self.udp_sourceLineEdit.setSizePolicy(sizePolicy6)

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.udp_sourceLineEdit)

        self.udp_destLineEdit = QLineEdit(self.udp_GroupBox)
        self.udp_destLineEdit.setObjectName(u"udp_destLineEdit")

        self.formLayout_6.setWidget(1, QFormLayout.FieldRole, self.udp_destLineEdit)

        self.udp_destLabel = QLabel(self.udp_GroupBox)
        self.udp_destLabel.setObjectName(u"udp_destLabel")
        sizePolicy3.setHeightForWidth(self.udp_destLabel.sizePolicy().hasHeightForWidth())
        self.udp_destLabel.setSizePolicy(sizePolicy3)

        self.formLayout_6.setWidget(1, QFormLayout.LabelRole, self.udp_destLabel)


        self.verticalLayout.addLayout(self.formLayout_6)

        self.udp_openPushButton = QPushButton(self.udp_GroupBox)
        self.udp_openPushButton.setObjectName(u"udp_openPushButton")
        self.udp_openPushButton.setEnabled(False)
        self.udp_openPushButton.setMaximumSize(QSize(150, 16777215))

        self.verticalLayout.addWidget(self.udp_openPushButton, 0, Qt.AlignmentFlag.AlignRight)


        self.gridLayout.addWidget(self.udp_GroupBox, 1, 0, 1, 2, Qt.AlignmentFlag.AlignTop)

        self.advanced_section = Section(ChannelSettingsWidget)
        self.advanced_section.setObjectName(u"advanced_section")
        sizePolicy.setHeightForWidth(self.advanced_section.sizePolicy().hasHeightForWidth())
        self.advanced_section.setSizePolicy(sizePolicy)
        self.chanmask_label = QLabel(self.advanced_section)
        self.chanmask_label.setObjectName(u"chanmask_label")
        self.chanmask_label.setGeometry(QRect(9, 9, 97, 16))
        self.chanmask_label.setMinimumSize(QSize(0, 0))
        self.firmware_label = QLabel(self.advanced_section)
        self.firmware_label.setObjectName(u"firmware_label")
        self.firmware_label.setGeometry(QRect(9, 41, 105, 16))
        self.firmware_label.setMinimumSize(QSize(0, 0))
        self.firmware_file_upload_widget = FileUploadWidget(self.advanced_section)
        self.firmware_file_upload_widget.setObjectName(u"firmware_file_upload_widget")
        self.firmware_file_upload_widget.setGeometry(QRect(120, 41, 318, 16))
        self.chanmask_lineEdit = QLineEdit(self.advanced_section)
        self.chanmask_lineEdit.setObjectName(u"chanmask_lineEdit")
        self.chanmask_lineEdit.setGeometry(QRect(211, 12, 133, 22))
        self.chanmask_pushButton = QPushButton(self.advanced_section)
        self.chanmask_pushButton.setObjectName(u"chanmask_pushButton")
        self.chanmask_pushButton.setGeometry(QRect(350, 11, 75, 24))

        self.gridLayout.addWidget(self.advanced_section, 3, 0, 1, 3, Qt.AlignmentFlag.AlignTop)


        self.retranslateUi(ChannelSettingsWidget)

        QMetaObject.connectSlotsByName(ChannelSettingsWidget)
    # setupUi

    def retranslateUi(self, ChannelSettingsWidget):
        ChannelSettingsWidget.setWindowTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Form", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Resonator Settings", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("ChannelSettingsWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("ChannelSettingsWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone list file:", None))
        self.tone_power_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone power file:", None))
        self.attenuation_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Attenuation Settings", None))
        self.rfoutLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfout:", None))
        self.rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfout_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.rfinLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfin:", None))
        self.rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfin_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.udp_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"UDP Connection", None))
        self.udp_sourceLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Source port:", None))
        self.udp_destLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Destination port:", None))
        self.udp_openPushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Open Socket", None))
        self.chanmask_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Channel mask file:", None))
        self.firmware_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Firmware bitstream:", None))
        self.chanmask_pushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Browse...", None))
    # retranslateUi

