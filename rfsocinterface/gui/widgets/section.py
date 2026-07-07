"""A collapsible section for toggling whether a group of widgets are visible.

Elypson/qt-collapsible-section
(c) 2016 Michael A. Voelkel - michael.alexander.voelkel@gmail.com
This file is part of Elypson/qt-collapsible section.
Elypson/qt-collapsible-section is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, version 3 of the License, or
(at your option) any later version.
Elypson/qt-collapsible-section is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.
You should have received a copy of the GNU General Public License
along with Elypson/qt-collapsible-section. If not, see <http:#www.gnu.org/licenses/>.
"""

from typing import Literal, override

from PySide6.QtCore import (
    QAbstractAnimation,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from rfsocinterface.gui.widgets.utils import layout_widgets

TOGGLE_BUTTON_CSS = """
        QToolButton {
            border: none;
        }
        QToolButton[active = "false"]:hover {
            background: lightgray;
        }
        QToolButton[active = "true"]:hover {
            background: qradialgradient(
                cx: 0.3, cy: -0.4, fx: -0.3, fy: 0.4,
                radius: 1.35, stop: 0 lightblue, stop: 1 lightskyblue
            );
        }
        QToolButton:pressed {
            background: lightgray;
        }
        QToolButton[active = "true"]{
            background-color: lightskyblue;
            border: none;
        }
        QToolButton[active = "false"]{
            border: none;
        }
"""


class Section(QWidget):
    """Collapsible container for other widgets."""
    clicked = Signal()

    def __init__(self, parent=None, *, animation_duration=100):
        """Initialize a Section."""
        super().__init__(parent)
        self.initialized = False
        self.animation_duration = animation_duration
        self.toggle_button = QToolButton(self)
        self.header_line = QFrame(self)
        self.toggle_animation = QParallelAnimationGroup(self)
        self.content_area = QScrollArea(self)
        self.main_layout = QGridLayout(self)
        self.content_height = 0

        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        # self.toggleButton.setStyleSheet("QToolButton {border: none;}")
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.set_active('false')

        self.header_line.setFrameShape(QFrame.HLine)
        self.header_line.setFrameShadow(QFrame.Sunken)
        self.header_line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        # self.contentArea.setLayout(wd.QHBoxLayout())
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        # start out collapsed
        self.content_area.setMaximumHeight(0)
        self.content_area.setMinimumHeight(0)

        # let the entire widget grow and shrink with its content
        self.toggle_animation.addAnimation(QPropertyAnimation(self, b'minimumHeight'))
        self.toggle_animation.addAnimation(QPropertyAnimation(self, b'maximumHeight'))
        self.toggle_animation.addAnimation(
            QPropertyAnimation(self.content_area, b'maximumHeight')
        )

        self.main_layout.setVerticalSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        row = 0
        self.main_layout.addWidget(self.toggle_button, row, 0, 1, 1)
        self.main_layout.addWidget(self.header_line, row, 2, 1, 1)
        self.main_layout.addWidget(self.content_area, row + 1, 0, 1, 3)
        self.setLayout(self.main_layout)

        self.toggle_button.toggled.connect(self.toggle)
        # self.toggleButton.clicked.connect(lambda: self.clicked.emit())
        self.parent_sections = []
        self.children_sections = []
        self.children_height = 0
        self.initialized = True

    def set_active(self, value: Literal['true', 'false']):
        """Set whether this section is active.

        Arguments:
            value (str): The value of the "active" property. Must be "true" or "false".
        """
        self.toggle_button.setProperty('active', value)
        self.toggle_button.setStyleSheet(TOGGLE_BUTTON_CSS)

    def install_event_filter_recursively(self, obj: QObject | None):
        """Install an event filter to this widget and all children recursively."""
        if obj is None:
            return
        if isinstance(obj, QLayout):
            children = layout_widgets(obj)
            for child in children:
                self.install_event_filter_recursively(child)
            for child in obj.findChildren(QLayout):
                self.install_event_filter_recursively(child)
        else:
            # if isinstance(obj, IconLabel):
            #     obj.hidden.connect(self.update_self)
            if obj.isWidgetType():
                obj.installEventFilter(self)
            if isinstance(obj, QAbstractButton):
                obj.clicked.connect(self.clicked.emit)
            # if isinstance(obj, Section):
            #     self.install_event_filter_recursively(obj.layout())
            self.install_event_filter_recursively(obj.layout())

    @override
    def eventFilter(self, watched, event):
        if event.type() == QMouseEvent.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.clicked.emit()
            return False
        return super().eventFilter(watched, event)

    def set_title(self, title):
        """Set the title of this section."""
        self.toggle_button.setText(title)

    def set_content_layout(self, content_layout: QLayout):
        """Set the laytout for the inside content."""
        layout = self.content_area.layout()
        del layout
        self.content_area.setLayout(content_layout)
        self.setMinimumWidth(content_layout.minimumSize().width())

        self.children_sections = find_children_sections(content_layout)
        for child in self.children_sections:
            child.parent_sections.append(self)
            # child.installEventFilter(self)
        self.install_event_filter_recursively(self.layout())

        self.collapsed_height = (
            self.sizeHint().height() - self.content_area.maximumHeight()
        )
        self.content_height = self.content_area.layout().sizeHint().height()
        self.update_size()
        self.update_animation()

    def update_animation(self):
        """Update the section's toggle animation."""
        for i in range(self.toggle_animation.animationCount() - 1):
            section_animation = self.toggle_animation.animationAt(i)
            section_animation.setDuration(self.animation_duration)
            section_animation.setStartValue(self.collapsed_height)
            section_animation.setEndValue(self.collapsed_height + self.content_height)
        content_animation = self.toggle_animation.animationAt(
            self.toggle_animation.animationCount() - 1
        )
        content_animation.setDuration(self.animation_duration)
        content_animation.setStartValue(0)
        content_animation.setEndValue(self.content_height)

    def resize_animation(self, duration):
        """Animate the section resizing as it collapses / expands."""
        resize_animation = QParallelAnimationGroup(self)

        section_animation_min = QPropertyAnimation(self, b'minimumHeight')
        section_animation_min.setDuration(duration)
        section_animation_min.setStartValue(self.height())
        section_animation_min.setEndValue(self.collapsed_height + self.content_height)
        section_animation = QPropertyAnimation(self, b'maximumHeight')
        section_animation.setDuration(duration)
        section_animation.setStartValue(self.height())
        section_animation.setEndValue(self.collapsed_height + self.content_height)
        content_animation_min = QPropertyAnimation(
            self.content_area, b'minimumHeight'
        )
        content_animation_min.setDuration(duration)
        content_animation_min.setStartValue(self.content_area.height())
        content_animation_min.setEndValue(self.content_height)
        content_animation = QPropertyAnimation(self.content_area, b'maximumHeight')
        content_animation.setDuration(duration)
        content_animation.setStartValue(self.content_area.height())
        content_animation.setEndValue(self.content_height)

        resize_animation.addAnimation(section_animation_min)
        resize_animation.addAnimation(section_animation)
        resize_animation.addAnimation(content_animation)
        resize_animation.start()

    def set_duration(self, duration: int):
        """Set the suration for the animation."""
        for i in range(self.toggle_animation.animationCount()):
            animation = self.toggle_animation.animationAt(i)
            animation.setDuration(duration)
        self.animation_duration = duration

    def update_size(self):
        """Update the size of the section based on its content."""
        self.content_height -= self.children_height
        self.children_height = self.find_children_height()
        self.content_height += self.children_height

    def find_children_height(self) -> int:
        """Find the total height of all children."""
        total = 0
        for child in self.children_sections:
            if child.toggle_button.isChecked():
                total += child.content_height
            # total += child.collapsedHeight
        return total

    @Slot(bool)
    def toggle(self, collapsed: bool):
        """Toggle whether the section is collapsed or not."""
        if collapsed:
            self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
            direction = QAbstractAnimation.Forward
        else:
            self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
            direction = QAbstractAnimation.Backward
        self.toggle_animation.setDirection(direction)
        self.toggle_animation.start()
        # time.sleep(0.1)
        self.update_parent_sections()

    def update_parent_sections(self):
        """Update the size of every section containing this section."""
        for parent in self.parent_sections:
            parent.update_size()
            parent.update_animation()
            parent.resize_animation(self.animation_duration)

    def collapse(self, recursive: bool = False):
        """Collapse this section.

        Arguments:
            recursive (bool, optional): Whether to collapse all children sections
                recursively. Defaults to False.
        """
        if recursive:
            for child in self.children_sections:
                child.collapse()
        self.set_duration(0)
        self.toggle_button.setChecked(False)
        self.set_duration(self.animation_duration)

    def expand(self, recursive: bool = False):
        """Expand this section.

        Arguments:
            recursive (bool, optional): Whether to expand all children sections
                recursively. Defaults to False.
        """
        if recursive:
            for child in self.children_sections:
                child.expand()
        self.set_duration(0)
        self.toggle_button.setChecked(True)
        self.set_duration(self.animation_duration)

    def height_changed(self):
        """Update the widget when the height of it's content has changed."""
        self.content_height = self.content_area.layout().sizeHint().height()
        self.update_animation()
        self.resize_animation(self.animation_duration)
        self.update_parent_sections()


def find_children_sections(widget: QWidget) -> list[Section]:
    """Return a list of all descendants that are Sections."""
    children = []
    if widget is None:
        return children
    if isinstance(widget, Section):
        children.append(widget)

    if isinstance(widget, QLayout):
        for child in layout_widgets(widget):
            children.extend(find_children_sections(child))
    else:
        layout = widget.layout()
        if layout:
            for child in layout_widgets(layout):
                children.extend(find_children_sections(child))
    return children
