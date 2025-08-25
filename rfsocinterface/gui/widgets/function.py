

from email.mime import application
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFormLayout, QWidget, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QStackedWidget, QScrollArea, QLabel


from typing import Any, Callable, Concatenate, overload

import numpy as np

from rfsocinterface.core.utils import P, R, Q
from rfsocinterface.gui.utils import ArgumentType
from rfsocinterface.gui.widgets.drag_and_drop import ClickableDragWidget, ClickableDragItem, ClickableMultiSectionDragWidget


class FunctionWidget(QWidget):
    """Class for generalizing a function and its arguments for a Qt GUI."""

    def __init__(
            self,
            fn: Callable[P, R],
            args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[],
            parent=None,
    ):
        super().__init__(parent=parent)
        self.fn = fn
        self.args: list[tuple[str, tuple[ArgumentType, ...]]] = []

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

    def add_argument(self, label: str, arg_types: ArgumentType | tuple[ArgumentType], *args: Q.args, **kwargs: Q.kwargs):

        label = label.strip(': ')
        has_default = False
        if 'default' in kwargs:
            has_default = True
            default_vals = kwargs.pop('default')
            if not isinstance(default_vals, tuple):
                default_vals = (default_vals,)

        if isinstance(arg_types, ArgumentType):
            arg_types = (arg_types,)
        self.args.append((label, arg_types))
        
        new_row = QHBoxLayout()
        for i, arg_type in enumerate(arg_types):
            widget = self.arg_to_widget(label, arg_type, *args, default_val=default_vals[i] if has_default else None, **kwargs)
            new_row.addWidget(widget)
        if any(arg_type != ArgumentType.BOOL for arg_type in arg_types):
            self.form_layout.addRow(label + ':', new_row)
        else:
            self.form_layout.addRow(new_row)
    
    def arg_to_widget(self, label: str, arg_type: ArgumentType, *args: Q.args, default_val=None, **kwargs: Q.kwargs) -> QWidget:
        match arg_type:
            case ArgumentType.BOOL:
                widget = arg_type.widget(label, *args, parent=self, **kwargs)
                if default_val is not None:
                    widget.setChecked(default_val)
                return widget
            case ArgumentType.ENUM:
                # Get options to populate the combo box with
                options = kwargs.pop('options')  
                widget = arg_type.widget(*args, parent=self, **kwargs)
                widget.addItems(options)
                if default_val is not None:
                    widget.setCurrentText(default_val)
                return widget
            case _:
                widget = arg_type.widget(*args, parent=self, **kwargs)
                if default_val is not None:
                    widget.setText(str(default_val))
                return widget

    def get_inputs(self) -> list[Any]:
        values = []
        for i, (_, arg_types) in enumerate(self.args):
            if len(arg_types) > 1:
                # If there are multiple arguments, get the values from each widget
                this_value = []
                hlayout: QHBoxLayout = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
                for j, arg_type in enumerate(arg_types):
                    # Get every widget in the hlayout
                    input_widget = hlayout.itemAt(j).widget()
                    this_value.append(arg_type.access_function()(input_widget))
                values.append(tuple(this_value))
            else:
                hlayout: QHBoxLayout = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
                input_widget = hlayout.itemAt(0).widget()
                values.append(arg_types[0].access_function()(input_widget))
        return values

    def call_function(self):
        values = self.get_inputs()
        return self.fn(*values)

class FunctionDragItem(ClickableDragItem):
    def __init__(
            self,
            fn: Callable[P, R],
            args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[],
            label: str = None,
            *init_args,
            **init_kwargs,
    ):
        if not label:
            label = fn.__name__
        super().__init__(label, *init_args, **init_kwargs)
        self.fn = fn
        self.args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=args
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

    @property
    def active_item(self) -> FunctionDragItem | None:
        return self.drag.active_item

    @overload
    def add_item(self, item: FunctionDragItem) -> FunctionDragItem:
        pass
    
    @overload
    def add_item(self, label: str, fn: Callable, args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[]) -> FunctionDragItem:
        pass

    def add_item(self, *data):
        if not isinstance(data[0], FunctionDragItem):
            label, fn, args = data
            item = FunctionDragItem(fn, args, label=label, parent=self)
            item.set_data(fn.__name__)
        else:
            item = data[0]
        self.drag.add_item(item)
        item.clicked.connect(self.display_args)
        self.func_container.addWidget(item.func_widget)
        return item
    
    def clear(self):
        for item in self.drag.items():
            self.drag.remove_item(item)
            self.func_container.removeWidget(item.func_widget)
        self.func_container.setCurrentIndex(0)
    
    def remove_item(self, item: FunctionDragItem):
        self.drag.remove_item(item)
        self.func_container.removeWidget(item.func_widget)
        item.deleteLater()
        self.func_container.setCurrentIndex(0)
    
    def items(self) -> list[FunctionDragItem]:
        return self.drag.items()
    
    @Slot()
    def display_args(self):
        item: FunctionDragItem = self.sender()
        self.func_container.setCurrentIndex(self.func_container.indexOf(item.func_widget))
    
    def mousePressEvent(self, event: QMouseEvent):
        child = self.childAt(event.position())
        # Clicking off of the list items or parameters should deselect
        if child is None or child == self.drop_container or child == self.drag:
            self.drag.set_active_item(None)
            self.func_container.setCurrentIndex(0)
        return super().mousePressEvent(event)

class MultiSectionDragFunctionWidget(QWidget):
    orderChanged = Signal(list, list)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.drag = ClickableMultiSectionDragWidget(orientation=Qt.Orientation.Vertical)
        self.drag.orderChanged.connect(self.orderChanged.emit)
        self.drag.orderChanged.connect(lambda _, l: print(l))

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
    
    @property
    def active_item(self) -> tuple[int, FunctionDragItem | None]:
        return self.drag.active_item

    def add_section(self, label: str):
        self.drag.add_section(label)
    
    @overload
    def add_item(self, i_section: int, item: FunctionDragItem) -> FunctionDragItem:
        pass
    
    @overload
    def add_item(self, i_section: int, label: str, fn: Callable, args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[]) -> FunctionDragItem:
        pass

    def add_item(self, *data):
        if not isinstance(data[1], FunctionDragItem):
            label, fn, args = data[1:]
            item = FunctionDragItem(fn, args, label=label, parent=self)
            item.set_data(fn.__name__)
        else:
            item = data[1]
        self.drag.add_item(data[0], item)
        item.clicked.connect(self.display_args)
        self.func_container.addWidget(item.func_widget)
        return item
    
    def clear(self):
        for i_sec, sec in enumerate(self.drag.sections):
            for item in sec.items():
                self.drag.remove_item(i_sec, item)
                self.func_container.removeWidget(item.func_widget)
        self.func_container.setCurrentIndex(0)
    
    def remove_item(self, i_section: int, item: FunctionDragItem):
        self.drag.remove_item(i_section, item)
        self.func_container.removeWidget(item.func_widget)
        item.deleteLater()
        self.func_container.setCurrentIndex(0)

    def items(self) -> list[FunctionDragItem]:
        return self.drag.items()
    
    def items_separated(self) -> list[list[FunctionDragItem]]:
        return self.drag.items_separated()

    def item_data_separated(self) -> list[list]:
        return self.drag.get_item_data_separated()


    @Slot()
    def display_args(self):
        item: FunctionDragItem = self.sender()
        self.func_container.setCurrentIndex(self.func_container.indexOf(item.func_widget))
    
    def mousePressEvent(self, event: QMouseEvent):
        child = self.childAt(event.position())
        # Clicking off of the list items or parameters should deselect
        if child is None or child == self.drop_container or child == self.drag:
            self.drag.set_active_item(-1, None)
            self.func_container.setCurrentIndex(0)
        return super().mousePressEvent(event)


    
    
enum_choices = ['hello', 'world']

def dummy_func(string: str, num: float, nums: tuple[float, float], enum: str, check: bool):
    assert enum in enum_choices
    print(f'"{string}", {num}, {nums}, {enum}, {check}')


def root(n: float) -> float:
    return np.sqrt(n)


if __name__ == '__main__':
    app = QApplication()
    w = QMainWindow()
    # ...
    drag = MultiSectionDragFunctionWidget(parent=w)
    w.setCentralWidget(drag)

    n_sections = 2
    counter = 0
    for i_sec, section_name in enumerate([f'Section {i + 1}' for i in range(n_sections)]):
        drag.add_section(section_name)
        drag.add_item(
            i_sec,
            'Square Root',
            root,
            [
                (('Number: ', ArgumentType.FLOAT), {'default': 2.25}),
            ],
        )
        drag.add_item(
            i_sec,
            'Dummy Func',
            dummy_func,
            [
                (('Str Arg: ', ArgumentType.STR), {'default': ('default string',)}),
                (('Float Arg: ', ArgumentType.FLOAT), {'default': (10.2,)}),
                (('Double Float Arg: ', (ArgumentType.FLOAT, ArgumentType.FLOAT)), {'default': (10.2, 64.7)}),
                (('Enum Arg: ', ArgumentType.ENUM), {'options': enum_choices, 'default': ('world',)}),
                (('Bool Arg', ArgumentType.BOOL), {'default': (True,)}),
            ],
        )

    w.show()
    app.exec()