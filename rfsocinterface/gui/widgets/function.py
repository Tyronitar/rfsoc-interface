

from email.mime import application
from enum import IntEnum
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget, QCheckBox, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QStackedWidget, QScrollArea


from typing import Any, Callable, Concatenate

import numpy as np

from rfsocinterface.core.utils import get_num_value, P, R, Q
from rfsocinterface.gui.widgets.drag_and_drop import ClickableDragWidget, ClickableDragItem
from rfsocinterface.gui.widgets.file_select import FileSelectWidget


class ArgumentType(IntEnum):
    """Class for specifying the type of argument to add to a GUI."""
    BOOL = 0
    ENUM = 1
    INT = 2
    FLOAT = 3
    STR = 4
    FILE = 5

    def widget(self, *args, **kwargs) -> QWidget:
        match self.value:
            case ArgumentType.BOOL:
                return QCheckBox(*args, **kwargs)
            case ArgumentType.ENUM:
                return QComboBox(*args, **kwargs)
            case ArgumentType.FILE:
                return FileSelectWidget(*args, **kwargs)
            case _:
                return QLineEdit(*args, **kwargs)

    def access_function(self) -> Callable:
        match self.value:
            case ArgumentType.BOOL:
                return QCheckBox.isChecked
            case ArgumentType.ENUM:
                return QComboBox.currentText
            case ArgumentType.INT:
                return (lambda wid: get_num_value(wid, int))
            case ArgumentType.FLOAT:
                return (lambda wid: get_num_value(wid, float))
            case ArgumentType.FILE:
                return FileSelectWidget.text
            case _:
                return QLineEdit.text


class FunctionWidget(QWidget):
    """Class for generalizing a function and its arguments for a Qt GUI."""

    def __init__(
            self,
            fn: Callable[P, R],
            args: list[tuple[tuple[Concatenate[str, ArgumentType, Q]], dict]]=[],
            parent=None,
    ):
        super().__init__(parent=parent)
        self.fn = fn
        self.args: list[tuple[str, ArgumentType]] = []

        self.scroll_area = QScrollArea(self)
        container = QWidget()
        self.scroll_area.setLayout(QVBoxLayout())
        self.scroll_area.setWidget(container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.layout().addWidget(container)

        self.form_layout = QFormLayout(parent=container)
        container.setLayout(self.form_layout)
        for (arg, kwargs) in args:
            self.add_argument(*arg, **kwargs)

        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

    def add_argument(self, label: str, arg_type: ArgumentType, *args: Q.args, **kwargs: Q.kwargs):
        self.args.append((label, arg_type))
        has_default = False
        if 'default' in kwargs:
            has_default = True
            default_val = kwargs.pop('default')
        
        match arg_type:
            case ArgumentType.BOOL:
                widget = arg_type.widget(label, *args, parent=self, **kwargs)
                self.form_layout.addRow(widget)  # QCheckBox has its label built-in
                if has_default:
                    widget.setChecked(default_val)
            case ArgumentType.ENUM:
                # Get options to populate the combo box with
                options = kwargs.pop('options')  
                widget = arg_type.widget(*args, parent=self, **kwargs)
                widget.addItems(options)
                if has_default:
                    widget.setCurrentText(default_val)
                self.form_layout.addRow(label, widget)
            case _:
                widget = arg_type.widget(*args, parent=self, **kwargs)
                if has_default:
                    widget.setText(str(default_val))
                self.form_layout.addRow(label, widget)

    def get_inputs(self) -> list[Any]:
        values = []
        for i, (_, arg_type) in enumerate(self.args):
            input_widget = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole).widget()
            values.append(arg_type.access_function()(input_widget))
        return values

    def call_function(self):
        values = self.get_inputs()
        self.fn(*values)

class FunctionDragItem(ClickableDragItem):
    def __init__(
            self,
            fn: Callable[P, R],
            args: list[tuple[tuple[Concatenate[str, ArgumentType, Q]], dict]]=[],
            label: str = None,
            *init_args,
            **init_kwargs,
    ):
        if not label:
            label = fn.__name__
        super().__init__(label, *init_args, **init_kwargs)
        self.fn = fn
        self.args: list[tuple[tuple[Concatenate[str, ArgumentType, Q]], dict]]=args
        self.func_widget = FunctionWidget(self.fn, self.args, parent=self.parent())

class DragFunctionWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.drag = ClickableDragWidget(orientation=Qt.Orientation.Vertical)

        hlayout = QHBoxLayout()

        self.drop_container = QWidget(parent=self)
        drop_vlayout = QVBoxLayout()
        drop_vlayout.addStretch(1)
        drop_vlayout.addWidget(self.drag)
        drop_vlayout.addStretch(1)
        self.drop_container.setLayout(drop_vlayout)
        hlayout.addWidget(self.drop_container)

        hlayout.addStretch(1)

        # scrollArea.layout().setContentsMargins(0, 0, 0, 0)
        self.func_container = QStackedWidget(parent=self)
        placheolder_widget = QWidget(parent=self)
        self.func_container.addWidget(placheolder_widget)
        hlayout.addWidget(self.func_container)

        # self.setCentralWidget(drop_container)
        self.setLayout(hlayout)
    
    def add_item(self, label: str, fn: Callable, args: list[tuple[tuple[Concatenate[str, ArgumentType, Q]], dict]]=[]):
        item = FunctionDragItem(fn, args, label=label, parent=self)
        item.set_data(fn.__name__)
        self.drag.add_item(item)
        item.clicked.connect(self.display_args)
        self.func_container.addWidget(item.func_widget)
    
    @Slot()
    def display_args(self):
        item: FunctionDragItem = self.sender()
        self.func_container.setCurrentIndex(self.func_container.indexOf(item.func_widget))
    
    def mousePressEvent(self, event):
        child = self.childAt(event.pos())
        print(child)
        # Clicking off of the list items or parameters should deselect
        if child is None or child == self.drop_container or child == self.drag:
            self.drag.set_active_item(None)
            self.func_container.setCurrentIndex(0)
        return super().mousePressEvent(event)
    
enum_choices = ['hello', 'world']

def dummy_func(string: str, num: float, enum: str, check: bool):
    assert enum in enum_choices
    print(f'"{string}", {num}, {enum}, {check}')


def root(n: float) -> float:
    return np.sqrt(n)


if __name__ == '__main__':
    app = QApplication()
    w = QMainWindow()
    # ...
    drag = DragFunctionWidget(parent=w)
    w.setCentralWidget(drag)
    drag.add_item(
        'Square Root',
        root,
        [
            (('Number: ', ArgumentType.FLOAT), {}),
        ],
    )
    drag.add_item(
        'Dummy Func',
        dummy_func,
        [
            (('Str Arg: ', ArgumentType.STR), {'default': 'default string'}),
            (('Float Arg: ', ArgumentType.FLOAT), {'default': 10.2}),
            (('Enum Arg: ', ArgumentType.ENUM), {'options': enum_choices, 'default': 'world'}),
            (('Bool Arg', ArgumentType.BOOL), {'default': True}),
        ],
    )
    w.show()
    app.exec()