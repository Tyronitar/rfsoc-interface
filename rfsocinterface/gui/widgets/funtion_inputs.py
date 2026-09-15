"""Custom widgets for representing function arguments that can have multiple values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import (
    Any,
    TypeVar,
    TypeVarTuple,
    Union,
    cast,
    get_args,
    get_origin,
    override,
)

from PySide6.QtCore import QSize, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.data.routines import GuiMeta
from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from rfsocinterface.gui.widgets.file_select import FileSelectWidget

NONE_TYPE = type(None)
E = TypeVar('E', bound=Enum)
Ts = TypeVarTuple('Ts')

type TypeAnnotation = Any


def check_type(value: Any, expected_type: TypeAnnotation) -> bool:
    """Recursively check that a value is the correct type."""
    base_type = get_origin(expected_type)

    # Base type of None means it's not a generic, so just check the type directly.
    if base_type is None:
        return isinstance(value, expected_type)

    # Recursively check each element
    internal_type = get_args(expected_type)
    if issubclass(base_type, Mapping):
        # Chec kkey and values separately for a dictionary
        key_type, val_type = internal_type
        internals = [
            check_type(k, key_type) and check_type(v, val_type)
            for k, v in value.items()
        ]
        return all(internals) and isinstance(value, base_type)
    if issubclass(base_type, Sequence):
        # Check each element in a sequence
        if len(internal_type) == 1:
            # Single type so just check if each one is the right one
            internals = [check_type(v, internal_type) for v in value]
        elif len(internal_type) < len(value):
            return False
        else:
            # Multiple types, so each element should be the corresponsing type
            internals = [
                check_type(v, type_)
                for (v, type_) in zip(value, internal_type, strict=True)
            ]
        return all(internals) and isinstance(value, base_type)
    # Unhandled generic type scenario; just check base class
    return isinstance(value, base_type)


class InputWidget[T](ABC):
    """Interface for widgets that support GUI function integration."""

    @abstractmethod
    def value(self) -> T:
        """Return the value represented by this widget."""

    @abstractmethod
    def set_value(self, value: T) -> None:
        """Set the value represented by this widget."""


#
# Standard Input types
#

# ruff: disable[ARG002]


class IntInputWidget(QSpinBox, InputWidget[int]):
    """InputWidget that handles integer inputs."""

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize an IntInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> int:
        return QSpinBox.value(self)

    @override
    def set_value(self, value: int):
        QSpinBox.setValue(self, value)


class FloatInputWidget(QDoubleSpinBox, InputWidget[float]):
    """InputWidget that handles float inputs."""

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize a FloatInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> float:
        return QDoubleSpinBox.value(self)

    @override
    def set_value(self, value: float):
        QDoubleSpinBox.setValue(self, value)


class BoolInputWidget(QCheckBox, InputWidget[bool]):
    """InputWidget that handles Boolean inputs."""

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize a BoolInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> bool:
        return self.isChecked()

    @override
    def set_value(self, value: bool):
        self.setChecked(value)


class StringInputWidget(QLineEdit, InputWidget[str]):
    """InputWidget that handles string inputs."""

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize a StringInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> str:
        return self.text()

    @override
    def set_value(self, value: str):
        self.setText(value)


class FileInputWidget(FileSelectWidget, InputWidget[Path]):
    """InputWidget that handles file inputs."""

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize a FileInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> Path:
        return Path(self.text())

    @override
    def set_value(self, value: Path | str):
        self.set_text(str(value))


class NoneInputWidget(QWidget, InputWidget[NONE_TYPE]):
    """Dummy InputWidget for handling `None` inputs.

    Needed for generating InputWidgets for types of the kind T1 | T2 | ... | None. It's
    not an Optional[T], so it will need some way to handle the `None` option.
    """

    def __init__(self, gui_meta: GuiMeta | None = None, parent: QWidget | None = None):
        """Initialize a NoneInputWidget."""
        super().__init__(parent=parent)

    @override
    def value(self) -> None:
        return None

    @override
    def set_value(self, value: Any):
        if value is not None:
            raise ValueError(f'The only accepted input is `None`; got "{value}"')


#
# Enum types
#


def is_enum_value(value: Any, enum_cls: type[Enum]) -> bool:
    """Return whether a value is a valid value for the specified enum class."""
    try:
        enum_cls(value)
    except ValueError:
        return False
    else:
        return True


class EnumInputWidget[E: Enum](QComboBox, InputWidget[E]):
    """InputWidget that handles enum inputs.

    Given an enum class, it will populate a QComboBox with each member of the class.
    """

    def __init__(
        self,
        enum_type: type[E],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize an EnumInputWidget."""
        super().__init__(parent=parent)
        self.enum_type = enum_type
        for member in enum_type:
            self.addItem(str(member), userData=member)

    @override
    def value(self) -> E:
        return self.currentData()

    @override
    def set_value(self, value: E):
        if not is_enum_value(value):
            raise ValueError(
                f'Provided value {value} is not a valid value for type {self.enum_type}'
            )
        self.setCurrentIndex(self.findData(self.enum_type(value)))


class MultiEnumInputWidget[E: Enum](CheckableComboBox, InputWidget[E]):
    """InputWidget that handles enum inputs, allowing for selecting multiple options."""

    def __init__(
        self,
        enum_type: type[E],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a MultiInputEnumInputWidget."""
        super().__init__(parent=parent)
        self.enum_type = enum_type
        for member in enum_type:
            self.addItem(str(member), userData=member)

    @override
    def value(self) -> list[E]:
        return [self.itemData(i) for i in self.checked_indices()]

    @override
    def set_value(self, value: list[E]):
        for v in value:
            if not is_enum_value(v, self.enum_type):
                raise ValueError(
                    f'Provided value {v} is not a valid value for type {self.enum_type}'
                )
        enum_values = [self.enum_type(v) for v in value]

        all_indices = list(range(self.count()))
        for idx in all_indices:
            val = self.itemData(idx)
            self.set_item_checked(val in enum_values)


#
# Collection types
#


class SequenceInputRow[T](QWidget, InputWidget[T]):
    """Widget representing a single element of a SequenceInputWidget."""

    removed = Signal()

    def __init__(self, widget: InputWidget[T], parent: QWidget | None = None):
        """Initialize a SequenceInputRow."""
        super().__init__(parent=parent)
        self.hlayout = QHBoxLayout()

        self.widget = widget
        self.hlayout.addWidget(widget)

        self.spacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum
        )
        self.hlayout.addSpacerItem(self.spacer)

        self.remove_button = QToolButton(parent=self)
        icon = QIcon()
        icon.addFile(':/icons/remove.png', QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.remove_button.setIcon(icon)
        self.remove_button.setIconSize(QSize(32, 32))
        self.hlayout.addWidget(self.remove_button)

        self.setLayout(self.hlayout)

        self.remove_button.clicked.connect(self.removed.emit)

    @override
    def value(self) -> T:
        return self.widget.value()

    @override
    def set_value(self, value: T):
        self.widget.set_value(value)


class SequenceInputWidget[T, S: Sequence[T]](QWidget, InputWidget[S]):
    """InputWidget representing seqeunce inputs (e.g. list[T], tuple[T, ...], etc.).

    Given the specified type `item_type`, will automatically generate the appropriate
    widgets for each list item.
    """

    def __init__(
        self,
        item_type: TypeAnnotation,
        container_type: Callable[[Iterable[T]], S],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a SequenceInputWidget.

        Arguments:
            item_type (type): The type of sequence elements (i.e. the "T" of
                Sequence[T]).
            container_type (Callable[[Iterable[T]], S]): A function that converts an
                iterable into the desired container type. (e.g. `list`, `tuple`).
            gui_meta (GuiMeta, optional): Metadata to further describe the widgets
                created. Defaults to `None`.
            parent (QObject, optional): The parent of this widget. Defaults to `None`.
        """
        super().__init__(parent)

        self.item_type = item_type
        self.rows: list[SequenceInputRow[T]] = []
        self.container_type = container_type

        # layout setup...
        self.vlayout = QVBoxLayout()
        self.setLayout(self.vlayout)

    def add_item(self, value: T | None = None):
        """Add an item to the sequence.

        If `value` is not `None` the new row's value will be assigned.
        """
        widget = create_input_widget(self.item_type)
        widget.setParent(self)
        new_row = SequenceInputRow(widget)
        new_row.removed.connect(self.remove_row)

        if value is not None:
            new_row.set_value(value)

        self.rows.append(new_row)
        # add widget + remove button to layout
        self.vlayout.addWidget(new_row)

    @Slot()
    def remove_row(self):
        """Remove a row from the sequence."""
        row: SequenceInputRow = self.sender()
        self.vlayout.removeWidget(row)
        self.rows.remove(row)
        row.deleteLater()

    def clear(self):
        """Remove all rows from the widget."""
        while self.rows:
            row = self.rows.pop()
            self.vlayout.removeWidget(row)
            row.deleteLater()

    @override
    def value(self) -> S:
        return self.container_type(row.value() for row in self.rows)

    @override
    def set_value(self, value: S):
        if not isinstance(value, Sequence):
            raise TypeError(f'Expected a sequence of values; got {type(value)}')
        if not all(check_type(v, self.item_type) for v in value):
            raise TypeError(
                f'Not all values are the correct type "{self.item_type}";  '
                f'value={value}'
            )
        self.clear()
        for v in value:
            self.add_item(v)


class TupleInputWidget[*Ts](QWidget, InputWidget[tuple[*Ts]]):
    """InputWidget representing tuple inputs.

    Given the specified type `item_type` will automatically generate the appropriate
    widgets for each item.
    """

    def __init__(
        self,
        types: tuple[TypeAnnotation, ...],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a TupleInputWidget."""
        super().__init__(parent)

        self.types = types
        self.widgets = []

        # layout setup...
        self.vlayout = QVBoxLayout()

        for type_ in types:
            widget = create_input_widget(type_, parent=self)
            self.widgets.append(widget)
            self.vlayout.addWidget(widget)

        self.setLayout(self.vlayout)

    def count(self) -> int:
        """Return the length of the tuple."""
        return len(self.types)

    @override
    def value(self) -> tuple[*Ts]:
        return cast(
            tuple[*Ts],
            tuple(widget.value() for widget in self.widgets),
        )

    @override
    def set_value(self, value: tuple[*Ts]):
        if len(value) != self.count():
            raise ValueError(f'Expected {self.count()} values, got {len(value)}.')

        for val, expected_type in zip(value, self.types, strict=True):
            if not check_type(val, expected_type):
                raise TypeError(
                    f'Expected value of type {expected_type!r}, got {type(val)!r}'
                )

        for widget, item_value in zip(self.widgets, value, strict=True):
            widget.set_value(item_value)


#
# Union Types
#


def is_union(annotation: TypeAnnotation) -> bool:
    """Return whether a type annotation is a union type."""
    origin = get_origin(annotation)
    return origin is Union or origin is UnionType


def is_optional(annotation: TypeAnnotation) -> bool:
    """Return whether a type annotation is optional."""
    if not is_union(annotation):
        return False

    args = get_args(annotation)

    return len(args) == 2 and NONE_TYPE in args  # noqa: PLR2004


def get_optional_type(annotation: TypeAnnotation) -> TypeAnnotation | None:
    """Extract the type from an optional type annotation."""
    args = get_args(annotation)

    if type(None) not in args:
        return None

    non_none = tuple(arg for arg in args if arg is not type(None))

    if len(non_none) != 1:
        # Type was not Optional[T] but of the form T1 | T2 | ... | None
        return None

    return non_none[0]


def convert_type_to_string(type_: TypeAnnotation) -> str:
    """Return a string representation of types."""
    if type_ is NONE_TYPE:
        return 'None'
    return type_.__name__


class UnionInputWidget[T](QWidget, InputWidget[T]):
    """Widget representing inputs of union type (e.g. str | int)."""

    def __init__(
        self,
        types: tuple[TypeAnnotation, ...],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a UnionInputWidget."""
        super().__init__(parent)

        self.types = types

        self.type_combo = QComboBox(parent=self)
        self.vlayout = QVBoxLayout()
        self.stack = QStackedWidget(parent=self)

        for annotation in types:
            self.type_combo.addItem(convert_type_to_string(annotation))
            self.stack.addWidget(create_input_widget(annotation))

        self.type_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.vlayout.addWidget(self.type_combo)
        self.vlayout.addWidget(self.stack)
        self.setLayout(self.vlayout)

    @override
    def value(self) -> T:
        widget = cast(InputWidget[T], self.stack.currentWidget())
        return widget.value()

    @override
    def set_value(self, value: T) -> None:
        for i, type_ in enumerate(self.types):
            widget = self.stack.widget(i)

            if check_type(value, type_):
                self.type_combo.setCurrentIndex(i)
                widget.set_value(value)
                return

        raise TypeError(
            f'Value "{value!r}" of type "{type(value)}" does not match any of '
            f'{self.types!r}'
        )


class OptionalInputWidget[T](QWidget, InputWidget):
    """InputWidget that handles optional inputs."""

    def __init__(
        self,
        type_: type[T],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize an OptionalInputWidget."""
        super().__init__(parent=parent)

        self.hlayout = QHBoxLayout()
        self.checkbox = QCheckBox('Use value', parent=self)
        self.hlayout.addWidget(self.checkbox)

        self.widget = create_input_widget(type_)
        self.hlayout.addWidget(self.widget)

        self.checkbox.toggled.connect(self.widget.setEnabled)
        self.checkbox.setChecked(True)  # Default to enabled
        self.widget.setEnabled(True)

    @override
    def value(self) -> T | None:
        return self.widget.value() if self.checkbox.isChecked() else None

    @override
    def set_value(self, value: T | None):
        if value is None:
            self.checkbox.setChecked(False)
        else:
            self.checkbox.setChecked(True)
            self.widget.set_value(value)


#
# Widget Factory
#


def create_input_widget[T](  # noqa: PLR0911
    annotation: type[T],
    *,
    gui_meta: GuiMeta | None = None,
    parent: QWidget | None = None,
) -> InputWidget[T]:
    """Recursively create a widget appropriate for a type annotation."""
    # Optional[T]
    if is_optional(annotation):
        inner_type = get_optional_type(annotation)

        return OptionalInputWidget(
            inner_type,
            gui_meta=gui_meta,
            parent=parent,
        )

    origin = get_origin(annotation)

    # list[T]
    if origin is list:
        args = get_args(annotation)

        if len(args) != 1:
            raise TypeError(f'Expected list[T], got {annotation!r}')

        return cast(
            InputWidget[T],
            SequenceInputWidget(
                args[0],
                list,
                gui_meta=gui_meta,
                parent=parent,
            ),
        )

    if origin is tuple:
        args = get_args(annotation)

        # tuple[T, ...]
        if len(args) == 2 and args[1] is Ellipsis:  # noqa: PLR2004
            return cast(
                InputWidget[T],
                SequenceInputWidget(
                    args[0],
                    tuple,
                    gui_meta=gui_meta,
                    parent=parent,
                ),
            )

        # tuple[T1, T2, ..., TN]
        return cast(
            InputWidget[T],
            TupleInputWidget(
                args,
                gui_meta=gui_meta,
                parent=parent,
            ),
        )

    # A | B | ...
    if is_union(annotation):
        return UnionInputWidget(
            get_args(annotation),
            gui_meta=gui_meta,
            parent=parent,
        )

    # Enum subclass
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        # TODO: Check GuiMeta for whether single or multi-input
        return EnumInputWidget(
            annotation,
            gui_meta=gui_meta,
            parent=parent,
        )

    # Scalar types
    if annotation is bool:
        return BoolInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    if annotation is int:
        return IntInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    if annotation is float:
        return FloatInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    if annotation is str:
        return StringInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    if annotation is Path:
        return FileInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    # Only used in cases of T1 | T2 | ... | None
    if annotation is NONE_TYPE:
        return NoneInputWidget(
            gui_meta=gui_meta,
            parent=parent,
        )

    raise TypeError(f'No GUI widget defined for annotation "{annotation!r}"')


# ruff: enable[ARG002]

# if __name__ == '__main__':
#     import pdb

#     from PySide6.QtWidgets import QApplication

#     class ExEnum(Enum):
#         ONE = 1
#         TWO = 2
#         THREE = 3

#     app = QApplication()
#     pdb.set_trace()
#     app.exec()
