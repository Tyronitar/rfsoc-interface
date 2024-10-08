# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'full_ui.ui'
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QMainWindow,
    QMenuBar, QSizePolicy, QStatusBar, QTabWidget,
    QVBoxLayout, QWidget)

from rfsocinterface.initialization import InitializationWidget
from rfsocinterface.loconfig import LoConfigWidget
from rfsocinterface.telescope import TelescopeControlWidget
from . import icons_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(892, 603)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")
        self.initialization_tab = QWidget()
        self.initialization_tab.setObjectName(u"initialization_tab")
        self.verticalLayout = QVBoxLayout(self.initialization_tab)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.initialization_widget = InitializationWidget(self.initialization_tab)
        self.initialization_widget.setObjectName(u"initialization_widget")

        self.verticalLayout.addWidget(self.initialization_widget)

        self.tabWidget.addTab(self.initialization_tab, "")
        self.losweep_tab = QWidget()
        self.losweep_tab.setObjectName(u"losweep_tab")
        self.verticalLayout_4 = QVBoxLayout(self.losweep_tab)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.losweep_widget = LoConfigWidget(self.losweep_tab)
        self.losweep_widget.setObjectName(u"losweep_widget")

        self.verticalLayout_4.addWidget(self.losweep_widget)

        self.tabWidget.addTab(self.losweep_tab, "")
        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName(u"telescope_tab")
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.telescope_widget = TelescopeControlWidget(self.telescope_tab)
        self.telescope_widget.setObjectName(u"telescope_widget")

        self.gridLayout.addWidget(self.telescope_widget, 0, 0, 1, 1)

        self.tabWidget.addTab(self.telescope_tab, "")
        self.data_tab = QWidget()
        self.data_tab.setObjectName(u"data_tab")
        self.tabWidget.addTab(self.data_tab, "")
        self.imaging_tab = QWidget()
        self.imaging_tab.setObjectName(u"imaging_tab")
        self.tabWidget.addTab(self.imaging_tab, "")

        self.horizontalLayout.addWidget(self.tabWidget)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 892, 22))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        self.tabWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.initialization_tab), QCoreApplication.translate("MainWindow", u"Initialization", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.losweep_tab), QCoreApplication.translate("MainWindow", u"LO Sweep", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.telescope_tab), QCoreApplication.translate("MainWindow", u"Telescope", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.data_tab), QCoreApplication.translate("MainWindow", u"Data", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.imaging_tab), QCoreApplication.translate("MainWindow", u"Imaging", None))
    # retranslateUi

