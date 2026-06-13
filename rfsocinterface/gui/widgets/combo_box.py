from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPalette, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QStylePainter


class CheckableComboBox(QComboBox):
    """A combobox that allows for checkable items.

    Code adapted from: https://stackoverflow.com/a/22775990 and
    https://stackoverflow.com/a/35831986.
    """

    def __init__(self, title: str = '', parent=None):
        super().__init__(parent)
        self.setTitle(title)
        self._default_title = title
        self.view().pressed.connect(self.handleItemPressed)
        self.view().doubleClicked.connect(self.handleItemPressed)
        self.setModel(QStandardItemModel(self))
        self._changed = False

    def checked_indices(self) -> list[int]:
        return [
            i
            for i in range(self.count())
            if self.model().item(i, self.modelColumn()).checkState()
            == Qt.CheckState.Checked
        ]

    def deselect_all(self):
        for i in range(self.count()):
            self.setItemChecked(i, False)
        self.update_checked_items()

    def select_all(self):
        for i in range(self.count()):
            self.setItemChecked(i, True)
        self.update_checked_items()

    def handleItemPressed(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)
        self.update_checked_items()
        self._changed = True

    def hidePopup(self):
        if not self._changed:
            super(CheckableComboBox, self).hidePopup()
        self._changed = False

    def itemChecked(self, index):
        item = self.model().item(index, self.modelColumn())
        return item.checkState() == Qt.CheckState.Checked

    def setItemChecked(self, index, checked=True):
        item = self.model().item(index, self.modelColumn())
        if checked:
            item.setCheckState(Qt.CheckState.Checked)
        else:
            item.setCheckState(Qt.CheckState.Unchecked)

    def set_default_title(self, title: str):
        self._default_title = title
        self.setTitle(title)

    def update_checked_items(self):
        checked = self.checked_indices()
        if checked:
            items = [self.itemText(i) for i in checked]
            self.setTitle(', '.join(items))
        else:
            self.setTitle(self._default_title)

    def title(self):
        return self._title

    def setTitle(self, title):
        self._title = title
        self.repaint()

    def paintEvent(self, event):
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
