from typing import TYPE_CHECKING, Callable, Any

from PySide6.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit, QStackedLayout

from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.widgets.function import FunctionWidget, ArgumentType
from rfsocinterface.gui.telescope import TelescopeMotorController

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class ImagingWidget(MainWidget, Ui_ImagingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout(parent=self)
        self.dither_groupBox.layout().addLayout(self.stacked_layout)

        self.add_dither_pattern(
            'Scan Mode',
            TelescopeMotorController.az_scan_mode,
            [
                ('Start: ', ArgumentType.FLOAT),
                ('Stop: ', ArgumentType.FLOAT),
                ('File: ', ArgumentType.FILE),
                ('N Repeats: ', ArgumentType.INT),
            ]
        )
        self.dither_comboBox.currentIndexChanged.connect(self.choose_pattern)
        self.dither_comboBox.setCurrentIndex(-1)
    
    def add_dither_pattern(self, label: str, fn: Callable, args: list[tuple[str, ArgumentType]]):
        pattern = FunctionWidget(fn, args=args, parent=self)
        self.patterns.append(pattern)
        self.dither_comboBox.addItem(label)
        self.stacked_layout.addWidget(pattern)
    
    def set_pattern_visibility(self, visible: bool):
        for pattern in self.patterns:
            pattern.setVisible(visible)
    
    def choose_pattern(self, index: int):
        if index == -1:
            # TODO: Remove current function widget from screen
            self.set_pattern_visibility(False)
        self.set_pattern_visibility(True)
        print(f'Showing current pattern: {index}')
        self.stacked_layout.setCurrentIndex(index)
        # pattern = self.patterns[index]

