import logging
from typing import TYPE_CHECKING, Iterator
from PySide6.QtWidgets import QWidget, QCheckBox, QProgressDialog
from PySide6.QtCore import Qt, Slot, QTimer, QCoreApplication, Signal
from functools import partial
from pathlib import Path
import time
import glob
import copy

from kidpy3 import capture
import tables

from rfsocinterface.gui.uic.data_streaming_ui import Ui_DataStreamingWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW, get_tod_template, unpack_file_name
from rfsocinterface.core.data import ProcessedData, DataPipeline
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.gui.utils import PathValidator, get_lineEdit_text, get_num_value, DATA_ROUTINE_FUNCTION_WIDGET_ARGS
from rfsocinterface.gui.widgets.pipeline import PipelineDialog


if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)

class DataStreamingWidget(MainWidget, Ui_DataStreamingWidget):

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.save_location_widget.file_type = 'tod'

        self.pipeline_dialog = PipelineDialog(self)
        self.pipeline = DataPipeline()
        self._add_default_routines()

        self._file =  '.'

        self.channel_comboBox.set_default_title('Select Channels...')
        self.setup_connections()
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))

    def update_current_file(self) -> Path:
        f = self.save_location_widget.get_chosen_save_location()
        self._file = f

    def get_current_file(self) -> Path:
        return self._file

    # TODO: Replace this with presets
    def _add_default_routines(self):
        default_routines = self.settings['defaults']['data']['dataRoutines']
        for routine_dict in default_routines:
            routine_type = routine_dict['type']
            base_args = copy.copy(DATA_ROUTINE_FUNCTION_WIDGET_ARGS[routine_type])
            if 'defaults' in routine_dict:
                default_args_dict = routine_dict['defaults']
                for base_arg in base_args[2]:
                    base_arg_name = base_arg[0][0].strip(': ')
                    if base_arg_name in default_args_dict:
                        base_arg[1]['default'] = default_args_dict[base_arg_name]
            self.pipeline_dialog.add_routine(routine_type, *base_args)
            # self.pipeline_dialog.drag_function_widget.add_item(*base_args)
        self.pipeline_dialog.accept()
        self.pipeline = self.pipeline_dialog.make_pipeline()
    
    def setup_connections(self):
        self.start_pushButton.clicked.connect(self.start_streaming)
        self.auto_process_checkBox.checkStateChanged.connect(self.toggle_auto_processing)
        self.routines_pushButton.clicked.connect(self.choose_data_routines)

    def choose_data_routines(self):
        if self.pipeline_dialog.exec():
            # Get the selected routines, instantiate them, and store in the class
            self.pipeline = self.pipeline_dialog.make_pipeline()
            # TODO: validate the inputs somehow...
    
    @Slot(Qt.CheckState)
    def toggle_auto_processing(self, state: Qt.CheckState):
        self.routines_pushButton.setHidden(state == Qt.CheckState.Unchecked)
    
    def wait_for_TOD(self, duration: int) -> int:
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
                return 1  # Nonzero exit code for cancellation
            time.sleep(0.1)
            QCoreApplication.processEvents()
            now = time.time()
            remaining_time = duration - (now - start)
            pd.setLabelText(f'Collecting data...\nRemaining time: {int(remaining_time)} seconds')
            pd.setValue(now - start)
            counter += 1
            if counter % 50 == 0:
                _logger.info(f'Collecting data: {100 * (now - start) / duration:.2f}% complete...')
        return 0
        
    def process_data(self):
        current_file = self.get_current_file().stem
        date, setnum = unpack_file_name(current_file)
        _logger.debug(f'Preparing data processing for {date}set{setnum}')

        total_steps = len(self.pipeline) + 2  # Add two for creating the ProcessedData L0 and L1 objects
        pd = QProgressDialog('Processing Data...', 'Cancel', 0, total_steps, parent=self)
        pd.setWindowTitle('rfsocinterface')
        pd.setValue(0)
        pd.canceled.connect(self.pipeline.stop)
        def update_progress():
            nonlocal pd
            pd.setValue(pd.value() + 1)

        pd.show()
        data = self.pipeline.run_pipeline(date, setnum, progress_callbacks=(pd.setLabelText, update_progress))
        data.close()
    
    def start_streaming(self):
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        self.update_current_file()
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=rfchan.tile_name, touch_file=True, mode=PERMISSIONS_USR_RW, mkdir=True)
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)

        duration = get_num_value(self.duration_lineEdit, int, use_placeholder_text=True)
        _logger.debug(f'Streaming {duration} seconds of data for chans: {[chan.tile_name for chan in rfchans]}')
        exit_code = capture(rfchans, self.wait_for_TOD, duration)
        _logger.debug(f'Data collection finished with code {exit_code}.')
        if exit_code == 0 and self.auto_process_checkBox.isChecked():
            self.process_data()