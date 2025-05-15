"""Drag and Drop widget.

Implementation from https://www.pythonguis.com/faq/pyside6-drag-drop-widgets/
"""

from PySide6.QtCore import QMimeData, Qt, Signal, QPoint
from PySide6.QtGui import QDrag, QPixmap, QMouseEvent, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

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
        self.setCursor(Qt.CursorShape.OpenHandCursor)

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

    orderChanged = Signal(list)

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

    def dragEnterEvent(self, e):
        e.accept()

    def dragLeaveEvent(self, e):
        self._drag_target_indicator.hide()
        e.accept()

    def dragMoveEvent(self, e):
        # Find the correct location of the drop target, so we can move it there.
        index = self._find_drop_location(e)
        if index is not None:
            # Inserting moves the item if its alreaady in the layout.
            self.blayout.insertWidget(index, self._drag_target_indicator)
            # Hide the item being dragged.
            e.source().hide()
            # Show the target.
            self._drag_target_indicator.show()
        e.accept()

    def dropEvent(self, e):
        widget = e.source()
        # Use drop target location for destination, then remove it.
        self._drag_target_indicator.hide()
        index = self.blayout.indexOf(self._drag_target_indicator)
        if index is not None:
            self.blayout.insertWidget(index, widget)
            self.orderChanged.emit(self.get_item_data())
            widget.show()
            self.blayout.activate()
        e.accept()

    def _find_drop_location(self, e):
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
        item.setParent(None)

    def get_item_data(self):
        data = []
        for n in range(self.blayout.count()):
            # Get the widget at each index in turn.
            w = self.blayout.itemAt(n).widget()
            if w != self._drag_target_indicator:
                # The target indicator has no data.
                data.append(w.data)
        return data



    # def mousePressEvent(self, event):
    #     widget = self.childAt(event.pos())
    #     if widget is None:
    #         return
    #     print(widget)


class ClickableDragWidget(DragWidget):
    def __init__(self, *args, orientation=Qt.Orientation.Vertical, **kwargs):
        super().__init__(*args, orientation=orientation, **kwargs)
        self.active_item = None

    def add_item(self, item: ClickableDragItem):
        super().add_item(item)
        item.clicked.connect(self.item_clicked)

    def remove_item(self, item: ClickableDragItem):
        super().remove_item(item)
        self.set_active_item(None)

    def set_active_item(self, item: ClickableDragItem):
        if self.active_item is not None:
            self.active_item.set_active('false')

        self.active_item = item 
        if self.active_item is not None:
            self.active_item.set_active('true')

    def item_clicked(self):
        item: ClickableDragItem = self.sender()
        if self.blayout.indexOf(item) != -1:
            self.set_active_item(item)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.drag = DragWidget(orientation=Qt.Orientation.Vertical)
        for n, l in enumerate(["A", "B", "C", "D"]):
            item = DragItem(l)
            item.set_data(n)  # Store the data.
            self.drag.add_item(item)

        # Print out the changed order.
        self.drag.orderChanged.connect(print)

        container = QWidget()
        layout = QVBoxLayout()
        layout.addStretch(1)
        layout.addWidget(self.drag)
        layout.addStretch(1)
        container.setLayout(layout)

        self.setCentralWidget(container)


if __name__ == '__main__':
    app = QApplication([])
    w = MainWindow()
    w.show()

    app.exec()