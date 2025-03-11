from typing import TYPE_CHECKING, Callable, Any, Concatenate
from pathlib import Path

from PySide6.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit, QStackedLayout

from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import PathLike, P
from rfsocinterface.gui.widgets.function import FunctionWidget, ArgumentType
from rfsocinterface.gui.telescope import TelescopeMotorController

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow


def dummy_func(string: str, num: float, check: bool):
    print(f'"{string}", {num}, {check}')

class DitherPatternWidget(FunctionWidget):
    def __init__(self, fn: Callable[Concatenate[PathLike, P], Any], file_func: Callable[[], PathLike], *args: P.args, parent=None):
        super().__init__(fn, *args, parent)
        self.file_func = file_func
    
    def call_function(self):
        values = self.get_inputs()
        file = self.file_func()
        self.fn(file, *values)

class ImagingWidget(MainWidget, Ui_ImagingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout(parent=self)
        self.dither_groupBox.layout().addLayout(self.stacked_layout, 2, 0, 1, 2)

        self.add_dither_pattern(
            'AZ Scan Mode',
            TelescopeMotorController.az_scan_mode,
            [
                ('File: ', ArgumentType.FILE),
                ('Starting azimuth: ', ArgumentType.FLOAT),
                ('End azimuth: ', ArgumentType.FLOAT),
                ('N Repeats: ', ArgumentType.INT),
                ('Zenith angle dither: ', ArgumentType.FLOAT),
                ('Return to starting position', ArgumentType.BOOL),
            ]
        )
        self.add_dither_pattern(
            'Test Pattern',
            dummy_func,
            [
                ('Arg 1: ', ArgumentType.STR),
                ('Arg 2: ', ArgumentType.FLOAT),
                ('Arg 3', ArgumentType.BOOL),
            ]
        )
        # self.dither_comboBox.setPlaceholderText('Choose dither pattern...')
        self.dither_comboBox.activated.connect(self.choose_pattern)
        self.pushButton.clicked.connect(self.run)
        self.choose_pattern(0)
    
    def add_dither_pattern(self, label: str, fn: Callable, args: list[tuple[str, ArgumentType]]):
        pattern = FunctionWidget(fn, args=args, parent=self)
        self.patterns.append(pattern)
        self.dither_comboBox.addItem(label)
        self.stacked_layout.addWidget(pattern)
    
    def choose_pattern(self, index: int):
        self.stacked_layout.setCurrentIndex(index)
        self.active_pattern = self.patterns[index]
        # pattern = self.patterns[index]
    
    def run(self):
        # TODO: Start streaming data
        
        # TODO: validate the inputs somehow...
        self.active_pattern.call_function()

