# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'routine_list.ui'
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QSizePolicy, QSpacerItem,
    QToolButton, QWidget)

from rfsocinterface.gui.widgets.drag_and_drop import MultiSectionDragFunctionWidget

class Ui_RoutineListWidget(object):
    def setupUi(self, RoutineListWidget):
        if not RoutineListWidget.objectName():
            RoutineListWidget.setObjectName(u"RoutineListWidget")
        RoutineListWidget.resize(400, 300)
        self.gridLayout = QGridLayout(RoutineListWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.horizontalSpacer = QSpacerItem(287, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 1, 0, 1, 1)

        self.add_toolButton = QToolButton(RoutineListWidget)
        self.add_toolButton.setObjectName(u"add_toolButton")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
        self.add_toolButton.setIcon(icon)
        self.add_toolButton.setIconSize(QSize(32, 32))

        self.gridLayout.addWidget(self.add_toolButton, 1, 1, 1, 1)

        self.drag_function_widget = MultiSectionDragFunctionWidget(RoutineListWidget)
        self.drag_function_widget.setObjectName(u"drag_function_widget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.drag_function_widget.sizePolicy().hasHeightForWidth())
        self.drag_function_widget.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.drag_function_widget, 0, 0, 1, 3)

        self.remove_toolButton = QToolButton(RoutineListWidget)
        self.remove_toolButton.setObjectName(u"remove_toolButton")
        icon1 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListRemove))
        self.remove_toolButton.setIcon(icon1)
        self.remove_toolButton.setIconSize(QSize(32, 32))

        self.gridLayout.addWidget(self.remove_toolButton, 1, 2, 1, 1)


        self.retranslateUi(RoutineListWidget)

        QMetaObject.connectSlotsByName(RoutineListWidget)
    # setupUi

    def retranslateUi(self, RoutineListWidget):
        RoutineListWidget.setWindowTitle(QCoreApplication.translate("RoutineListWidget", u"Form", None))
        self.add_toolButton.setText(QCoreApplication.translate("RoutineListWidget", u"...", None))
        self.remove_toolButton.setText(QCoreApplication.translate("RoutineListWidget", u"...", None))
    # retranslateUi

