"""Drag and Drop widget.

Implementation from https://www.pythonguis.com/faq/pyside6-drag-drop-widgets/
"""
from itertools import chain
from enum import StrEnum
from typing import Any

from PySide6.QtCore import QMimeData, Qt, Signal, QPoint, Slot
from PySide6.QtGui import QDrag, QPixmap, QMouseEvent, QDropEvent, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QFormLayout,
)

from rfsocinterface.gui.widgets.divider import VLine, HLine

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(25, 5, 25, 5)
        self.setStyleSheet(
            "QLabel { background-color: #ccc; border: 1px solid black; }"
        )


class DragItem(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setContentsMargins(25, 5, 25, 5)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 1px solid black;")
        # Store data separately from display label, but use label for default.
        self.data = self.text()

    def set_data(self, data):
        self.data = data

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton:
            # Render at x2 pixel ratio to avoid blur on Retina screens.
            pixmap = QPixmap(self.size().width() * 2, self.size().height() * 2)
            pixmap.setDevicePixelRatio(2)
            self.render(pixmap)

            # TODO: Change the mouse cursor when dragging
            drag = QDrag(self)
            drag.setDragCursor
            mime = QMimeData()
            drag.setMimeData(mime)


            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(drag.pixmap().width()/4, drag.pixmap().height() / 4))


            drag.exec(Qt.DropAction.MoveAction)
            self.show() # Show this widget again, if it's dropped outside.


class ClickableDragItem(DragItem):
    doubleClicked = Signal()
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_active('false')
    
    def mousePressEvent(self, event: QMouseEvent):
        self.clicked.emit()
        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.doubleClicked.emit()
        return super().mouseDoubleClickEvent(event)

    def set_active(self, value: str):
        self.setProperty('active', value)
        self.setStyleSheet(DRAG_ITEM_CSS)


class DragWidget(QWidget):
    """
    Generic list sorting handler.
    """

    orderChanged = Signal(list, list)

    def __init__(self, *args, orientation=Qt.Orientation.Vertical, **kwargs):
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

    def dragEnterEvent(self, e: QDragEnterEvent):
        e.accept()

    def dragLeaveEvent(self, e: QDragLeaveEvent):
        self._drag_target_indicator.hide()
        e.accept()

    def dragMoveEvent(self, e: QDragMoveEvent):
        # Find the correct location of the drop target, so we can move it there.
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
            self.orderChanged.emit(self.items(), self.get_item_data())
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
        self.blayout.addWidget(item)
        item.setParent(self)
    
    def remove_item(self, item: DragItem):
        self.blayout.removeWidget(item)

    def get_item_data(self):
        data = []
        for n in range(self.blayout.count()):
            # Get the widget at each index in turn.
            w = self.blayout.itemAt(n).widget()
            if w != self._drag_target_indicator:
                # The target indicator has no data.
                data.append(w.data)
        return data
    
    def items(self) -> list[DragItem]:
        all_items = [self.blayout.itemAt(i).widget() for i in range(self.blayout.count())]
        # print(all_items)
        return list(filter(lambda item: isinstance(item, DragItem), all_items))

    # def mousePressEvent(self, event):
    #     widget = self.childAt(event.pos())
    #     if widget is None:
    #         return
    #     print(widget)


class ClickableDragWidget(DragWidget):
    activeItemChanged = Signal(QWidget)

    def __init__(self, *args, orientation=Qt.Orientation.Vertical, **kwargs):
        super().__init__(*args, orientation=orientation, **kwargs)
        self.active_item = None

    def add_item(self, item: ClickableDragItem):
        super().add_item(item)
        item.clicked.connect(self.item_clicked)

    def remove_item(self, item: ClickableDragItem):
        super().remove_item(item)
        if item == self.active_item:
            self.set_active_item(None)

    def set_active_item(self, item: ClickableDragItem):
        if self.active_item is not None:
            self.active_item.set_active('false')

        self.active_item = item 
        if self.active_item is not None:
            self.active_item.set_active('true')
        self.activeItemChanged.emit(item)

    def item_clicked(self):
        item: ClickableDragItem = self.sender()
        if self.blayout.indexOf(item) != -1:
            self.set_active_item(item)

class SectionType(StrEnum):
    DRAG = 'drag'
    MISC = 'misc'


class ContainerSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.form_layout = QFormLayout()
        self.items = dict[str, Any]
        self.setLayout(self.form_layout)
    
    def add_item(self, label: str):
        pass

class MultiSectionDragWidget(QWidget):
    orderChanged = Signal(list, list)

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(parent=parent)
        self.orientation = orientation
        self.sections: list[tuple[SectionType, DragWidget | QWidget]] = []
        self._items = []
        self._item_data = []

        if self.orientation == Qt.Orientation.Vertical:
            self.blayout = QVBoxLayout()
        else:
            self.blayout = QHBoxLayout()
        self.setLayout(self.blayout)
    
    def get_item_data(self) -> list:
        return list(chain(*self._item_data))

    def get_item_data_separated(self) -> list[list]:
        return self._item_data
    
    def _update_item_data(self):
        self._item_data = [section.get_item_data() for section in self.sections]

    def items(self) -> list[DragItem]:
        return list(chain(*self._items))
    
    def items_separated(self) -> list[list[DragItem]]:
        return self._items
    
    def _update_items(self):
        self._items = [section.items() for section in self.sections]

    @Slot(list, list)
    def update_order(self, items: list, data: list):
        sender = self.sender()
        i_sec = self.sections.index(sender)
        self._items[i_sec] = items
        self._item_data[i_sec] = data
        self.orderChanged.emit(self._items, self._item_data)

    def __len__(self) -> int:
        return len(self.sections)

    def add_section(self, label: str, type: SectionType) -> DragWidget:
        if len(self) > 0:
            if self.orientation == Qt.Orientation.Vertical:
                self.blayout.addWidget(HLine())
            else:
                self.blayout.addWidget(VLine())
        section_label = QLabel(label, self)
        if type == SectionType.DRAG:
            new_section = DragWidget(orientation=self.orientation, parent=self)
            new_section.orderChanged.connect(self.update_order)
        else:
            new_section = QWidget(parent=self)
        self.blayout.addWidget(section_label)
        self.blayout.addWidget(new_section)
        self.sections.append(new_section)
        self._items.append([])
        self._item_data.append([])
        return new_section
    
    def add_item(self, i_section: int, item: DragItem):
        self.sections[i_section].add_item(item)
        self._items[i_section].append(item)
        self._item_data[i_section].append(item.data)

    def remove_item(self, i_section: int, item: DragItem):
        self.sections[i_section].remove_item(item)
        self._items[i_section].remove(item)
        self._item_data[i_section].remove(item.data)


class ClickableMultiSectionDragWidget(MultiSectionDragWidget):
    activeItemChanged = Signal(int, QWidget)

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(orientation, parent)
        self.active_item = (-1, None)

    def add_section(self, label: str) -> ClickableDragWidget:
        if len(self) > 0:
            if self.orientation == Qt.Orientation.Vertical:
                self.blayout.addWidget(HLine())
            else:
                self.blayout.addWidget(VLine())
        section_label = QLabel(label, self)
        new_section = ClickableDragWidget(orientation=self.orientation, parent=self)
        new_section.orderChanged.connect(self.update_order)
        self.blayout.addWidget(section_label)
        self.blayout.addWidget(new_section)
        i_sec = len(self.sections)
        new_section.activeItemChanged.connect(lambda item: self.set_active_item(i_sec, item))
        self.sections.append(new_section)
        self._items.append([])
        self._item_data.append([])
        return new_section

    @Slot(int, object)
    def set_active_item(self, section: int, item: ClickableDragItem):
        if self.active_item[1] is not None:
            self.active_item[1].set_active('false')

        self.active_item = (section, item)
        if self.active_item[1] is not None:
            self.active_item[1].set_active('true')
        self.activeItemChanged.emit(section, item)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.multi_drag = ClickableMultiSectionDragWidget(orientation=Qt.Orientation.Horizontal, parent=self)
        n_sections = 2
        counter = 0
        for i_sec, section_name in enumerate([f'Section {i + 1}' for i in range(n_sections)]):
            self.multi_drag.add_section(section_name)
            for l in ["A", "B", "C", "D"]:
                item = ClickableDragItem(l)
                item.set_data(counter)  # Store the data.
                counter += 1
                self.multi_drag.add_item(i_sec, item)
        # self.drag = DragWidget(orientation=Qt.Orientation.Vertical)
        # for n, l in enumerate(["A", "B", "C", "D"]):
        #     item = DragItem(l)
        #     item.set_data(n)  # Store the data.
        #     self.drag.add_item(item)

        # Print out the changed order.
        # self.drag.orderChanged.connect(print)
        self.multi_drag.orderChanged.connect(lambda _, l: print(l))

        container = QWidget()
        layout = QVBoxLayout()
        layout.addStretch(1)
        # layout.addWidget(self.drag)
        layout.addWidget(self.multi_drag)
        layout.addStretch(1)
        container.setLayout(layout)

        self.setCentralWidget(container)


if __name__ == '__main__':
    app = QApplication([])
    w = MainWindow()
    w.show()

    app.exec()