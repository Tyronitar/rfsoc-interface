"""Labels with Icons at the front."""

import qtawesome as qta
from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget

ERROR_ICON_CODE = 'fa5s.exclamation-circle'


class IconLabel(QWidget):
    """A text label with an icon in the front."""
    IconSize = QSize(16, 16)
    HorizontalSpacing = 2

    def __init__(
        self,
        qta_id: str,
        text: str,
        color: str = 'black',
        final_stretch: bool = True,
        wrap_text: bool = False,
        parent: QWidget | None = None,
    ):
        """Initialize an IconLabel.

        Arguments:
            qta_id (str): The icon ID in qtawesome.
            text (str): The text to display.
            color (str, optional): What color to display the icon and text in. Defautls
                to 'black'.
            final_stretch (bool, optional): Whether to add stretch to the end of the
                widget's layout. Defaults to True.
            wrap_text (bool, optional): whether to wrap the text. Defaults to False.
            parent (QWidget, optional): The parent widget. Defautls to None.
        """
        super().__init__(parent=parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.icon = QLabel()
        self.set_icon(qta_id, color=color)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.icon)
        layout.addSpacing(self.HorizontalSpacing)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.label.setWordWrap(wrap_text)
        self.min_width = self.label.fontMetrics().horizontalAdvance(self.label.text())
        self.set_color(color)
        layout.addWidget(self.label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if final_stretch:
            layout.addStretch()

    def set_icon(self, icon_id: str, color: str = 'black'):
        """Set the icon to a new qtawesome ID."""
        self.icon.setPixmap(qta.icon(icon_id, color=color).pixmap(self.IconSize))

    def set_color(self, color: str):
        """Set the color for the icon and text."""
        self.label.setStyleSheet(f'color: {color};')

    def set_text(self, text: str):
        """Set the text of the label."""
        self.label.setText(text)


def highlight_error_line_edit(line_edit: QLineEdit):
    """Set a QLineEdit to show in red, indicating an error."""
    line_edit.setStyleSheet(
        """QLineEdit {border-style: solid; border: 2px solid red; color: red;
        border-radius: 5px;
        background-color: #fff1f1;};
        """
    )


def verify_line_edit(
    source: QLineEdit,
    error_label: IconLabel | None = None,
    toggle_enabled: list[QWidget] | None = None,
) -> tuple[bool, bool]:
    """Verfiy the contents of a lineEdit are good and indicate errors if needed."""
    if toggle_enabled is None:
        toggle_enabled = []
    toggled = False
    if not source.hasAcceptableInput():
        # Highlight in red
        highlight_error_line_edit(source)
        for widget in toggle_enabled:
            widget.setEnabled(False)

        # Show the error_label
        if error_label is not None:
            toggled = error_label.isHidden()
            error_label.setVisible(True)
        QCoreApplication.processEvents()
        return False, toggled
    # Value is valid
    # Remove the error label since the value is valid
    if error_label is not None:
        toggled = error_label.isVisible()
        error_label.setVisible(False)
    QCoreApplication.processEvents()

    source.setStyleSheet('')
    for widget in toggle_enabled:
        widget.setEnabled(True)

    return True, toggled
