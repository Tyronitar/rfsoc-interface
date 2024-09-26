import matplotlib as mpl
import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

mpl.use('QtAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from rfsocinterface.ui.blit_manager import BlitManager


class ScrollableCanvas(QScrollArea):
    """Widget for displating a Matplotlib canvas in a scroll area."""

    def __init__(self, parent=None):
        """Initialize a ScrollableCanvas."""
        super().__init__(parent)

        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet('QScrollArea {background-color:white;}')

        self.set_figure(Figure(figsize=(5, 5)))

        self.setLayout(QVBoxLayout(self))
        self.layout().addWidget(self.canvas)
        self.layout().installEventFilter(self)

    def set_figure(self, fig: Figure):
        """Set the figure for this widget's canvas."""
        self.canvas = FigureCanvas(fig)
        self.canvas.sizePolicy().setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setWidget(self.canvas)
        self.widget().setStyleSheet('background-color:white;')
        self.bm = BlitManager(self.canvas)

    def eventFilter(self, obj: QObject, event: QEvent):
        """Filter all mouse scroll events inside the canvas."""
        if isinstance(event, QWheelEvent):
            vangle = event.angleDelta().y()
            hangle = event.angleDelta().x()
            vbar = self.verticalScrollBar()
            hbar = self.verticalScrollBar()
            # Vertical scrolling
            if vangle > 0:
                vbar.setValue(max(vbar.minimum(), vbar.value() - vangle / 2))
            else:
                vbar.setValue(min(vbar.maximum(), vbar.value() - vangle / 2))

            # Horizontal scrolling
            if hangle > 0:
                hbar.setValue(max(hbar.minimum(), hbar.value() - hangle / 2))
            else:
                hbar.setValue(min(hbar.maximum(), hbar.value() - hangle / 2))
            return True
        return super().eventFilter(obj, event)


class ResonatorCanvas(QWidget):
    """Widget for displaying the data for a single resonator and adjusting the fit."""

    def __init__(self, parent=None, fig: Figure | None = None):
        """Initialize a ResonatorCanvas."""
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(fig)
        self.canvas.figure = fig
        # self.nav = NavigationToolbar(self.canvas, self)

        self.setLayout(QVBoxLayout())
        # self.layout().addWidget(self.nav)
        self.layout().addWidget(self.canvas)

    def update_figure(self):
        """Update the figure of this widget."""
        self.update()

    def set_figure(self, fig: Figure | None):
        """Set the figure of this widget."""
        self.canvas.figure = fig
        if fig is not None:
            ax = fig.get_axes()[0]
            self.line = ax.get_lines()[1]


class DiagnosticsCanvas(ScrollableCanvas):
    """Widget for displaying all the resonator plots from an LO sweep."""

    def __init__(self, parent=None):
        """Initialize a DiagnosticsCanvas."""
        super().__init__(parent)
        self.selected_axes: plt.Axes | None = None

    def set_figure(self, fig: Figure):
        """Set the figure of this canvas."""
        self.unflagged = fig.axes.copy()
        super().set_figure(fig)
        # All of the axes need to be animated, so add them to the blit manager
        for ax in self.canvas.figure.axes:
            self.bm.add_artist(fig, ax.patch)
            self.bm.add_artist(fig, ax)

    def set_flagged(self, flagged: npt.NDArray):
        """Update the list of flagged plots."""
        self.unflagged = np.delete(self.canvas.figure.axes, flagged)

    def show_all(self):
        """Show all axes."""
        for ax in self.unflagged:
            ax.set_visible(True)
            ax.patch.set_visible(True)
        self.bm.update()

    def hide_unflagged(self):
        """Hide all the unflagged axes."""
        for ax in self.unflagged:
            ax.set_visible(False)
            ax.patch.set_visible(False)
        self.bm.update()

    def select_axis(self, axes: plt.Axes | None):
        """Select the provided axes.

        Draws a blue highlight around the axes and deselects the previous axes if there
        was one.
        """
        fig = self.canvas.figure
        # Deselect previous axes
        if self.selected_axes is not None:
            ax = self.selected_axes
            # Clear the blue outline by drawing a white outline over it
            ax.patch.set_linewidth(6)
            ax.patch.set_edgecolor('w')
            fig.draw_artist(ax.patch)

            ax.patch.set_linewidth(0)
            self.bm.update_artists([
                (ax.patch, ax.patch.get_tightbbox()),
                (ax, ax.bbox),
            ])
        # Select new axes
        if axes is not None:
            axes.patch.set_linewidth(5)
            axes.patch.set_edgecolor('cornflowerblue')
            self.bm.update_artists([
                (axes.patch, axes.patch.get_clip_box()),
                (axes, axes.bbox),
            ])
        self.selected_axes = axes
        self.canvas.blit()
        self.canvas.flush_events()
