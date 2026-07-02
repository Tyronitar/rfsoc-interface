"""Drag and Drop widget.

Implementation from https://www.pythonguis.com/faq/pyside6-drag-drop-widgets/
"""

from itertools import chain
from typing import override

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal, Slot
from PySide6.QtGui import (
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.gui.widgets.divider import HLine, VLine

DRAG_ITEM_CSS = """
        QLabel {
            border: 1px solid black;
        }
        QLabel[active = "false"]:hover {
            background: lightgray;
        }
        QLabel[active = "true"]:hover {
            background: qradialgradient(
                cx: 0.3, cy: -0.4, fx: -0.3, fy: 0.4,
                radius: 1.35, stop: 0 lightblue, stop: 1 lightskyblue
            );
        }
        QLabel:pressed {
            background: lightgray;
        }
        QLabel[active = "true"]{
            background-color: lightskyblue;
            border: 1px solid black;
        }
        QLabel[active = "false"]{
            border: 1px solid black;
        }
"""


class DragTargetIndicator(QLabel):
    """Indicator for where a draggable widget will be dropped."""

    def __init__(self, parent=None):
        """Initialize a DragTargetIndicator."""
        super().__init__(parent)
        self.setContentsMargins(25, 5, 25, 5)
        self.setStyleSheet(
            'QLabel { background-color: #ccc; border: 1px solid black; }'
        )


class DragItem(QLabel):
    """Item representing something dragable in a list."""

    def __init__(self, *args, **kwargs):
        """Initialize a DragItem."""
        super().__init__(*args, **kwargs)
        self.setContentsMargins(25, 5, 25, 5)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet('border: 1px solid black;')
        # Store data separately from display label, but use label for default.
        self.data = self.text()

    def set_data(self, data):
        """Set the data stored in this item."""
        self.data = data

    @override
    def mouseMoveEvent(self, e: QMouseEvent):
        """Handle the dragging of the item."""
        if e.buttons() == Qt.MouseButton.LeftButton:
            # Render at x2 pixel ratio to avoid blur on Retina screens.
            pixmap = QPixmap(self.size().width() * 2, self.size().height() * 2)
            pixmap.setDevicePixelRatio(2)
            self.render(pixmap)

            # TODO: Change the mouse cursor when dragging
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            drag.setPixmap(pixmap)
            drag.setHotSpot(
                QPoint(drag.pixmap().width() / 4, drag.pixmap().height() / 4)
            )

            drag.exec(Qt.DropAction.MoveAction)
            self.show()  # Show this widget again, if it's dropped outside.


class ClickableDragItem(DragItem):
    """A DragItem that emits clicked signals."""
    double_clicked = Signal()
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        """Initialize a ClickableDragItem."""
        super().__init__(*args, **kwargs)
        self.set_active('false')

    @override
    def mousePressEvent(self, event: QMouseEvent):
        self.clicked.emit()
        return super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.double_clicked.emit()
        return super().mouseDoubleClickEvent(event)

    def set_active(self, value: str):
        """Set whether this item is active."""
        self.setProperty('active', value)
        self.setStyleSheet(DRAG_ITEM_CSS)


class DragWidget(QWidget):
    """Generic list sorting handler."""

    order_changed = Signal(list, list)

    def __init__(self, *args, orientation=Qt.Orientation.Vertical, **kwargs):
        """Initialize a DragWidget."""
        super().__init__()
        self.setAcceptDrops(True)

        # Store the orientation for drag checks later.
        self.orientation = orientation

        if self.orientation == Qt.Orientation.Vertical:
            self.blayout = QVBoxLayout()
        else:
            self.blayout = QHBoxLayout()

        # Add the drag target indicator. This is invisible by default,
        # we show it and move it around while the drag is active.
        self._drag_target_indicator = DragTargetIndicator()
        self.blayout.addWidget(self._drag_target_indicator)
        self._drag_target_indicator.hide()

        self.setLayout(self.blayout)

    @override
    def dragEnterEvent(self, e: QDragEnterEvent):
        e.accept()

    @override
    def dragLeaveEvent(self, e: QDragLeaveEvent):
        self._drag_target_indicator.hide()
        e.accept()

    @override
    def dragMoveEvent(self, e: QDragMoveEvent):
        """Find the correct location of the drop target, so we can move it there."""
        if e.source().parent() != self:
            e.ignore()
            return
        index = self._find_drop_location(e)
        if index is not None:
            # Inserting moves the item if its alreaady in the layout.
            self.blayout.insertWidget(index, self._drag_target_indicator)
            # Hide the item being dragged.
            e.source().hide()
            # Show the target.
            self._drag_target_indicator.show()
        e.accept()

    @override
    def dropEvent(self, e: QDropEvent):
        widget = e.source()
        # Use drop target location for destination, then remove it.
        self._drag_target_indicator.hide()
        if widget.parent() != self:
            e.ignore()
            return
        index = self.blayout.indexOf(self._drag_target_indicator)
        if index is not None:
            self.blayout.insertWidget(index, widget)
            self.order_changed.emit(self.items(), self.get_item_data())
            widget.show()
            self.blayout.activate()
        e.accept()

    def _find_drop_location(self, e: QDragMoveEvent):
        pos = e.position()
        spacing = self.blayout.spacing() / 2

        for n in range(self.blayout.count()):
            # Get the widget at each index in turn.
            w = self.blayout.itemAt(n).widget()

            if self.orientation == Qt.Orientation.Vertical:
                # Drag drop vertically.
                drop_here = (
                    pos.y() >= w.y() - spacing
                    and pos.y() <= w.y() + w.size().height() + spacing
                )
            else:
                # Drag drop horizontally.
                drop_here = (
                    pos.x() >= w.x() - spacing
                    and pos.x() <= w.x() + w.size().width() + spacing
                )

            if drop_here:
                # Drop over this target.
                break

        return n

    def add_item(self, item: DragItem):
        """Add an item to the list."""
        self.blayout.addWidget(item)
        item.setParent(self)

    def remove_item(self, item: DragItem):
        """Remove an item from the list."""
        self.blayout.removeWidget(item)

    def get_item_data(self):
        """Return a list of the data in each DragItem."""
        data = []
        for n in range(self.blayout.count()):
            # Get the widget at each index in turn.
            w = self.blayout.itemAt(n).widget()
            if w != self._drag_target_indicator:
                # The target indicator has no data.
                data.append(w.data)
        return data

    def items(self) -> list[DragItem]:
        """Return a list of all DragItems."""
        all_items = [
            self.blayout.itemAt(i).widget() for i in range(self.blayout.count())
        ]
        # print(all_items)
        return list(filter(lambda item: isinstance(item, DragItem), all_items))

    # def mousePressEvent(self, event):
    #     widget = self.childAt(event.pos())
    #     if widget is None:
    #         return
    #     print(widget)


class ClickableDragWidget(DragWidget):
    """DragWidget that uses ClickableDragItems."""
    active_item_changed = Signal(QWidget)

    def __init__(self, *args, orientation=Qt.Orientation.Vertical, **kwargs):
        """Initialize a ClickableDragWidget."""
        super().__init__(*args, orientation=orientation, **kwargs)
        self.active_item = None

    @override
    def add_item(self, item: ClickableDragItem):
        super().add_item(item)
        item.clicked.connect(self.item_clicked)

    @override
    def remove_item(self, item: ClickableDragItem):
        super().remove_item(item)
        if item == self.active_item:
            self.set_active_item(None)

    def set_active_item(self, item: ClickableDragItem):
        """Set the item as the current active item."""
        if self.active_item is not None:
            self.active_item.set_active('false')

        self.active_item = item
        if self.active_item is not None:
            self.active_item.set_active('true')
        self.active_item_changed.emit(item)

    @Slot()
    def item_clicked(self):
        """Slot for when an item has been clicked."""
        item: ClickableDragItem = self.sender()
        if self.blayout.indexOf(item) != -1:
            self.set_active_item(item)


class MultiSectionDragWidget(QWidget):
    """DragWidget with multiple independent sections."""
    order_changed = Signal(list, list)

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        """Initialize a MultiSectionDragWidget."""
        super().__init__(parent=parent)
        self.orientation = orientation
        self.sections: list[DragWidget] = []
        self._items = []
        self._item_data = []

        if self.orientation == Qt.Orientation.Vertical:
            self.blayout = QVBoxLayout()
        else:
            self.blayout = QHBoxLayout()
        self.setLayout(self.blayout)

    def get_item_data(self) -> list:
        """Return a list of all item data."""
        return list(chain(*self._item_data))

    def get_item_data_separated(self) -> list[list]:
        """Return all the item data, split into lists by section."""
        return self._item_data

    def _update_item_data(self):
        """Update the _item_data attribute."""
        self._item_data = [section.get_item_data() for section in self.sections]

    def items(self) -> list[DragItem]:
        """Return a list of each DragItem."""
        return list(chain(*self._items))

    def items_separated(self) -> list[list[DragItem]]:
        """Return all the DragItems, split into lists by section."""
        return self._items

    def _update_items(self):
        """Update the _items attribute."""
        self._items = [section.items() for section in self.sections]

    @Slot(list, list)
    def update_order(self, items: list, data: list):
        """Update the order of the items."""
        sender = self.sender()
        i_sec = self.sections.index(sender)
        self._items[i_sec] = items
        self._item_data[i_sec] = data
        self.order_changed.emit(self._items, self._item_data)

    def __len__(self) -> int:
        """Return the number of sections."""
        return len(self.sections)

    def add_section(self, label: str) -> DragWidget:
        """Add a new section to the widget."""
        if len(self) > 0:
            if self.orientation == Qt.Orientation.Vertical:
                self.blayout.addWidget(HLine())
            else:
                self.blayout.addWidget(VLine())
        section_label = QLabel(label, self)
        new_section = DragWidget(orientation=self.orientation, parent=self)
        new_section.order_changed.connect(self.update_order)
        self.blayout.addWidget(section_label)
        self.blayout.addWidget(new_section)
        self.sections.append(new_section)
        self._items.append([])
        self._item_data.append([])
        return new_section

    def add_item(self, i_section: int, item: DragItem):
        """Add an item to the specified section."""
        self.sections[i_section].add_item(item)
        self._items[i_section].append(item)
        self._item_data[i_section].append(item.data)

    def remove_item(self, i_section: int, item: DragItem):
        """Remove an item from the specified section."""
        self.sections[i_section].remove_item(item)
        self._items[i_section].remove(item)
        self._item_data[i_section].remove(item.data)


class ClickableMultiSectionDragWidget(MultiSectionDragWidget):
    """A MultiSectionDragWidget that uses ClickableDragWidgets."""
    active_item_changed = Signal(int, QWidget)

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        """Intialize a ClickableMultiSectionDragWidget."""
        super().__init__(orientation, parent)
        self.active_item = (-1, None)

    @override
    def add_section(self, label: str) -> ClickableDragWidget:
        if len(self) > 0:
            if self.orientation == Qt.Orientation.Vertical:
                self.blayout.addWidget(HLine())
            else:
                self.blayout.addWidget(VLine())
        section_label = QLabel(label, self)
        new_section = ClickableDragWidget(orientation=self.orientation, parent=self)
        new_section.order_changed.connect(self.update_order)
        self.blayout.addWidget(section_label)
        self.blayout.addWidget(new_section)
        i_sec = len(self.sections)
        new_section.active_item_changed.connect(
            lambda item: self.set_active_item(i_sec, item)
        )
        self.sections.append(new_section)
        self._items.append([])
        self._item_data.append([])
        return new_section

    @Slot(int, object)
    def set_active_item(self, section: int, item: ClickableDragItem):
        """Update the current active item."""
        if self.active_item[1] is not None:
            self.active_item[1].set_active('false')

        self.active_item = (section, item)
        if self.active_item[1] is not None:
            self.active_item[1].set_active('true')
        self.active_item_changed.emit(section, item)
