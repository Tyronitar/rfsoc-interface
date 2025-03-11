from rfsocinterface.core.utils import ArgumentType


from PySide6.QtWidgets import QFormLayout, QWidget, QCheckBox


from typing import Any, Callable


class FunctionWidget(QWidget):
    """Class for generalizing a function and its arguments for a Qt GUI."""

    def __init__(self, fn: Callable, args: list[tuple]=[], parent=None):
        super().__init__(parent=parent)
        self.fn = fn
        self.args: list[tuple[str, ArgumentType]] = []
        self.form_layout = QFormLayout(parent=self)
        for arg in args:
            self.add_argument(*args)
        self.setLayout(self.layout)

    def add_argument(self, label: str, arg_type: ArgumentType, *args, **kwargs):
        self.args.append((label, arg_type))
        if arg_type == ArgumentType.BOOL:
            widget = arg_type.widget(label, *args, parent=self, **kwargs)
            self.form_layout.addRow(widget)  # QCheckBox has its label built-in
        else:
            widget = arg_type.widget(*args, parent=self, **kwargs)
            self.form_layout.addRow(label, widget)

    def get_inputs(self) -> list[Any]:
        values = []
        for i, (_, arg_type) in enumerate(self.args):
            input_widget = self.form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            values.append(arg_type.access_function()(input_widget))
        return values

    def call_function(self):
        values = self.get_inputs()
        self.fn(*values)