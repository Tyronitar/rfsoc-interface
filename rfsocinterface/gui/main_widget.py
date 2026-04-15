from typing import TYPE_CHECKING, Iterator, Callable, Protocol
from functools import partial
from multiprocessing import Queue, Pipe
import time
from abc import ABC, abstractmethod
import logging

import numpy.typing as npt
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QCoreApplication
from kidpy3.data_handler import Rfchan

from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.settings import SettingsError
from rfsocinterface.core.utils import wait_for_telescope_command, PERMISSIONS_USR_RW, TabName
from rfsocinterface.gui.widgets import CheckableComboBox, SaveLocationWidget
if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)

class MainWidget(QWidget):
    tab_name: TabName

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings
    
    @property
    def _telescope_queue(self) -> Queue:
        """Return the telescope queue for communication with the telescope controller."""
        return self.main_window.telescope_queue
    
    @property
    def is_active_tab(self) -> bool:
        return self.main_window.get_active_tab() == self.tab_name

    def update_channel_choices(self, combo_box: CheckableComboBox):
        total = 0
        combo_box.clear()
        combo_box.deselect_all()
        for rfsoc in self.rfsocs:
            for i in range(2):
                combo_box.addItem(rfsoc.channel_as_text(i + 1))
                item = combo_box.model().item(total, 0)
                item.setCheckState(Qt.CheckState.Unchecked)
                total += 1

    def get_selected_channels(self, combo_box: CheckableComboBox) -> list[tuple[RFSOCWrapper, int]]:
        checked_ids = combo_box.checked_indices()
        checked_text = [combo_box.itemText(i) for i in checked_ids]
        if not checked_text:
            raise SettingsError('No channel selected')
        return list(map(partial(get_channel_from_text, rfsocs=self.rfsocs), checked_text))
    
    def closeEvent(self, event):
        return super().closeEvent(event)

class TelescopeMainWidget(MainWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs, settings, client_id: str, parent = None):
        super().__init__(main_window, rfsocs, settings, parent)

        self.main_window.telescopeUpdate.connect(self.handle_telescope)
        self.main_window.cameraUpdate.connect(self.handle_camera)
        self.telescope_commands: dict[str, list[Callable]] = {}
        self._telescope_command_data = None  # Data returned from a command that was waited for
        self.camera_commands: dict[str, list[Callable]] = {}
        self._camera_command_data = None  # Data returned from a command that was waited for

    def handle_telescope(self, command: str, args: tuple):
        if command in self.telescope_commands:
            for callback in self.telescope_commands[command]:
                callback(*args)

    def handle_camera(self, command: str, args: tuple):
        _logger.debug(f'Handling camera command: {command} with args: {args}')
        if command in self.camera_commands:
            for callback in self.camera_commands[command]:
                callback(*args)
    
    def get_current_image(self) -> tuple[npt.NDArray, float]:
        return self.main_window.get_current_image()
    
    def connect_to_telescope_command(self, command: str, callback: Callable):
        self.telescope_commands.setdefault(command, []).append(callback)

    def disconnect_telescope_command(self, command: str, callback: Callable):
        self.telescope_commands[command].remove(callback)
    
    def send_telescope_command(self, command: str, *data):
        self.main_window.telescope_parent_conn.send([command, *data])

    def connect_to_camera_command(self, command: str, callback: Callable):
        self.camera_commands.setdefault(command, []).append(callback)

    def disconnect_camera_command(self, command: str, callback: Callable):
        self.camera_commands[command].remove(callback)

    def send_camera_command(self, command: str, *data):
        self.main_window.camera_parent_conn.send([command, *data])

    def wait_for_telescope_command(self, command: str, err_msg: str=''):
        wait = True
        def stop_waiting(data: tuple):
            nonlocal wait
            wait = False
            self._telescope_command_data = data
        self.connect_to_telescope_command(command, stop_waiting)
        while wait:
            time.sleep(1e-3)
            QCoreApplication.processEvents()
        self.disconnect_telescope_command(command, stop_waiting)
    
    def wait_for_camera_command(self, command: str, err_msg: str=''):
        wait = True
        def stop_waiting(data: tuple):
            nonlocal wait
            wait = False
            self._camera_command_data = data
        self.connect_to_camera_command(command, stop_waiting)
        while wait:
            time.sleep(1e-3)
            QCoreApplication.processEvents()
        self.disconnect_camera_command(command, stop_waiting)

    def closeEvent(self, event):
        return super().closeEvent(event)


class DataCollectionMainWidget(MainWidget):
    channelComboBox: CheckableComboBox
    save_location_widget: SaveLocationWidget

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
    
    def setup_data_collection(self) -> tuple[list[Rfchan], str, int]:
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=rfchan.tile_name, touch_file=True, mode=PERMISSIONS_USR_RW, mkdir=True)
            rfchan.raw_filename = str(save_location)
            rfchans.extend(rfsoc.setup_capture(save_location, [chan]))
        date = save_location.stem[:8]
        setnum = int(save_location.stem[-4:])
        return rfchans, date, setnum