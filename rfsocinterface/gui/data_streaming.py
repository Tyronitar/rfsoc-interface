"""GUI tab for timed data collection."""

import logging
import time
from typing import TYPE_CHECKING

from kidpy3 import capture
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QProgressDialog

from rfsocinterface.core.rfsoc import RFSoCWrapper
from rfsocinterface.core.utils import (
    TabName,
)
from rfsocinterface.gui.main_widget import DataCollectionMainWidget
from rfsocinterface.gui.uic.data_streaming_ui import Ui_DataStreamingWidget
from rfsocinterface.gui.widgets import get_num_value

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)


class DataStreamingWidget(DataCollectionMainWidget, Ui_DataStreamingWidget):
    """GUI tab for timed data collection."""

    tab_name = TabName.DATA

    def __init__(
        self,
        main_window: 'MainWindow',
        rfsocs: list[RFSoCWrapper],
        settings: dict,
        parent=None,
    ):
        """Initialize a DataStreamingWidget."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.save_location_widget.file_type = 'tod'

        self.channel_comboBox.set_default_title('Select Channels...')
        self.setup_connections()
        self.update_channel_choices(self.channel_comboBox)
        main_window.channel_names_updated.connect(
            lambda: self.update_channel_choices(self.channel_comboBox)
        )

    def setup_connections(self):
        """Setup widget connections."""
        self.start_pushButton.clicked.connect(self.start_streaming)

    def wait_for_TOD(self, duration: int):
        """Wait for the TOD file to be created before processing."""
        pd = QProgressDialog('Collecting data...', 'Cancel', 0, duration, parent=self)
        pd.setValue(0)
        pd.setWindowTitle('rfsocinterface')
        pd.setModal(True)
        pd.show()
        start = time.time()
        now = time.time()
        counter = 0
        while now - start < duration:
            if pd.wasCanceled():
                pd.close()
                return
            time.sleep(0.1)
            QCoreApplication.processEvents()
            now = time.time()
            remaining_time = duration - (now - start)
            pd.setLabelText(
                f'Collecting data...\nRemaining time: {int(remaining_time)} seconds'
            )
            pd.setValue(now - start)
            counter += 1
            if counter % 50 == 0:
                _logger.info(
                    'Collecting data: '
                    f'{100 * (now - start) / duration:.2f}% complete...'
                )

    def process_data(self, date: str, setnum: int):
        """Process the data after collecting it."""
        # _logger.info('Processing data')

    def start_streaming(self):
        """Start collecting data."""
        self.save_location_widget.update_timer.stop()
        rfsocs, channels, rfchans, date, setnum = self.setup_data_collection()
        if not self.check_for_lo_sweep(rfsocs, channels):
            _logger.info('Missing 1 or more LO sweeps, cancelling data collection.')
            self.remove_TOD_files(rfchans)
            self.save_location_widget.update_timer.start()
            return

        duration = get_num_value(self.duration_lineEdit, int, use_placeholder_text=True)

        _logger.debug(
            f'Streaming {duration} seconds of data for chans: '
            f'{[chan.tile_name for chan in rfchans]}'
        )
        capture(rfchans, self.wait_for_TOD, duration)
        _logger.info('Completed data streaming')
        self.save_location_widget.update_default_save_location()
        self.save_location_widget.update_timer.start()
        # TODO: Add a check to see if the data collection was canceled
        self.append_global_data(rfsocs, channels, rfchans)
        self.process_data(date, setnum)
