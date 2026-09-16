"""Utils for PySide6 Custom Widgets."""

from collections.abc import Callable, Iterable
from enum import Enum, IntEnum
from numbers import Number
from pathlib import Path
from typing import Any, override

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from rfsocinterface.core.utils import GuiArg, ensure_path, is_type
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


def gui_arg_to_widget(arg: GuiArg) -> tuple[QLabel | None, QWidget]:
    """Return the appropriate label and widget for the argument type."""
    annotation = arg.annotation
    meta = arg.metadata
    default = None if arg.required else arg.default
    widget = None
    if annotation is Any:
        widget = QLineEdit()
        widget.setText(str(default) if default is not None else '')
    elif is_type(annotation, bool):
        widget = QCheckBox()
        widget.setChecked(default or False)
    elif is_type(annotation, int):
        widget = QSpinBox()
        widget.setValue(default or 0)
    elif is_type(annotation, float):
        widget = QDoubleSpinBox()
        widget.setValue(default or 0)
    elif is_type(annotation, Path):
        widget = FileSelectWidget()
        widget.set_text(default or '')
    elif is_type(annotation, str) or (
        isinstance(annotation, type) and issubclass(annotation, Iterable)
    ):
        widget = QLineEdit()
        widget.setText(str(default or ''))
    elif isinstance(annotation, type) and issubclass(annotation, Enum):
        widget = QComboBox()
        for member in annotation:
            widget.addItem(member.name, member)
        widget.setCurrentText(str(default) if default is not None else '')
    else:
        raise TypeError(f'No GUI widget defined for {annotation!r}')

    # Apply metadata
    if meta is not None:
        widget.setToolTip(meta.tooltip or '')
        if isinstance(widget, QAbstractSpinBox):
            widget.setMinimum(meta.minimum or 0)
            widget.setMaximum(meta.maximum or 99)

    # Checkboxes store text internally, no need for separate label
    if isinstance(widget, QCheckBox):
        text = arg.name
        if meta is not None:
            text = meta.label or text
        widget.setText(text)
        return None, widget

    # Otherwise, create a label with appropriate text
    label_text = f'{arg.name}'
    if meta is not None:
        label_text = meta.label or label_text
    # Make sure the label ends with ":"
    label_text = label_text if label_text.endswith(':') else label_text + ':'
    return QLabel(label_text), widget


def get_value_from_widget(widget: QWidget) -> Any:
    """Get the value from a widget of unknown type."""
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QAbstractSpinBox):
        return widget.value()
    if isinstance(widget, FileSelectWidget):
        return Path(widget.text())
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    raise TypeError(f'Widgets of type "{widget.__class__.__name__}" are unsupported.')


class ArgumentType(IntEnum):
    """Class for specifying the type of argument to add to the GUI."""

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
