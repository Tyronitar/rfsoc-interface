from typing import TYPE_CHECKING, Iterator
from PySide6.QtWidgets import QWidget, QCheckBox
from PySide6.QtCore import Qt, Slot, QTimer
from functools import partial
from pathlib import Path
import time

from kidpy3 import capture

from rfsocinterface.gui.uic.data_streaming_ui import Ui_DataStreamingWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.utils import get_filename
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.gui.utils import PathValidator, get_lineEdit_text, get_num_value


if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class DataStreamingWidget(MainWidget, Ui_DataStreamingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.save_location_widget.file_type = 'tod'

        self.channel_comboBox.set_default_title('Select Channels...')
        self.setup_connections()
        self.update_channel_choices(self.channel_comboBox)
    
    def setup_connections(self):
        self.start_pushButton.clicked.connect(self.start_streaming)
    
    def start_streaming(self):
        # TODO: Do this in another thread
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=f'chan_{chan}')
            save_location.parent.mkdir(parents=True, exist_ok=True)
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)
        duration = get_num_value(self.duration_lineEdit)
        capture(rfchans, time.sleep, duration)
    
    def stop_streaming(self):
        raise NotImplementedError('Stop streaming not implemented yet')