"""Common code for the main tabs of the GUI."""

import logging
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, override

import numpy.typing as npt
from kidpy3.data_handler import Rfchan
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from rfsocinterface.core.rfsoc import RFSoCWrapper, get_channel_from_text
from rfsocinterface.core.settings import SettingsError
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.core.utils import PERMISSIONS_USR_RW, TabName
from rfsocinterface.gui.widgets import CheckableComboBox, SaveLocationWidget

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)


class MainWidget(QWidget):
    """Widget representing one of the tabs in the GUI."""

    tab_name: TabName

    def __init__(
        self,
        main_window: 'MainWindow',
        rfsocs: list[RFSoCWrapper],
        settings: dict,
        parent: QWidget | None = None,
    ):
        """Initialize a MainWidget."""
        super().__init__(parent)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings
        self.gui_state = {}

    @property
    def is_active_tab(self) -> bool:
        """Whether this tab is the currently active one."""
        return self.main_window.get_active_tab() == self.tab_name

    def update_channel_choices(self, combo_box: CheckableComboBox):
        """Update possible channel choices in a combo box."""
        total = 0
        combo_box.clear()
        combo_box.deselect_all()
        for rfsoc in self.rfsocs:
            for i in range(2):
                combo_box.addItem(rfsoc.channel_as_text(i + 1))
                item = combo_box.model().item(total, 0)
                item.setCheckState(Qt.CheckState.Unchecked)
                total += 1

    def get_selected_channels(
        self, combo_box: CheckableComboBox
    ) -> list[tuple[RFSoCWrapper, int]]:
        """Get the currently selected channels from a combo box."""
        checked_ids = combo_box.checked_indices()
        checked_text = [combo_box.itemText(i) for i in checked_ids]
        if not checked_text:
            msg = f'{self.tab_name}: No channel selected.'
            _logger.error(msg)
            raise SettingsError('No channel selected')
        return list(
            map(partial(get_channel_from_text, rfsocs=self.rfsocs), checked_text)
        )

    def _save_state(self):
        """Save current GUI state of the tab.

        To be implemented by subclasses.
        """
        self.settings['app'][self.tab_name] = self.gui_state

    @override
    def closeEvent(self, event):
        self._save_state()
        return super().closeEvent(event)


class TelescopeMainWidget(MainWidget):
    """A MainWidget that communicates with the telescope and camera controllers."""

    def __init__(self, main_window: 'MainWindow', rfsocs, settings, parent=None):
        """Initialize a TelescopeMainbWidget."""
        super().__init__(main_window, rfsocs, settings, parent)

        self.main_window.telescopeUpdate.connect(self.handle_telescope)
        self.main_window.cameraUpdate.connect(self.handle_camera)
        self.telescope_commands: dict[str, list[Callable]] = {}
        self._telescope_command_data = (
            None  # Data returned from a command that was waited for
        )
        self.camera_commands: dict[str, list[Callable]] = {}
        self._camera_command_data = (
            None  # Data returned from a command that was waited for
        )

    def handle_telescope(self, command: str, args: tuple):
        """Call any registered callbacks upon receipt of a telescope command."""
        if command in self.telescope_commands:
            for callback in self.telescope_commands[command]:
                callback(*args)

    def handle_camera(self, command: str, args: tuple):
        """Call any registered callbacks upon receipt of a camera command."""
        _logger.debug(f'Handling camera command: {command} with args: {args}')
        if command in self.camera_commands:
            for callback in self.camera_commands[command]:
                callback(*args)

    def get_current_image(self) -> tuple[npt.NDArray, float]:
        """Get the current optical image."""
        return self.main_window.get_current_image()

    def connect_to_telescope_command(self, command: str, callback: Callable):
        """Connect a callback to a telescope controller command."""
        self.telescope_commands.setdefault(command, []).append(callback)

    def disconnect_telescope_command(self, command: str, callback: Callable):
        """Disconnect a callback from a telescope controller command."""
        self.telescope_commands[command].remove(callback)

    def send_telescope_command(self, command: str, *data):
        """Send a command to the telescope controller."""
        self.main_window.telescope_parent_conn.send([command, *data])

    def connect_to_camera_command(self, command: str, callback: Callable):
        """Connect a callback to a camera controller command."""
        self.camera_commands.setdefault(command, []).append(callback)

    def disconnect_camera_command(self, command: str, callback: Callable):
        """Disconnect a callback from a camera controller command."""
        self.camera_commands[command].remove(callback)

    def send_camera_command(self, command: str, *data):
        """Send a command to the camera controller."""
        self.main_window.camera_parent_conn.send([command, *data])

    def wait_for_telescope_command(self, command: str, err_msg: str = ''):  # noqa: ARG002
        """Wait for the specified command from the telescope controller."""
        wait = True

        def stop_waiting(*data):
            nonlocal wait
            wait = False
            self._telescope_command_data = data

        self.connect_to_telescope_command(command, stop_waiting)
        while wait:
            time.sleep(1e-3)
            QCoreApplication.processEvents()
        self.disconnect_telescope_command(command, stop_waiting)

    def wait_for_camera_command(self, command: str, err_msg: str = ''):  # noqa: ARG002
        """Wait for the specified command from the camera controller."""
        wait = True

        def stop_waiting(*data):
            nonlocal wait
            wait = False
            self._camera_command_data = data

        self.connect_to_camera_command(command, stop_waiting)
        while wait:
            time.sleep(1e-3)
            QCoreApplication.processEvents()
        self.disconnect_camera_command(command, stop_waiting)

    @override
    def closeEvent(self, event):
        return super().closeEvent(event)


class DataCollectionMainWidget(MainWidget):
    """GUI tab that collects data."""

    save_location_widget: SaveLocationWidget

    def __init__(
        self,
        main_window: 'MainWindow',
        rfsocs: list[RFSoCWrapper],
        settings: dict,
        parent=None,
    ):
        """Initialize a DataCollectionMainWidget."""
        super().__init__(main_window, rfsocs, settings, parent=parent)

    def setup_data_collection(
        self,
    ) -> tuple[list[RFSoCWrapper], list[int], list[Rfchan], str, int]:
        """Setup the data collection for all selected channels."""
        chans = self.get_selected_channels(self.channel_comboBox)
        rfsocs = []
        channels = []
        rfchans = []
        for rfsoc, chan in chans:
            rfsocs.append(rfsoc)
            channels.append(chan)
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(
                chan_name=rfchan.tile_name,
                touch_file=True,
                mode=PERMISSIONS_USR_RW,
                mkdir=True,
            )
            rfchan.raw_filename = str(save_location)
            rfchans.extend(rfsoc.setup_capture(save_location, [chan]))
        date = save_location.stem[:8]
        setnum = int(save_location.stem[-4:])
        return rfsocs, channels, rfchans, date, setnum

    def append_global_data(
        self, rfsocs: list[RFSoCWrapper], channels: list[int], rfchans: list[Rfchan]
    ):
        """Append global data for each selected channel."""
        for rfsoc, channel, rfchan in zip(rfsocs, channels, rfchans, strict=False):
            rfsoc.append_global_data(channel, rfchan.raw_filename)

    def remove_TOD_files(self, rfchans: list[Rfchan]):
        """Remove TOD files in case of collection cancellation after setup."""
        for rfchan in rfchans:
            path = Path(rfchan.raw_filename)
            path.unlink(missing_ok=True)

    def check_for_lo_sweep(
        self, rfsocs: list[RFSoCWrapper], channels: list[int]
    ) -> bool:
        """Check that a LO sweep has been run for all selected channels today.

        Returns:
            bool: Whether to proceed with data collection.
        """
        for rfsoc, channel in zip(rfsocs, channels, strict=False):
            tile_name = rfsoc.get_tile_name(channel)
            sweep = LoSweepData.load_most_recent(tile_name)
            if sweep is None:
                msg = QMessageBox(
                    QMessageBox.Icon.Warning,
                    'Confirm Data Collection',
                    'No high-res LO Sweeps have been performed today for '
                    f'"{tile_name}". '
                    'Do you want to proceed with data collection anyway? '
                    '(A missing LO sweep may cause issues for data procssing later)',
                    parent=self,
                )
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.YesToAll
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel
                )
                msg.setDefaultButton(QMessageBox.StandardButton.No)
                ret = msg.exec()
                match ret:
                    case QMessageBox.StandardButton.Yes:
                        continue
                    case (
                        QMessageBox.StandardButton.Cancel
                        | QMessageBox.StandardButton.No
                    ):
                        return False
                    case QMessageBox.StandardButton.YesToAll:
                        return True
                    case _:
                        msg = f'Unexpected option returned from QMessageBox: {ret}'
                        _logger.error(msg)
                        raise RuntimeError(msg)
        return True
