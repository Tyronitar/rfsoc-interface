# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'channel_settings.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QSizePolicy, QToolButton, QWidget)

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.lineedit import ClickableLineEdit
from rfsocinterface.ui.section import Section
from . import icons_rc

class Ui_ChannelSettingsWidget(object):
    def setupUi(self, ChannelSettingsWidget):
        if not ChannelSettingsWidget.objectName():
            ChannelSettingsWidget.setObjectName(u"ChannelSettingsWidget")
        ChannelSettingsWidget.resize(407, 154)
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

        self.gridLayout.addWidget(self.buttonBox, 4, 0, 1, 2, Qt.AlignmentFlag.AlignBottom)

        self.advanced_section = Section(ChannelSettingsWidget)
        self.advanced_section.setObjectName(u"advanced_section")
        sizePolicy.setHeightForWidth(self.advanced_section.sizePolicy().hasHeightForWidth())
        self.advanced_section.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.advanced_section, 3, 0, 1, 2, Qt.AlignmentFlag.AlignTop)

        self.attenuation_GroupBox = QGroupBox(ChannelSettingsWidget)
        self.attenuation_GroupBox.setObjectName(u"attenuation_GroupBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.attenuation_GroupBox.sizePolicy().hasHeightForWidth())
        self.attenuation_GroupBox.setSizePolicy(sizePolicy1)
        self.formLayout_4 = QFormLayout(self.attenuation_GroupBox)
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.rfoutLabel = QLabel(self.attenuation_GroupBox)
        self.rfoutLabel.setObjectName(u"rfoutLabel")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.rfoutLabel.sizePolicy().hasHeightForWidth())
        self.rfoutLabel.setSizePolicy(sizePolicy2)

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.rfoutLabel)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.rfout_lineEdit = ClickableLineEdit(self.attenuation_GroupBox)
        self.rfout_lineEdit.setObjectName(u"rfout_lineEdit")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfout_lineEdit.setSizePolicy(sizePolicy3)
        self.rfout_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_2.addWidget(self.rfout_lineEdit)

        self.rfout_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfout_uploadToolButton.setObjectName(u"rfout_uploadToolButton")
        self.rfout_uploadToolButton.setEnabled(False)
        sizePolicy3.setHeightForWidth(self.rfout_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfout_uploadToolButton.setSizePolicy(sizePolicy3)
        self.rfout_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.rfout_uploadToolButton.setIcon(icon)
        self.rfout_uploadToolButton.setArrowType(Qt.ArrowType.NoArrow)

        self.horizontalLayout_2.addWidget(self.rfout_uploadToolButton)


        self.formLayout_4.setLayout(0, QFormLayout.FieldRole, self.horizontalLayout_2)

        self.rfinLabel = QLabel(self.attenuation_GroupBox)
        self.rfinLabel.setObjectName(u"rfinLabel")
        sizePolicy2.setHeightForWidth(self.rfinLabel.sizePolicy().hasHeightForWidth())
        self.rfinLabel.setSizePolicy(sizePolicy2)

        self.formLayout_4.setWidget(1, QFormLayout.LabelRole, self.rfinLabel)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.rfin_lineEdit = ClickableLineEdit(self.attenuation_GroupBox)
        self.rfin_lineEdit.setObjectName(u"rfin_lineEdit")
        sizePolicy3.setHeightForWidth(self.rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.rfin_lineEdit.setSizePolicy(sizePolicy3)
        self.rfin_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_3.addWidget(self.rfin_lineEdit)

        self.rfin_uploadToolButton = QToolButton(self.attenuation_GroupBox)
        self.rfin_uploadToolButton.setObjectName(u"rfin_uploadToolButton")
        self.rfin_uploadToolButton.setEnabled(False)
        sizePolicy3.setHeightForWidth(self.rfin_uploadToolButton.sizePolicy().hasHeightForWidth())
        self.rfin_uploadToolButton.setSizePolicy(sizePolicy3)
        self.rfin_uploadToolButton.setMaximumSize(QSize(150, 16777215))
        self.rfin_uploadToolButton.setIcon(icon)

        self.horizontalLayout_3.addWidget(self.rfin_uploadToolButton)


        self.formLayout_4.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout_3)


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


        self.gridLayout.addWidget(self.resonator_GroupBox, 1, 0, 1, 1)


        self.retranslateUi(ChannelSettingsWidget)

        QMetaObject.connectSlotsByName(ChannelSettingsWidget)
    # setupUi

    def retranslateUi(self, ChannelSettingsWidget):
        ChannelSettingsWidget.setWindowTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Form", None))
        self.attenuation_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Attenuation Settings", None))
        self.rfoutLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfout:", None))
        self.rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfout_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.rfinLabel.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Rfin:", None))
        self.rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("ChannelSettingsWidget", u"0", None))
        self.rfin_uploadToolButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Upload Selected Tone List", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"Resonator Settings", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("ChannelSettingsWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("ChannelSettingsWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone list file:", None))
        self.tone_power_label.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Tone power file:", None))
    # retranslateUi

