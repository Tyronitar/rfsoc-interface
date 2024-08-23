# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loconfig.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenuBar, QPushButton,
    QRadioButton, QSizePolicy, QSpacerItem, QStatusBar,
    QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 600)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label = QLabel(self.centralwidget)
        self.label.setObjectName(u"label")

        self.verticalLayout.addWidget(self.label)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.label_9 = QLabel(self.centralwidget)
        self.label_9.setObjectName(u"label_9")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_9)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.lineEdit_8 = QLineEdit(self.centralwidget)
        self.lineEdit_8.setObjectName(u"lineEdit_8")

        self.horizontalLayout.addWidget(self.lineEdit_8)

        self.pushButton = QPushButton(self.centralwidget)
        self.pushButton.setObjectName(u"pushButton")

        self.horizontalLayout.addWidget(self.pushButton)


        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.horizontalLayout)

        self.label_2 = QLabel(self.centralwidget)
        self.label_2.setObjectName(u"label_2")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_2)

        self.lineEdit_2 = QLineEdit(self.centralwidget)
        self.lineEdit_2.setObjectName(u"lineEdit_2")
        self.lineEdit_2.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.lineEdit_2)

        self.label_3 = QLabel(self.centralwidget)
        self.label_3.setObjectName(u"label_3")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_3)

        self.lineEdit_3 = QLineEdit(self.centralwidget)
        self.lineEdit_3.setObjectName(u"lineEdit_3")
        self.lineEdit_3.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.lineEdit_3)

        self.label_4 = QLabel(self.centralwidget)
        self.label_4.setObjectName(u"label_4")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_4)

        self.lineEdit = QLineEdit(self.centralwidget)
        self.lineEdit.setObjectName(u"lineEdit")
        self.lineEdit.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.lineEdit)

        self.label_6 = QLabel(self.centralwidget)
        self.label_6.setObjectName(u"label_6")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_6)

        self.lineEdit_6 = QLineEdit(self.centralwidget)
        self.lineEdit_6.setObjectName(u"lineEdit_6")
        self.lineEdit_6.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.lineEdit_6)

        self.label_5 = QLabel(self.centralwidget)
        self.label_5.setObjectName(u"label_5")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_5)

        self.checkBox = QCheckBox(self.centralwidget)
        self.checkBox.setObjectName(u"checkBox")
        self.checkBox.setChecked(True)

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.checkBox)

        self.checkBox_2 = QCheckBox(self.centralwidget)
        self.checkBox_2.setObjectName(u"checkBox_2")
        self.checkBox_2.setChecked(True)

        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.checkBox_2)

        self.checkBox_3 = QCheckBox(self.centralwidget)
        self.checkBox_3.setObjectName(u"checkBox_3")
        self.checkBox_3.setChecked(True)

        self.formLayout.setWidget(8, QFormLayout.LabelRole, self.checkBox_3)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.label_8 = QLabel(self.centralwidget)
        self.label_8.setObjectName(u"label_8")
        self.label_8.setEnabled(True)

        self.horizontalLayout_2.addWidget(self.label_8)

        self.lineEdit_9 = QLineEdit(self.centralwidget)
        self.lineEdit_9.setObjectName(u"lineEdit_9")
        self.lineEdit_9.setEnabled(True)
        self.lineEdit_9.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout_2.addWidget(self.lineEdit_9)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)


        self.formLayout.setLayout(8, QFormLayout.FieldRole, self.horizontalLayout_2)

        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.radioButton = QRadioButton(self.centralwidget)
        self.buttonGroup = QButtonGroup(MainWindow)
        self.buttonGroup.setObjectName(u"buttonGroup")
        self.buttonGroup.addButton(self.radioButton)
        self.radioButton.setObjectName(u"radioButton")
        self.radioButton.setChecked(True)

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.radioButton)

        self.radioButton_2 = QRadioButton(self.centralwidget)
        self.buttonGroup.addButton(self.radioButton_2)
        self.radioButton_2.setObjectName(u"radioButton_2")
        self.radioButton_2.setEnabled(True)
        self.radioButton_2.setChecked(False)

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.radioButton_2)

        self.lineEdit_5 = QLineEdit(self.centralwidget)
        self.lineEdit_5.setObjectName(u"lineEdit_5")
        self.lineEdit_5.setEnabled(False)
        self.lineEdit_5.setMaximumSize(QSize(200, 16777215))
        self.lineEdit_5.setReadOnly(False)

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.lineEdit_5)

        self.radioButton_3 = QRadioButton(self.centralwidget)
        self.buttonGroup.addButton(self.radioButton_3)
        self.radioButton_3.setObjectName(u"radioButton_3")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.radioButton_3)

        self.lineEdit_4 = QLineEdit(self.centralwidget)
        self.lineEdit_4.setObjectName(u"lineEdit_4")
        self.lineEdit_4.setEnabled(False)
        self.lineEdit_4.setMaximumSize(QSize(200, 16777215))

        self.formLayout_2.setWidget(2, QFormLayout.FieldRole, self.lineEdit_4)

        self.label_7 = QLabel(self.centralwidget)
        self.label_7.setObjectName(u"label_7")

        self.formLayout_2.setWidget(3, QFormLayout.LabelRole, self.label_7)

        self.lineEdit_7 = QLineEdit(self.centralwidget)
        self.lineEdit_7.setObjectName(u"lineEdit_7")
        self.lineEdit_7.setEnabled(False)

        self.formLayout_2.setWidget(3, QFormLayout.FieldRole, self.lineEdit_7)


        self.formLayout.setLayout(5, QFormLayout.FieldRole, self.formLayout_2)


        self.verticalLayout.addLayout(self.formLayout)

        self.buttonBox = QDialogButtonBox(self.centralwidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)

        self.verticalLayout.addWidget(self.buttonBox)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 22))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"LO Sweep Configuration", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"LO Sweep Settings", None))
#if QT_CONFIG(tooltip)
        self.label_9.setToolTip(QCoreApplication.translate("MainWindow", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_9.setWhatsThis(QCoreApplication.translate("MainWindow", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.label_9.setText(QCoreApplication.translate("MainWindow", u"Tone List:", None))
        self.pushButton.setText(QCoreApplication.translate("MainWindow", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.label_2.setToolTip(QCoreApplication.translate("MainWindow", u"Amount to shift each tone in KHz, at 400 MHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_2.setWhatsThis(QCoreApplication.translate("MainWindow", u"Amount to shift each tone in KHz, at 400 MHz", None))
#endif // QT_CONFIG(whatsthis)
        self.label_2.setText(QCoreApplication.translate("MainWindow", u"Global shift (KHz):", None))
        self.lineEdit_2.setText("")
        self.lineEdit_2.setPlaceholderText(QCoreApplication.translate("MainWindow", u"0", None))
#if QT_CONFIG(tooltip)
        self.label_3.setToolTip(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_3.setWhatsThis(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.label_3.setText(QCoreApplication.translate("MainWindow", u"df (KHz):", None))
        self.lineEdit_3.setPlaceholderText(QCoreApplication.translate("MainWindow", u"1", None))
#if QT_CONFIG(tooltip)
        self.label_4.setToolTip(QCoreApplication.translate("MainWindow", u"Total span of sweep in KHZ", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_4.setWhatsThis(QCoreApplication.translate("MainWindow", u"Total span of sweep in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.label_4.setText(QCoreApplication.translate("MainWindow", u"\u0394f (KHz):", None))
        self.lineEdit.setText("")
        self.lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"100", None))
#if QT_CONFIG(tooltip)
        self.label_6.setToolTip(QCoreApplication.translate("MainWindow", u"Maximum shift to flag", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_6.setWhatsThis(QCoreApplication.translate("MainWindow", u"Maximum shift to flag", None))
#endif // QT_CONFIG(whatsthis)
        self.label_6.setText(QCoreApplication.translate("MainWindow", u"Flagging Threshold (KHz):", None))
        self.lineEdit_6.setPlaceholderText(QCoreApplication.translate("MainWindow", u"3", None))
#if QT_CONFIG(tooltip)
        self.label_5.setToolTip(QCoreApplication.translate("MainWindow", u"Suffix to append to the end of the LO sweep file", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_5.setWhatsThis(QCoreApplication.translate("MainWindow", u"Suffix to append to the end of the LO sweep file", None))
#endif // QT_CONFIG(whatsthis)
        self.label_5.setText(QCoreApplication.translate("MainWindow", u"Filename suffix:", None))
#if QT_CONFIG(tooltip)
        self.checkBox.setToolTip(QCoreApplication.translate("MainWindow", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.checkBox.setWhatsThis(QCoreApplication.translate("MainWindow", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.checkBox.setText(QCoreApplication.translate("MainWindow", u"Show diagnostics", None))
#if QT_CONFIG(tooltip)
        self.checkBox_2.setToolTip(QCoreApplication.translate("MainWindow", u"Review the new tone list after the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.checkBox_2.setWhatsThis(QCoreApplication.translate("MainWindow", u"Review the new tone list after the sweep. Unchecking this box will accept the input tone list", None))
#endif // QT_CONFIG(whatsthis)
        self.checkBox_2.setText(QCoreApplication.translate("MainWindow", u"Review new tones", None))
#if QT_CONFIG(tooltip)
        self.checkBox_3.setToolTip(QCoreApplication.translate("MainWindow", u"Run a second LO sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.checkBox_3.setWhatsThis(QCoreApplication.translate("MainWindow", u"Run a second LO sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.checkBox_3.setText(QCoreApplication.translate("MainWindow", u"Perform second sweep", None))
#if QT_CONFIG(tooltip)
        self.label_8.setToolTip(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.label_8.setWhatsThis(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.label_8.setText(QCoreApplication.translate("MainWindow", u"df (KHz):", None))
        self.lineEdit_9.setText(QCoreApplication.translate("MainWindow", u"0.1", None))
        self.radioButton.setText(QCoreApplication.translate("MainWindow", u"None", None))
        self.radioButton_2.setText(QCoreApplication.translate("MainWindow", u"Temperature", None))
        self.radioButton_3.setText(QCoreApplication.translate("MainWindow", u"Elevation", None))
        self.label_7.setText(QCoreApplication.translate("MainWindow", u"Example:", None))
        self.lineEdit_7.setText(QCoreApplication.translate("MainWindow", u"YYYYMMDD_RFSOCX_LO_Sweep_HH", None))
    # retranslateUi

