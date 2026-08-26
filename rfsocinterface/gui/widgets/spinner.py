"""Loading spinner for indeterminate-length loading screens.

Code is from QtWaitingSpinner
- GitHub: https://github.com/theycallmek/QtWaitingSpinner-PySide6
- PyPi: https://pypi.org/project/pyqtspinner/

I'm copying it here, because it wasn't working just installing the package.

The MIT License (MIT)

Copyright (c) 2012-2014 Alexander Turkin
Copyright (c) 2014 William Hallatt
Copyright (c) 2015 Jacob Dawid
Copyright (c) 2016 Luca Weiss
Copyright (c) 2017 fbjorn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
import sys
from random import random
from typing import override

import numpy as np
from PySide6 import QtGui
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtCore import Slot as pyqtSlot
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

STANDARD_STICKY_SPINNER_SETTINGS = {
    'roundness': 100,
    'opacity': 100.0,
    'fade': 80,
    'radius': 15,
    'lines': 50,
    'line_length': 10,
    'line_width': 10,
    'speed': 0.7,
    'color': QColor(233, 84, 32),  # Ubuntu orange
}


# pylint: disable=too-many-instance-attributes,too-many-arguments
class WaitingSpinner(QWidget):
    """WaitingSpinner is a highly configurable, custom spinner widget."""

    def __init__(
        self,
        parent: QWidget = None,
        center_on_parent: bool = True,
        disable_parent_when_spinning: bool = False,
        modality: Qt.WindowModality = Qt.WindowModality.NonModal,
        roundness: float = 100.0,
        opacity: float = 3.0,
        fade: float = 80.0,
        lines: int = 20,
        line_length: int = 10,
        line_width: int = 2,
        radius: int = 10,
        speed: float = math.pi / 2,
        color: QColor | None = None,
    ) -> None:
        """Initialize a WaitingSpinner."""
        super().__init__(parent=parent)

        if color is None:
            color = QColor(0, 0, 0)

        self._center_on_parent: bool = center_on_parent
        self._disable_parent_when_spinning: bool = disable_parent_when_spinning

        self._color: QColor = color
        self._roundness: float = roundness
        self._minimum_trail_opacity: float = opacity
        self._trail_fade_percentage: float = fade
        self._revolutions_per_second: float = speed
        self._number_of_lines: int = lines
        self._line_length: int = line_length
        self._line_width: int = line_width
        self._inner_radius: int = radius
        self._current_counter: int = 0
        self._is_spinning: bool = False

        self._timer: QTimer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._update_size()
        self._update_timer()
        self.hide()

        self.setWindowModality(modality)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    @override
    def paintEvent(self, _: QPaintEvent) -> None:  # pylint: disable=invalid-name
        """Paint the WaitingSpinner."""
        self._update_position()
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._current_counter >= self._number_of_lines:
            self._current_counter = 0

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self._number_of_lines):
            painter.save()
            painter.translate(
                self._inner_radius + self._line_length,
                self._inner_radius + self._line_length,
            )
            rotate_angle = 360 * i / self._number_of_lines
            painter.rotate(rotate_angle)
            painter.translate(self._inner_radius, 0)
            distance = self._line_count_distance_from_primary(
                i, self._current_counter, self._number_of_lines
            )
            color = self._current_line_color(
                distance,
                self._number_of_lines,
                self._trail_fade_percentage,
                self._minimum_trail_opacity,
                self._color,
            )
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRect(
                    0,
                    -self._line_width // 2,
                    self._line_length,
                    self._line_width,
                ),
                self._roundness,
                self._roundness,
                Qt.SizeMode.RelativeSize,
            )
            painter.restore()

    def start(self) -> None:
        """Show and start spinning the WaitingSpinner."""
        self._update_position()
        self._is_spinning = True
        self.show()

        if self.parentWidget and self._disable_parent_when_spinning:
            self.parentWidget().setEnabled(False)

        if not self._timer.isActive():
            self._timer.start()
            self._current_counter = 0

    def stop(self) -> None:
        """Hide and stop spinning the WaitingSpinner."""
        self._is_spinning = False
        self.hide()

        if self.parentWidget() and self._disable_parent_when_spinning:
            self.parentWidget().setEnabled(True)

        if self._timer.isActive():
            self._timer.stop()
            self._current_counter = 0

    @property
    def color(self) -> QColor:
        """Return color of WaitingSpinner."""
        return self._color

    @color.setter
    def color(self, color: Qt.GlobalColor = Qt.GlobalColor.black) -> None:
        """Set color of WaitingSpinner."""
        self._color = QColor(color)

    @property
    def roundness(self) -> float:
        """Return roundness of WaitingSpinner."""
        return self._roundness

    @roundness.setter
    def roundness(self, roundness: float) -> None:
        """Set color of WaitingSpinner."""
        self._roundness = max(0.0, min(100.0, roundness))

    @property
    def minimum_trail_opacity(self) -> float:
        """Return minimum trail opacity of WaitingSpinner."""
        return self._minimum_trail_opacity

    @minimum_trail_opacity.setter
    def minimum_trail_opacity(self, minimum_trail_opacity: float) -> None:
        """Set minimum trail opacity of WaitingSpinner."""
        self._minimum_trail_opacity = minimum_trail_opacity

    @property
    def trail_fade_percentage(self) -> float:
        """Return trail fade percentage of WaitingSpinner."""
        return self._trail_fade_percentage

    @trail_fade_percentage.setter
    def trail_fade_percentage(self, trail: float) -> None:
        """Set trail fade percentage of WaitingSpinner."""
        self._trail_fade_percentage = trail

    @property
    def revolutions_per_second(self) -> float:
        """Return revolutions per second of WaitingSpinner."""
        return self._revolutions_per_second

    @revolutions_per_second.setter
    def revolutions_per_second(self, revolutions_per_second: float) -> None:
        """Set revolutions per second of WaitingSpinner."""
        self._revolutions_per_second = revolutions_per_second
        self._update_timer()

    @property
    def number_of_lines(self) -> int:
        """Return number of lines of WaitingSpinner."""
        return self._number_of_lines

    @number_of_lines.setter
    def number_of_lines(self, lines: int) -> None:
        """Set number of lines of WaitingSpinner."""
        self._number_of_lines = lines
        self._current_counter = 0
        self._update_timer()

    @property
    def line_length(self) -> int:
        """Return line length of WaitingSpinner."""
        return self._line_length

    @line_length.setter
    def line_length(self, length: int) -> None:
        """Set line length of WaitingSpinner."""
        self._line_length = length
        self._update_size()

    @property
    def line_width(self) -> int:
        """Return line width of WaitingSpinner."""
        return self._line_width

    @line_width.setter
    def line_width(self, width: int) -> None:
        """Set line width of WaitingSpinner."""
        self._line_width = width
        self._update_size()

    @property
    def inner_radius(self) -> int:
        """Return inner radius size of WaitingSpinner."""
        return self._inner_radius

    @inner_radius.setter
    def inner_radius(self, radius: int) -> None:
        """Set inner radius size of WaitingSpinner."""
        self._inner_radius = radius
        self._update_size()

    @property
    def is_spinning(self) -> bool:
        """Return actual spinning status of WaitingSpinner."""
        return self._is_spinning

    def _rotate(self) -> None:
        """Rotate the WaitingSpinner."""
        self._current_counter += 1
        if self._current_counter >= self._number_of_lines:
            self._current_counter = 0
        self.update()

    def _update_size(self) -> None:
        """Update the size of the WaitingSpinner."""
        size = (self._inner_radius + self._line_length) * 2
        self.setFixedSize(size, size)

    def _update_timer(self) -> None:
        """Update the spinning speed of the WaitingSpinner."""
        self._timer.setInterval(
            int(1000 / (self._number_of_lines * self._revolutions_per_second))
        )

    def _update_position(self) -> None:
        """Center WaitingSpinner on parent widget."""
        if self.parentWidget() and self._center_on_parent:
            self.move(self.parent().rect().center() - self.rect().center())

    @staticmethod
    def _line_count_distance_from_primary(
        current: int, primary: int, total_nr_of_lines: int
    ) -> int:
        """Return the amount of lines from _current_counter."""
        distance = primary - current
        if distance < 0:
            distance += total_nr_of_lines
        return distance

    @staticmethod
    def _current_line_color(
        count_distance: int,
        total_nr_of_lines: int,
        trail_fade_perc: float,
        min_opacity: float,
        color_input: QColor,
    ) -> QColor:
        """Returns the current color for the WaitingSpinner."""
        color = QColor(color_input)
        if count_distance == 0:
            return color
        min_alpha_f = min_opacity / 100.0
        distance_threshold = math.ceil(
            (total_nr_of_lines - 1) * trail_fade_perc / 100.0
        )
        if count_distance > distance_threshold:
            color.setAlphaF(min_alpha_f)
        else:
            alpha_diff = color.alphaF() - min_alpha_f
            gradient = alpha_diff / float(distance_threshold + 1)
            result_alpha = color.alphaF() - gradient * count_distance
            # If alpha is out of bounds, clip it.
            result_alpha = min(1.0, max(0.0, result_alpha))
            color.setAlphaF(result_alpha)
        return color


class StickyWaitingSpinner(WaitingSpinner):
    """Waiting spinner where the animation slows down and "bunches up" at the top."""

    def __init__(
        self,
        parent: QWidget = None,
        center_on_parent: bool = True,
        disable_parent_when_spinning: bool = False,
        modality: Qt.WindowModality = Qt.WindowModality.NonModal,
        roundness: float = 100.0,
        opacity: float = 3,
        fade: float = 80.0,
        lines: int = 20,
        line_length: int = 10,
        line_width: int = 2,
        radius: int = 10,
        speed: float = math.pi / 2,
        color: QColor | None = None,
    ) -> None:
        """Initialize a StickyWaitingSpinner."""
        self._primary_angle = 0
        if color is None:
            color = QColor(0, 0, 0)

        super().__init__(
            parent=parent,
            center_on_parent=center_on_parent,
            disable_parent_when_spinning=disable_parent_when_spinning,
            modality=modality,
            roundness=roundness,
            opacity=opacity,
            fade=fade,
            lines=lines,
            line_length=line_length,
            line_width=line_width,
            radius=radius,
            speed=speed,
            color=color,
        )

    @override
    def paintEvent(self, _: QPaintEvent) -> None:  # pylint: disable=invalid-name
        """Paint the WaitingSpinner."""
        self._update_position()
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._current_counter >= self._number_of_lines:
            self._current_counter = 0

        # primary_angle = 360 * self._current_counter / self._number_of_lines
        # self._current_angle = primary_angle
        dist = (self._primary_angle - 270 + 180) % 360 - 180
        alpha = 10
        sigma = 30
        normalization_factor = 20
        # normalization_factor = 1
        normalization_factor = self._revolutions_per_second / 60 * 1100
        current_angle = self._primary_angle
        self._primary_angle += (
            1 / (1 + alpha * np.exp(-(dist**2 / (2 * sigma**2)))) * normalization_factor
        )
        self._primary_angle %= 360

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self._number_of_lines):
            painter.save()
            painter.translate(
                self._inner_radius + self._line_length,
                self._inner_radius + self._line_length,
            )
            dist = (current_angle - 270 + 180) % 360 - 180
            rotate_angle = (
                1
                / (1 + alpha * np.exp(-(dist**2 / (2 * sigma**2))))
                * normalization_factor
                / 2
            )
            current_angle = (current_angle - rotate_angle) % 360
            # rotate_angle = 360 * i / self._number_of_lines
            painter.rotate(current_angle)
            painter.translate(self._inner_radius, 0)
            # distance = current_angle - self._primary_angle
            # distance = self._line_count_distance_from_primary(
            #     i, self._current_counter, self._number_of_lines
            # )
            color = self._current_line_color(
                i,
                self._number_of_lines,
                self._trail_fade_percentage,
                self._minimum_trail_opacity,
                self._color,
            )
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRect(
                    0,
                    -self._line_width // 2,
                    self._line_length,
                    self._line_width,
                ),
                self._roundness,
                self._roundness,
                Qt.SizeMode.RelativeSize,
            )
            painter.restore()

    def _update_timer(self) -> None:
        """Update the spinning speed of the WaitingSpinner."""
        self._timer.setInterval(int(1000 / 60))


# Code for determining the parameters I want:
class SpinnerConfigurator(QWidget):
    """Interactive GUI for configuring spinner settings."""

    sb_roundness = None
    sb_opacity = None
    sb_fadeperc = None
    sb_lines = None
    sb_line_length = None
    sb_line_width = None
    sb_inner_radius = None
    sb_rev_s = None

    btn_start = None
    btn_stop = None
    btn_pick_color = None

    spinner = None

    def __init__(self, sticky: bool = False) -> None:
        """Initialize a SpinnerConfigurator."""
        super().__init__()
        self.sticky = sticky
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize ui."""
        grid = QGridLayout()
        groupbox1 = QGroupBox()
        groupbox1_layout = QHBoxLayout()
        groupbox2 = QGroupBox()
        groupbox2_layout = QGridLayout()
        button_hbox = QHBoxLayout()
        self.setLayout(grid)
        self.setWindowTitle('QtWaitingSpinner Configurator')
        self.setWindowFlags(Qt.WindowType.Dialog)

        # SPINNER
        if self.sticky:
            self.spinner = StickyWaitingSpinner(self)
        else:
            self.spinner = WaitingSpinner(self)

        # Spinboxes
        self.sb_roundness = QDoubleSpinBox()
        self.sb_opacity = QDoubleSpinBox()
        self.sb_fadeperc = QDoubleSpinBox()
        self.sb_lines = QSpinBox()
        self.sb_line_length = QSpinBox()
        self.sb_line_width = QSpinBox()
        self.sb_inner_radius = QSpinBox()
        self.sb_rev_s = QDoubleSpinBox()

        # set spinbox default values
        self.sb_roundness.setValue(100)
        self.sb_roundness.setRange(0, 9999)
        self.sb_opacity.setValue(math.pi)
        self.sb_opacity.setRange(0, 9999)
        self.sb_fadeperc.setValue(80)
        self.sb_fadeperc.setRange(0, 9999)
        self.sb_lines.setValue(20)
        self.sb_lines.setRange(1, 9999)
        self.sb_line_length.setValue(10)
        self.sb_line_length.setRange(0, 9999)
        self.sb_line_width.setValue(2)
        self.sb_line_width.setRange(0, 9999)
        self.sb_inner_radius.setValue(10)
        self.sb_inner_radius.setRange(0, 9999)
        self.sb_rev_s.setValue(math.pi / 2)
        self.sb_rev_s.setRange(0.1, 9999)

        # Buttons
        self.btn_start = QPushButton('Start')
        self.btn_stop = QPushButton('Stop')
        self.btn_pick_color = QPushButton('Pick Color')
        self.btn_randomize = QPushButton('Randomize')
        self.btn_show_init = QPushButton('Show init args')

        # Connects
        self.sb_roundness.valueChanged.connect(
            lambda x: setattr(self.spinner, 'roundness', x)
        )
        self.sb_opacity.valueChanged.connect(
            lambda x: setattr(self.spinner, 'minimum_trail_opacity', x)
        )
        self.sb_fadeperc.valueChanged.connect(
            lambda x: setattr(self.spinner, 'trail_fade_percentage', x)
        )
        self.sb_lines.valueChanged.connect(
            lambda x: setattr(self.spinner, 'number_of_lines', x)
        )
        self.sb_line_length.valueChanged.connect(
            lambda x: setattr(self.spinner, 'line_length', x)
        )
        self.sb_line_width.valueChanged.connect(
            lambda x: setattr(self.spinner, 'line_width', x)
        )
        self.sb_inner_radius.valueChanged.connect(
            lambda x: setattr(self.spinner, 'inner_radius', x)
        )
        self.sb_rev_s.valueChanged.connect(
            lambda x: setattr(self.spinner, 'revolutions_per_second', x)
        )

        self.btn_start.clicked.connect(self.spinner.start)
        self.btn_stop.clicked.connect(self.spinner.stop)
        self.btn_pick_color.clicked.connect(self.show_color_picker)
        self.btn_randomize.clicked.connect(self._randomize)
        self.btn_show_init.clicked.connect(self.show_init_args)

        # Layout adds
        groupbox1_layout.addWidget(self.spinner)
        groupbox1.setLayout(groupbox1_layout)

        groupbox2_layout.addWidget(QLabel('Roundness:'), *(1, 1))
        groupbox2_layout.addWidget(self.sb_roundness, *(1, 2))
        groupbox2_layout.addWidget(QLabel('Opacity:'), *(2, 1))
        groupbox2_layout.addWidget(self.sb_opacity, *(2, 2))
        groupbox2_layout.addWidget(QLabel('Fade Perc:'), *(3, 1))
        groupbox2_layout.addWidget(self.sb_fadeperc, *(3, 2))
        groupbox2_layout.addWidget(QLabel('Lines:'), *(4, 1))
        groupbox2_layout.addWidget(self.sb_lines, *(4, 2))
        groupbox2_layout.addWidget(QLabel('Line Length:'), *(5, 1))
        groupbox2_layout.addWidget(self.sb_line_length, *(5, 2))
        groupbox2_layout.addWidget(QLabel('Line Width:'), *(6, 1))
        groupbox2_layout.addWidget(self.sb_line_width, *(6, 2))
        groupbox2_layout.addWidget(QLabel('Inner Radius:'), *(7, 1))
        groupbox2_layout.addWidget(self.sb_inner_radius, *(7, 2))
        groupbox2_layout.addWidget(QLabel('Rev/s:'), *(8, 1))
        groupbox2_layout.addWidget(self.sb_rev_s, *(8, 2))

        groupbox2.setLayout(groupbox2_layout)

        button_hbox.addWidget(self.btn_start)
        button_hbox.addWidget(self.btn_stop)
        button_hbox.addWidget(self.btn_pick_color)
        button_hbox.addWidget(self.btn_randomize)
        button_hbox.addWidget(self.btn_show_init)

        grid.addWidget(groupbox1, *(1, 1))
        grid.addWidget(groupbox2, *(1, 2))
        grid.addLayout(button_hbox, *(2, 1))

        self.spinner.start()
        self.show()

    @pyqtSlot(name='randomize')
    def _randomize(self) -> None:
        self.sb_roundness.setValue(random() * 1000)
        self.sb_opacity.setValue(random() * 50)
        self.sb_fadeperc.setValue(random() * 100)
        self.sb_lines.setValue(math.floor(random() * 150))
        self.sb_line_length.setValue(math.floor(10 + random() * 20))
        self.sb_line_width.setValue(math.floor(random() * 30))
        self.sb_inner_radius.setValue(math.floor(random() * 30))
        self.sb_rev_s.setValue(random())

    @pyqtSlot(name='show_color_picker')
    def show_color_picker(self) -> None:
        """Set the color for the spinner."""
        assert self.spinner
        self.spinner.color = QColorDialog.getColor()

    @pyqtSlot(name='show_init_args')
    def show_init_args(self) -> None:
        """Display used arguments."""
        assert self.spinner
        text = (
            f'WaitingSpinner(\n    parent,\n    '
            f'roundness={self.spinner.roundness},\n    '
            f'opacity={self.spinner.minimum_trail_opacity},\n    '
            f'fade={self.spinner.trail_fade_percentage},\n    '
            f'radius={self.spinner.inner_radius},\n    '
            f'lines={self.spinner.number_of_lines},\n    '
            f'line_length={self.spinner.line_length},\n    '
            f'line_width={self.spinner.line_width},\n    '
            f'speed={self.spinner.revolutions_per_second},\n    '
            f'color={self.spinner.color.getRgb()[:3]}\n)\n'
        )
        msg_box = QMessageBox()
        msg_box.setText(text)
        msg_box.setWindowTitle('Text was copied to clipboard')
        clipboard = QApplication.clipboard()
        clipboard.clear()
        clipboard.setText(text)
        print(text)  # noqa: T201
        msg_box.exec_()


def set_palette(my_app):
    """Set the color palette for the SpinnerConfigurator."""
    my_app.setStyle('Fusion')
    dark_palette = QtGui.QPalette()
    dark_color = QtGui.QColor(45, 45, 45)
    disabled_color = QtGui.QColor(127, 127, 127)
    white_color = QtGui.QColor(255, 255, 255)
    dark_palette.setColor(QtGui.QPalette.Window, dark_color)
    dark_palette.setColor(QtGui.QPalette.WindowText, white_color)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(18, 18, 18))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, dark_color)
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, white_color)
    dark_palette.setColor(QtGui.QPalette.ToolTipText, white_color)
    dark_palette.setColor(QtGui.QPalette.Text, white_color)
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, disabled_color)
    dark_palette.setColor(QtGui.QPalette.Button, dark_color)
    dark_palette.setColor(QtGui.QPalette.ButtonText, white_color)
    dark_palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, disabled_color
    )
    dark_palette.setColor(QtGui.QPalette.BrightText, QtGui.QColor(187, 134, 252))
    dark_palette.setColor(QtGui.QPalette.Link, QtGui.QColor(187, 134, 252))
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(187, 134, 252))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    dark_palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.HighlightedText, disabled_color
    )
    my_app.setPalette(dark_palette)
    my_app.setStyleSheet(
        'QToolTip { color: #ffffff; background-color: rgb(187, 134, 252); '
        'border: 0px solid white; }'
    )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    set_palette(app)
    configurator = SpinnerConfigurator(True)
    sys.exit(app.exec())
