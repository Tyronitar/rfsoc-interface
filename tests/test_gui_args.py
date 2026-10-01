"""Test automatic GUI argument discovery for DataRoutines."""

# ruff: noqa: PLR2004
import inspect
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import pytest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from rfsocinterface.core.data.routines import get_gui_args
from rfsocinterface.core.utils import NONE_TYPE
from rfsocinterface.gui.widgets.function_inputs import (
    BoolInputWidget,
    CollectionInputWidget,
    EnumInputWidget,
    FileInputWidget,
    FloatInputWidget,
    InputWidget,
    IntInputWidget,
    LiteralInputWidget,
    MappingInputWidget,
    NoneInputWidget,
    OptionalInputWidget,
    StringInputWidget,
    TupleInputWidget,
    UnionInputWidget,
    create_input_widget,
    gui_arg_to_widget,
)
from rfsocinterface.gui.widgets.utils import gui_arg_to_widget as old_gui_arg_to_widget
from tests.utils import (
    AnyAnnotationRoutine,
    ArgsAnyAnnotationRoutine,
    ArgsMissingAnnotationRoutine,
    CreateValueRoutine,
    CreateValueRoutineWithDefault,
    CreateValueRoutineWithMetadata,
    CreateValueRoutineWithMetadataAndDefault,
    CreateValueRoutineWithOptionalArgument,
    DocstringExtractionRoutine,
    ExEnum,
    KeywordAnyAnnotationRoutine,
    KeywordMissingAnnotationRoutine,
    MissingAnnotationRoutine,
    ReduceRoutine,
    ReductionOperation,
    VariableParameterRoutine,
)


def test_arg_extraction():
    """Test that getting GuiArgs from routines works."""
    arg = get_gui_args(CreateValueRoutine, use_defaults=False)[0]
    assert arg.name == 'val'
    assert arg.required
    assert arg.annotation is int
    assert arg.metadata is None
    assert arg.default is inspect.Parameter.empty
    assert arg.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    arg = get_gui_args(CreateValueRoutineWithDefault, use_defaults=False)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation is int
    assert arg.metadata is None
    assert arg.default == 0
    assert arg.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    arg = get_gui_args(CreateValueRoutineWithOptionalArgument, use_defaults=False)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation == (int | None)
    assert arg.metadata is None
    assert arg.default is None
    assert arg.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    arg = get_gui_args(CreateValueRoutineWithMetadata, use_defaults=False)[0]
    assert arg.name == 'val'
    assert arg.required
    assert arg.annotation is int
    assert arg.metadata is not None
    assert arg.metadata.label == 'Value:'
    assert arg.metadata.tooltip == 'The value of the routine'
    assert arg.metadata.minimum == -50
    assert arg.metadata.maximum == 50
    assert arg.default is inspect.Parameter.empty
    assert arg.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    arg = get_gui_args(CreateValueRoutineWithMetadataAndDefault, use_defaults=False)[0]
    assert arg.name == 'val'
    assert not arg.required
    assert arg.annotation is int
    assert arg.metadata is not None
    assert arg.metadata.label == 'Value:'
    assert arg.metadata.tooltip == 'The value of the routine'
    assert arg.metadata.minimum == -50
    assert arg.metadata.maximum == 50
    assert arg.default == 10
    assert arg.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    args = get_gui_args(ReduceRoutine, use_defaults=False)
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
    assert args[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    assert args[1].name == 'operation'
    assert not args[1].required
    assert args[1].annotation is ReductionOperation
    assert args[1].metadata is not None
    assert args[1].metadata.label == 'Reduction operation:'
    assert args[1].metadata.tooltip == 'The reduction operation to perform'
    assert args[1].metadata.minimum is None
    assert args[1].metadata.maximum is None
    assert args[1].default == ReductionOperation.SUM
    assert args[1].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    assert args[2].name == 'start'
    assert not args[2].required
    assert args[2].annotation is int
    assert args[2].metadata is None
    assert args[2].default == 0
    assert args[2].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    assert args[3].name == 'reverse'
    assert not args[3].required
    assert args[3].annotation is bool
    assert args[3].metadata is not None
    assert args[3].metadata.label == 'Reverse order'
    assert args[3].metadata.tooltip is None
    assert args[3].metadata.minimum is None
    assert args[3].metadata.maximum is None
    assert args[3].default == False  # noqa: E712
    assert args[3].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD


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
        (Literal['hello', 'world'], LiteralInputWidget),
        (tuple[int, int], TupleInputWidget),
        (tuple[int, ...], CollectionInputWidget),
        (list[int], CollectionInputWidget),
        (set[int], CollectionInputWidget),
        (Sequence[int], CollectionInputWidget),
        (Collection[int], CollectionInputWidget),
        (int | float, UnionInputWidget),
        (int | float | None, UnionInputWidget),
        (int | None, OptionalInputWidget),
        (dict[int, str], MappingInputWidget),
        (Mapping[int, str], MappingInputWidget),
        (Mapping[str, list[int]], MappingInputWidget),
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
    elif isinstance(widget, CollectionInputWidget) and origin in (list, set, tuple):
        assert widget.container_type is origin
        assert widget.item_type == args[0]
    elif isinstance(widget, CollectionInputWidget):
        assert widget.container_type is list
        assert widget.item_type == args[0]
    elif isinstance(widget, UnionInputWidget):
        assert widget.types == args
    elif isinstance(widget, OptionalInputWidget):
        assert widget.item_type == args[0]
    elif isinstance(widget, EnumInputWidget):
        assert widget.enum_type == annotation
    elif isinstance(widget, LiteralInputWidget):
        assert widget.values == ('hello', 'world')
    elif isinstance(widget, MappingInputWidget):
        assert widget.key_type == args[0]
        assert widget.value_type == args[1]


def test_arg_to_widget_with_metadata(qtbot):
    """Test that metadata and default values are used properly when creating widgets."""
    arg = get_gui_args(CreateValueRoutineWithMetadataAndDefault)[0]
    label, widget = old_gui_arg_to_widget(arg)

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

    label0, widget0 = old_gui_arg_to_widget(args[0])
    assert label0 is not None
    qtbot.addWidget(widget0)
    qtbot.addWidget(label0)
    assert isinstance(label0, QLabel)
    assert label0.text() == 'Terms:'
    assert isinstance(widget0, QLineEdit)
    assert widget0.toolTip() == 'The values to perform the reduction on'
    assert widget0.text() == ''

    label1, widget1 = old_gui_arg_to_widget(args[1])
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

    label2, widget2 = old_gui_arg_to_widget(args[2])
    assert label2 is not None
    qtbot.addWidget(widget2)
    qtbot.addWidget(label2)
    assert isinstance(label2, QLabel)
    assert label2.text() == 'start:'
    assert isinstance(widget2, QSpinBox)
    assert widget2.toolTip() == ''
    assert widget2.text() == '0'

    label3, widget3 = old_gui_arg_to_widget(args[3])
    assert label3 is None
    qtbot.addWidget(widget3)
    assert isinstance(widget3, QCheckBox)
    assert widget3.toolTip() == ''
    assert widget3.text() == 'Reverse order'
    assert not widget3.isChecked()


def test_docstring_extraction():
    """Test that extracting values from the docstring works as expected."""
    args = get_gui_args(DocstringExtractionRoutine)

    assert len(args) == 4

    assert args[0].metadata is not None
    assert args[0].metadata.label == 'Argument 1:'
    assert args[0].metadata.tooltip == 'The first argument'

    assert args[1].metadata is not None
    assert args[1].metadata.label == 'arg2:'  # Default label
    assert args[1].metadata.minimum == -10
    assert args[1].metadata.maximum == 10
    # Check that GuiMeta has precendence over docstring
    assert args[1].metadata.tooltip == 'The second argument'

    assert args[2].metadata is not None
    assert args[2].metadata.label == 'arg3:'  # Default label
    assert args[2].metadata.minimum == -10
    assert args[2].metadata.maximum == 10
    assert args[2].metadata.tooltip is None  # No docstring or GuiMeta tooltip

    assert args[3].metadata is not None
    assert args[3].metadata.label == 'arg4:'  # Default label
    assert args[3].metadata.minimum is None  # Default minimum
    assert args[3].metadata.maximum is None  # Default maximum
    assert args[3].metadata.tooltip == 'The fourth argument.'  # From docstring


def test_variable_parameters(qtbot):
    """Test arg extraction from routines with variable parameters."""
    args = get_gui_args(VariableParameterRoutine)
    assert len(args) == 5

    widget = gui_arg_to_widget(args[0])
    qtbot.addWidget(widget)
    assert args[0].name == 'var0'
    assert args[0].kind == inspect.Parameter.POSITIONAL_ONLY
    assert isinstance(widget, StringInputWidget)

    widget = gui_arg_to_widget(args[1])
    qtbot.addWidget(widget)
    assert args[1].name == 'var1'
    assert args[1].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert isinstance(widget, FloatInputWidget)

    widget = gui_arg_to_widget(args[2])
    qtbot.addWidget(widget)
    assert args[2].name == 'args'
    assert args[2].kind == inspect.Parameter.VAR_POSITIONAL
    assert isinstance(widget, CollectionInputWidget)
    assert widget.item_type is int
    assert widget.container_type is tuple

    widget = gui_arg_to_widget(args[3])
    qtbot.addWidget(widget)
    assert args[3].name == 'var2'
    assert args[3].kind == inspect.Parameter.KEYWORD_ONLY
    assert isinstance(widget, BoolInputWidget)

    widget = gui_arg_to_widget(args[4])
    qtbot.addWidget(widget)
    assert args[4].name == 'kwargs'
    assert args[4].kind == inspect.Parameter.VAR_KEYWORD
    assert isinstance(widget, MappingInputWidget)
    assert widget.key_type is str
    assert widget.value_type is str
    assert widget.container_type is dict


def test_bad_annotations():
    """Test that exceptions are raised with bad type hints."""
    with pytest.raises(TypeError, match='must have a type annotation'):
        get_gui_args(MissingAnnotationRoutine)

    with pytest.raises(TypeError, match='a concrete type is required'):
        get_gui_args(AnyAnnotationRoutine)

    with pytest.raises(TypeError, match='must have a type annotation'):
        get_gui_args(ArgsMissingAnnotationRoutine)

    with pytest.raises(TypeError, match='a concrete type is required'):
        get_gui_args(ArgsAnyAnnotationRoutine)

    args = get_gui_args(KeywordMissingAnnotationRoutine)
    assert len(args) == 0
    args = get_gui_args(KeywordAnyAnnotationRoutine)
    assert len(args) == 0

    with pytest.raises(TypeError, match=r'Expected .*\[K, V\], got'):
        create_input_widget(dict[int])

    with pytest.raises(TypeError, match=r'Expected .*\[T\], got'):
        create_input_widget(list[int, int])

    with pytest.raises(TypeError, match='No GUI widget defined for'):
        create_input_widget(bytes)
