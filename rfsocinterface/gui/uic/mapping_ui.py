# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mapping.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QGridLayout, QSizePolicy, QSpacerItem, QToolButton,
    QWidget)

from rfsocinterface.gui.widgets.function import DragFunctionWidget

class Ui_MappingDialog(object):
    def setupUi(self, MappingDialog):
        if not MappingDialog.objectName():
            MappingDialog.setObjectName(u"MappingDialog")
        MappingDialog.resize(426, 348)
        self.gridLayout = QGridLayout(MappingDialog)
        self.gridLayout.setObjectName(u"gridLayout")
        self.drag_function_widget = DragFunctionWidget(MappingDialog)
        self.drag_function_widget.setObjectName(u"drag_function_widget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.drag_function_widget.sizePolicy().hasHeightForWidth())
        self.drag_function_widget.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.drag_function_widget, 0, 0, 1, 4)

        self.buttonBox = QDialogButtonBox(MappingDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)

        self.gridLayout.addWidget(self.buttonBox, 2, 1, 1, 3)

        self.remove_toolButton = QToolButton(MappingDialog)
        self.remove_toolButton.setObjectName(u"remove_toolButton")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListRemove))
        self.remove_toolButton.setIcon(icon)
        self.remove_toolButton.setIconSize(QSize(32, 32))

        self.gridLayout.addWidget(self.remove_toolButton, 1, 3, 1, 1)

        self.add_toolButton = QToolButton(MappingDialog)
        self.add_toolButton.setObjectName(u"add_toolButton")
        icon1 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
        self.add_toolButton.setIcon(icon1)
        self.add_toolButton.setIconSize(QSize(32, 32))

        self.gridLayout.addWidget(self.add_toolButton, 1, 2, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 1, 0, 1, 2)


        self.retranslateUi(MappingDialog)
        self.buttonBox.accepted.connect(MappingDialog.accept)
        self.buttonBox.rejected.connect(MappingDialog.reject)

        QMetaObject.connectSlotsByName(MappingDialog)
    # setupUi

    def retranslateUi(self, MappingDialog):
        MappingDialog.setWindowTitle(QCoreApplication.translate("MappingDialog", u"Dialog", None))
        self.remove_toolButton.setText(QCoreApplication.translate("MappingDialog", u"...", None))
        self.add_toolButton.setText(QCoreApplication.translate("MappingDialog", u"...", None))
    # retranslateUi

