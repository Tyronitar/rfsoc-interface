# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'rfsoc_advanced_settings.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QSizePolicy, QWidget)

from rfsocinterface.ui.file_upload import FileUploadWidget

class Ui_RFSOCAdvancedSettingsWidget(object):
    def setupUi(self, RFSOCAdvancedSettingsWidget):
        if not RFSOCAdvancedSettingsWidget.objectName():
            RFSOCAdvancedSettingsWidget.setObjectName(u"RFSOCAdvancedSettingsWidget")
        RFSOCAdvancedSettingsWidget.resize(351, 232)
        self.formLayout_3 = QFormLayout(RFSOCAdvancedSettingsWidget)
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_2 = QLabel(RFSOCAdvancedSettingsWidget)
        self.label_2.setObjectName(u"label_2")

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.label_2)

        self.redis_GroupBox = QGroupBox(RFSOCAdvancedSettingsWidget)
        self.redis_GroupBox.setObjectName(u"redis_GroupBox")
        self.formLayout_2 = QFormLayout(self.redis_GroupBox)
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.redis_ip_label = QLabel(self.redis_GroupBox)
        self.redis_ip_label.setObjectName(u"redis_ip_label")
        self.redis_ip_label.setMinimumSize(QSize(0, 0))
        self.redis_ip_label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.redis_ip_label)

        self.redis_port_label = QLabel(self.redis_GroupBox)
        self.redis_port_label.setObjectName(u"redis_port_label")
        self.redis_port_label.setMinimumSize(QSize(0, 0))

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.redis_port_label)

        self.lineEdit = QLineEdit(self.redis_GroupBox)
        self.lineEdit.setObjectName(u"lineEdit")

        self.formLayout_2.setWidget(0, QFormLayout.FieldRole, self.lineEdit)

        self.lineEdit_2 = QLineEdit(self.redis_GroupBox)
        self.lineEdit_2.setObjectName(u"lineEdit_2")

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.lineEdit_2)


        self.formLayout_3.setWidget(2, QFormLayout.SpanningRole, self.redis_GroupBox)

        self.bitstream_fileUploadWidget = FileUploadWidget(RFSOCAdvancedSettingsWidget)
        self.bitstream_fileUploadWidget.setObjectName(u"bitstream_fileUploadWidget")

        self.formLayout_3.setWidget(0, QFormLayout.FieldRole, self.bitstream_fileUploadWidget)

        self.comport_groupBox = QGroupBox(RFSOCAdvancedSettingsWidget)
        self.comport_groupBox.setObjectName(u"comport_groupBox")
        self.formLayout = QFormLayout(self.comport_groupBox)
        self.formLayout.setObjectName(u"formLayout")
        self.comport_atten_label = QLabel(self.comport_groupBox)
        self.comport_atten_label.setObjectName(u"comport_atten_label")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.comport_atten_label)

        self.comport_atten_fileUploadWidget = FileUploadWidget(self.comport_groupBox)
        self.comport_atten_fileUploadWidget.setObjectName(u"comport_atten_fileUploadWidget")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.comport_atten_fileUploadWidget)

        self.comport_channel1_label = QLabel(self.comport_groupBox)
        self.comport_channel1_label.setObjectName(u"comport_channel1_label")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.comport_channel1_label)

        self.comport_channel2_label = QLabel(self.comport_groupBox)
        self.comport_channel2_label.setObjectName(u"comport_channel2_label")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.comport_channel2_label)

        self.comport_channel1_fileUploadWidger = FileUploadWidget(self.comport_groupBox)
        self.comport_channel1_fileUploadWidger.setObjectName(u"comport_channel1_fileUploadWidger")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.comport_channel1_fileUploadWidger)

        self.comport_channel2_fileUploadWidget = FileUploadWidget(self.comport_groupBox)
        self.comport_channel2_fileUploadWidget.setObjectName(u"comport_channel2_fileUploadWidget")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.comport_channel2_fileUploadWidget)


        self.formLayout_3.setWidget(3, QFormLayout.SpanningRole, self.comport_groupBox)


        self.retranslateUi(RFSOCAdvancedSettingsWidget)

        QMetaObject.connectSlotsByName(RFSOCAdvancedSettingsWidget)
    # setupUi

    def retranslateUi(self, RFSOCAdvancedSettingsWidget):
        RFSOCAdvancedSettingsWidget.setWindowTitle(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Form", None))
        self.label_2.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Firmware bitstream:", None))
        self.redis_GroupBox.setTitle(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"REDIS Settings", None))
#if QT_CONFIG(tooltip)
        self.redis_ip_label.setToolTip(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.redis_ip_label.setWhatsThis(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.redis_ip_label.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"IP address:", None))
        self.redis_port_label.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Port:", None))
        self.comport_groupBox.setTitle(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Comports", None))
        self.comport_atten_label.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Attenuators:", None))
        self.comport_channel1_label.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Channel 1 valon:", None))
        self.comport_channel2_label.setText(QCoreApplication.translate("RFSOCAdvancedSettingsWidget", u"Channel 2 valon:", None))
    # retranslateUi

