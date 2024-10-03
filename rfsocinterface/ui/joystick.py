from PySide6.QtCore import Qt, QPointF, QRectF, QLineF
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QMouseEvent, QEventPoint, QPaintEvent, QPen

from enum import Enum

class Direction(Enum):
    Left = 0
    Right = 1
    Up = 2
    Down = 3

class Joystick(QWidget):
    """Joystick for 360 degree directional input.
    
    Adapted from https://stackoverflow.com/a/55899694.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.movingOffset = QPointF(0, 0)
        self.grabCenter = False
        self.__maxDistance = 50

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        pen = QPen()
        pen.setWidth(2)
        pen.setColor('black')
        painter.setPen(pen)
        bounds = QRectF(-self.__maxDistance, -self.__maxDistance, self.__maxDistance * 2, self.__maxDistance * 2).translated(self._center())
        painter.drawEllipse(bounds)
        painter.setBrush(Qt.BrushStyle.SolidPattern)
        painter.drawEllipse(self._centerEllipse())

    def _centerEllipse(self):
        if self.grabCenter:
            return QRectF(-20, -20, 40, 40).translated(self.movingOffset)
        return QRectF(-20, -20, 40, 40).translated(self._center())

    def _center(self):
        return QPointF(self.width()/2, self.height()/2)

    def _boundJoystick(self, point: QEventPoint):
        limitLine = QLineF(self._center(), point)
        if (limitLine.length() > self.__maxDistance):
            limitLine.setLength(self.__maxDistance)
        return limitLine.p2()

    def joystickDirection(self):
        if not self.grabCenter:
            return 0
        normVector = QLineF(self._center(), self.movingOffset)
        currentDistance = normVector.length()
        angle = normVector.angle()

        distance = min(currentDistance / self.__maxDistance, 1.0)
        if 45 <= angle < 135:
            return (Direction.Up, distance)
        elif 135 <= angle < 225:
            return (Direction.Left, distance)
        elif 225 <= angle < 315:
            return (Direction.Down, distance)
        return (Direction.Right, distance)


    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.grabCenter = self._centerEllipse().contains(event.pos())
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.grabCenter = False
        self.movingOffset = QPointF(0, 0)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.grabCenter:
            print("Moving")
            self.movingOffset = self._boundJoystick(event.pos())
            self.update()
        print(self.joystickDirection())

