import tomllib
from pathlib import Path
import yaml

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QScreen
import PySide6.QtGui as QtGui

from kidpy import kidpy, testConnection, wait_for_reply, wait_for_free
# from kidpy3 import RFSOC
from rfsocinterface.gui.uic.full_ui_ui import Ui_MainWindow
from rfsocinterface.gui.initialization import InitializationWidget
from rfsocinterface.gui.loconfig import LoConfigWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.data_streaming import DataStreamingWidget

from rfsocinterface.core.utils import SettingsError, ensure_path, convert_to_kidy_format

TAB_NAMES = {
    "initialization",
    "losweep",
    "telescope",
    "data",
    "imaging",
}

import json


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    @ensure_path(1)
    def __init__(self, settings_file: Path, parent: QWidget | None=None):
        super().__init__(parent)

        with settings_file.open('rb') as f:
            self.settings = tomllib.load(f)
        
        self.tabs = {}
        self.rfsocs: list[RFSOCWrapper] = []
        self.init_rfsocs()
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
        self.initialization_widget = InitializationWidget(self, self.rfsocs, self.settings, self.initialization_tab)
        self.initialization_widget.setObjectName(u"initialization_widget")
        self.verticalLayout.addWidget(self.initialization_widget)
        self.tabWidget.addTab(self.initialization_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.initialization_tab), QCoreApplication.translate("MainWindow", u"Initialization", None))
        self.tabs['initialization'] = self.initialization_widget
    
    def _make_losweep_tab(self):
        self.losweep_tab = QWidget()
        self.losweep_tab.setObjectName(u"losweep_tab")
        self.verticalLayout_4 = QVBoxLayout(self.losweep_tab)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.losweep_widget = LoConfigWidget(self, self.rfsocs, self.settings, self.losweep_tab)
        self.losweep_widget.setObjectName(u"losweep_widget")
        self.verticalLayout_4.addWidget(self.losweep_widget)
        self.tabWidget.addTab(self.losweep_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.losweep_tab), QCoreApplication.translate("MainWindow", u"LO Sweep", None))
        self.tabs['losweep'] = self.losweep_widget
    
    def _make_telescope_tab(self):
        from rfsocinterface.telescope import TelescopeControlWidget
        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName(u"telescope_tab")
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.telescope_widget = TelescopeControlWidget(self, self.rfsocs, self.telescope_tab)
        self.telescope_widget.setObjectName(u"telescope_widget")
        self.gridLayout.addWidget(self.telescope_widget, 0, 0, 1, 1)
        self.tabWidget.addTab(self.telescope_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.telescope_tab), QCoreApplication.translate("MainWindow", u"Telescope", None))
        self.tabs['telescope'] = self.telescope_widget
    
    def _make_data_tab(self):
        self.data_tab = QWidget()
        self.data_tab.setObjectName(u"data_tab")
        self.tabWidget.addTab(self.data_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.data_tab), QCoreApplication.translate("MainWindow", u"Data", None))
        self.data_widget = DataStreamingWidget(self, self.rfsocs, self.data_tab)
        self.verticalLayout_5 = QVBoxLayout(self.data_tab)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.addWidget(self.data_widget)
        self.tabs['data'] = self.data_widget
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
                    raise SettingsError(f'Invalid name "{tab}" in general.tabs; valid options are {TAB_NAMES}')

        self.tabWidget.setCurrentIndex(0)

    def index(self, tab_name: str) -> int:
        return list(self.tabs.keys()).index(tab_name)

    def init_rfsocs(self):
        rfsoc_settings: dict
        for rfsoc_settings in self.settings['rfsocs']:
            rfsoc = RFSOCWrapper(self.settings['defaults'], rfsoc_settings)
            self.rfsocs.append(rfsoc)

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

def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())