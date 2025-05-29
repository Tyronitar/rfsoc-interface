from typing import TYPE_CHECKING, Callable, Any, Concatenate, Type
from pathlib import Path
from threading import Thread
from multiprocessing import Pipe
import h5py
import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit, QStackedLayout, QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
from kidpy3 import capture

from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import TelescopeMainWidget
from rfsocinterface.gui.uic.mapping_ui import Ui_MappingDialog
from rfsocinterface.gui.widgets.function import FunctionDragItem
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import PathLike, P, wait_for_telescope_command, get_filename
from rfsocinterface.gui.utils import DATA_ROUTINE_FUNCTION_WIDGET_ARGS, ArgumentType
from rfsocinterface.gui.widgets.function import FunctionWidget
from rfsocinterface.core.camera import SKPR_Camera_Control
from rfsocinterface.core.data import ProcessedData, MapData
from rfsocinterface.core.map import Mapper, DataRoutine

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

enum_choices = ['hello', 'world']

def dummy_func(file: Path, string: str, num: float, enum: str, check: bool):
    assert enum in enum_choices
    print(f'{file}, "{string}", {num}, {enum}, {check}')


class RoutineSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi()

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
    
    def setupUi(self):
        self.setWindowTitle('Select Mapping Routine')
        self.setModal(True)
        layout = QFormLayout()

        self.combo_box = QComboBox(self)
        self.combo_box.addItems(DATA_ROUTINE_FUNCTION_WIDGET_ARGS.keys())
        layout.addRow('Routine Type:', self.combo_box)

        self.button_box = QDialogButtonBox(self)
        self.button_box.setOrientation(Qt.Orientation.Horizontal)
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(self.button_box)

        self.setLayout(layout)

class MappingDialog(QDialog, Ui_MappingDialog):
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        # self.add_toolButton.clicked.connect(self.select_and_add_routine)
        self.add_toolButton.clicked.connect(lambda _: self.select_and_add_routine())
        self.remove_toolButton.clicked.connect(lambda _: self._temp_remove_item())
        # self.buttonBox.accepted.connect(self.accept)
        # self.buttonBox.rejected.connect(self.reject)

        self._current_items: list[FunctionDragItem] = []
        self._new_items: list[FunctionDragItem] = []
        self._removed_items: list[FunctionDragItem] = []
    
    def exec(self):
        self._current_items = self.drag_function_widget.items()
        return super().exec()
    
    def reject(self):
        # Un-remove any items that were removed
        for item in self._removed_items:
            item.show()
        self._removed_items.clear()

        # Delete new items
        for item in self._new_items:
            self.remove_routine(item)
        self._new_items.clear()

        # Restore the order of the original items
        for i, item in enumerate(self._current_items):
            self.drag_function_widget.drag.blayout.insertWidget(i, item)

        super().reject()
    
    def accept(self):
        # Actually remove items
        for item in self._removed_items:
            self.remove_routine(item)
        self._removed_items.clear()
        self._new_items.clear()  # New items were already added

        super().accept()
    
    def select_and_add_routine(self):
        routine_type = self.select_routine()
        if routine_type is None:
            return
        self.add_routine(routine_type)

    def select_routine(self) -> str | None:
        """Open a dialog to select a routine type."""
        d = RoutineSelectionDialog(self)
        if d.exec():
            return d.combo_box.currentText()
    
    def add_routine(self, routine_type_name: str):
        if routine_type_name not in DATA_ROUTINE_FUNCTION_WIDGET_ARGS:
            raise ValueError(f'Routine type {routine_type_name} not in DATA_ROUTINE_FUNCTION_WIDGET_ARGS')
        args = DATA_ROUTINE_FUNCTION_WIDGET_ARGS[routine_type_name]
        item = self.drag_function_widget.add_item(*args)
        item.clicked.emit()  # Set active itme and display the function's aruments
        self._new_items.append(item)
    
    def remove_routine(self, item: FunctionDragItem | None=None):
        if item is None:
            item = self.drag_function_widget.active_item
        if item is not None:
            self.drag_function_widget.remove_item(item)
    
    def _temp_remove_item(self):
        item = self.drag_function_widget.active_item
        # No need to keep track of new items that are then removed
        if item in self._new_items:  
            self._new_items.remove(item)
            self.remove_routine(item)
        else:
            # Hide the item to look like it was removed...
            item.hide()
            # ...but keep track of it in case changes are discarded
            self._removed_items.append(item)


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
        self.mapping_dialog = MappingDialog(self)
        self.routines = []
        self._add_default_routines()

        self._file =  '.'
        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
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
            self.mapping_dialog.drag_function_widget.add_item(*base_args)
        routine_widgets = self.mapping_dialog.drag_function_widget.items()
        self.routines = [item.func_widget.call_function() for item in routine_widgets]
        
    def run_telescope_scan(self, command: str, *args):
        # Tell the controller to start moving the telescope according to the scan type
        self._telescope_queue.put([self._client_id, command, *args])

        # Wait until the motor controller indicates the scan is complete
        self.wait_for_telescope_command(
            f'{command}_complete',
            err_msg=f'Error occured while running command "{command}"',
        )
        print(f'{command} completed.')
        self.startMapping.emit()
    
    def make_map(self):
        print('Generating map...')
        current_file = self.get_current_file().stem
        date = current_file[:8]
        setnum = int(current_file[-4:])
        p = ProcessedData.from_tod(date, setnum)

        # TODO: Make Qt widget for mapping , so signals can be emitted after completing 
        # each routine. Needed for showing progress
        mapper = Mapper(self.routines)
        map_data: MapData = mapper(p)
        map_data.plot(self.show_checkBox.isChecked())
    
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
        if self.mapping_dialog.exec():
            # Get the selected routines, instantiate them, and store in the class
            routine_widgets = self.mapping_dialog.drag_function_widget.items()
            # TODO: validate the inputs somehow...
            self.routines = [item.func_widget.call_function() for item in routine_widgets]
        print(self.routines)
    
    def run(self):
        chans = self.get_selected_channels(self.channel_comboBox)
        rfchans = []
        # Update the current save file
        self.update_current_file()
        for rfsoc, chan in chans:
            rfchan = rfsoc.get_channel(chan)
            save_location = self.save_location_widget.get_chosen_save_location(chan_name=f'{rfsoc.name}_{rfchan.name}', mkdir=True, touch_file=True)
            # save_location.parent.mkdir(parents=True, exist_ok=True)
            # Ensure the TOD file exists before getting the AZEL and optcam filenames
            # with h5py.File(save_location, 'w'):
            #     pass
            rfchan.raw_filename = str(save_location)
            rfchans.append(rfchan)

        # Take optical image
        self.cam_ctrl.take_pic(save=True)

        # Dither telescope and collect data in separate thread
        capture_thread = Thread(target=capture, args=(rfchans, self.active_pattern.call_function))
        capture_thread.start()

    
        
if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

    app = QApplication()

    w = QMainWindow()
    butt = QPushButton('Click me')
    d = MappingDialog(w)
    butt.clicked.connect(d.exec)
    w.setCentralWidget(butt)

    w.show()
    app.exec()

