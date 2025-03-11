from typing import TYPE_CHECKING, Iterator
from PySide6.QtWidgets import QWidget, QCheckBox
from PySide6.QtCore import Qt, Slot, QTimer
from functools import partial
from pathlib import Path
import time

from kidpy3 import capture

from rfsocinterface.gui.uic.data_streaming_ui import Ui_DataStreamingWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.utils import get_num_value, get_lineEdit_text, PathValidator, get_filename
from rfsocinterface.gui.main_widget import MainWidget


if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class DataStreamingWidget(MainWidget, Ui_DataStreamingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent=None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.channel_comboBox.set_default_title('Select Channels...')
        self.setup_connections()
        self.update_channel_choices(self.channel_comboBox)
        self.data_locale_checkBox.setCheckState(Qt.CheckState.Checked)
        self.change_save_location_visibility(False)
        self.update_default_save_location()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_default_save_location)
        self.update_timer.start(10000)
    
    def setup_connections(self):
        self.start_pushButton.clicked.connect(self.start_streaming)
        self.data_locale_checkBox.checkStateChanged.connect(self.handle_click_default_box)
    
    def change_save_location_visibility(self, visible: bool):
        self.data_directory_label.setVisible(visible)
        self.data_directory_lineEdit.setVisible(visible)
        self.data_directory_pushButton.setVisible(visible)
        self.data_filename_label.setVisible(visible)
        self.data_filename_lineEdit.setVisible(visible)
        self.data_filename_pushButton.setVisible(visible)
    
    def get_chosen_save_location(self) -> Path:
        if self.data_locale_checkBox.isChecked():
            save_path = get_filename(file_type='lo')
        else:
            directory = get_lineEdit_text(self.data_directory_lineEdit)
            filename = get_lineEdit_text(self.data_filename_lineEdit)
            save_path = Path(f'{directory}/{filename}')
        return save_path
    
    @Slot(Qt.CheckState)
    def handle_click_default_box(self, state: Qt.CheckState):
        self.change_save_location_visibility(state == Qt.CheckState.Unchecked)
        save_path = self.get_chosen_save_location()
        self.save_locale_label.setText(f'Saving to "{save_path}"')
    
    def update_default_save_location(self):
        self._default_path = get_filename(file_type='tod')
        if self.data_locale_checkBox.isChecked():
            self.save_locale_label.setText(f'Saving to "{self._default_path}"')

    def get_selected_channels(self) -> Iterator[tuple[RFSOCWrapper, int]]:
        checked_ids = self.channel_comboBox.checked_indices()
        checked_text = [self.channel_comboBox.itemText(i) for i in checked_ids]
        return map(partial(get_channel_from_text, rfsocs=self.rfsocs), checked_text)
    
    def start_streaming(self):
        # TODO: Do this in another thread
        rfchans = [rfsoc.get_channel(chan) for rfsoc, chan in self.get_selected_channels()]
        save_location = self.get_chosen_save_location()
        save_location.parent.mkdir(parents=True, exist_ok=True)
        for rfchan in rfchans:
            rfchan.raw_filename = str(save_location)
        duration = get_num_value(self.duration_lineEdit)
        capture(rfchans, time.sleep, duration)
    
    def stop_streaming(self):
        pass