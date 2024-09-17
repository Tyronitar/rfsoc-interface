# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loresonator.ui'
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
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMenuBar, QPushButton, QSizePolicy, QSpacerItem,
    QStatusBar, QToolBar, QVBoxLayout, QWidget)

from rfsocinterface.ui.canvas import ResonatorCanvas
from . import icons_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(633, 532)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_2 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.canvas = ResonatorCanvas(self.centralwidget)
        self.canvas.setObjectName(u"canvas")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.canvas.sizePolicy().hasHeightForWidth())
        self.canvas.setSizePolicy(sizePolicy1)

        self.verticalLayout_2.addWidget(self.canvas)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.old_freq_label = QLabel(self.centralwidget)
        self.old_freq_label.setObjectName(u"old_freq_label")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.old_freq_label)

        self.old_freq_value_label = QLabel(self.centralwidget)
        self.old_freq_value_label.setObjectName(u"old_freq_value_label")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.old_freq_value_label)

        self.new_freq_label = QLabel(self.centralwidget)
        self.new_freq_label.setObjectName(u"new_freq_label")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.new_freq_label)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.new_freq_lineEdit = QLineEdit(self.centralwidget)
        self.new_freq_lineEdit.setObjectName(u"new_freq_lineEdit")
        self.new_freq_lineEdit.setMaximumSize(QSize(200, 16777215))

        self.horizontalLayout_2.addWidget(self.new_freq_lineEdit)

        self.reset_pushButton = QPushButton(self.centralwidget)
        self.reset_pushButton.setObjectName(u"reset_pushButton")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.reset_pushButton.sizePolicy().hasHeightForWidth())
        self.reset_pushButton.setSizePolicy(sizePolicy2)

        self.horizontalLayout_2.addWidget(self.reset_pushButton)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)


        self.formLayout.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout_2)

        self.delta_label = QLabel(self.centralwidget)
        self.delta_label.setObjectName(u"delta_label")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.delta_label)

        self.delta_value_label = QLabel(self.centralwidget)
        self.delta_value_label.setObjectName(u"delta_value_label")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.delta_value_label)

        self.depth_label = QLabel(self.centralwidget)
        self.depth_label.setObjectName(u"depth_label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.depth_label)

        self.depth_value_label = QLabel(self.centralwidget)
        self.depth_value_label.setObjectName(u"depth_value_label")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.depth_value_label)


        self.verticalLayout_2.addLayout(self.formLayout)

        self.buttonBox = QDialogButtonBox(self.centralwidget)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)

        self.verticalLayout_2.addWidget(self.buttonBox)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 633, 22))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.toolBar = QToolBar(MainWindow)
        self.toolBar.setObjectName(u"toolBar")
        MainWindow.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolBar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.old_freq_label.setText(QCoreApplication.translate("MainWindow", u"Old Frequency:", None))
        self.old_freq_value_label.setText("")
        self.new_freq_label.setText(QCoreApplication.translate("MainWindow", u"New Frequency:", None))
        self.reset_pushButton.setText(QCoreApplication.translate("MainWindow", u"Reset", None))
        self.delta_label.setText(QCoreApplication.translate("MainWindow", u"\u0394f:", None))
        self.delta_value_label.setText("")
        self.depth_label.setText(QCoreApplication.translate("MainWindow", u"Resonance Depth:", None))
        self.depth_value_label.setText("")
        self.toolBar.setWindowTitle(QCoreApplication.translate("MainWindow", u"toolBar", None))
    # retranslateUi

