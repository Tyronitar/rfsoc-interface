# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'telescope_control.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

from rfsocinterface.gui.widgets.canvas import ScrollableCanvas
from rfsocinterface.gui.widgets.controller import Controller
from . import icons_rc

class Ui_TelescopeControlWidget(object):
    def setupUi(self, TelescopeControlWidget):
        if not TelescopeControlWidget.objectName():
            TelescopeControlWidget.setObjectName(u"TelescopeControlWidget")
        TelescopeControlWidget.resize(1021, 397)
        self.gridLayout_2 = QGridLayout(TelescopeControlWidget)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.optical_pushButton = QPushButton(TelescopeControlWidget)
        self.optical_pushButton.setObjectName(u"optical_pushButton")
        self.optical_pushButton.setCheckable(True)

        self.gridLayout_2.addWidget(self.optical_pushButton, 1, 0, 1, 1)

        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer_2, 0, 4, 1, 1)

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer_3)

        self.stop_pushButton = QPushButton(TelescopeControlWidget)
        self.stop_pushButton.setObjectName(u"stop_pushButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.stop_pushButton.sizePolicy().hasHeightForWidth())
        self.stop_pushButton.setSizePolicy(sizePolicy)
        self.stop_pushButton.setMinimumSize(QSize(200, 200))
        self.stop_pushButton.setMaximumSize(QSize(600, 600))
        self.stop_pushButton.setBaseSize(QSize(500, 500))
        font = QFont()
        font.setPointSize(20)
        font.setWeight(QFont.Black)
        self.stop_pushButton.setFont(font)
        self.stop_pushButton.setStyleSheet(u"border: none;")
        icon = QIcon()
        icon.addFile(u":/icons/stop.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.stop_pushButton.setIcon(icon)
        self.stop_pushButton.setIconSize(QSize(190, 190))

        self.verticalLayout_2.addWidget(self.stop_pushButton)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer_2)


        self.gridLayout.addLayout(self.verticalLayout_2, 0, 0, 1, 1)

        self.control_groupBox = QGroupBox(TelescopeControlWidget)
        self.control_groupBox.setObjectName(u"control_groupBox")
        self.verticalLayout_3 = QVBoxLayout(self.control_groupBox)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.manual_controlcheckBox = QCheckBox(self.control_groupBox)
        self.manual_controlcheckBox.setObjectName(u"manual_controlcheckBox")

        self.verticalLayout_3.addWidget(self.manual_controlcheckBox)

        self.controller = Controller(self.control_groupBox)
        self.controller.setObjectName(u"controller")
        self.controller.setEnabled(False)
        self.controller.setMinimumSize(QSize(280, 250))

        self.verticalLayout_3.addWidget(self.controller)


        self.gridLayout.addWidget(self.control_groupBox, 0, 5, 1, 1)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.position_groupBox = QGroupBox(TelescopeControlWidget)
        self.position_groupBox.setObjectName(u"position_groupBox")
        self.gridLayout_3 = QGridLayout(self.position_groupBox)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.formLayout_2.setFormAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.zenithLabel = QLabel(self.position_groupBox)
        self.zenithLabel.setObjectName(u"zenithLabel")
        font1 = QFont()
        font1.setPointSize(20)
        font1.setUnderline(True)
        self.zenithLabel.setFont(font1)
        self.zenithLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.formLayout_2.setWidget(0, QFormLayout.SpanningRole, self.zenithLabel)

        self.zenith_actualLabel = QLabel(self.position_groupBox)
        self.zenith_actualLabel.setObjectName(u"zenith_actualLabel")
        font2 = QFont()
        font2.setPointSize(15)
        self.zenith_actualLabel.setFont(font2)

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.zenith_actualLabel)

        self.zenith_actual_valLabel = QLabel(self.position_groupBox)
        self.zenith_actual_valLabel.setObjectName(u"zenith_actual_valLabel")
        self.zenith_actual_valLabel.setFont(font2)

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.zenith_actual_valLabel)

        self.zenith_ppsLabel = QLabel(self.position_groupBox)
        self.zenith_ppsLabel.setObjectName(u"zenith_ppsLabel")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.zenith_ppsLabel)

        self.zenith_pps_valLabel = QLabel(self.position_groupBox)
        self.zenith_pps_valLabel.setObjectName(u"zenith_pps_valLabel")

        self.formLayout_2.setWidget(2, QFormLayout.FieldRole, self.zenith_pps_valLabel)

        self.zenith_commandedLabel = QLabel(self.position_groupBox)
        self.zenith_commandedLabel.setObjectName(u"zenith_commandedLabel")

        self.formLayout_2.setWidget(3, QFormLayout.LabelRole, self.zenith_commandedLabel)

        self.zenith_commanded_valLabel = QLabel(self.position_groupBox)
        self.zenith_commanded_valLabel.setObjectName(u"zenith_commanded_valLabel")

        self.formLayout_2.setWidget(3, QFormLayout.FieldRole, self.zenith_commanded_valLabel)

        self.zenith_errorLabel = QLabel(self.position_groupBox)
        self.zenith_errorLabel.setObjectName(u"zenith_errorLabel")

        self.formLayout_2.setWidget(4, QFormLayout.LabelRole, self.zenith_errorLabel)

        self.zenith_error_valLabel = QLabel(self.position_groupBox)
        self.zenith_error_valLabel.setObjectName(u"zenith_error_valLabel")

        self.formLayout_2.setWidget(4, QFormLayout.FieldRole, self.zenith_error_valLabel)

        self.zenith_velocityLabel = QLabel(self.position_groupBox)
        self.zenith_velocityLabel.setObjectName(u"zenith_velocityLabel")

        self.formLayout_2.setWidget(5, QFormLayout.LabelRole, self.zenith_velocityLabel)

        self.zenith_velocity_valLabel = QLabel(self.position_groupBox)
        self.zenith_velocity_valLabel.setObjectName(u"zenith_velocity_valLabel")

        self.formLayout_2.setWidget(5, QFormLayout.FieldRole, self.zenith_velocity_valLabel)

        self.zenith_setlineEdit = QLineEdit(self.position_groupBox)
        self.zenith_setlineEdit.setObjectName(u"zenith_setlineEdit")

        self.formLayout_2.setWidget(6, QFormLayout.LabelRole, self.zenith_setlineEdit)

        self.zenith_setpushButton = QPushButton(self.position_groupBox)
        self.zenith_setpushButton.setObjectName(u"zenith_setpushButton")

        self.formLayout_2.setWidget(6, QFormLayout.FieldRole, self.zenith_setpushButton)


        self.gridLayout_3.addLayout(self.formLayout_2, 1, 2, 1, 1)

        self.line = QFrame(self.position_groupBox)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.Shape.VLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.gridLayout_3.addWidget(self.line, 1, 1, 1, 1)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFormAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.azimuthLabel = QLabel(self.position_groupBox)
        self.azimuthLabel.setObjectName(u"azimuthLabel")
        self.azimuthLabel.setFont(font1)
        self.azimuthLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.formLayout.setWidget(0, QFormLayout.SpanningRole, self.azimuthLabel)

        self.azimuth_actualLabel = QLabel(self.position_groupBox)
        self.azimuth_actualLabel.setObjectName(u"azimuth_actualLabel")
        self.azimuth_actualLabel.setFont(font2)

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.azimuth_actualLabel)

        self.azimuth_actual_valLabel = QLabel(self.position_groupBox)
        self.azimuth_actual_valLabel.setObjectName(u"azimuth_actual_valLabel")
        self.azimuth_actual_valLabel.setFont(font2)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.azimuth_actual_valLabel)

        self.azimuth_ppsLabel = QLabel(self.position_groupBox)
        self.azimuth_ppsLabel.setObjectName(u"azimuth_ppsLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.azimuth_ppsLabel)

        self.azimuth_pps_valLabel = QLabel(self.position_groupBox)
        self.azimuth_pps_valLabel.setObjectName(u"azimuth_pps_valLabel")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.azimuth_pps_valLabel)

        self.azimuth_commandedLabel = QLabel(self.position_groupBox)
        self.azimuth_commandedLabel.setObjectName(u"azimuth_commandedLabel")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.azimuth_commandedLabel)

        self.azimuth_commanded_valLabel = QLabel(self.position_groupBox)
        self.azimuth_commanded_valLabel.setObjectName(u"azimuth_commanded_valLabel")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.azimuth_commanded_valLabel)

        self.azimuth_errorLabel = QLabel(self.position_groupBox)
        self.azimuth_errorLabel.setObjectName(u"azimuth_errorLabel")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.azimuth_errorLabel)

        self.azimuth_error_valLabel = QLabel(self.position_groupBox)
        self.azimuth_error_valLabel.setObjectName(u"azimuth_error_valLabel")

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.azimuth_error_valLabel)

        self.azimuth_velocityLabel = QLabel(self.position_groupBox)
        self.azimuth_velocityLabel.setObjectName(u"azimuth_velocityLabel")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.azimuth_velocityLabel)

        self.azimuth_velocity_valLabel = QLabel(self.position_groupBox)
        self.azimuth_velocity_valLabel.setObjectName(u"azimuth_velocity_valLabel")

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.azimuth_velocity_valLabel)

        self.azimuth_setlineEdit = QLineEdit(self.position_groupBox)
        self.azimuth_setlineEdit.setObjectName(u"azimuth_setlineEdit")

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.azimuth_setlineEdit)

        self.azimuth_setpushButton = QPushButton(self.position_groupBox)
        self.azimuth_setpushButton.setObjectName(u"azimuth_setpushButton")

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.azimuth_setpushButton)


        self.gridLayout_3.addLayout(self.formLayout, 1, 0, 1, 1)

        self.enable_motion_checkBox = QCheckBox(self.position_groupBox)
        self.enable_motion_checkBox.setObjectName(u"enable_motion_checkBox")
        self.enable_motion_checkBox.setChecked(True)

        self.gridLayout_3.addWidget(self.enable_motion_checkBox, 0, 0, 1, 1)


        self.verticalLayout.addWidget(self.position_groupBox)


        self.gridLayout.addLayout(self.verticalLayout, 0, 3, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 0, 1, 1, 1)


        self.gridLayout_2.addLayout(self.gridLayout, 0, 0, 1, 1)

        self.live_footage_canvas = ScrollableCanvas(TelescopeControlWidget)
        self.live_footage_canvas.setObjectName(u"live_footage_canvas")

        self.gridLayout_2.addWidget(self.live_footage_canvas, 2, 0, 1, 1)


        self.retranslateUi(TelescopeControlWidget)

        QMetaObject.connectSlotsByName(TelescopeControlWidget)
    # setupUi

    def retranslateUi(self, TelescopeControlWidget):
        TelescopeControlWidget.setWindowTitle(QCoreApplication.translate("TelescopeControlWidget", u"MainWindow", None))
        self.optical_pushButton.setText(QCoreApplication.translate("TelescopeControlWidget", u"Show Optical Video", None))
        self.stop_pushButton.setText("")
        self.control_groupBox.setTitle(QCoreApplication.translate("TelescopeControlWidget", u"Manual Control", None))
        self.manual_controlcheckBox.setText(QCoreApplication.translate("TelescopeControlWidget", u"Enable Manual Control", None))
        self.position_groupBox.setTitle(QCoreApplication.translate("TelescopeControlWidget", u"Telescope Position", None))
        self.zenithLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Zenith", None))
        self.zenith_actualLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Actual", None))
        self.zenith_actual_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.zenith_ppsLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"PPS pos:", None))
        self.zenith_pps_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"N/A", None))
        self.zenith_commandedLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Commanded", None))
        self.zenith_commanded_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.zenith_errorLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Error", None))
        self.zenith_error_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.zenith_velocityLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Velocity", None))
        self.zenith_velocity_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0/sec", None))
        self.zenith_setpushButton.setText(QCoreApplication.translate("TelescopeControlWidget", u"Set", None))
        self.azimuthLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Azimuth", None))
        self.azimuth_actualLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Actual", None))
        self.azimuth_actual_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_ppsLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"PPS pos:", None))
        self.azimuth_pps_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"N/A", None))
        self.azimuth_commandedLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Commanded", None))
        self.azimuth_commanded_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_errorLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Error", None))
        self.azimuth_error_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0", None))
        self.azimuth_velocityLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"Velocity", None))
        self.azimuth_velocity_valLabel.setText(QCoreApplication.translate("TelescopeControlWidget", u"0.0\u00b0/sec", None))
        self.azimuth_setpushButton.setText(QCoreApplication.translate("TelescopeControlWidget", u"Set", None))
        self.enable_motion_checkBox.setText(QCoreApplication.translate("TelescopeControlWidget", u"Enable Telescope Motion", None))
    # retranslateUi

