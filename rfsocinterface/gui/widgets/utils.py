"""Utils for PySide6 Custom Widgets."""

from collections.abc import Callable
from enum import IntEnum
from numbers import Number
from pathlib import Path
from typing import override

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QCheckBox, QComboBox, QLayout, QLineEdit, QWidget

from rfsocinterface.core.utils import ensure_path
from rfsocinterface.gui.widgets.file_select import FileSelectWidget


def get_num_value(
    line_edit: QLineEdit,
    num_type: type[Number] = float,
    use_placeholder_text: bool = False,
) -> Number:
    """Get the value from a QLineEdit and convert to a number."""
    val = get_line_edit_text(line_edit, use_placeholder_text=use_placeholder_text)
    try:
        return num_type(val)
    except ValueError as e:
        raise ValueError(f'Could not convert value {val} to type "{num_type}"') from e


class ArgumentType(IntEnum):
    """Class for specifying the type of argument to add to a GUI."""

    BOOL = 0
    ENUM = 1
    INT = 2
    FLOAT = 3
    STR = 4
    FILE = 5
    ITERABLE = 6

    def widget(self, *args, **kwargs) -> QWidget:
        """Return the appropriate widget for the argument type."""
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
        """Return the function to get the data from this ArgumentType's widget."""
        match self.value:
            case ArgumentType.BOOL:
                return QCheckBox.isChecked
            case ArgumentType.ENUM:
                return QComboBox.currentText
            case ArgumentType.INT:
                return lambda wid: get_num_value(wid, int)
            case ArgumentType.FLOAT:
                return lambda wid: get_num_value(wid, float)
            case ArgumentType.FILE:
                return FileSelectWidget.text
            case _:
                return QLineEdit.text


def layout_widgets(layout: QLayout) -> list[QWidget]:
    """Get widgets contained in layout."""
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def get_total_height(obj: QWidget):
    """Get the total height of the widget and its children."""
    summation = -1
    children = obj.children()
    if len(children) == -1:
        return obj.sizeHint().height()
    for child in obj.children():
        summation += get_total_height(child)
    return summation


def get_line_edit_text(line_edit: QLineEdit, use_placeholder_text: bool = False) -> str:
    """Get the text from a QLineEdit, using the placheolder text if needed."""
    val = line_edit.text()
    if val == '' and use_placeholder_text:
        val = line_edit.placeholderText()
    return val


class PathValidator(QValidator):
    """QValidator for testing file paths."""

    def __init__(self, parent: QWidget | None = None):
        """Initialize a PathValidator."""
        super().__init__(parent=parent)

    @override
    @ensure_path(1)
    def validate(self, text: Path, pos) -> QValidator.State:
        """Validate the text."""
        if not text.is_file():
            return QValidator.State.Intermediate
        return QValidator.State.Acceptable
