"""Custom widgets for representing function arguments that can have multiple values."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Literal,
    cast,
    get_args,
    get_origin,
    override,
)

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QObject, QSize, Signal, Slot
from PySide6.QtGui import QIcon, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.utils import (
    MAX_FLOAT,
    MAX_INT,
    MIN_FLOAT,
    MIN_INT,
    NONE_TYPE,
    GuiArg,
    GuiMeta,
    TypeAnnotation,
    check_type,
    convert_type_to_string,
    get_optional_type,
    is_empty,
    is_enum_value,
    is_optional,
    is_union,
    unwrap_annotated,
)
from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from rfsocinterface.gui.widgets.file_select import FileSelectWidget
from rfsocinterface.gui.widgets.scroll_area import ExpandingScrollArea
from rfsocinterface.gui.widgets.stacked_widget import ResizingStackedWidget


@dataclass
class GuiArgWidget[T]:
    """Paif of argument and its corresponding InputWidget."""

    arg: GuiArg[T]
    widget: InputWidget[T]

    def value(self) -> T:
        """Return the value of the input widget."""
        return self.widget.value()


class InputWidget[T]:
    """Interface for widgets that support GUI function integration."""

    def value(self) -> T:
        """Return the value represented by this widget."""

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
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        if gui_meta is not None:
            if gui_meta.tooltip is not None:
                self.setToolTip(gui_meta.tooltip)
            self.setMinimum(
                gui_meta.minimum if gui_meta.minimum is not None else MIN_INT
            )
            self.setMaximum(
                gui_meta.maximum if gui_meta.maximum is not None else MAX_INT
            )
            self.setPrefix(gui_meta.prefix if gui_meta.prefix is not None else '')
            self.setSuffix(gui_meta.suffix if gui_meta.suffix is not None else '')

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
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        if gui_meta is not None:
            if gui_meta.tooltip is not None:
                self.setToolTip(gui_meta.tooltip)
            self.setMinimum(
                gui_meta.minimum if gui_meta.minimum is not None else MIN_FLOAT
            )
            self.setMaximum(
                gui_meta.maximum if gui_meta.maximum is not None else MAX_FLOAT
            )
            self.setPrefix(gui_meta.prefix if gui_meta.prefix is not None else '')
            self.setSuffix(gui_meta.suffix if gui_meta.suffix is not None else '')

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
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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


class LiteralInputWidget[T](QComboBox, InputWidget[T]):
    """InputWidget for choosing from a fixed set of literal values."""

    def __init__(
        self,
        values: tuple[T, ...],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a LiteralInputWidget.

        Given the possible values, it will populate a QComboBox with each one.
        """
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )

        self.values = values

        for value in values:
            self.addItem(str(value), userData=value)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

    @override
    def value(self) -> T:
        return self.currentData()

    @override
    def set_value(self, value: T) -> None:
        for index, literal in enumerate(self.values):
            # Test type and value to prevent spurious cases like True == 1
            if type(value) is type(literal) and value == literal:
                self.setCurrentIndex(index)
                return

        raise ValueError(f'{value!r} is not one of the allowed values {self.values!r}')


#
# Enum types
#


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
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.enum_type = enum_type
        for member in enum_type:
            self.addItem(member.name, userData=member)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.enum_type = enum_type
        for member in enum_type:
            self.addItem(member.name, userData=member)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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


class CollectionInputRow[T](QGroupBox, InputWidget[T]):
    """Widget representing a single element of a CollectionInputWidget."""

    removed = Signal()

    def __init__(self, widget: InputWidget[T], parent: QWidget | None = None):
        """Initialize a SequenceInputRow."""
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.hlayout = QHBoxLayout()

        self.widget = widget
        self.hlayout.addWidget(widget)

        # self.spacer = QSpacerItem(
        #     40, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum
        # )
        # self.hlayout.addSpacerItem(self.spacer)

        self.remove_button = QToolButton(parent=self)
        icon = QIcon()
        icon.addFile(':/icons/remove.png', QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.remove_button.setIcon(icon)
        self.remove_button.setIconSize(QSize(16, 16))
        self.remove_button.setToolTip('Remove this tem from the sequence')
        self.hlayout.addWidget(self.remove_button)

        self.setLayout(self.hlayout)

        self.remove_button.clicked.connect(self.removed.emit)

    @override
    def value(self) -> T:
        return self.widget.value()

    @override
    def set_value(self, value: T):
        self.widget.set_value(value)


class CollectionInputWidget[T, C: Collection[T]](QGroupBox, InputWidget[C]):
    """InputWidget representing collection inputs (e.g. list[T], tuple[T, ...], etc.).

    Given the specified type `item_type`, will automatically generate the appropriate
    widgets for each collection item.
    """

    def __init__(
        self,
        item_type: TypeAnnotation,
        container_type: Callable[[Iterable[T]], C],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a CollectionInputWidget.

        Arguments:
            item_type (type): The type of collection elements (i.e. the "T" of
                Collection[T]).
            container_type (Callable[[Iterable[T]], C]): A function that converts an
                iterable into the desired container type. (e.g. `list`, `tuple`).
            gui_meta (GuiMeta, optional): Metadata to further describe the widgets
                created. Defaults to `None`.
            parent (QObject, optional): The parent of this widget. Defaults to `None`.
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.item_type = item_type
        self.rows: list[CollectionInputRow[T]] = []
        self.container_type = container_type

        # layout setup...
        self.vlayout = QVBoxLayout()

        self.scroll_area = ExpandingScrollArea(widgetResizable=True, parent=self)
        self.scroll_layout = QVBoxLayout()
        self.scroll_area.setMinimumHeight(100)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_container = QWidget(parent=self.scroll_area)
        self.scroll_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_spacer = QSpacerItem(
            20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.scroll_layout.addSpacerItem(self.scroll_spacer)
        self.scroll_container.setLayout(self.scroll_layout)
        # self.scroll_area.setLayout(QVBoxLayout())
        # self.scroll_area.layout().addWidget(self.scroll_container)
        self.scroll_area.setWidget(self.scroll_container)
        self.vlayout.addWidget(self.scroll_area)

        self.spacer = QSpacerItem(
            20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.vlayout.addSpacerItem(self.spacer)

        self.add_button = QToolButton(parent=self)
        self.add_button.setCheckable(False)
        icon = QIcon()
        icon.addFile(':/icons/add.png', QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.add_button.setIcon(icon)
        self.add_button.setIconSize(QSize(16, 16))
        self.add_button.clicked.connect(lambda _: self.add_item())
        self.add_button.setToolTip('Add an item to the sequence')
        self.vlayout.addWidget(self.add_button)

        self.setLayout(self.vlayout)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

    def add_item(self, value: T | None = None):
        """Add an item to the sequence.

        If `value` is not `None` the new row's value will be assigned.
        """
        widget = create_input_widget(self.item_type)
        widget.setParent(self)
        new_row = CollectionInputRow(widget)
        new_row.removed.connect(self.remove_row)

        if value is not None:
            new_row.set_value(value)

        self.rows.append(new_row)
        # add widget + remove button to layout
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, new_row)
        # self.vlayout.insertWidget(self.vlayout.count() - 2, new_row)
        # self.adjustSize()
        # self.vlayout.addWidget(new_row)
        self.scroll_container.adjustSize()
        self.scroll_area.updateGeometry()
        self.updateGeometry()

    @Slot()
    def remove_row(self):
        """Remove a row from the sequence."""
        row: CollectionInputRow = self.sender()
        # self.vlayout.removeWidget(row)
        self.scroll_layout.removeWidget(row)
        self.rows.remove(row)
        row.deleteLater()
        # self.adjustSize()
        self.scroll_container.adjustSize()
        self.scroll_area.updateGeometry()
        self.updateGeometry()

    def clear(self):
        """Remove all rows from the widget."""
        while self.rows:
            row = self.rows.pop()
            # self.vlayout.removeWidget(row)
            self.scroll_layout.removeWidget(row)
            row.deleteLater()
        # self.adjustSize()

    @override
    def value(self) -> C:
        return self.container_type([row.value() for row in self.rows])

    @override
    def set_value(self, value: C):
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


class TupleInputWidget[*Ts](QGroupBox, InputWidget[tuple[*Ts]]):
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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.types = types
        self.widgets = []

        # layout setup...
        self.form_layout = QFormLayout()

        for annotation in types:
            unwrapped_annotation, gui_meta = unwrap_annotated(annotation)
            widget = create_input_widget(
                unwrapped_annotation, gui_meta=gui_meta, parent=self
            )
            self.widgets.append(widget)
            if gui_meta is not None and gui_meta.label is not None:
                self.form_layout.addRow(gui_meta.label, widget)
            else:
                self.form_layout.addRow(widget)

        self.setLayout(self.form_layout)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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
# Mapping Types
#
class MappingInputRow[K, V](QObject):
    """Widgets representing one key/value pair in a mapping."""

    removed = Signal()

    def __init__(
        self,
        key_widget: InputWidget[K],
        value_widget: InputWidget[V],
        parent: QObject | None = None,
    ):
        """Initialize a MappingInputRow."""
        super().__init__(parent)

        self.key_widget = key_widget
        self.value_widget = value_widget

        self.remove_button = QToolButton()
        self.remove_button.setToolTip('Remove this item')
        self.remove_button.clicked.connect(self.removed.emit)

        icon = QIcon()
        icon.addFile(
            ':/icons/remove.png',
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        self.remove_button.setIcon(icon)
        self.remove_button.setIconSize(QSize(16, 16))

    @property
    def key(self) -> K:
        """The value of this pair's key widget."""
        return self.key_widget.value()

    @property
    def value(self) -> V:
        """The value of this pair's value widget."""
        return self.value_widget.value()

    def set_value(self, key: K, value: V) -> None:
        """Set the value of this key/value pair."""
        self.key_widget.set_value(key)
        self.value_widget.set_value(value)

    @override
    def deleteLater(self) -> None:
        self.key_widget.deleteLater()
        self.value_widget.deleteLater()
        self.remove_button.deleteLater()
        super().deleteLater()


class MappingInputWidget[K, V, M: Mapping[K, V]](QGroupBox, InputWidget[M]):
    """InputWidget representing mapping inputs (i.e. dict[K, V]).

    Given the specified types `key_type` and `value_type` will automatically generate
    the appropriate widgets for each key/value pair.
    """

    def __init__(
        self,
        key_type: TypeAnnotation,
        value_type: TypeAnnotation,
        container_type: Callable[[Iterable[tuple[K, V]]], M],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a MappingInputWidget.

        Arguments:
            key_type (type): The type of the map's keys.
            value_type (type): The type of the map's values.
            container_type (Callable[[Iterable[tuple[K, V]]], M]): A function that
                converts an iterable of tuples of key/value pairs into the desired
                mapping type. (e.g. `dict`)
            gui_meta (GuiMeta, optional): Metadata to further describe the widgets
                created. Defaults to `None`.
            parent (QObject, optional): The parent of this widget. Defaults to `None`.
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.key_type = key_type
        self.value_type = value_type
        self.container_type = container_type
        self.rows: list[MappingInputRow[K, V]] = []

        # layout setup...
        self.vlayout = QVBoxLayout()

        self.scroll_area = ExpandingScrollArea(widgetResizable=True, parent=self)
        self.grid_layout = QGridLayout()
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)
        self.grid_layout.setColumnStretch(2, 0)
        self.scroll_area.setMinimumHeight(100)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll_container = QWidget(parent=self.scroll_area)
        self.scroll_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.key_label = QLabel('Key', parent=self.scroll_container)
        self.grid_layout.addWidget(self.key_label, 0, 0)
        self.value_label = QLabel('Value', parent=self.scroll_container)
        self.grid_layout.addWidget(self.value_label, 0, 1)
        self.scroll_container.setLayout(self.grid_layout)

        # self.scroll_area.setLayout(QVBoxLayout())
        # self.scroll_area.layout().addWidget(self.scroll_container)
        self.scroll_area.setWidget(self.scroll_container)
        self.vlayout.addWidget(self.scroll_area)

        self.spacer = QSpacerItem(
            20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.vlayout.addSpacerItem(self.spacer)

        self.add_button = QToolButton(parent=self)
        self.add_button.setCheckable(False)
        icon = QIcon()
        icon.addFile(':/icons/add.png', QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.add_button.setIcon(icon)
        self.add_button.setIconSize(QSize(16, 16))
        self.add_button.clicked.connect(lambda _: self.add_item())
        self.add_button.setToolTip('Add an item to the sequence')
        self.vlayout.addWidget(self.add_button)

        self.setLayout(self.vlayout)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

    def add_item(self, key: K | None = None, value: V | None = None):
        """Add an item to the sequence.

        If `value` is not `None` the new row's value will be assigned.
        """
        key_widget = create_input_widget(
            self.key_type,
            parent=self.scroll_container,
        )
        value_widget = create_input_widget(
            self.value_type,
            parent=self.scroll_container,
        )

        row = MappingInputRow(key_widget, value_widget, parent=self.scroll_container)
        row.removed.connect(lambda row=row: self.remove_row(row))
        self.rows.append(row)
        row_idx = len(self.rows)
        self.grid_layout.addWidget(row.key_widget, row_idx, 0)
        self.grid_layout.addWidget(row.value_widget, row_idx, 1)
        self.grid_layout.addWidget(row.remove_button, row_idx, 2)

        if key is not None:
            row.key_widget.set_value(key)
        if value is not None:
            row.value_widget.set_value(value)

        self.scroll_container.adjustSize()
        self.scroll_area.updateGeometry()
        self.updateGeometry()

    @Slot()
    def remove_row(
        self,
        row: MappingInputRow[K, V],
    ) -> None:
        """Remove a row from the map."""
        self.rows.remove(row)

        self.grid_layout.removeWidget(row.key_widget)
        self.grid_layout.removeWidget(row.value_widget)
        self.grid_layout.removeWidget(row.remove_button)

        row.deleteLater()

        self._reposition_rows()

        self.scroll_container.adjustSize()
        self.scroll_area.updateGeometry()
        self.updateGeometry()

    def _reposition_rows(self) -> None:
        for grid_row, row in enumerate(self.rows, start=1):
            self.grid_layout.addWidget(
                row.key_widget,
                grid_row,
                0,
            )
            self.grid_layout.addWidget(
                row.value_widget,
                grid_row,
                1,
            )
            self.grid_layout.addWidget(
                row.remove_button,
                grid_row,
                2,
            )

    def clear(self) -> None:
        """Remove all rows from the widget."""
        for row in self.rows:
            self.grid_layout.removeWidget(row.key_widget)
            self.grid_layout.removeWidget(row.value_widget)
            self.grid_layout.removeWidget(row.remove_button)
            row.deleteLater()

        self.rows.clear()

        self.scroll_container.adjustSize()
        self.scroll_area.updateGeometry()
        self.updateGeometry()

    @override
    def value(self) -> M:
        items: list[tuple[K, V]] = []
        keys: list[K] = []

        for row in self.rows:
            key = row.key

            if key in keys:
                raise ValueError(f'Duplicate mapping key: {key!r}')

            keys.append(key)
            items.append((key, row.value))

        return self.container_type(items)

    @override
    def set_value(self, value: M) -> None:
        if not isinstance(value, Mapping):
            raise TypeError(f'Expected a mapping, got {type(value)!r}')

        if not all(
            check_type(key, self.key_type) and check_type(item, self.value_type)
            for key, item in value.items()
        ):
            raise TypeError(
                f'Mapping does not match {self.key_type!r} -> {self.value_type!r}'
            )

        self.clear()

        for key, item in value.items():
            self.add_item(key, item)


#
# Union Types
#


class UnionInputWidget[T](QGroupBox, InputWidget[T]):
    """Widget representing inputs of union type (e.g. str | int)."""

    def __init__(
        self,
        types: tuple[TypeAnnotation, ...],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize a UnionInputWidget."""
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.types = types

        self.grid_layout = QGridLayout()

        self.type_label = QLabel('Input type:', parent=self)
        self.grid_layout.addWidget(self.type_label, 0, 0)

        self.type_combo = QComboBox(parent=self)
        self.type_combo.setPlaceholderText('Select object type...')
        self.grid_layout.addWidget(self.type_combo, 0, 1)

        self.stack = ResizingStackedWidget(parent=self)
        self.stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        for annotation in types:
            self.type_combo.addItem(convert_type_to_string(annotation))
            self.stack.addWidget(create_input_widget(annotation))
        self.type_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        # self.stack.currentChanged.connect(self.stack.adjustSize)
        # self.stack.currentChanged.connect(self.adjustSize)
        self.type_combo.setCurrentIndex(0)
        self.grid_layout.addWidget(self.stack, 1, 0, 1, 2)

        self.setLayout(self.grid_layout)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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


class OptionalInputWidget[T](QGroupBox, InputWidget[T]):
    """InputWidget that handles optional inputs."""

    def __init__(
        self,
        type_: type[T],
        gui_meta: GuiMeta | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize an OptionalInputWidget."""
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.item_type = type_

        self.vlayout = QVBoxLayout()
        self.checkbox = QCheckBox('Specify value?', parent=self)
        self.vlayout.addWidget(self.checkbox)

        self.widget = create_input_widget(type_)
        self.vlayout.addWidget(self.widget)

        self.checkbox.toggled.connect(self.widget.setEnabled)
        self.checkbox.setChecked(True)  # Default to enabled
        self.widget.setEnabled(True)

        self.setLayout(self.vlayout)

        if gui_meta is not None and gui_meta.tooltip is not None:
            self.setToolTip(gui_meta.tooltip)

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


def create_input_widget[T](  # noqa: PLR0911, PLR0912
    annotation: type[T],
    *,
    gui_meta: GuiMeta | None = None,
    parent: QWidget | None = None,
) -> InputWidget[T]:
    """Recursively create a widget appropriate for a type annotation."""
    # Annotated[T, ...]
    annotation, annotation_meta = unwrap_annotated(annotation)

    if annotation_meta is not None:
        gui_meta = annotation_meta

    # Optional[T]
    if is_optional(annotation):
        inner_type = get_optional_type(annotation)

        return OptionalInputWidget(
            inner_type,
            gui_meta=gui_meta,
            parent=parent,
        )

    origin = get_origin(annotation)

    # dict[K, V], Mapping[K, V]
    if origin in (dict, Mapping):
        args = get_args(annotation)

        if len(args) != 2:  # noqa: PLR2004
            raise TypeError(
                f'Expected {convert_type_to_string(origin)}[K, V], got {annotation!r}'
            )

        key_type, value_type = args

        return cast(
            InputWidget[T],
            MappingInputWidget(
                key_type,
                value_type,
                dict,
                gui_meta=gui_meta,
                parent=parent,
            ),
        )

    # list[T], Sequence[T], Collection[T], set[T], NDArray[T]...
    if origin in (list, Sequence, Collection, set, npt.NDArray):
        args = get_args(annotation)

        if len(args) != 1:
            raise TypeError(
                f'Expected {convert_type_to_string(origin)}[T], got {annotation!r}'
            )

        if origin in (Sequence, Collection):
            container_type = list
        elif origin is npt.NDArray:
            container_type = np.asarray
        else:
            container_type = origin

        return cast(
            InputWidget[T],
            CollectionInputWidget(
                args[0],
                container_type,
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
                CollectionInputWidget(
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

    # Literal[v1, v2, ...]
    if origin is Literal:
        values = get_args(annotation)

        return cast(
            InputWidget[T],
            LiteralInputWidget(
                values,
                gui_meta=gui_meta,
                parent=parent,
            ),
        )

    # Enum subclass
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if gui_meta is not None and gui_meta.multi_input:
            return MultiEnumInputWidget(
                annotation,
                gui_meta=gui_meta,
                parent=parent,
            )
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


# TODO: Make a function for calling the DataRoutine with all of the args
# This needs to account for the GuiArg.kind.
def gui_arg_to_widget[T](
    gui_arg: GuiArg[T], parent: QWidget | None = None
) -> InputWidget[T]:
    """Create an appropriate widget for the gui argument."""
    match gui_arg.kind:
        # *args: T
        case inspect.Parameter.VAR_POSITIONAL:
            widget = CollectionInputWidget(
                gui_arg.annotation,
                tuple,
                gui_meta=gui_arg.metadata,
                parent=parent,
            )
        # **kwargs: T
        case inspect.Parameter.VAR_KEYWORD:
            # TODO: Make MappingInputWidget[K, V]
            widget = MappingInputWidget(
                str,
                gui_arg.annotation,
                dict,
                gui_meta=gui_arg.metadata,
                parent=parent,
            )
        # param: T
        case _:
            widget = create_input_widget(
                gui_arg.annotation,
                gui_meta=gui_arg.metadata,
                parent=parent,
            )
    if not is_empty(gui_arg.default):
        widget.set_value(gui_arg.default)
    return widget


# ruff: enable[ARG002]

if __name__ == '__main__':
    # ruff: disable[D101,D102,D107]

    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton

    # import pdb
    # from rfsocinterface.core.utils import (
    #     get_parameter_descriptions,
    #     get_inherited_parameter_description,
    # )
    # from rfsocinterface.core.data.routines import get_gui_args
    # from rfsocinterface.analysis import ComputeNoisePSD
    # params = get_parameter_descriptions(ComputeNoisePSD.__init__)
    # args = get_gui_args(ComputeNoisePSD)
    # pdb.set_trace()
    # exit()

    class ExEnum(Enum):
        ONE = 1
        TWO = 2
        THREE = 3

    ANNOTATION_NAMESPACE = {
        'int': int,
        'float': float,
        'str': str,
        'bool': bool,
        'list': list,
        'tuple': tuple,
        'set': set,
        'dict': dict,
        'Mapping': Mapping,
        'Sequence': Sequence,
        'Collection': Collection,
        'NDArray': npt.NDArray,
        'Path': Path,
        'None': None,
        'Literal': Literal,
        'ExEnum': ExEnum,
        'Annotated': Annotated,
        'GuiMeta': GuiMeta,
    }

    def parse_annotation(text: str):
        """Parse a string form of a type annotation."""
        return eval(text, {'__builtins__': {}}, ANNOTATION_NAMESPACE)

    app = QApplication()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()

            self.container = QWidget(parent=self)
            self.vlayout = QVBoxLayout()

            self.line_edit = QLineEdit(parent=self.container)
            self.vlayout.addWidget(self.line_edit)

            self.push_button = QPushButton('Generate widget', parent=self.container)
            self.push_button.clicked.connect(self.parse_annotation)
            self.vlayout.addWidget(self.push_button)

            self.value_label = QLabel('Value:', parent=self.container)
            self.vlayout.addWidget(self.value_label)

            self.value_button = QPushButton('Get current value', parent=self.container)
            self.value_button.clicked.connect(self.display_value)
            self.vlayout.addWidget(self.value_button)

            self.widget = None

            self.container.setLayout(self.vlayout)
            self.setCentralWidget(self.container)

        def parse_annotation(self):
            if self.line_edit.text():
                annotation = parse_annotation(self.line_edit.text())
                self.create_widget(annotation)

        def create_widget(self, annotation: TypeAnnotation):
            new_widget = create_input_widget(annotation, parent=self.container)
            if self.widget is not None:
                self.vlayout.removeWidget(self.widget)
                self.widget.deleteLater()
            self.widget = new_widget
            self.vlayout.addWidget(new_widget, alignment=Qt.AlignmentFlag.AlignTop)
            # self.adjustSize()

        def set_widget(self, new_widget: InputWidget):
            if self.widget is not None:
                self.vlayout.removeWidget(self.widget)
                self.widget.deleteLater()
            self.widget = new_widget
            self.vlayout.addWidget(new_widget, alignment=Qt.AlignmentFlag.AlignTop)

        def display_value(self):
            if self.widget is not None:
                val = self.widget.value()
                self.value_label.setText(f'Value: {val}')

    # ruff: enable[D101,D102,D107]
    w = MainWindow()
    w.show()
    # w.create_widget(ExEnum | Annotated[ExEnum, GuiMeta(multi_input=True)])
    # from rfsocinterface.core.data import ROUTINE_GUI_ARGS
    # from rfsocinterface.analysis import ComputeNoisePSD
    # w.set_widget(gui_arg_to_widget(ROUTINE_GUI_ARGS['ComputeNoisePSD'][0], parent=w))

    app.exec()
