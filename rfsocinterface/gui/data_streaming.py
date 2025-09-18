import logging
from typing import TYPE_CHECKING, Iterator
from PySide6.QtWidgets import QWidget, QCheckBox, QProgressDialog
from PySide6.QtCore import Qt, Slot, QTimer, QCoreApplication, Signal
from functools import partial
from pathlib import Path
import time
import glob

from kidpy3 import capture
import tables

from rfsocinterface.gui.uic.data_streaming_ui import Ui_DataStreamingWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.utils import get_filename
from rfsocinterface.core.data import ProcessedData, get_tod_template
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.gui.utils import PathValidator, get_lineEdit_text, get_num_value


if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)

class DataStreamingWidget(MainWidget, Ui_DataStreamingWidget):

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.save_location_widget.file_type = 'tod'

        self.channel_comboBox.set_default_title('Select Channels...')
        self.setup_connections()
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))
    
    def setup_connections(self):
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
        while now - start < duration:
            if pd.wasCanceled():
                pd.close()
                return
            time.sleep(0.1)
            QCoreApplication.processEvents()
            now = time.time()
            remaining_time = duration - (now - start)
            pd.setLabelText(f'Collecting data...\nRemaining time: {int(remaining_time)} seconds')
            pd.setValue(now - start)
        
    def process_data(self, date: str, setnum: int):
        pass
        # _logger.info('Processing data')
    
    def start_streaming(self):
        # TODO: Do this in another thread
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=rfchan.tile_name, touch_file=True, mode=0o644, mkdir=True)
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)
        duration = get_num_value(self.duration_lineEdit, int, use_placeholder_text=True)
        date = save_location.stem[:8]
        setnum = int(save_location.stem[-4:])
        capture(rfchans, self.wait_for_TOD, duration)
        # TODO: Add a check to see if the data collection was canceled
        self.process_data(date, setnum)
    
    def stop_streaming(self):
        raise NotImplementedError('Stop streaming not implemented yet')