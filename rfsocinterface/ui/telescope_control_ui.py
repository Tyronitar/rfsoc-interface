# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'telescope_control.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

from rfsocinterface.ui.controller import Controller
from . import icons_rc

class Ui_TelescopeControlWidget(object):
    def setupUi(self, TelescopeControlWidget):
        if not TelescopeControlWidget.objectName():
            TelescopeControlWidget.setObjectName(u"TelescopeControlWidget")
        TelescopeControlWidget.resize(862, 360)
        self.gridLayout_2 = QGridLayout(TelescopeControlWidget)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer_2, 0, 4, 1, 1)

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer_3)

        self.pushButton = QPushButton(TelescopeControlWidget)
        self.pushButton.setObjectName(u"pushButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy)
        self.pushButton.setMinimumSize(QSize(200, 200))
        self.pushButton.setMaximumSize(QSize(600, 600))
        self.pushButton.setBaseSize(QSize(500, 500))
        font = QFont()
        font.setPointSize(20)
        font.setWeight(QFont.Black)
        self.pushButton.setFont(font)
        self.pushButton.setStyleSheet(u"border-image: url(:/icons/octagon.svg);")
        self.pushButton.setIconSize(QSize(100, 100))
        self.pushButton.setFlat(False)

        self.verticalLayout_2.addWidget(self.pushButton)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer_2)


        self.gridLayout.addLayout(self.verticalLayout_2, 0, 0, 1, 1)

        self.control_groupBox = QGroupBox(TelescopeControlWidget)
        self.control_groupBox.setObjectName(u"control_groupBox")
        self.verticalLayout_3 = QVBoxLayout(self.control_groupBox)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.widget = Controller(self.control_groupBox)
        self.widget.setObjectName(u"widget")
        self.widget.setMinimumSize(QSize(250, 250))

        self.verticalLayout_3.addWidget(self.widget)


        self.gridLayout.addWidget(self.control_groupBox, 0, 5, 1, 1)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.position_groupBox = QGroupBox(TelescopeControlWidget)
        self.position_groupBox.setObjectName(u"position_groupBox")
        self.horizontalLayout = QHBoxLayout(self.position_groupBox)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFormAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.azimuthLabel = QLabel(self.position_groupBox)
        self.azimuthLabel.setObjectName(u"azimuthLabel")
        font1 = QFont()
        font1.setPointSize(20)
        font1.setUnderline(True)
        self.azimuthLabel.setFont(font1)
        self.azimuthLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.formLayout.setWidget(0, QFormLayout.SpanningRole, self.azimuthLabel)

        self.azimuth_actualLabel = QLabel(self.position_groupBox)
        self.azimuth_actualLabel.setObjectName(u"azimuth_actualLabel")
        font2 = QFont()
        font2.setPointSize(15)
        self.azimuth_actualLabel.setFont(font2)

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.azimuth_actualLabel)

        self.label = QLabel(self.position_groupBox)
        self.label.setObjectName(u"label")
        self.label.setFont(font2)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.label)

        self.azimuth_commandedLabel = QLabel(self.position_groupBox)
        self.azimuth_commandedLabel.setObjectName(u"azimuth_commandedLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.azimuth_commandedLabel)

        self.label_3 = QLabel(self.position_groupBox)
        self.label_3.setObjectName(u"label_3")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.label_3)

        self.azimuth_errorLabel = QLabel(self.position_groupBox)
        self.azimuth_errorLabel.setObjectName(u"azimuth_errorLabel")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.azimuth_errorLabel)

        self.label_5 = QLabel(self.position_groupBox)
        self.label_5.setObjectName(u"label_5")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.label_5)

        self.azimuth_velocityLabel = QLabel(self.position_groupBox)
        self.azimuth_velocityLabel.setObjectName(u"azimuth_velocityLabel")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.azimuth_velocityLabel)

        self.label_6 = QLabel(self.position_groupBox)
        self.label_6.setObjectName(u"label_6")

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.label_6)


        self.horizontalLayout.addLayout(self.formLayout)

        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.formLayout_2.setFormAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.zenith_actualLabel = QLabel(self.position_groupBox)
        self.zenith_actualLabel.setObjectName(u"zenith_actualLabel")
        self.zenith_actualLabel.setFont(font2)

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.zenith_actualLabel)

        self.zenithLabel = QLabel(self.position_groupBox)
        self.zenithLabel.setObjectName(u"zenithLabel")
        self.zenithLabel.setFont(font1)
        self.zenithLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.formLayout_2.setWidget(0, QFormLayout.SpanningRole, self.zenithLabel)

        self.zenith_commandedLabel = QLabel(self.position_groupBox)
        self.zenith_commandedLabel.setObjectName(u"zenith_commandedLabel")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.zenith_commandedLabel)

        self.zenith_errorLabel = QLabel(self.position_groupBox)
        self.zenith_errorLabel.setObjectName(u"zenith_errorLabel")

        self.formLayout_2.setWidget(3, QFormLayout.LabelRole, self.zenith_errorLabel)

        self.zenith_velocityLabel = QLabel(self.position_groupBox)
        self.zenith_velocityLabel.setObjectName(u"zenith_velocityLabel")

        self.formLayout_2.setWidget(4, QFormLayout.LabelRole, self.zenith_velocityLabel)

        self.label_2 = QLabel(self.position_groupBox)
        self.label_2.setObjectName(u"label_2")
        self.label_2.setFont(font2)

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.label_2)

        self.label_4 = QLabel(self.position_groupBox)
        self.label_4.setObjectName(u"label_4")

        self.formLayout_2.setWidget(2, QFormLayout.FieldRole, self.label_4)

        self.label_7 = QLabel(self.position_groupBox)
        self.label_7.setObjectName(u"label_7")

        self.formLayout_2.setWidget(3, QFormLayout.FieldRole, self.label_7)

        self.label_8 = QLabel(self.position_groupBox)
        self.label_8.setObjectName(u"label_8")

        self.formLayout_2.setWidget(4, QFormLayout.FieldRole, self.label_8)


        self.horizontalLayout.addLayout(self.formLayout_2)


        self.verticalLayout.addWidget(self.position_groupBox)


        self.gridLayout.addLayout(self.verticalLayout, 0, 3, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 0, 1, 1, 1)


        self.gridLayout_2.addLayout(self.gridLayout, 0, 0, 1, 1)


        self.retranslateUi(TelescopeControlWidget)

        QMetaObject.connectSlotsByName(TelescopeControlWidget)
    # setupUi

    def retranslateUi(self, TelescopeControlWidget):
        TelescopeControlWidget.setWindowTitle(QCoreApplication.translate("TelescopeControlWidget", u"MainWindow", None))
        self.pushButton.setText(QCoreApplication.translate("TelescopeControlWidget", u"STOP", None))
        self.control_groupBox.setTitle(QCoreApplication.translate("TelescopeControlWidget", u"Manual Control", None))
        self.position_groupBox.setTitle(QCoreApplication.translate("TelescopeControlWidget", u"Telescope Position", None))
        self.azimuthLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Azimuth", None))
        self.azimuth_actualLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Actual", None))
        self.label.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_commandedLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Commanded", None))
        self.label_3.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_errorLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Error", None))
        self.label_5.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_velocityLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Velocity", None))
        self.label_6.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0/sec", None))
        self.zenith_actualLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Actual", None))
        self.zenithLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Zenith", None))
        self.zenith_commandedLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Commanded", None))
        self.zenith_errorLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Error", None))
        self.zenith_velocityLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Velocity", None))
        self.label_2.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.label_4.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.label_7.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.label_8.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0/sec", None))
    # retranslateUi

