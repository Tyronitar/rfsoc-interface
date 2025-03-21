

from enum import IntEnum
from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget, QCheckBox


from typing import Any, Callable

from rfsocinterface.core.utils import get_num_value
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

    def __init__(self, fn: Callable, args: list[tuple[tuple, dict]]=[], parent=None):
        super().__init__(parent=parent)
        self.fn = fn
        self.args: list[tuple[str, ArgumentType]] = []
        self.form_layout = QFormLayout(parent=self)
        for (arg, kwargs) in args:
            self.add_argument(*arg, **kwargs)
        self.setLayout(self.form_layout)

    def add_argument(self, label: str, arg_type: ArgumentType, *args, **kwargs):
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