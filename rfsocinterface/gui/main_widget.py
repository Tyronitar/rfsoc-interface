from typing import TYPE_CHECKING, Iterator, Callable
from functools import partial
from multiprocessing import Queue, Pipe
import time

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QCoreApplication

from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from rfsocinterface.core.utils import wait_for_telescope_command
if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class MainWidget(QWidget):


    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings
    
    @property
    def _telescope_queue(self) -> Queue:
        """Return the telescope queue for communication with the telescope controller."""
        return self.main_window.telescope_queue

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
        self.commands: dict[str, list[Callable]] = {}
        self._command_data = None  # Data returned from a command that was waited for

    def handle_telescope(self, command: str, args: tuple):
        if command in self.commands:
            for callback in self.commands[command]:
                callback(*args)
    
    def connect_to_command(self, command: str, callback: Callable):
        self.commands.setdefault(command, []).append(callback)

    def disconnect_command(self, command: str, callback: Callable):
        self.commands[command].remove(callback)
    
    def send_command(self, command: str, *data):
        self.main_window.telescope_parent_conn.send([command, *data])

    def wait_for_telescope_command(self, command: str, err_msg: str=''):
        wait = True
        def stop_waiting(data: tuple):
            nonlocal wait
            wait = False
            self._command_data = data
        self.connect_to_command(command, stop_waiting)
        while wait:
            time.sleep(1e-3)
            QCoreApplication.processEvents()
        self.disconnect_command(command, stop_waiting)

    def closeEvent(self, event):
        return super().closeEvent(event)


class DataCollectionWidget(MainWidget):
    channelComboBox: CheckableComboBox
    save_location_widget: Sa
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
    
    def setup_data_collection(self):
        assert 'save_location_widget' in vars(self)