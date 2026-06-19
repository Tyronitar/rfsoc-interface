from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout

from rfsocinterface.core.data import (
    ROUTINE_NAME_MAP,
    DataRoutine,
    Pipeline,
    ProcessingStage,
)
from rfsocinterface.gui.uic.pipeline_ui import Ui_PipelineDialog
from rfsocinterface.gui.utils import DATA_ROUTINE_FUNCTION_WIDGET_ARGS
from rfsocinterface.gui.widgets.function import FunctionDragItem


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
        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addRow(self.button_box)

        self.setLayout(layout)


STAGE_TO_SECTION_MAP = {
    ProcessingStage.PRE_PROCESSING: 0,
    ProcessingStage.PROCESSING_L1: 1,
    ProcessingStage.PROCESSING_L2: 2,
    ProcessingStage.POST_PROCESSING: 3,
}


class PipelineDialog(QDialog, Ui_PipelineDialog):
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

        self._current_items: list[list[FunctionDragItem]] = [[]] * 4
        self._new_items: list[list[FunctionDragItem]] = [[]] * 4
        self._removed_items: list[list[FunctionDragItem]] = [[]] * 4
        self.drag_function_widget.add_section('Pre-processing')
        self.drag_function_widget.add_section('Processing Level 1')
        self.drag_function_widget.add_section('Processing Level 2')
        self.drag_function_widget.add_section('Post-processing')
        # self.drag_function_widget.orderChanged.connect(self.update_order)

    def exec(self):
        self._current_items = self.drag_function_widget.items_separated()
        print(f'Original order: {self.drag_function_widget.item_data_separated()}\n')
        self._new_items = [[]] * 4
        self._removed_items = [[]] * 4
        return super().exec()

    # @Slot(list, list)
    # def update_order(self, items: list[list[FunctionDragItem]], data: list):
    #     self._current_items = items
    #     print('updated order')

    def make_pipeline(self) -> Pipeline:
        new_pipeline = Pipeline()
        for item in self.drag_function_widget.items():
            new_pipeline.add_routine(item.func_widget.call_function())
        return new_pipeline

    def reject(self):
        # Un-remove any items that were removed
        for section_items in self._removed_items:
            for item in section_items:
                item.show()
        self._removed_items = [[]] * 4

        # Delete new items
        for section_items in self._new_items:
            for item in section_items:
                self.remove_routine(item)
        self._new_items = [[]] * 4

        # Restore the order of the original items
        # print(f'New order: {self.drag_function_widget.item_data_separated()}\n')
        for i_sec, section_items in enumerate(self._current_items):
            section = self.drag_function_widget.drag.sections[i_sec]
            for i, item in enumerate(section_items):
                section.blayout.insertWidget(i, item)

        super().reject()

    def accept(self):
        # Actually remove items
        for section in self._removed_items:
            for item in section:
                self.remove_routine(item)
        self._new_items = [[]] * 4  # New items were already added
        self._removed_items = [[]] * 4

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
        return None

    def add_routine(self, routine_type_name: str, *args):
        routine_cls: type[DataRoutine] = ROUTINE_NAME_MAP[routine_type_name]
        if routine_type_name not in ROUTINE_NAME_MAP:
            raise ValueError(
                f'Routine type {routine_type_name} not in DATA_ROUTINE_FUNCTION_WIDGET_ARGS'
            )
        if len(args) == 0:
            args = DATA_ROUTINE_FUNCTION_WIDGET_ARGS[
                routine_type_name
            ]  # Get default values
        section = STAGE_TO_SECTION_MAP[routine_cls.stage]
        item = self.drag_function_widget.add_item(section, *args)
        # item = self.drag_function_widget.add_item(*args)
        item.clicked.emit()  # Set active itme and display the function's aruments
        self._new_items[section].append(item)

    def remove_routine(self, i_sec: int, item: FunctionDragItem | None = None):
        if item is None:
            i_sec, item = self.drag_function_widget.active_item
        if item is not None:
            self.drag_function_widget.remove_item(i_sec, item)

    def _temp_remove_item(self):
        i_sec, item = self.drag_function_widget.active_item
        # No need to keep track of new items that are then removed
        if item in self._new_items[i_sec]:
            self._new_items[i_sec].remove(item)
            self.remove_routine(i_sec, item)
        elif item is not None:
            # Hide the item to look like it was removed...
            item.hide()
            # ...but keep track of it in case changes are discarded
            self._removed_items[i_sec].append(item)


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

    app = QApplication()

    w = QMainWindow()
    butt = QPushButton('Click me')
    d = PipelineDialog(w)
    butt.clicked.connect(d.exec)
    w.setCentralWidget(butt)

    w.show()
    app.exec()
