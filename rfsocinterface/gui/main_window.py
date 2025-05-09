from pathlib import Path
import yaml
from multiprocessing import Queue, Process, Pipe

from multiprocessing.connection import Connection
from threading import Thread

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QScreen
import PySide6.QtGui as QtGui

# from kidpy3 import RFSOC
from rfsocinterface.core.settings import Settings, SettingsError, convert_to_kidy_format
from rfsocinterface.gui.uic.full_ui_ui import Ui_MainWindow
from rfsocinterface.gui.initialization import InitializationWidget
from rfsocinterface.gui.loconfig import LoConfigWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.data_streaming import DataStreamingWidget
from rfsocinterface.gui.main_widget import MainWidget

from rfsocinterface.core.utils import ensure_path, TabName, wait_for_telescope_command

import json


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    @ensure_path(1)
    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)

        self.settings = Settings()
        self.settings.load_settings()

        self.telescope_queue: Queue = None
        self.telescope_conn: Connection = None
        self.telescope_controller_process: Process = None
        
        self.tabs: dict[TabName, MainWidget] = {}
        self.rfsocs: list[RFSOCWrapper] = []
        self.init_rfsocs()

        self.setupUi(self)
        self._additional_ui_setup()
        self.tabWidget.currentChanged.connect(self.resize_to_current)
        self.tabWidget.setCurrentIndex(0)
        self.resize_to_current(0)
    
    def _make_telescope_controller(self):
        from rfsocinterface.core.telescope import make_controller
        # If it already exists, we're good
        if self.telescope_queue is not None:
            return
        self.telescope_queue = Queue()
        self.telescope_parent_conn, self.telescope_child_conn = Pipe(duplex=False)
        self.telescope_controller_process = Process(target=make_controller, args=(self.telescope_queue,))
        self.telescope_controller_process.start()

        self._client_id = 'MAIN'
        self.telescope_queue.put([self._client_id, 'add_connection', self.telescope_child_conn])
        self.wait_for_telescope_command(
            'add_connection_succesful',
            err_msg=f'Error received from telescope controller when adding connection {self._client_id}',
        )
        self._listener_thread = Thread(target=self._listener_loop)
        self._listener_thread.start()

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
        self.tabs[TabName.INITIALIZATION] = self.initialization_widget
    
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
        self.tabs[TabName.LOSWEEP] = self.losweep_widget
       
    def _make_data_tab(self):
        self.data_tab = QWidget()
        self.data_tab.setObjectName(u"data_tab")
        self.tabWidget.addTab(self.data_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.data_tab), QCoreApplication.translate("MainWindow", u"Data", None))
        self.data_widget = DataStreamingWidget(self, self.rfsocs, self.settings, self.data_tab)
        self.verticalLayout_5 = QVBoxLayout(self.data_tab)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.addWidget(self.data_widget)
        self.tabs[TabName.DATA] = self.data_widget

    def _make_telescope_tab(self):
        from rfsocinterface.gui.telescope import TelescopeControlWidget
        self._make_telescope_controller()
        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName(u"telescope_tab")
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName(u"gridLayout")
        self.telescope_widget = TelescopeControlWidget(self, self.rfsocs, self.settings, TabName.TELESCOPE, self.telescope_tab)
        self.telescope_widget.setObjectName(u"telescope_widget")
        self.gridLayout.addWidget(self.telescope_widget, 0, 0, 1, 1)
        self.tabWidget.addTab(self.telescope_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.telescope_tab), QCoreApplication.translate("MainWindow", u"Telescope", None))
        self.tabs[TabName.TELESCOPE] = self.telescope_widget
 
    
    def _make_imaging_tab(self):
        from rfsocinterface.gui.imaging import ImagingWidget
        self._make_telescope_controller()
        self.imaging_tab = QWidget()
        self.imaging_tab.setObjectName(u"imaging_tab")
        self.tabWidget.addTab(self.imaging_tab, "")
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.imaging_tab), QCoreApplication.translate("MainWindow", u"Imaging", None))
        self.imaging_widget = ImagingWidget(self, self.rfsocs, self.settings, TabName.IMAGING, self.imaging_tab)
        self.verticalLayout_6 = QVBoxLayout(self.imaging_tab)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.verticalLayout_6.addWidget(self.imaging_widget)
        self.tabs[TabName.IMAGING] = self.imaging_widget
    
    def _additional_ui_setup(self):
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")

        self.horizontalLayout.addWidget(self.tabWidget)
        tab: str
        for tab in self.settings['app']['tabs']:
            match tab.lower():
                case TabName.INITIALIZATION:
                    self._make_initialization_tab()
                case TabName.LOSWEEP:
                    self._make_losweep_tab()
                case TabName.TELESCOPE:
                    self._make_telescope_tab()
                case TabName.DATA:
                    self._make_data_tab()
                case TabName.IMAGING:
                    self._make_imaging_tab()
                case _:
                    raise SettingsError(f'Invalid name "{tab}" in general.tabs; valid options are {[name.value for name in TabName]}')

        active_tab = self.settings['app'].get('activeTab', TabName.INITIALIZATION)
        self.tabWidget.setCurrentIndex(self.index(active_tab))

    def index(self, tab_name: TabName) -> int:
        return list(self.tabs.keys()).index(tab_name)

    def init_rfsocs(self):
        for rfsoc_settings in self.settings['rfsocs']:
            rfsoc = RFSOCWrapper(rfsoc_settings)
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
    
    def _listener_loop(self):
        self.wait_for_telescope_command('done')

    def wait_for_telescope_command(self, command: str, err_msg: str=''):
        wait_for_telescope_command(self.telescope_parent_conn, self._client_id, command, err_msg=err_msg)

    def closeEvent(self, event):
        self.hide()
        for tab in self.tabs.values():
            tab.close()

        if self.telescope_controller_process is not None:
            self.telescope_queue.put([self._client_id, 'terminate'])
            self._listener_thread.join()
            self.telescope_controller_process.join()
        return super().closeEvent(event)

def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())
