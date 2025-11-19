import logging
from typing import TYPE_CHECKING, Callable, Any, Concatenate
from pathlib import Path
from threading import Thread
from multiprocessing import Pipe
import h5py
import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QCheckBox, QStackedLayout, QVBoxLayout, QProgressDialog
from kidpy3 import capture

from rfsocinterface.gui.pipeline import PipelineDialog
from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import TelescopeMainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import PathLike, P, wait_for_telescope_command, PERMISSIONS_USR_RW
from rfsocinterface.gui.utils import DATA_ROUTINE_FUNCTION_WIDGET_ARGS, ArgumentType
from rfsocinterface.gui.widgets.function import FunctionWidget
from rfsocinterface.core.camera import SKPR_Camera_Control
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

class ImagingWidget(TelescopeMainWidget, Ui_ImagingWidget):
    startMapping = Signal()

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, client_id: str, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, client_id, parent=parent)
        self.setupUi(self)
        self.cam_ctrl = SKPR_Camera_Control()
        self.pipeline_dialog = PipelineDialog(self)
        self.pipeline = DataPipeline()
        self._add_default_routines()

        self._file =  '.'
        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout(parent=self)
        self.dither_groupBox.layout().addLayout(self.stacked_layout, 2, 0, 1, 2)
        self.startMapping.connect(self.make_map)

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
        self.choose_pattern(0)

    
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
        pd.canceled.connect(lambda: self.send_command('stop_telescope'))
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.setValue(0)
        pd.setWindowTitle('rfsocinterface')
        pd.setModal(True)

        self.active_command = command
        self.connect_to_command(f'{command}_maximum', pd.setMaximum)
        self.connect_to_command(f'{command}_progress', pd.setValue)
        self.connect_to_command(f'{command}_label', pd.setLabelText)

        # Tell the controller to start moving the telescope according to the scan type
        self.send_command(command, *args)
        pd.show()

        # Wait until the motor controller indicates the scan is complete
        self.wait_for_telescope_command(
            f'{command}_complete',
            err_msg=f'Error occured while running command "{command}"',
        )
        _logger.info(f'{command} completed with data {self._command_data}.')
        self.disconnect_command(f'{command}_maximum', pd.setMaximum)
        self.disconnect_command(f'{command}_progress', pd.setValue)
        self.disconnect_command(f'{command}_label', pd.setLabelText)
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
        self.stacked_layout.setCurrentIndex(index)
        self.active_pattern = self.patterns[index]
    
    def choose_mapping_routines(self):
        if self.pipeline_dialog.exec():
            self.pipeline = self.pipeline_dialog.make_pipeline()
            # Get the selected routines, instantiate them, and store in the class
            # TODO: validate the inputs somehow...
        print(self.pipeline.all_routines())
    
    def run(self):
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        # Update the current save file
        self.update_current_file()
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=f'{rfchan.tile_name}', mkdir=True, touch_file=True, mode=PERMISSIONS_USR_RW)
            # save_location.parent.mkdir(parents=True, exist_ok=True)
            # Ensure the TOD file exists before getting the AZEL and optcam filenames
            # with h5py.File(save_location, 'w'):
            #     pass
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)

        # Take optical image
        self.cam_ctrl.take_pic(save=True)

        # Dither telescope and collect data in separate thread
        capture(rfchans, self.active_pattern.call_function)
        if self._command_data == 0:  # Value other than 1 idicates the scan stopped early
            self.make_map()

