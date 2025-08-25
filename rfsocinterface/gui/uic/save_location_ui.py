# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'save_location.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QGroupBox,
    QLabel, QSizePolicy, QVBoxLayout, QWidget)

from rfsocinterface.gui.widgets.file_select import FileSelectWidget

class Ui_SaveLocationWidget(object):
    def setupUi(self, SaveLocationWidget):
        if not SaveLocationWidget.objectName():
            SaveLocationWidget.setObjectName(u"SaveLocationWidget")
        SaveLocationWidget.resize(284, 140)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SaveLocationWidget.sizePolicy().hasHeightForWidth())
        SaveLocationWidget.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(SaveLocationWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.groupBox = QGroupBox(SaveLocationWidget)
        self.groupBox.setObjectName(u"groupBox")
        self.gridLayout_3 = QGridLayout(self.groupBox)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.directory_label = QLabel(self.groupBox)
        self.directory_label.setObjectName(u"directory_label")

        self.gridLayout_3.addWidget(self.directory_label, 1, 0, 1, 1)

        self.filename_label = QLabel(self.groupBox)
        self.filename_label.setObjectName(u"filename_label")

        self.gridLayout_3.addWidget(self.filename_label, 2, 0, 1, 1)

        self.checkBox = QCheckBox(self.groupBox)
        self.checkBox.setObjectName(u"checkBox")
        self.checkBox.setChecked(True)

        self.gridLayout_3.addWidget(self.checkBox, 0, 0, 1, 1)

        self.save_locale_label = QLabel(self.groupBox)
        self.save_locale_label.setObjectName(u"save_locale_label")

        self.gridLayout_3.addWidget(self.save_locale_label, 3, 0, 1, 2)

        self.directory_file_select = FileSelectWidget(self.groupBox)
        self.directory_file_select.setObjectName(u"directory_file_select")

        self.gridLayout_3.addWidget(self.directory_file_select, 1, 1, 1, 1)

        self.filename_file_select = FileSelectWidget(self.groupBox)
        self.filename_file_select.setObjectName(u"filename_file_select")

        self.gridLayout_3.addWidget(self.filename_file_select, 2, 1, 1, 1)


        self.verticalLayout.addWidget(self.groupBox)


        self.retranslateUi(SaveLocationWidget)

        QMetaObject.connectSlotsByName(SaveLocationWidget)
    # setupUi

    def retranslateUi(self, SaveLocationWidget):
        SaveLocationWidget.setWindowTitle(QCoreApplication.translate("SaveLocationWidget", u"Form", None))
        self.groupBox.setTitle(QCoreApplication.translate("SaveLocationWidget", u"Save Location", None))
        self.directory_label.setText(QCoreApplication.translate("SaveLocationWidget", u"Directory:", None))
        self.filename_label.setText(QCoreApplication.translate("SaveLocationWidget", u"Filename:", None))
        self.checkBox.setText(QCoreApplication.translate("SaveLocationWidget", u"Use default data location", None))
        self.save_locale_label.setText(QCoreApplication.translate("SaveLocationWidget", u"Saving to \"/data/\"", None))
    # retranslateUi

