import logging
from typing import TYPE_CHECKING, Callable, Any, Concatenate
from pathlib import Path
from threading import Thread
from multiprocessing import Pipe
import h5py
import copy
import time

import numpy as np
from PySide6.QtCore import Signal, Slot, QCoreApplication
from PySide6.QtWidgets import QWidget, QCheckBox, QStackedLayout, QVBoxLayout, QProgressDialog
from kidpy3 import capture

from rfsocinterface.gui.pipeline import PipelineDialog
from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import TelescopeMainWidget, DataCollectionMainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import PathLike, P, wait_for_telescope_command, PERMISSIONS_USR_RW, TabName, get_filename
from rfsocinterface.gui.utils import DATA_ROUTINE_FUNCTION_WIDGET_ARGS
from rfsocinterface.gui.widgets import FunctionWidget, ArgumentType
from rfsocinterface.core.camera import SKPR_Camera_Control, MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH
from rfsocinterface.core.data import (
    ProcessedData,
    MapData,
    DataPipeline,
    DataRoutine,
)

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow


_logger = logging.getLogger(__name__)

enum_choices = ['hello', 'world']


def dummy_func(file: Path, string: str, num: float, enum: str, check: bool):
    assert enum in enum_choices
    print(f'{file}, "{string}", {num}, {enum}, {check}')


class DitherPatternWidget(FunctionWidget):
    def __init__(self, fn: Callable[Concatenate[str, PathLike, P], Any], command: str, file_func: Callable[[], PathLike], args: list[tuple]=[], parent=None):
        super().__init__(fn, args, parent)
        self.command = command
        self.file_func = file_func
    
    def call_function(self):
        values = self.get_inputs()
        file = self.file_func()
        self.fn(self.command, file, *values)

class ImagingWidget(TelescopeMainWidget, DataCollectionMainWidget, Ui_ImagingWidget):
    tab_name = TabName.IMAGING
    startMapping = Signal()

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, client_id: str, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, client_id, parent=parent)
        self.setupUi(self)
        # self.cam_ctrl = SKPR_Camera_Control()
        self.cam_ctrl = None
        self.pipeline_dialog = PipelineDialog(self)
        self.pipeline = DataPipeline()
        self._add_default_routines()
        self.video_file: h5py.File = None
        self.video_thread = None

        self._file =  '.'
        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout(parent=self)
        self.dither_groupBox.layout().addLayout(self.stacked_layout, 2, 0, 1, 2)
        self.startMapping.connect(self.make_map)
        self.optical_frame_rate = 5  # Frames / second

        self.add_dither_pattern(
            'AZ Scan Mode',
            'az_scan_mode',
            [
                (('Starting azimuth: ', ArgumentType.FLOAT), {'default': -5}),
                (('End azimuth: ', ArgumentType.FLOAT), {'default': 5}),
                (('N Repeats: ', ArgumentType.INT), {'default': 2}),
                (('Zenith angle dither: ', ArgumentType.FLOAT), {'default': 0.04}),
                (('Return to starting position', ArgumentType.BOOL), {'default': True}),
                (('Large Map Mode', ArgumentType.BOOL), {'default': False}),
            ],
        )

        self.add_dither_pattern(
            'Dither Pattern',
            'dither_pattern',
            [
                (('Primary start: ', ArgumentType.FLOAT), {'default': -5}),
                (('Primary stop: ', ArgumentType.FLOAT), {'default': 5}),
                (('N Repeats: ', ArgumentType.INT), {'default': 2}),
                (('Secondary Dither: ', ArgumentType.FLOAT), {'default': 0.04}),
                (('Return to starting position', ArgumentType.BOOL), {'default': True}),
                (('Large Map Mode', ArgumentType.BOOL), {'default': False}),
                (('Primary Direction', ArgumentType.ENUM), {'options': ['AZ', 'ZA'], 'default': 'AZ'}),
            ],
        )
        self.add_dither_pattern(
            'Stared Image',
            'stared_image',
            [
                (('Duration (s): ', ArgumentType.FLOAT), {'default': 60}),
            ],
        )
        # self.add_dither_pattern(
        #     'Test Pattern',
        #     dummy_func,
        #     [
        #         (('Str Arg: ', ArgumentType.STR), {'default': 'default string'}),
        #         (('Float Arg: ', ArgumentType.FLOAT), {'default': 10.2}),
        #         (('Enum Arg: ', ArgumentType.ENUM), {'options': enum_choices, 'default': 'world'}),
        #         (('Bool Arg', ArgumentType.BOOL), {'default': True}),
        #     ],
        # )
        # self.dither_comboBox.setPlaceholderText('Choose dither pattern...')
        self.dither_comboBox.activated.connect(self.choose_pattern)
        self.start_pushButton.clicked.connect(self.run)
        self.mapping_pushButton.clicked.connect(self.choose_mapping_routines)
        self.choose_pattern(1)

    
    def _add_default_routines(self):
        default_routines = self.settings['defaults']['imaging']['mappingRoutines']
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
    
        
    def run_telescope_scan(self, command: str, *args) -> int:
        pd = QProgressDialog('Running...', 'Cancel and Stop Telescope', 0, 100, parent=self)
        pd.canceled.connect(lambda: self.send_telescope_command('stop_telescope'))
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.setValue(0)
        pd.setWindowTitle('rfsocinterface')
        pd.setModal(True)

        self.active_command = command
        self.connect_to_telescope_command(f'{command}_maximum', pd.setMaximum)
        self.connect_to_telescope_command(f'{command}_progress', pd.setValue)
        self.connect_to_telescope_command(f'{command}_label', pd.setLabelText)

        # Tell the controller to start moving the telescope according to the scan type
        self.send_telescope_command(command, *args)
        pd.show()

        # Wait until the motor controller indicates the scan is complete
        self.wait_for_telescope_command(
            f'{command}_complete',
            err_msg=f'Error occured while running command "{command}"',
        )
        _logger.info(f'{command} completed with data {self._telescope_command_data}.')
        self.disconnect_telescope_command(f'{command}_maximum', pd.setMaximum)
        self.disconnect_telescope_command(f'{command}_progress', pd.setValue)
        self.disconnect_telescope_command(f'{command}_label', pd.setLabelText)
        pd.close()
    
    def make_map(self):
        print('Generating map...')
        # current_file = self.get_current_file().stem
        # date = current_file[:8]
        # setnum = int(current_file[-4:])
        # p = ProcessedData.from_tod(date, setnum)

        # # TODO: Make Qt widget for mapping , so signals can be emitted after completing 
        # # each routine. Needed for showing progress
        # mapper = Mapper(self.routines)
        # map_data: MapData = mapper(p)
        # map_data.plot(self.show_checkBox.isChecked())
    
    def update_current_file(self) -> Path:
        f = self.save_location_widget.get_chosen_save_location()
        self._file = f
        return f
    
    def get_current_file(self) -> Path:
        return self._file
    
    def get_azel_file(self) -> Path:
        return Path(str(self._file).replace('TOD', 'AZEL'))
    
    def add_dither_pattern(self, label: str, command: str, args: list[tuple[str, ArgumentType]]):
        pattern = DitherPatternWidget(
            self.run_telescope_scan,
            command,
            # lambda: get_filename(file_type='azel').with_suffix('.h5'),
            self.get_azel_file,
            args=args,
            parent=self,
        )
        self.patterns.append(pattern)
        self.dither_comboBox.addItem(label)
        self.stacked_layout.addWidget(pattern)
    
    def choose_pattern(self, index: int):
        self.dither_comboBox.setCurrentIndex(index)
        self.stacked_layout.setCurrentIndex(index)
        self.active_pattern = self.patterns[index]
    
    def choose_mapping_routines(self):
        if self.pipeline_dialog.exec():
            self.pipeline = self.pipeline_dialog.make_pipeline()
            # Get the selected routines, instantiate them, and store in the class
            # TODO: validate the inputs somehow...
        print(self.pipeline.all_routines())
    
    def capture_image(self):
        savefile = get_filename(file_type='optcam').with_suffix('.h5')
        savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
        optcam_file = h5py.File(savefile, 'a')
        optical_image_array = optcam_file.create_dataset(
            'optical_image',
            shape=(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3),
            dtype=np.uint8,
            compression='lzf',
        )
        image,  = self.get_current_image()
        optical_image_array[:] = image
        optcam_file.close()

    
    def start_recording_video(self):
        savefile = get_filename(file_type='optcam').with_suffix('.h5')
        savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
        self.video_file = h5py.File(savefile, 'a')
        self.video_file.create_dataset(
            'optical_video',
            shape=(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3, 0),
            maxshape=(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3, None),
            dtype=np.uint8,
            compression='lzf',
        )
        self.video_file.create_dataset('timestamp', shape=(0,), maxshape=(None,), dtype=np.float64)
        self.video_thread = Thread(target=self.video_loop)
        self.video_thread.start()
    
    def video_loop(self):
        while self.video_file is not None:
            t0 = time.time()
            self.append_video_frame()
            while time.time() < t0 + 1 / self.optical_frame_rate:
                time.sleep(1e-3)
    
    def stop_recording_video(self):
        self.video_file.close()
        self.video_file = None
        self.video_thread.join()
    
    def append_video_frame(self):
        if self.video_file:
            n_frames = self.video_file['optical_video'].shape[-1]
            image, timestamp = self.get_current_image()
            self.video_file['optical_video'].resize(n_frames + 1, axis=3)
            self.video_file['optical_video'][:, :, :, -1] = image
            self.video_file['timestamp'].resize(n_frames + 1, axis=0)
            self.video_file['timestamp'][-1] = timestamp
    
    def run(self):
        # Update the current save file
        self.update_current_file()
        rfchans, _, _ = self.setup_data_collection()

        # Take optical image
        if self.buttonGroup.checkedButton() == self.video_radioButton:
            self.start_recording_video()
        else:
            self.capture_image()

        # Dither telescope and collect data in separate thread
        capture(rfchans, self.active_pattern.call_function)
        if self.buttonGroup.checkedButton() == self.video_radioButton:
            self.stop_recording_video()

        if self._telescope_command_data == 0:  # Value other than 1 idicates the scan stopped early
            self.make_map()

