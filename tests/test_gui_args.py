"""Test automatic GUI argument discovery for DataRoutines."""

# ruff: noqa: PLR2004
import inspect
from enum import Enum
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from rfsocinterface.core.data.routines import get_gui_args
from rfsocinterface.core.utils import GuiArg, GuiMeta, NONE_TYPE
from rfsocinterface.gui.widgets.file_select import FileSelectWidget
from rfsocinterface.gui.widgets.utils import gui_arg_to_widget
from tests.utils import (
    CreateValueRoutine,
    CreateValueRoutineWithDefault,
    CreateValueRoutineWithMetadata,
    CreateValueRoutineWithMetadataAndDefault,
    CreateValueRoutineWithOptionalArgument,
    ReduceRoutine,
    ReductionOperation,
    ExEnum,
)
from rfsocinterface.gui.widgets.funtion_inputs import (
    InputWidget,
    IntInputWidget,
    FloatInputWidget,
    BoolInputWidget,
    StringInputWidget,
    FileInputWidget,
    NoneInputWidget,
    EnumInputWidget,
    MultiEnumInputWidget,
    SequenceInputRow,
    SequenceInputWidget,
    TupleInputWidget,
    UnionInputWidget,
    OptionalInputWidget,
    create_input_widget,
)


def test_arg_extraction():
    """Test that getting GuiArgs from routines works."""
    arg = get_gui_args(CreateValueRoutine)[0]
    assert arg.name == 'val'
    assert arg.required
    assert arg.annotation is int
    assert arg.metadata is None
    assert arg.default is inspect.Parameter.empty

    arg = get_gui_args(CreateValueRoutineWithDefault)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation is int
    assert arg.metadata is None
    assert arg.default == 0

    arg = get_gui_args(CreateValueRoutineWithOptionalArgument)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation == (int | None)
    assert arg.metadata is None
    assert arg.default is None

    arg = get_gui_args(CreateValueRoutineWithMetadata)[0]
    assert arg.name == 'val'
    assert arg.required
    assert arg.annotation is int
    assert arg.metadata is not None
    assert arg.metadata.label == 'Value:'
    assert arg.metadata.tooltip == 'The value of the routine'
    assert arg.metadata.minimum == -50
    assert arg.metadata.maximum == 50
    assert arg.default is inspect.Parameter.empty

    arg = get_gui_args(CreateValueRoutineWithMetadataAndDefault)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation is int
    assert arg.metadata is not None
    assert arg.metadata.label == 'Value:'
    assert arg.metadata.tooltip == 'The value of the routine'
    assert arg.metadata.minimum == -50
    assert arg.metadata.maximum == 50
    assert arg.default == 10

    args = get_gui_args(ReduceRoutine)
    assert len(args) == 4
    assert args[0].name == 'terms'
    assert args[0].required
    assert args[0].annotation is list
    assert args[0].metadata is not None
    assert args[0].metadata.label == 'Terms:'
    assert args[0].metadata.tooltip == 'The values to perform the reduction on'
    assert args[0].metadata.minimum is None
    assert args[0].metadata.maximum is None
    assert args[0].default is inspect.Parameter.empty

    assert args[1].name == 'operation'
    assert not args[1].required
    assert args[1].annotation is ReductionOperation
    assert args[1].metadata is not None
    assert args[1].metadata.label == 'Reduction operation:'
    assert args[1].metadata.tooltip == 'The reduction operation to perform'
    assert args[1].metadata.minimum is None
    assert args[1].metadata.maximum is None
    assert args[1].default == ReductionOperation.SUM

    assert args[2].name == 'start'
    assert not args[2].required
    assert args[2].annotation is Any
    assert args[2].metadata is None
    assert args[2].default == 0

    assert args[3].name == 'reverse'
    assert not args[3].required
    assert args[3].annotation is bool
    assert args[3].metadata is not None
    assert args[3].metadata.label == 'Reverse order'
    assert args[3].metadata.tooltip is None
    assert args[3].metadata.minimum is None
    assert args[3].metadata.maximum is None
    assert args[3].default == False  # noqa: E712


@pytest.mark.parametrize(
    'annotation, widget_type',
    [
        (NONE_TYPE, NoneInputWidget),
        (int, IntInputWidget),
        (float, FloatInputWidget),
        (bool, BoolInputWidget),
        (str, StringInputWidget),
        (Path, FileInputWidget),
        (ExEnum, EnumInputWidget),
        (tuple[int, int], TupleInputWidget),
        (tuple[int, ...], SequenceInputWidget),
        (list[int], SequenceInputWidget),
        (int | float, UnionInputWidget),
        (int | float | None, UnionInputWidget),
        (int | None, OptionalInputWidget),
    ],
)
def test_annotation_to_widget(qtbot, annotation: Any, widget_type: type[InputWidget]):
    """Test converting type annotations to widgets."""
    widget = create_input_widget(annotation)
    qtbot.addWidget(widget)
    assert isinstance(widget, widget_type)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if isinstance(widget, TupleInputWidget):
        assert widget.types == args
    elif isinstance(widget, SequenceInputWidget):
        assert widget.container_type == origin
        assert widget.item_type == args[0]
    elif isinstance(widget, UnionInputWidget):
        assert widget.types == args
    elif isinstance(widget, OptionalInputWidget):
        assert widget.item_type == args[0]
    elif isinstance(widget, EnumInputWidget):
        assert widget.enum_type == annotation


def test_arg_to_widget_with_metadata(qtbot):
    """Test that metadata and default values are used properly when creating widgets."""
    arg = get_gui_args(CreateValueRoutineWithMetadataAndDefault)[0]
    label, widget = gui_arg_to_widget(arg)

    qtbot.addWidget(widget)

    assert label is not None
    qtbot.addWidget(label)
    assert isinstance(label, QLabel)
    assert label.text() == 'Value:'
    assert isinstance(widget, QSpinBox)
    assert widget.toolTip() == 'The value of the routine'
    assert widget.minimum() == -50
    assert widget.maximum() == 50
    assert widget.value() == 10

    # Check more complicated routine
    args = get_gui_args(ReduceRoutine)

    label0, widget0 = gui_arg_to_widget(args[0])
    assert label0 is not None
    qtbot.addWidget(widget0)
    qtbot.addWidget(label0)
    assert isinstance(label0, QLabel)
    assert label0.text() == 'Terms:'
    assert isinstance(widget0, QLineEdit)
    assert widget0.toolTip() == 'The values to perform the reduction on'
    assert widget0.text() == ''

    label1, widget1 = gui_arg_to_widget(args[1])
    assert label1 is not None
    qtbot.addWidget(widget1)
    qtbot.addWidget(label1)
    assert isinstance(label1, QLabel)
    assert label1.text() == 'Reduction operation:'
    assert isinstance(widget1, QComboBox)
    assert widget1.toolTip() == 'The reduction operation to perform'
    for member in ReductionOperation:
        assert widget1.findText(member.name) >= 0
    assert widget1.currentText() == 'SUM'

    label2, widget2 = gui_arg_to_widget(args[2])
    assert label2 is not None
    qtbot.addWidget(widget2)
    qtbot.addWidget(label2)
    assert isinstance(label2, QLabel)
    assert label2.text() == 'start:'
    assert isinstance(widget2, QLineEdit)
    assert widget2.toolTip() == ''
    assert widget2.text() == '0'

    label3, widget3 = gui_arg_to_widget(args[3])
    assert label3 is None
    qtbot.addWidget(widget3)
    assert isinstance(widget3, QCheckBox)
    assert widget3.toolTip() == ''
    assert widget3.text() == 'Reverse order'
    assert not widget3.isChecked()
