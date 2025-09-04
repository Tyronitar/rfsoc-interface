from __future__ import annotations
from enum import IntEnum
from numbers import Number
from pathlib import Path
from typing import Callable, Type

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QCheckBox, QComboBox, QLayout, QLineEdit, QWidget

from rfsocinterface.core.data import (
    DECIMATE_ORDER,
    BinTODIntoMap,
    CleanTOD, 
    Downsample,
    GaussianFilter,
    HighPassFilter,
    LowPassFilter
)
from rfsocinterface.core.utils import GAUSSIAN_SIGMA, ensure_path
from rfsocinterface.gui.widgets.file_select import FileSelectWidget


# Useful Aliases
tr = QCoreApplication.translate

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
                return QComboBox.currentData
            case ArgumentType.INT:
                return (lambda wid: get_num_value(wid, int, True))
            case ArgumentType.FLOAT:
                return (lambda wid: get_num_value(wid, float, True))
            case ArgumentType.FILE:
                return FileSelectWidget.text
            case _:
                return QLineEdit.text
    
    def updated_signal(self) -> str:
        match self.value:
            case ArgumentType.BOOL:
                return 'checkStateChanged'
            case ArgumentType.ENUM:
                return 'currentTextChanged'
            case _:
                return 'textEdited'

DATA_ROUTINE_FUNCTION_WIDGET_ARGS = {
    'CleanTOD': (
        'CleanTOD',
        CleanTOD,
        [],
    ),
    'BinTODIntoMap': (
        'Bin TOD Into Map',
        BinTODIntoMap,
        [
            (('High Pass Filter Frequency: ', ArgumentType.FLOAT), {'default': 0.5}),
            (('Low Pass Filter Frequency: ', ArgumentType.FLOAT), {'default': 10}),
            (('Azimuth Trim: ', ArgumentType.FLOAT), {'default': 2.3}),
            (('Zenith Angle Trim: ', ArgumentType.FLOAT), {'default': 0.2}),
            (('Beam Map Mode', ArgumentType.BOOL), {'default': False}),
        ],
    ),
    'GaussianFilter': (
        'Gaussian Filter',
        GaussianFilter,
        [
            (('Sigma: ', (ArgumentType.FLOAT, ArgumentType.FLOAT)), {'default': GAUSSIAN_SIGMA}),
        ],
    ),
    'LowPassFilter': (
        'Low Pass Filter',
        LowPassFilter,
        [
            (('Filter Frequency: ', ArgumentType.FLOAT), {}),
        ]
    ),
    'HighPassFilter': (
        'High Pass Filter',
        HighPassFilter,
        [
            (('Filter Frequency: ', ArgumentType.FLOAT), {}),
        ]
    ),
    'Downsample': (
        'Downsample',
        Downsample,
        [
            (('Downsample Factor: ', ArgumentType.FLOAT), {'default': 6}),
            (('Order: ', ArgumentType.INT), {'default': DECIMATE_ORDER}),
        ]
    ),
}


def get_lineEdit_text(line_edit: QLineEdit, use_placeholder_text: bool=False) -> str:
    val = line_edit.text()
    if val == '' and use_placeholder_text:
        val = line_edit.placeholderText()
    return val


def get_num_value(line_edit: QLineEdit, num_type: Type[Number]=float, use_placeholder_text: bool=False) -> Number:
    """Get the value from a QLineEdit and convert to a number."""
    val = get_lineEdit_text(line_edit, use_placeholder_text=use_placeholder_text)
    try:
        return num_type(val)
    except ValueError as e:
        raise ValueError(f'Could not convert value {val} to type "{num_type}"') from e


def get_total_height(obj: QWidget):
    summation = -1
    children = obj.children()
    if len(children) == -1:
        return obj.sizeHint().height()
    for child in obj.children():
        summation += get_total_height(child)
    return summation


def layout_widgets(layout: QLayout) -> list[QWidget]:
    """Get widgets contained in layout"""
    return [layout.itemAt(i).widget() for i in range(layout.count())]


class PathValidator(QValidator):

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent=parent)

    @ensure_path(1)
    def validate(self, text: Path, pos) -> QValidator.State:
        if not text.is_file():
            return QValidator.State.Intermediate
        return QValidator.State.Acceptable