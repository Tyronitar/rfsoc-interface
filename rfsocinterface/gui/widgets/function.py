"""Widgets for representing functions and their arguments."""

import inspect
from collections.abc import Callable, Sequence
from typing import Any, Concatenate, overload, override

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.utils import (
    GuiArg,
    get_gui_args,
)
from rfsocinterface.gui.widgets.drag_and_drop import (
    ClickableDragItem,
    ClickableDragWidget,
    ClickableMultiSectionDragWidget,
)
from rfsocinterface.gui.widgets.function_inputs import (
    GuiArgWidget,
    gui_arg_to_widget,
)
from rfsocinterface.gui.widgets.scroll_area import ExpandingScrollArea
from rfsocinterface.gui.widgets.utils import ArgumentType


class FunctionWidget[**P, **Q, R](QWidget):
    """Class for generalizing a function and its arguments for a Qt GUI."""

    def __init__(
        self,
        fn: Callable[P, R],
        args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]
        | None = None,
        parent=None,
    ):
        """Initialize a FunctionWidget."""
        if args is None:
            args = []
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
        for arg, kwargs in args:
            self.add_argument(*arg, **kwargs)

        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

    def add_argument(
        self,
        label: str,
        arg_types: ArgumentType | tuple[ArgumentType],
        *args: Q.args,
        **kwargs: Q.kwargs,
    ):
        """Add an argument to the widget."""
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
            widget = self.arg_to_widget(
                label,
                arg_type,
                *args,
                default_val=default_vals[i] if has_default else None,
                **kwargs,
            )
            new_row.addWidget(widget)
        if any(arg_type != ArgumentType.BOOL for arg_type in arg_types):
            self.form_layout.addRow(label + ':', new_row)
        else:
            self.form_layout.addRow(new_row)

    def arg_to_widget(
        self,
        label: str,
        arg_type: ArgumentType,
        *args: Q.args,
        default_val=None,
        **kwargs: Q.kwargs,
    ) -> QWidget:
        """Create the appropriate widget for the desired argument."""
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
        """Get the inputs for the function from the GUI."""
        values = []
        for i, (_, arg_types) in enumerate(self.args):
            if len(arg_types) > 1:
                # If there are multiple arguments, get the values from each widget
                this_value = []
                hlayout: QHBoxLayout = self.form_layout.itemAt(
                    i, QFormLayout.ItemRole.FieldRole
                )
                for j, arg_type in enumerate(arg_types):
                    # Get every widget in the hlayout
                    input_widget = hlayout.itemAt(j).widget()
                    this_value.append(arg_type.access_function()(input_widget))
                values.append(tuple(this_value))
            else:
                hlayout: QHBoxLayout = self.form_layout.itemAt(
                    i, QFormLayout.ItemRole.FieldRole
                )
                input_widget = hlayout.itemAt(0).widget()
                values.append(arg_types[0].access_function()(input_widget))
        return values

    def call_function(self):
        """Call the function represented by this widget."""
        values = self.get_inputs()
        return self.fn(*values)


class FunctionDragItem[**P, **Q, R](ClickableDragItem):
    """Drag and drop item representing a function."""

    def __init__(
        self,
        fn: Callable[P, R],
        args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]
        | None = None,
        label: str | None = None,
        *init_args,
        **init_kwargs,
    ):
        """Initialize a FunctionDragItem."""
        if args is None:
            args = []
        if not label:
            label = fn.__name__
        super().__init__(label, *init_args, **init_kwargs)
        self.fn = fn
        self.args: list[
            tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]
        ] = args
        self.func_widget = FunctionWidget(self.fn, self.args, parent=self.parent())


class DragFunctionWidget(QWidget):
    """A orderable list of functions with a side panel for entering arguments."""

    active_item_changed = Signal(QWidget)

    def __init__(self, parent=None):
        """Initialize a DragFunctionWidget."""
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

        self.drag.active_item_changed.connect(self.active_item_changed.emit)

    @property
    def active_item(self) -> FunctionDragItem | None:
        """Return the currently selected item."""
        return self.drag.active_item

    @overload
    def add_item(self, item: FunctionDragItem) -> FunctionDragItem:
        pass

    @overload
    def add_item[**Q](
        self,
        label: str,
        fn: Callable,
        args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]
        | None = None,
    ) -> FunctionDragItem:
        pass

    def add_item(self, *data):
        """Add an item to the list."""
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

    @overload
    def insert_item(self, index: int, item: FunctionDragItem) -> FunctionDragItem:
        pass

    @overload
    def insert_item[**Q](
        self,
        index: int,
        label: str,
        fn: Callable,
        args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]
        | None = None,
    ) -> FunctionDragItem:
        pass

    def insert_item(self, index: int, *data):
        """Insert an item to the list."""
        if not isinstance(data[0], FunctionDragItem):
            label, fn, args = data
            item = FunctionDragItem(fn, args, label=label, parent=self)
            item.set_data(fn.__name__)
        else:
            item = data[0]
        self.drag.insert_item(index, item)
        item.clicked.connect(self.display_args)
        self.func_container.addWidget(item.func_widget)
        self.func_container.insertWidget()
        return item

    def clear(self):
        """Clear all items from the list."""
        for item in self.drag.items():
            self.drag.remove_item(item)
            self.func_container.removeWidget(item.func_widget)
        self.func_container.setCurrentIndex(0)

    def remove_item(self, item: FunctionDragItem):
        """Remove an item from the list."""
        self.drag.remove_item(item)
        self.func_container.removeWidget(item.func_widget)
        item.deleteLater()
        self.func_container.setCurrentIndex(0)

    def items(self) -> list[FunctionDragItem]:
        """Return a list of all items."""
        return self.drag.items()

    @Slot()
    def display_args(self):
        """Show the arguments for the selected function in the side panel."""
        item: FunctionDragItem = self.sender()
        self.func_container.setCurrentIndex(
            self.func_container.indexOf(item.func_widget)
        )

    @override
    def mousePressEvent(self, event: QMouseEvent):
        child = self.childAt(event.position())
        # Clicking off of the list items or parameters should deselect
        if child is None or child in (self.drop_container, self.drag):
            self.drag.set_active_item(None)
            self.func_container.setCurrentIndex(0)
        return super().mousePressEvent(event)


class MultiSectionDragFunctionWidget(QWidget):
    """DragFunctionWidget that has multiple sections."""

    order_changed = Signal(list, list)

    def __init__(self, parent=None):
        """Initialize a MultiSectionDragFunctionWidget."""
        super().__init__(parent=parent)
        self.drag = ClickableMultiSectionDragWidget(orientation=Qt.Orientation.Vertical)
        self.drag.order_changed.connect(self.order_changed.emit)
        # self.drag.order_changed.connect(lambda _, item_data: print(item_data))

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
        """Return the currently selected item."""
        return self.drag.active_item

    def add_section(self, label: str):
        """Add a new section to the widget."""
        self.drag.add_section(label)

    @overload
    def add_item(self, i_section: int, item: FunctionDragItem) -> FunctionDragItem:
        pass

    @overload
    def add_item[**Q](
        self,
        i_section: int,
        label: str,
        fn: Callable,
        args: list[tuple[tuple[Concatenate[str, tuple[ArgumentType, ...], Q]], dict]]
        | None = None,
    ) -> FunctionDragItem:
        pass

    def add_item(self, *data):
        """Add an item to the list."""
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
        """Clear all items from the list."""
        for i_sec, sec in enumerate(self.drag.sections):
            for item in sec.items():
                self.drag.remove_item(i_sec, item)
                self.func_container.removeWidget(item.func_widget)
        self.func_container.setCurrentIndex(0)

    def remove_item(self, i_section: int, item: FunctionDragItem):
        """Remove an item from the list."""
        self.drag.remove_item(i_section, item)
        self.func_container.removeWidget(item.func_widget)
        item.deleteLater()
        self.func_container.setCurrentIndex(0)

    def items(self) -> list[FunctionDragItem]:
        """Return a list of all items."""
        return self.drag.items()

    def items_separated(self) -> list[list[FunctionDragItem]]:
        """Return all items separated by section."""
        return self.drag.items_separated()

    def item_data_separated(self) -> list[list]:
        """Return the data of all items separated by section."""
        return self.drag.get_item_data_separated()

    @Slot()
    def display_args(self):
        """Show the arguments for the selected function in the side panel."""
        item: FunctionDragItem = self.sender()
        self.func_container.setCurrentIndex(
            self.func_container.indexOf(item.func_widget)
        )

    @override
    def mousePressEvent(self, event: QMouseEvent):
        child = self.childAt(event.position())
        # Clicking off of the list items or parameters should deselect
        if child is None or child in (self.drop_container, self.drag):
            self.drag.set_active_item(-1, None)
            self.func_container.setCurrentIndex(0)
        return super().mousePressEvent(event)


class CallableWidget(QWidget):
    """Class for generalizing a callable and its arguments for a Qt GUI."""

    def __init__(
        self,
        target: Callable[..., Any],
        args: Sequence[GuiArg] | None = None,
        use_defaults: bool = True,
        parent=None,
    ):
        """Initialize a FunctionWidget."""
        super().__init__(parent=parent)
        self.target_fn = target
        self.signature = inspect.signature(target)
        if args is None:
            args = get_gui_args(target, use_defaults=use_defaults)
        self.widgets: list[GuiArgWidget] = []

        self.scroll_area = ExpandingScrollArea(widgetResizable=True, parent=self)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.container = QWidget()
        self.container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setWidgetResizable(True)
        self.form_layout = QFormLayout(parent=self.container)

        for arg in args:
            self.add_argument(arg)

        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll_area)

    def add_argument(
        self,
        arg: GuiArg,
    ):
        """Add an argument to the widget."""
        new_widget = gui_arg_to_widget(arg, parent=self.container)
        gui_meta = arg.metadata
        if gui_meta is not None and gui_meta.label is not None:
            label_text = gui_meta.label
        else:
            label_text = f'{arg.name}:'
        self.widgets.append(GuiArgWidget(arg=arg, widget=new_widget))
        self.form_layout.addRow(
            label_text,
            new_widget,
        )
        label = self.form_layout.labelForField(new_widget)
        label.setToolTip(new_widget.toolTip())

    def get_inputs(self) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Get the inputs of the target function in the proper format."""
        args: list[Any] = []
        kwargs: dict[str, Any] = {}

        has_var_positional = any(
            item.arg.kind is inspect.Parameter.VAR_POSITIONAL for item in self.widgets
        )

        for item in self.widgets:
            gui_arg = item.arg
            value = item.value()

            match gui_arg.kind:
                case inspect.Parameter.POSITIONAL_ONLY:
                    args.append(value)

                case inspect.Parameter.POSITIONAL_OR_KEYWORD:
                    if has_var_positional:
                        args.append(value)
                    else:
                        kwargs[gui_arg.name] = value

                case inspect.Parameter.VAR_POSITIONAL:
                    args.extend(value)

                case inspect.Parameter.KEYWORD_ONLY:
                    kwargs[gui_arg.name] = value

                case inspect.Parameter.VAR_KEYWORD:
                    kwargs.update(value)

                case inspect.Parameter.VAR_KEYWORD:
                    duplicates = kwargs.keys() & value.keys()

                    if duplicates:
                        raise ValueError(
                            "Variable keyword arguments conflict with explicit "
                            f"arguments: {', '.join(sorted(duplicates))}"
                        )

                    kwargs.update(value)

        args = tuple(args)
        self.signature.bind(*args, **kwargs)
        return args, kwargs

    def call(self) -> Any:
        """Call the function with the given inputs."""
        args, kwargs = self.get_inputs()
        return self.target_fn(*args, **kwargs)


class CallableDragItem[**P, **Q, R](ClickableDragItem):
    """Drag and drop item representing a callable."""

    def __init__(
        self,
        target: Callable[..., Any],
        *init_args,
        label: str | None = None,
        args: Sequence[GuiArg] | None = None,
        use_defaults: bool = True,
        parent=None,
        **init_kwargs,
    ):
        """Initialize a FunctionDragItem."""
        if not label:
            label = target.__name__
        super().__init__(label, *init_args, parent=parent, **init_kwargs)
        self.widget = CallableWidget(
            target, args=args, use_defaults=use_defaults, parent=parent
        )


class CallableListWidget(QWidget):
    """A orderable list of callables with a side panel for entering arguments."""

    active_item_changed = Signal(QWidget)

    def __init__(
        self, parent=None, orientation: Qt.Orientation = Qt.Orientation.Vertical
    ):
        """Initialize a DragFunctionWidget."""
        super().__init__(parent=parent)
        self.drag = ClickableDragWidget(orientation=orientation)

        hlayout = QHBoxLayout()

        self.drop_container = QWidget(parent=self)
        drop_vlayout = QVBoxLayout()
        drop_vlayout.addStretch(1)
        drop_vlayout.addWidget(self.drag)
        drop_vlayout.addStretch(1)
        self.drop_container.setLayout(drop_vlayout)
        hlayout.addWidget(self.drop_container)

        hlayout.addStretch(1)

        self.args_container = QStackedWidget(parent=self)
        self.args_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        placheolder_widget = QWidget(parent=self)
        self.args_container.addWidget(placheolder_widget)
        hlayout.addWidget(self.args_container)

        self.setLayout(hlayout)

        self.drag.active_item_changed.connect(self.active_item_changed.emit)

    @property
    def active_item(self) -> CallableDragItem | None:
        """Return the currently selected item."""
        return self.drag.active_item

    def add_item(
        self,
        item: CallableDragItem,
    ):
        """Add an item to the list."""
        self.insert_item(-1, item)

    def insert_item(
        self,
        idx: int,
        item: CallableDragItem,
    ):
        """Inset an item in the list at the specified index."""
        self.drag.insert_item(idx, item)
        item.clicked.connect(self.display_args)
        self.args_container.insertWidget(idx, item.widget)

    def add_callable(
        self,
        target: Callable[..., Any],
        *init_args,
        label: str | None = None,
        args: Sequence[GuiArg] | None = None,
        use_defaults: bool = True,
        **init_kwargs,
    ):
        """Create an item for the callable and add it to the list."""
        self.insert_callable(
            -1,
            target,
            *init_args,
            label=label,
            args=args,
            use_defaults=use_defaults,
            **init_kwargs,
        )

    def insert_callable(
        self,
        idx: int,
        target: Callable[..., Any],
        *init_args,
        label: str | None = None,
        args: Sequence[GuiArg] | None = None,
        use_defaults: bool = True,
        **init_kwargs,
    ):
        """Create an item for the callable and add it to the list."""
        item = CallableDragItem(
            target,
            *init_args,
            label=label or target.__name__,
            args=args,
            use_defaults=use_defaults,
            parent=self,
            **init_kwargs,
        )
        self.insert_item(idx, item)

    def clear(self):
        """Clear all items from the list."""
        item: CallableDragItem
        for item in self.drag.items():
            self.drag.remove_item(item)
            self.args_container.removeWidget(item.widget)
        self.args_container.setCurrentIndex(0)

    def remove_item(self, item: CallableDragItem):
        """Remove an item from the list."""
        self.drag.remove_item(item)
        self.args_container.removeWidget(item.widget)
        item.deleteLater()
        self.args_container.setCurrentIndex(0)

    def items(self) -> list[CallableDragItem]:
        """Return a list of all items."""
        return self.drag.items()

    @Slot()
    def display_args(self):
        """Show the arguments for the selected function in the side panel."""
        item: CallableDragItem = self.sender()
        idx = self.items().index(item) + 1
        self.args_container.setCurrentIndex(idx)
        # self.args_container.setCurrentIndex(
        #     self.args_container.indexOf(item.widget)
        # )

    @override
    def mousePressEvent(self, event: QMouseEvent):
        child = self.childAt(event.position())
        # Clicking off of the list items or parameters should deselect
        if child is None or child in (self.drop_container, self.drag):
            self.drag.set_active_item(None)
            self.args_container.setCurrentIndex(0)
        return super().mousePressEvent(event)


if __name__ == '__main__':
    # ruff: disable[D101,D102,D107]
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QMessageBox,
        QPushButton,
    )

    from rfsocinterface.core.data import (
        CleanTOD,
        DataRoutine,
        HighPassFilter,
        LowPassFilter,
        RemoveElectronicsNoise,
    )

    app = QApplication()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()

            self.container = QWidget(parent=self)
            self.vlayout = QVBoxLayout()

            self.callables_widget = CallableListWidget(parent=self)
            self.vlayout.addWidget(self.callables_widget)

            self.parse_push_button = QPushButton('Parse inputs', parent=self.container)
            self.parse_push_button.clicked.connect(self.parse_inputs)
            self.vlayout.addWidget(self.parse_push_button)

            self.call_push_button = QPushButton(
                'Call function(s)', parent=self.container
            )
            self.call_push_button.clicked.connect(self.call)
            self.vlayout.addWidget(self.call_push_button)

            self.container.setLayout(self.vlayout)
            self.setCentralWidget(self.container)

        def add_item(self, target: Callable):
            self.callables_widget.add_callable(target)

        def parse_inputs(self):
            inputs = [
                item.widget.get_inputs() for item in self.callables_widget.items()
            ]
            msg = QMessageBox(parent=self)
            strings = tuple(
                f'(Args: {input_[0]}\nKwargs: {input_[1]})\n' for input_ in inputs
            )
            msg.setText('\n'.join(strings))
            msg.exec()

        def call(self):
            outputs = []
            for item in self.callables_widget.items():
                res = item.widget.call()
                if isinstance(res, DataRoutine):
                    outputs.append(f'{res.__class__.__name__}({res.params})')
                else:
                    outputs.append(res)

            msg = QMessageBox(parent=self)
            msg.setText('\n'.join(outputs))
            msg.exec()

    w = MainWindow()
    w.add_item(RemoveElectronicsNoise)
    w.add_item(HighPassFilter)
    w.add_item(LowPassFilter)
    w.add_item(CleanTOD)
    w.show()

    # ruff: enable[D101,D102,D107]

    app.exec()
