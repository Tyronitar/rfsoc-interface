from typing import TYPE_CHECKING, Callable, Any, Concatenate
from pathlib import Path

from PySide6.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit, QStackedLayout
from kidpy3 import capture

from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import PathLike, P
from rfsocinterface.gui.widgets.function import FunctionWidget, ArgumentType
from rfsocinterface.core.telescope import TelescopeMotorController

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

enum_choices = ['hello', 'world']

def dummy_func(file: Path, string: str, num: float, enum: str, check: bool):
    assert enum in enum_choices
    print(f'{file}, "{string}", {num}, {enum}, {check}')

class DitherPatternWidget(FunctionWidget):
    def __init__(self, fn: Callable[Concatenate[PathLike, P], Any], file_func: Callable[[], PathLike], args: list[tuple]=[], parent=None):
        super().__init__(fn, args, parent)
        self.file_func = file_func
    
    def call_function(self):
        values = self.get_inputs()
        file = self.file_func()
        self.fn(file, *values)

class ImagingWidget(MainWidget, Ui_ImagingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self._file =  '.'
        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout(parent=self)
        self.dither_groupBox.layout().addLayout(self.stacked_layout, 2, 0, 1, 2)

        self.add_dither_pattern(
            'AZ Scan Mode',
            TelescopeMotorController.az_scan_mode,
            [
                (('Starting azimuth: ', ArgumentType.FLOAT), {}),
                (('End azimuth: ', ArgumentType.FLOAT), {}),
                (('N Repeats: ', ArgumentType.INT), {'default': 1}),
                (('Zenith angle dither: ', ArgumentType.FLOAT), {'default': 0.04}),
                (('Return to starting position', ArgumentType.BOOL), {'default': True}),
            ],
        )
        self.add_dither_pattern(
            'Test Pattern',
            dummy_func,
            [
                (('Str Arg: ', ArgumentType.STR), {'default': 'default string'}),
                (('Float Arg: ', ArgumentType.FLOAT), {'default': 10.2}),
                (('Enum Arg: ', ArgumentType.ENUM), {'options': enum_choices, 'default': 'world'}),
                (('Bool Arg', ArgumentType.BOOL), {'default': True}),
            ],
        )
        # self.dither_comboBox.setPlaceholderText('Choose dither pattern...')
        self.dither_comboBox.activated.connect(self.choose_pattern)
        self.pushButton.clicked.connect(self.run)
        self.choose_pattern(0)
    
    def get_file(self) -> Path:
        f = self.save_location_widget.get_chosen_save_location()
        self._file = f
        return f
    
    def get_current_file(self) -> Path:
        return self._file
    
    def add_dither_pattern(self, label: str, fn: Callable, args: list[tuple[str, ArgumentType]]):
        pattern = DitherPatternWidget(fn, self.get_current_file, args=args, parent=self)
        self.patterns.append(pattern)
        self.dither_comboBox.addItem(label)
        self.stacked_layout.addWidget(pattern)
    
    def choose_pattern(self, index: int):
        self.stacked_layout.setCurrentIndex(index)
        self.active_pattern = self.patterns[index]
        # pattern = self.patterns[index]
    
    def run(self):
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=f'chan_{chan}')
            save_location.parent.mkdir(parents=True, exist_ok=True)
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)
        # Update the current save file
        self.get_file()
        print(self.get_current_file())
        return
        capture(
            rfchans,
            self.active_pattern.call_function,
        )
        
        # TODO: validate the inputs somehow...
        self.active_pattern.call_function()

