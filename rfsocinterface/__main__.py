"""Main entry point for the rfsocinterface package."""

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication

from kidpy import kidpy, testConnection, wait_for_reply, wait_for_free
from rfsocinterface.ui.full_ui_ui import Ui_MainWindow
from rfsocinterface.initialization import InitializationWidget
from rfsocinterface.loconfig import LoConfigWidget
from rfsocinterface.telescope import TelescopeControlWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)

        # self.kpy = kidpy()
        self.init_kidpy()

        self.setupUi(self)
        self._additional_ui_setup()
        self.tabWidget.currentChanged.connect(self.resize_to_current)
        # Do this to 
        self.tabWidget.setCurrentIndex(0)
        self.resize_to_current(0)
    
    def _additional_ui_setup(self):
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")

        self.initialization_tab = QWidget()
        self.initialization_tab.setObjectName(u"initialization_tab")
        self.verticalLayout = QVBoxLayout(self.initialization_tab)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.initialization_widget = InitializationWidget(self.kpy, self.initialization_tab)
        self.initialization_widget.setObjectName(u"initialization_widget")
        self.verticalLayout.addWidget(self.initialization_widget)
        self.tabWidget.addTab(self.initialization_tab, "")

        self.losweep_tab = QWidget()
        self.losweep_tab.setObjectName(u"losweep_tab")
        self.verticalLayout_4 = QVBoxLayout(self.losweep_tab)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.losweep_widget = LoConfigWidget(self.kpy, self.losweep_tab)
        self.losweep_widget.setObjectName(u"losweep_widget")
        self.verticalLayout_4.addWidget(self.losweep_widget)
        self.tabWidget.addTab(self.losweep_tab, "")

        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName(u"telescope_tab")
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.telescope_widget = TelescopeControlWidget(self.kpy, self.telescope_tab)
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

        # Handle Translation
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.initialization_tab), QCoreApplication.translate("MainWindow", u"Initialization", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.losweep_tab), QCoreApplication.translate("MainWindow", u"LO Sweep", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.telescope_tab), QCoreApplication.translate("MainWindow", u"Telescope", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.data_tab), QCoreApplication.translate("MainWindow", u"Data", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.imaging_tab), QCoreApplication.translate("MainWindow", u"Imaging", None))

        self.tabWidget.setCurrentIndex(0)

    def init_kidpy(self):
        self.kpy = kidpy()
        conStatus = testConnection(self.kpy.r)
        if conStatus:
            print("\033[0;36m" + "\r\nConnected" + "\033[0m")
        else:
            print(
                "\033[0;31m"
                + "\r\nCouldn't connect to redis-server double check it's running and the generalConfig is correct"
                + "\033[0m"
            )
        if conStatus == False:
            exit(1)
    
    def resize_to_current(self, index: int):
        for i in range(self.tabWidget.count()):
            tab = self.tabWidget.widget(i)
            if i != index:
                tab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        curr_tab = self.tabWidget.widget(index)
        curr_tab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # curr_tab.resize(curr_tab.minimumSizeHint())
        # curr_tab.adjustSize()
        # self.resize(self.minimumSizeHint())
        # self.adjustSize()


if __name__ == '__main__':
    app = QApplication()

    w = MainWindow()
    w.show()
    app.exec()
