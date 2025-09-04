

from email.mime import application
from PySide6.QtWidgets import QFormLayout, QWidget, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QScrollArea
from PySide6.QtCore import Signal, Slot, SignalInstance


from typing import Any, Callable, Concatenate

import numpy as np

from rfsocinterface.core.utils import P, R, Q
from rfsocinterface.gui.utils import ArgumentType


def arg_to_widget(label: str, arg_type: ArgumentType, *args: Q.args, default_val=None, **kwargs: Q.kwargs) -> QWidget:
    match arg_type:
        case ArgumentType.BOOL:
            widget = arg_type.widget(label, *args, **kwargs)
            if default_val is not None:
                widget.setChecked(default_val)
            return widget
        case ArgumentType.ENUM:
            # Get options to populate the combo box with
            if 'options' not in kwargs:
                raise ValueError("ArgumentType.ENUM requires 'options' kwarg")
            options = kwargs.pop('options')  
            widget = arg_type.widget(*args, **kwargs)
            for option in options:
                widget.addItem(str(option), option)
            if default_val is not None:
                widget.setCurrentText(default_val)
            return widget
        case _:
            widget = arg_type.widget(*args, **kwargs)
            if default_val is not None:
                widget.setText(str(default_val))
            return widget

class ArgumentContainer(QWidget):
    valuesUpdated = Signal(list, list)

    def __init__(
            self,
            args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[],
            parent=None,
    ):
        super().__init__(parent=parent)
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
            widget = self._make_widget_from_arg(label, arg_type, *args, default_val=default_vals[i] if has_default else None, **kwargs)
            new_row.addWidget(widget)
        if any(arg_type != ArgumentType.BOOL for arg_type in arg_types):
            self.form_layout.addRow(label + ':', new_row)
        else:
            self.form_layout.addRow(new_row)
    
    def _make_widget_from_arg(self, label: str, arg_type: ArgumentType, *args: Q.args, default_val=None, **kwargs: Q.kwargs) -> QWidget:
        widget = arg_to_widget(label, arg_type, *args, default_val=default_val, **kwargs)
        if arg_type == ArgumentType.INT:
            widget.setPlaceholderText('0')
        elif arg_type == ArgumentType.FLOAT:
            widget.setPlaceholderText('0.0')
        widget.setParent(self)
        signal: SignalInstance = getattr(widget, arg_type.updated_signal())
        signal.connect(lambda _: self.emit_items())
        return widget
    
    def emit_items(self):
        self.valuesUpdated.emit(self.items(), self.get_item_data())

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

    def items(self) -> list[QWidget | tuple[QWidget, ...]]:
        widgets = []
        for i, (_, arg_types) in enumerate(self.args):
            if len(arg_types) > 1:
                # If there are multiple arguments, get the values from each widget
                this_widget = []
                hlayout: QHBoxLayout = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
                for j, _ in enumerate(arg_types):
                    # Get every widget in the hlayout
                    input_widget = hlayout.itemAt(j).widget()
                    this_widget.append(input_widget)
                widgets.append(tuple(this_widget))
            else:
                hlayout: QHBoxLayout = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
                input_widget = hlayout.itemAt(0).widget()
                widgets.append(input_widget)
        return widgets
    
    def get_item_data(self) -> list[Any]:
        return self.get_inputs()



class FunctionWidget(QWidget):
    """Class for generalizing a function and its arguments for a Qt GUI."""
    valuesUpdated = Signal(list, list)

    def __init__(
            self,
            fn: Callable[P, R],
            args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]=[],
            parent=None,
    ):
        super().__init__(parent=parent)
        self.fn = fn
        self.arg_container = ArgumentContainer(args=args, parent=self)
        self.arg_container.valuesUpdated.connect(self.valuesUpdated.emit)
        self.vlayout = QVBoxLayout(self)
        self.vlayout.addWidget(self.arg_container)
        self.setLayout(self.vlayout)
        self.args: list[tuple[str, tuple[ArgumentType, ...]]] = []

    def add_argument(self, label: str, arg_types: ArgumentType | tuple[ArgumentType], *args: Q.args, **kwargs: Q.kwargs):
        self.arg_container.add_argument(label, arg_types, *args, **kwargs)

    def get_inputs(self) -> list[Any]:
        return self.arg_container.get_inputs()

    def call_function(self):
        values = self.get_inputs()
        return self.fn(*values)
    
    def items(self) -> list[QWidget | tuple[QWidget, ...]]:
        return self.arg_container.items()
    
    def get_item_data(self) -> list[Any]:
        return self.get_inputs()


if __name__ == '__main__':
    app = QApplication()
    w = QMainWindow()

    def root(n: float) -> float:
        return np.sqrt(n)

    f = FunctionWidget(root, [(('Number: ', ArgumentType.FLOAT), {'default': 2.25})], parent=w)
    w.setCentralWidget(f)
    w.show()
    app.exec()