"""Main entry point for the rfsocinterface package."""

import tomllib
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication

from kidpy import kidpy, testConnection, wait_for_reply, wait_for_free
from rfsocinterface.ui.full_ui_ui import Ui_MainWindow
from rfsocinterface.initialization import InitializationWidget
from rfsocinterface.loconfig import LoConfigWidget
from rfsocinterface.telescope import TelescopeControlWidget
from rfsocinterface.utils import SettingsError, ensure_path

TAB_NAMES = {
    "initialization",
    "losweep",
    "telescope",
    "data",
    "imaging",
}


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    @ensure_path(1)
    def __init__(self, settings_file: Path, parent: QWidget | None=None):
        super().__init__(parent)

        with settings_file.open('rb') as f:
            self.settings = tomllib.load(f)

        self.tabs = []
        self.kpy = None
        # self.init_kidpy()

        self.setupUi(self)
        self._additional_ui_setup()
        self.tabWidget.currentChanged.connect(self.resize_to_current)
        # Do this to 
        self.tabWidget.setCurrentIndex(0)
        self.resize_to_current(0)

    def _make_initialization_tab(self):
        self.initialization_tab = QWidget()
        self.initialization_tab.setObjectName(u"initialization_tab")
        self.verticalLayout = QVBoxLayout(self.initialization_tab)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.initialization_widget = InitializationWidget(self.kpy, self.settings, self.initialization_tab)
        self.initialization_widget.setObjectName(u"initialization_widget")
        self.verticalLayout.addWidget(self.initialization_widget)
        self.tabWidget.addTab(self.initialization_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.initialization_tab), QCoreApplication.translate("MainWindow", u"Initialization", None))
        self.tabs.append(self.initialization_widget)
    
    def _make_losweep_tab(self):
        self.losweep_tab = QWidget()
        self.losweep_tab.setObjectName(u"losweep_tab")
        self.verticalLayout_4 = QVBoxLayout(self.losweep_tab)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.losweep_widget = LoConfigWidget(self.kpy, self.losweep_tab)
        self.losweep_widget.setObjectName(u"losweep_widget")
        self.verticalLayout_4.addWidget(self.losweep_widget)
        self.tabWidget.addTab(self.losweep_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.losweep_tab), QCoreApplication.translate("MainWindow", u"LO Sweep", None))
        self.tabs.append(self.losweep_widget)
    
    def _make_telescope_tab(self):
        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName(u"telescope_tab")
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.telescope_widget = TelescopeControlWidget(self.kpy, self.telescope_tab)
        self.telescope_widget.setObjectName(u"telescope_widget")
        self.gridLayout.addWidget(self.telescope_widget, 0, 0, 1, 1)
        self.tabWidget.addTab(self.telescope_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.telescope_tab), QCoreApplication.translate("MainWindow", u"Telescope", None))
        self.tabs.append(self.telescope_widget)
    
    def _make_data_tab(self):
        self.data_tab = QWidget()
        self.data_tab.setObjectName(u"data_tab")
        self.tabWidget.addTab(self.data_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.data_tab), QCoreApplication.translate("MainWindow", u"Data", None))
        # self.tabs.append(self.data_widget)
    
    def _make_imaging_tab(self):
        self.imaging_tab = QWidget()
        self.imaging_tab.setObjectName(u"imaging_tab")
        self.tabWidget.addTab(self.imaging_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.imaging_tab), QCoreApplication.translate("MainWindow", u"Imaging", None))
        # self.tabs.append(self.imaging_widget)
    
    def _additional_ui_setup(self):
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")

        self.horizontalLayout.addWidget(self.tabWidget)
        for tab in self.settings['general']['tabs']:
            match tab:
                case "initialization":
                    self._make_initialization_tab()
                case "losweep":
                    self._make_losweep_tab()
                case "telescope":
                    self._make_telescope_tab()
                case "data":
                    self._make_data_tab()
                case "imaging":
                    self._make_imaging_tab()
                case _:
                    raise SettingsError(f'Invalid name for general.tabs: "{tab}". Valid options are {TAB_NAMES}')

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
    
    def closeEvent(self, event):
        return super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication()

    w = MainWindow("settings_caltech.toml")
    w.show()
    app.exec()
