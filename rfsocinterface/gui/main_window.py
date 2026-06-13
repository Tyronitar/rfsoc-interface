import logging
from multiprocessing import Array, Lock, Pipe, Process, Queue
from multiprocessing.connection import Connection
from threading import Thread

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QCoreApplication, Signal, Slot
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import (
    QGridLayout,
    QMainWindow,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.camera import MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH
from rfsocinterface.core.rfsoc import RFSOCWrapper

# from kidpy3 import RFSOC
from rfsocinterface.core.settings import Settings, SettingsError
from rfsocinterface.core.utils import TabName, ensure_path
from rfsocinterface.gui.data_streaming import DataStreamingWidget
from rfsocinterface.gui.initialization import InitializationWidget
from rfsocinterface.gui.loconfig import LoConfigWidget
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.gui.uic.full_ui_ui import Ui_MainWindow

_logger = logging.getLogger(__name__)
_tele_logger = logging.getLogger('rfsocinterface.telescopeControl')
_camera_logger = logging.getLogger('rfsocinterface.cameraControl')


class MainWindow(QMainWindow, Ui_MainWindow):
    """The Main program window."""

    channelNamesUpdated = Signal()
    telescopeUpdate = Signal(str, tuple)
    cameraUpdate = Signal(str, tuple)
    closeWindow = Signal()

    @ensure_path(1)
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.settings = Settings()
        self.settings.load_settings()

        self.telescope_queue: Queue = None
        self.telescope_parent_conn: Connection = None
        self.telescope_child_conn: Connection = None
        self.telescope_controller_process: Process = None

        self.camera_queue: Queue = None
        self.camera_parent_conn: Connection = None
        self.camera_child_conn: Connection = None
        self.camera_controller_process: Process = None
        self.shared_camera_array = Array('B', MAX_FRAME_HEIGHT * MAX_FRAME_WIDTH * 3)
        self.shared_timestamp_array = Array('d', 1)
        self.camera_array = np.frombuffer(
            self.shared_camera_array.get_obj(), dtype=np.uint8
        ).reshape(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3)
        self.timestamp_array = np.frombuffer(
            self.shared_timestamp_array.get_obj(), dtype=np.float64
        ).reshape(1)
        self.camera_array_lock = Lock()
        self.timestamp_array_lock = Lock()

        self.tabs: dict[TabName, MainWidget] = {}
        self.rfsocs: list[RFSOCWrapper] = []
        self.init_rfsocs()

        self.setupUi(self)
        self._additional_ui_setup()
        self.closeWindow.connect(self.close)

    def get_current_image(self) -> tuple[npt.NDArray, float]:
        with self.camera_array_lock:
            with self.timestamp_array_lock:
                return self.camera_array[:], self.timestamp_array[:]

    def _make_telescope_controller(self):
        from rfsocinterface.core.telescope import make_controller

        # If it already exists, we're good
        if self.telescope_controller_process is not None:
            return
        self.telescope_parent_conn, self.telescope_child_conn = Pipe(duplex=True)
        self.telescope_controller_process = Process(
            target=make_controller, args=(self.telescope_child_conn,)
        )
        self.telescope_controller_process.start()

        self._telescope_listener_thread = Thread(target=self._telescope_listener_loop)
        self._telescope_listener_thread.start()

    def _make_camera_controller(self):
        from rfsocinterface.core.camera import make_controller

        # If it already exists, we're good
        if self.camera_controller_process is not None:
            return
        self.camera_parent_conn, self.camera_child_conn = Pipe(duplex=True)
        self.camera_controller_process = Process(
            target=make_controller,
            args=(
                self.camera_child_conn,
                self.shared_camera_array,
                self.shared_timestamp_array,
                self.camera_array_lock,
                self.timestamp_array_lock,
            ),
        )
        self.camera_controller_process.start()

        self._camera_listener_thread = Thread(target=self._camera_listener_loop)
        self._camera_listener_thread.start()

    def _make_initialization_tab(self):
        self.initialization_tab = QWidget()
        self.initialization_tab.setObjectName('initialization_tab')
        self.verticalLayout = QVBoxLayout(self.initialization_tab)
        self.verticalLayout.setObjectName('verticalLayout')
        self.initialization_widget = InitializationWidget(
            self, self.rfsocs, self.settings, self.initialization_tab
        )
        self.initialization_widget.setObjectName('initialization_widget')
        self.verticalLayout.addWidget(self.initialization_widget)
        self.tabWidget.addTab(self.initialization_tab, '')
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.initialization_tab),
            QCoreApplication.translate('MainWindow', 'Initialization', None),
        )
        self.tabs[TabName.INITIALIZATION] = self.initialization_widget

    def _make_losweep_tab(self):
        self.losweep_tab = QWidget()
        self.losweep_tab.setObjectName('losweep_tab')
        self.verticalLayout_4 = QVBoxLayout(self.losweep_tab)
        self.verticalLayout_4.setObjectName('verticalLayout_4')
        self.losweep_widget = LoConfigWidget(
            self, self.rfsocs, self.settings, self.losweep_tab
        )
        self.losweep_widget.setObjectName('losweep_widget')
        self.verticalLayout_4.addWidget(self.losweep_widget)
        self.tabWidget.addTab(self.losweep_tab, '')
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.losweep_tab),
            QCoreApplication.translate('MainWindow', 'LO Sweep', None),
        )
        self.tabs[TabName.LOSWEEP] = self.losweep_widget

    def _make_data_tab(self):
        self.data_tab = QWidget()
        self.data_tab.setObjectName('data_tab')
        self.tabWidget.addTab(self.data_tab, '')
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.data_tab),
            QCoreApplication.translate('MainWindow', 'Data', None),
        )
        self.data_widget = DataStreamingWidget(
            self, self.rfsocs, self.settings, self.data_tab
        )
        self.verticalLayout_5 = QVBoxLayout(self.data_tab)
        self.verticalLayout_5.setObjectName('verticalLayout_5')
        self.verticalLayout_5.addWidget(self.data_widget)
        self.tabs[TabName.DATA] = self.data_widget

    def _make_telescope_tab(self):
        from rfsocinterface.gui.telescope import TelescopeControlWidget

        self._make_telescope_controller()
        self._make_camera_controller()
        self.telescope_tab = QWidget()
        self.telescope_tab.setObjectName('telescope_tab')
        self.gridLayout = QGridLayout(self.telescope_tab)
        self.gridLayout.setObjectName('gridLayout')
        self.telescope_widget = TelescopeControlWidget(
            self, self.rfsocs, self.settings, TabName.TELESCOPE, self.telescope_tab
        )
        self.telescope_widget.setObjectName('telescope_widget')
        self.gridLayout.addWidget(self.telescope_widget, 0, 0, 1, 1)
        self.tabWidget.addTab(self.telescope_tab, '')
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.telescope_tab),
            QCoreApplication.translate('MainWindow', 'Telescope', None),
        )
        self.tabs[TabName.TELESCOPE] = self.telescope_widget

    def _make_imaging_tab(self):
        from rfsocinterface.gui.imaging import ImagingWidget

        self._make_telescope_controller()
        self._make_camera_controller()
        self.imaging_tab = QWidget()
        self.imaging_tab.setObjectName('imaging_tab')
        self.tabWidget.addTab(self.imaging_tab, '')
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.imaging_tab),
            QCoreApplication.translate('MainWindow', 'Imaging', None),
        )
        self.imaging_widget = ImagingWidget(
            self, self.rfsocs, self.settings, TabName.IMAGING, self.imaging_tab
        )
        self.verticalLayout_6 = QVBoxLayout(self.imaging_tab)
        self.verticalLayout_6.setObjectName('verticalLayout_6')
        self.verticalLayout_6.addWidget(self.imaging_widget)
        self.tabs[TabName.IMAGING] = self.imaging_widget

    def _additional_ui_setup(self):
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName('tabWidget')

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
                    raise SettingsError(
                        f'Invalid name "{tab}" in general.tabs; valid options are {[name.value for name in TabName]}'
                    )

        active_tab = self.settings['app'].get('activeTab', TabName.INITIALIZATION)
        self.tabWidget.currentChanged.connect(self.resize_to_current)
        self.tabWidget.currentChanged.connect(self.update_active_tab)
        self.set_active_tab(active_tab)

    def index(self, tab_name: TabName) -> int:
        return list(self.tabs.keys()).index(tab_name)

    def tab_at(self, index: int) -> TabName:
        """Return the tab at the given index."""
        return list(self.tabs.keys())[index]

    def init_rfsocs(self):
        for rfsoc_settings in self.settings['rfsocs']:
            rfsoc = RFSOCWrapper(rfsoc_settings)
            self.rfsocs.append(rfsoc)

    def resize_to_current(self, index: int):
        for i in range(self.tabWidget.count()):
            tab = self.tabWidget.widget(i)
            if i != index:
                tab.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
                )
        curr_tab = self.tabWidget.widget(index)
        curr_tab.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        # curr_tab.resize(curr_tab.minimumSizeHint())
        # curr_tab.adjustSize()
        # self.resize(self.minimumSizeHint())
        # self.adjustSize()

    def _telescope_listener_loop(self):
        _logger.debug('Started telescope listener loop')
        try:
            while True:
                if not self.telescope_parent_conn.poll(1e-4):
                    continue
                response, *data = self.telescope_parent_conn.recv()
                _tele_logger.debug(
                    f'MAIN got response from TELESCOPE: "{response}", data: {data}'
                )
                match response.lower():
                    case 'err':
                        criticality = data[0]
                        if criticality == 'CRITICAL':
                            raise RuntimeError(
                                f'Critical error from telescope controller: {data[1]}'
                            )
                    case 'done':
                        break
                    case _:
                        self.telescopeUpdate.emit(response, data)
        except RuntimeError as e:
            self.closeWindow.emit()
            raise RuntimeError from e

    def _camera_listener_loop(self):
        _logger.debug('Started camera listener loop')
        try:
            while True:
                if not self.camera_parent_conn.poll(1e-4):
                    continue
                response, *data = self.camera_parent_conn.recv()
                _camera_logger.debug(
                    f'MAIN got response from CAMERA: "{response}", data: {data}'
                )
                match response.lower():
                    case 'err':
                        criticality = data[0]
                        if criticality == 'CRITICAL':
                            raise RuntimeError(
                                f'Critical error from camera controller: {data[1]}'
                            )
                    case 'done':
                        break
                    case _:
                        self.cameraUpdate.emit(response, data)
        except RuntimeError as e:
            self.closeWindow.emit()
            raise RuntimeError from e

    @Slot(int)
    def update_active_tab(self, index: int):
        """Update the active tab in the settings."""
        tab_name = self.tab_at(index)
        self.settings['app']['activeTab'] = tab_name
        _logger.debug(f'Active tab updated to index {index}')

    def set_active_tab(self, tab: TabName):
        if tab in self.tabs:
            _logger.debug(f'Setting active tab to {tab}')
            self.tabWidget.setCurrentIndex(self.index(tab))

    def get_active_tab(self) -> TabName:
        return self.settings['app']['activeTab']

    def closeEvent(self, event):
        self.hide()
        for tab in self.tabs.values():
            tab.close()

        if self.telescope_controller_process is not None:
            self.telescope_parent_conn.send(['terminate'])
            self._telescope_listener_thread.join()
            self.telescope_controller_process.join()

        if self.camera_controller_process is not None:
            self.camera_parent_conn.send(['terminate'])
            self._camera_listener_thread.join()
            self.camera_controller_process.join()

        self.settings.save_settings()
        return super().closeEvent(event)


def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())
