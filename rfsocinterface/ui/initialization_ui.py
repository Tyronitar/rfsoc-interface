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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

class Ui_InitializationTabWidget(object):
    def setupUi(self, InitializationTabWidget):
        if not InitializationTabWidget.objectName():
            InitializationTabWidget.setObjectName(u"InitializationTabWidget")
        InitializationTabWidget.resize(504, 430)
        self.gridLayout = QGridLayout(InitializationTabWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.pushButton = QPushButton(InitializationTabWidget)
        self.pushButton.setObjectName(u"pushButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy)
        self.pushButton.setMaximumSize(QSize(150, 16777215))

        self.gridLayout.addWidget(self.pushButton, 3, 1, 1, 1, Qt.AlignmentFlag.AlignRight)

        self.attenuation_GroupBox = QGroupBox(InitializationTabWidget)
        self.attenuation_GroupBox.setObjectName(u"attenuation_GroupBox")
        self.formLayout = QFormLayout(self.attenuation_GroupBox)
        self.formLayout.setObjectName(u"formLayout")
        self.system1Label = QLabel(self.attenuation_GroupBox)
        self.system1Label.setObjectName(u"system1Label")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.system1Label.sizePolicy().hasHeightForWidth())
        self.system1Label.setSizePolicy(sizePolicy1)
        self.system1Label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.system1Label)

        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName(u"formLayout_6")
        self.system1_rfinLabel = QLabel(self.attenuation_GroupBox)
        self.system1_rfinLabel.setObjectName(u"system1_rfinLabel")

        self.formLayout_6.setWidget(1, QFormLayout.LabelRole, self.system1_rfinLabel)

        self.system1_rfoutLabel = QLabel(self.attenuation_GroupBox)
        self.system1_rfoutLabel.setObjectName(u"system1_rfoutLabel")

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.system1_rfoutLabel)

        self.system1_rfout_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.system1_rfout_lineEdit.setObjectName(u"system1_rfout_lineEdit")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.system1_rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.system1_rfout_lineEdit.setSizePolicy(sizePolicy2)
        self.system1_rfout_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.system1_rfout_lineEdit)

        self.system1_rfin_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.system1_rfin_lineEdit.setObjectName(u"system1_rfin_lineEdit")
        sizePolicy2.setHeightForWidth(self.system1_rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.system1_rfin_lineEdit.setSizePolicy(sizePolicy2)
        self.system1_rfin_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.formLayout_6.setWidget(1, QFormLayout.FieldRole, self.system1_rfin_lineEdit)


        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.formLayout_6)

        self.system2Label = QLabel(self.attenuation_GroupBox)
        self.system2Label.setObjectName(u"system2Label")
        sizePolicy1.setHeightForWidth(self.system2Label.sizePolicy().hasHeightForWidth())
        self.system2Label.setSizePolicy(sizePolicy1)
        self.system2Label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.system2Label)

        self.formLayout_7 = QFormLayout()
        self.formLayout_7.setObjectName(u"formLayout_7")
        self.system_rfinLabel = QLabel(self.attenuation_GroupBox)
        self.system_rfinLabel.setObjectName(u"system_rfinLabel")

        self.formLayout_7.setWidget(1, QFormLayout.LabelRole, self.system_rfinLabel)

        self.system2_rfoutLabel = QLabel(self.attenuation_GroupBox)
        self.system2_rfoutLabel.setObjectName(u"system2_rfoutLabel")

        self.formLayout_7.setWidget(0, QFormLayout.LabelRole, self.system2_rfoutLabel)

        self.system2_rfout_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.system2_rfout_lineEdit.setObjectName(u"system2_rfout_lineEdit")
        sizePolicy2.setHeightForWidth(self.system2_rfout_lineEdit.sizePolicy().hasHeightForWidth())
        self.system2_rfout_lineEdit.setSizePolicy(sizePolicy2)
        self.system2_rfout_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.formLayout_7.setWidget(0, QFormLayout.FieldRole, self.system2_rfout_lineEdit)

        self.system2_rfin_lineEdit = QLineEdit(self.attenuation_GroupBox)
        self.system2_rfin_lineEdit.setObjectName(u"system2_rfin_lineEdit")
        sizePolicy2.setHeightForWidth(self.system2_rfin_lineEdit.sizePolicy().hasHeightForWidth())
        self.system2_rfin_lineEdit.setSizePolicy(sizePolicy2)
        self.system2_rfin_lineEdit.setMaximumSize(QSize(50, 16777215))

        self.formLayout_7.setWidget(1, QFormLayout.FieldRole, self.system2_rfin_lineEdit)


        self.formLayout.setLayout(1, QFormLayout.FieldRole, self.formLayout_7)


        self.gridLayout.addWidget(self.attenuation_GroupBox, 2, 1, 1, 1)

        self.resonator_GroupBox = QGroupBox(InitializationTabWidget)
        self.resonator_GroupBox.setObjectName(u"resonator_GroupBox")
        self.formLayout_2 = QFormLayout(self.resonator_GroupBox)
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.tone_list_label = QLabel(self.resonator_GroupBox)
        self.tone_list_label.setObjectName(u"tone_list_label")
        self.tone_list_label.setMinimumSize(QSize(100, 24))
        self.tone_list_label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.tone_list_label)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.tone_list_horizontalLayout = QHBoxLayout()
        self.tone_list_horizontalLayout.setObjectName(u"tone_list_horizontalLayout")
        self.tone_list_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.tone_list_lineEdit.setObjectName(u"tone_list_lineEdit")

        self.tone_list_horizontalLayout.addWidget(self.tone_list_lineEdit)

        self.tone_list_browse_pushButton = QPushButton(self.resonator_GroupBox)
        self.tone_list_browse_pushButton.setObjectName(u"tone_list_browse_pushButton")

        self.tone_list_horizontalLayout.addWidget(self.tone_list_browse_pushButton)


        self.verticalLayout.addLayout(self.tone_list_horizontalLayout)

        self.tone_list_uploadPushButton = QPushButton(self.resonator_GroupBox)
        self.tone_list_uploadPushButton.setObjectName(u"tone_list_uploadPushButton")
        self.tone_list_uploadPushButton.setEnabled(False)
        sizePolicy2.setHeightForWidth(self.tone_list_uploadPushButton.sizePolicy().hasHeightForWidth())
        self.tone_list_uploadPushButton.setSizePolicy(sizePolicy2)
        self.tone_list_uploadPushButton.setMaximumSize(QSize(150, 16777215))

        self.verticalLayout.addWidget(self.tone_list_uploadPushButton, 0, Qt.AlignmentFlag.AlignRight)


        self.formLayout_2.setLayout(0, QFormLayout.FieldRole, self.verticalLayout)

        self.label = QLabel(self.resonator_GroupBox)
        self.label.setObjectName(u"label")
        self.label.setMinimumSize(QSize(100, 24))

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.label)

        self.tone_list_horizontalLayout_2 = QHBoxLayout()
        self.tone_list_horizontalLayout_2.setObjectName(u"tone_list_horizontalLayout_2")
        self.chanmask_lineEdit = QLineEdit(self.resonator_GroupBox)
        self.chanmask_lineEdit.setObjectName(u"chanmask_lineEdit")

        self.tone_list_horizontalLayout_2.addWidget(self.chanmask_lineEdit)

        self.chanmask_browse_pushButton = QPushButton(self.resonator_GroupBox)
        self.chanmask_browse_pushButton.setObjectName(u"chanmask_browse_pushButton")

        self.tone_list_horizontalLayout_2.addWidget(self.chanmask_browse_pushButton)


        self.formLayout_2.setLayout(1, QFormLayout.FieldRole, self.tone_list_horizontalLayout_2)


        self.gridLayout.addWidget(self.resonator_GroupBox, 0, 0, 1, 2)

        self.buttonBox = QDialogButtonBox(InitializationTabWidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttonBox.setCenterButtons(False)

        self.gridLayout.addWidget(self.buttonBox, 5, 0, 1, 2)

        self.udp_GroupBox = QGroupBox(InitializationTabWidget)
        self.udp_GroupBox.setObjectName(u"udp_GroupBox")
        self.verticalLayout_2 = QVBoxLayout(self.udp_GroupBox)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.socket1Label = QLabel(self.udp_GroupBox)
        self.socket1Label.setObjectName(u"socket1Label")
        self.socket1Label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.socket1Label)

        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.socket1_sourceLabel = QLabel(self.udp_GroupBox)
        self.socket1_sourceLabel.setObjectName(u"socket1_sourceLabel")

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.socket1_sourceLabel)

        self.socket1_sourceLineEdit = QLineEdit(self.udp_GroupBox)
        self.socket1_sourceLineEdit.setObjectName(u"socket1_sourceLineEdit")

        self.formLayout_4.setWidget(0, QFormLayout.FieldRole, self.socket1_sourceLineEdit)

        self.socket1_destLabel = QLabel(self.udp_GroupBox)
        self.socket1_destLabel.setObjectName(u"socket1_destLabel")

        self.formLayout_4.setWidget(1, QFormLayout.LabelRole, self.socket1_destLabel)

        self.socket1_destLineEdit = QLineEdit(self.udp_GroupBox)
        self.socket1_destLineEdit.setObjectName(u"socket1_destLineEdit")

        self.formLayout_4.setWidget(1, QFormLayout.FieldRole, self.socket1_destLineEdit)


        self.formLayout_3.setLayout(0, QFormLayout.FieldRole, self.formLayout_4)

        self.socket2Label = QLabel(self.udp_GroupBox)
        self.socket2Label.setObjectName(u"socket2Label")
        self.socket2Label.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)

        self.formLayout_3.setWidget(1, QFormLayout.LabelRole, self.socket2Label)

        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName(u"formLayout_5")
        self.socket2_sourceLabel = QLabel(self.udp_GroupBox)
        self.socket2_sourceLabel.setObjectName(u"socket2_sourceLabel")

        self.formLayout_5.setWidget(0, QFormLayout.LabelRole, self.socket2_sourceLabel)

        self.socket2_sourceLineEdit = QLineEdit(self.udp_GroupBox)
        self.socket2_sourceLineEdit.setObjectName(u"socket2_sourceLineEdit")

        self.formLayout_5.setWidget(0, QFormLayout.FieldRole, self.socket2_sourceLineEdit)

        self.socket2_destLabel = QLabel(self.udp_GroupBox)
        self.socket2_destLabel.setObjectName(u"socket2_destLabel")

        self.formLayout_5.setWidget(1, QFormLayout.LabelRole, self.socket2_destLabel)

        self.socket2_destLineEdit = QLineEdit(self.udp_GroupBox)
        self.socket2_destLineEdit.setObjectName(u"socket2_destLineEdit")

        self.formLayout_5.setWidget(1, QFormLayout.FieldRole, self.socket2_destLineEdit)


        self.formLayout_3.setLayout(1, QFormLayout.FieldRole, self.formLayout_5)


        self.verticalLayout_2.addLayout(self.formLayout_3)

        self.udp_openPushButton = QPushButton(self.udp_GroupBox)
        self.udp_openPushButton.setObjectName(u"udp_openPushButton")
        self.udp_openPushButton.setEnabled(False)
        self.udp_openPushButton.setMaximumSize(QSize(150, 16777215))

        self.verticalLayout_2.addWidget(self.udp_openPushButton, 0, Qt.AlignmentFlag.AlignRight)


        self.gridLayout.addWidget(self.udp_GroupBox, 2, 0, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_2, 4, 1, 1, 1)


        self.retranslateUi(InitializationTabWidget)

        QMetaObject.connectSlotsByName(InitializationTabWidget)
    # setupUi

    def retranslateUi(self, InitializationTabWidget):
        InitializationTabWidget.setWindowTitle(QCoreApplication.translate("InitializationTabWidget", u"Form", None))
        self.pushButton.setText(QCoreApplication.translate("InitializationTabWidget", u"Upload Bitstream", None))
        self.attenuation_GroupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Attenuation Settings", None))
        self.system1Label.setText(QCoreApplication.translate("InitializationTabWidget", u"IF system 1:", None))
        self.system1_rfinLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Rfin", None))
        self.system1_rfoutLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Rfout", None))
        self.system1_rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("InitializationTabWidget", u"0", None))
        self.system1_rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("InitializationTabWidget", u"0", None))
        self.system2Label.setText(QCoreApplication.translate("InitializationTabWidget", u"IF system 2:", None))
        self.system_rfinLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Rfin", None))
        self.system2_rfoutLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Rfout", None))
        self.system2_rfout_lineEdit.setPlaceholderText(QCoreApplication.translate("InitializationTabWidget", u"0", None))
        self.system2_rfin_lineEdit.setPlaceholderText(QCoreApplication.translate("InitializationTabWidget", u"0", None))
        self.resonator_GroupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"Resonator Settings", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("InitializationTabWidget", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("InitializationTabWidget", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("InitializationTabWidget", u"Tone list file:", None))
        self.tone_list_browse_pushButton.setText(QCoreApplication.translate("InitializationTabWidget", u"Browse...", None))
        self.tone_list_uploadPushButton.setText(QCoreApplication.translate("InitializationTabWidget", u"Upload Selected Tone List", None))
        self.label.setText(QCoreApplication.translate("InitializationTabWidget", u"Channel mask file:", None))
        self.chanmask_browse_pushButton.setText(QCoreApplication.translate("InitializationTabWidget", u"Browse...", None))
        self.udp_GroupBox.setTitle(QCoreApplication.translate("InitializationTabWidget", u"UDP Connection", None))
        self.socket1Label.setText(QCoreApplication.translate("InitializationTabWidget", u"Socket 1:", None))
        self.socket1_sourceLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Source port:", None))
        self.socket1_destLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Destination port:", None))
        self.socket2Label.setText(QCoreApplication.translate("InitializationTabWidget", u"Socket 2:", None))
        self.socket2_sourceLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Source port:", None))
        self.socket2_destLabel.setText(QCoreApplication.translate("InitializationTabWidget", u"Destination port:", None))
        self.udp_openPushButton.setText(QCoreApplication.translate("InitializationTabWidget", u"Open Connection", None))
    # retranslateUi

