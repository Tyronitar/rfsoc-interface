"""Variations of the QComboBox."""
from typing import override

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPalette, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QStylePainter


class CheckableComboBox(QComboBox):
    """A combobox that allows for checkable items.

    Code adapted from: https://stackoverflow.com/a/22775990 and
    https://stackoverflow.com/a/35831986.
    """

    def __init__(self, title: str = '', parent=None):
        """Initialize a CheckableComboBox."""
        super().__init__(parent)
        self.set_title(title)
        self._default_title = title
        self.view().pressed.connect(self.handle_item_pressed)
        self.view().doubleClicked.connect(self.handle_item_pressed)
        self.setModel(QStandardItemModel(self))
        self._changed = False

    def checked_indices(self) -> list[int]:
        """Return the indices of checked items."""
        return [
            i
            for i in range(self.count())
            if self.model().item(i, self.modelColumn()).checkState()
            == Qt.CheckState.Checked
        ]

    def deselect_all(self):
        """Uncheck all items."""
        for i in range(self.count()):
            self.set_item_checked(i, False)
        self.update_checked_items()

    def select_all(self):
        """Check all items."""
        for i in range(self.count()):
            self.set_item_checked(i, True)
        self.update_checked_items()

    def handle_item_pressed(self, index):
        """Helper method for handling items being clicked."""
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)
        self.update_checked_items()
        self._changed = True

    @override
    def hidePopup(self):
        if not self._changed:
            super().hidePopup()
        self._changed = False

    def item_checked(self, index: int):
        """Return whether the item is checked."""
        item = self.model().item(index, self.modelColumn())
        return item.checkState() == Qt.CheckState.Checked

    def set_item_checked(self, index, checked=True):
        """Set the check state of the item at the specified index."""
        item = self.model().item(index, self.modelColumn())
        if checked:
            item.setCheckState(Qt.CheckState.Checked)
        else:
            item.setCheckState(Qt.CheckState.Unchecked)

    def set_default_title(self, title: str):
        """Set the default title to show when not items are checked."""
        self._default_title = title
        self.set_title(title)

    def update_checked_items(self):
        """Update the title to show all checked items."""
        checked = self.checked_indices()
        if checked:
            items = [self.itemText(i) for i in checked]
            self.set_title(', '.join(items))
        else:
            self.set_title(self._default_title)

    def title(self):
        """Return the title."""
        return self._title

    def set_title(self, title):
        """Set the title of the combobox."""
        self._title = title
        self.repaint()

    @override
    def paintEvent(self, event):
        """Display the title, eliding text if needed."""
        with QStylePainter(self) as painter:
            painter.setPen(self.palette().color(QPalette.ColorRole.Text))
            opt = QStyleOptionComboBox()
            self.initStyleOption(opt)
            metrics = QFontMetrics(self.font())
            elided = metrics.elidedText(
                self._title, Qt.TextElideMode.ElideRight, self.width() - 25
            )
            opt.currentText = elided
            painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
            painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)
