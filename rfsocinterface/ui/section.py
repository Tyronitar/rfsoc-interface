'''
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
'''

import PySide6.QtCore as cr
from PySide6.QtCore import Qt, QEvent
import PySide6.QtWidgets as wd
from PySide6.QtGui import QMouseEvent
# import PyQt5.QtGui as gui
import sys
import time
from rfsocinterface.utils import get_total_height, layout_widgets

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

class Section(wd.QWidget):
    clicked = cr.Signal()

    def __init__(self, parent=None,*, animationDuration=100):
        super().__init__(parent)
        self.animationDuration = animationDuration
        self.toggleButton = wd.QToolButton(self)
        self.headerLine = wd.QFrame(self)
        self.toggleAnimation = cr.QParallelAnimationGroup(self)
        self.contentArea = wd.QScrollArea(self)
        self.mainLayout = wd.QGridLayout(self)

        self.toggleButton.setToolButtonStyle(cr.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # self.toggleButton.setStyleSheet("QToolButton {border: none;}")
        self.toggleButton.setArrowType(cr.Qt.ArrowType.RightArrow)
        self.toggleButton.setCheckable(True)
        self.toggleButton.setChecked(False)
        self.set_active('false')

        self.headerLine.setFrameShape(wd.QFrame.HLine)
        self.headerLine.setFrameShadow(wd.QFrame.Sunken)
        self.headerLine.setSizePolicy(wd.QSizePolicy.Expanding, wd.QSizePolicy.Maximum)

        # self.contentArea.setLayout(wd.QHBoxLayout())
        self.contentArea.setSizePolicy(wd.QSizePolicy.Expanding, wd.QSizePolicy.Fixed)

        # start out collapsed
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)

        # let the entire widget grow and shrink with its content
        self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self, b"minimumHeight"))
        self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self, b"maximumHeight"))
        self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self.contentArea, b"maximumHeight"))

        self.mainLayout.setVerticalSpacing(0)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)

        row = 0
        self.mainLayout.addWidget(self.toggleButton, row, 0, 1, 1)
        self.mainLayout.addWidget(self.headerLine, row, 2, 1, 1)
        self.mainLayout.addWidget(self.contentArea, row + 1, 0, 1, 3)
        self.setLayout(self.mainLayout)

        self.toggleButton.toggled.connect(self.toggle)
        # self.toggleButton.clicked.connect(lambda: self.clicked.emit())
        self.parent_sections = []
        self.children_sections = []
        self.children_height = 0
    
    def set_active(self, value: str):
        self.toggleButton.setProperty('active', value)
        self.toggleButton.setStyleSheet(TOGGLE_BUTTON_CSS)

    def install_event_filter_recursively(self, obj: cr.QObject | None):
        if obj is None:
            return
        if isinstance(obj, wd.QLayout):
            children = layout_widgets(obj)
            for child in children:
                self.install_event_filter_recursively(child)
            for child in obj.findChildren(wd.QLayout):
                self.install_event_filter_recursively(child)
        else:
            if isinstance(obj, wd.QWidget):
            # if type(obj) in (wd.QWidget, wd.QPushButton, wd.QToolButton, wd.QLineEdit):
                obj.installEventFilter(self)
            if isinstance(obj, wd.QAbstractButton):
                obj.clicked.connect(lambda: self.clicked.emit())
            # if isinstance(obj, Section):
            #     self.install_event_filter_recursively(obj.layout())
            self.install_event_filter_recursively(obj.layout())

    def eventFilter(self, watched, event):
        if event.type() == QMouseEvent.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.clicked.emit()
            return False
        return super().eventFilter(watched, event)

    def setTitle(self,title):
        self.toggleButton.setText(title)
    
    def setContentLayout(self, contentLayout: wd.QLayout):
        layout = self.contentArea.layout()
        del layout
        self.contentArea.setLayout(contentLayout)

        self.children_sections = find_children_sections(contentLayout)
        for child in self.children_sections:
            child.parent_sections.append(self)
            # child.installEventFilter(self)
        self.install_event_filter_recursively(self.layout())
        
        self.collapsedHeight = self.sizeHint().height() - self.contentArea.maximumHeight()
        self.contentHeight = self.contentArea.layout().sizeHint().height()
        self.update_size()
        self.update_animation()

        # self.collapsedHeight = self.sizeHint().height() - self.contentArea.maximumHeight()
        # # contentHeight = self.contentArea.maximumHeight()
        # self.contentHeight = contentLayout.sizeHint().height()  + find_section_height(contentLayout)
    
    def update_animation(self):
        for i in range(0, self.toggleAnimation.animationCount() - 1):
            SectionAnimation = self.toggleAnimation.animationAt(i)
            SectionAnimation.setDuration(self.animationDuration)
            SectionAnimation.setStartValue(self.collapsedHeight)
            SectionAnimation.setEndValue(self.collapsedHeight + self.contentHeight)
        contentAnimation = self.toggleAnimation.animationAt(self.toggleAnimation.animationCount() - 1)
        contentAnimation.setDuration(self.animationDuration)
        contentAnimation.setStartValue(0)
        contentAnimation.setEndValue(self.contentHeight)
    
    def resize_animation(self, duration):
        resize_animation = cr.QParallelAnimationGroup(self)

        section_animation_min = cr.QPropertyAnimation(self, b"minimumHeight")
        section_animation_min.setDuration(duration)
        section_animation_min.setStartValue(self.height())
        section_animation_min.setEndValue(self.collapsedHeight + self.contentHeight)
        section_animation = cr.QPropertyAnimation(self, b"maximumHeight")
        section_animation.setDuration(duration)
        section_animation.setStartValue(self.height())
        section_animation.setEndValue(self.collapsedHeight + self.contentHeight)
        content_animation_min = cr.QPropertyAnimation(self.contentArea, b"minimumHeight")
        content_animation_min.setDuration(duration)
        content_animation_min.setStartValue(self.contentArea.height())
        content_animation_min.setEndValue(self.contentHeight)
        content_animation = cr.QPropertyAnimation(self.contentArea, b"maximumHeight")
        content_animation.setDuration(duration)
        content_animation.setStartValue(self.contentArea.height())
        content_animation.setEndValue(self.contentHeight)

        # self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self, b"minimumHeight"))
        # self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self, b"maximumHeight"))
        # self.toggleAnimation.addAnimation(cr.QPropertyAnimation(self.contentArea, b"maximumHeight"))
        resize_animation.addAnimation(section_animation_min)
        resize_animation.addAnimation(section_animation)
        # resize_animation.addAnimation(content_animation_min)
        resize_animation.addAnimation(content_animation)
        # resize_animation.setDirection(direction)
        resize_animation.start()
    
    def set_duration(self, duration: int):
        for i in range(0, self.toggleAnimation.animationCount()):
            animation = self.toggleAnimation.animationAt(i)
            animation.setDuration(duration)
        self.animationDuration = duration
    
    def update_size(self):
        contentLayout = self.contentArea.layout()
        self.contentHeight -= self.children_height
        self.children_height = self.find_children_height()
        self.contentHeight += self.children_height
        # self.contentHeight = contentLayout.sizeHint().height() + self.find_children_height()
    
    def find_children_height(self) -> int:
        total = 0
        for child in self.children_sections:
            if child.toggleButton.isChecked():
                total += child.contentHeight
            # total += child.collapsedHeight
        return total

    def toggle(self, collapsed):
        if collapsed:
            self.toggleButton.setArrowType(cr.Qt.ArrowType.DownArrow)
            direction = cr.QAbstractAnimation.Forward
        else:
            self.toggleButton.setArrowType(cr.Qt.ArrowType.RightArrow)
            direction = cr.QAbstractAnimation.Backward
        self.toggleAnimation.setDirection(direction)
        self.toggleAnimation.start()
        # time.sleep(0.1)
        self.update_parent_sections(direction)
    
    def update_parent_sections(self, direction):
        for parent in self.parent_sections:
            parent.update_size()
            parent.update_animation()
            parent.resize_animation(self.animationDuration)
            # resize_animation = cr.QPropertyAnimation(parent, b"maximumHeight")
            # resize_animation.setDuration(parent.animationDuration)
            # resize_animation.setStartValue(parent.height())
            # resize_animation.setEndValue(parent.collapsedHeight + parent.contentHeight)
            # resize_animation.start()
            # parent.toggleAnimation.start()


def find_section_height(widget: wd.QWidget) -> int:
    total = 0
    if widget is None:
        return total
    if isinstance(widget, wd.QLayout):
        for child in layout_widgets(widget):
            total += find_section_height(child)
    else:
        layout = widget.layout()
        if layout:
            for child in layout_widgets(layout):
                total += find_section_height(child)
    if isinstance(widget, Section):
        # contentAnimation = widget.toggleAnimation.animationAt(widget.toggleAnimation.animationCount() - 1)
        # total += contentAnimation.endValue()
        if widget.toggleButton.isChecked():
            total += widget.contentHeight
        else:
            total += widget.collapsedHeight
    return total

def find_children_sections(widget: wd.QWidget) -> list[Section]:
    children = []
    if widget is None:
        return children 
    if isinstance(widget, Section):
        children.append(widget)

    if isinstance(widget, wd.QLayout):
        for child in layout_widgets(widget):
            children.extend(find_children_sections(child))
    else:
        layout = widget.layout()
        if layout:
            for child in layout_widgets(layout):
                children.extend(find_children_sections(child))
    return children



if __name__ == '__main__':
    class Window(wd.QMainWindow):
        def __init__(self, parent=None):
            super().__init__(parent)
            section = Section("Section", 100, self)

            anyLayout = wd.QVBoxLayout()
            anyLayout.addWidget(wd.QLabel("Some Text in Section", section))
            anyLayout.addWidget(wd.QPushButton("Button in Section", section))

            section.setContentLayout(anyLayout)

            self.place_holder = wd.QWidget()  # placeholder widget, only used to get acces to wd.QMainWindow functionalities
            mainLayout = wd.QHBoxLayout(self.place_holder)
            mainLayout.addWidget(section)
            mainLayout.addStretch(1)
            self.setCentralWidget(self.place_holder)


    app = wd.QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec_())