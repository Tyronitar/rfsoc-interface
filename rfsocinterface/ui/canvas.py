
import numpy as np
import numpy.typing as npt
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QSizePolicy, QGraphicsView, QStackedLayout, QGridLayout, QToolButton
from PySide6.QtCore import Qt, QObject, QEvent, QCoreApplication, QRect, QSize
from PySide6.QtGui import QWheelEvent, QIcon
from time import sleep

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation
from copy import deepcopy
from matplotlib.backend_bases import MouseEvent, MouseButton, DrawEvent
import matplotlib.pyplot as plt

from rfsocinterface.losweep import plot_lo_fit
from rfsocinterface.ui.blit_manager import BlitManager
from rfsocinterface.ui.editbutton import ResonatorEditButton

class ScrollableCanvas(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

        # self.scroll_area = QScrollArea(self)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # self.scroll_area.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setStyleSheet("QScrollArea {background-color:white;}");

        self.set_figure(Figure(figsize=(5, 5)))

        # self.nav = NavigationToolbar(self.canvas, self)
        
        self.setLayout(QVBoxLayout(self))
        # self.layout().addWidget(self.nav)
        self.layout().addWidget(self.canvas)
        self.layout().installEventFilter(self)

        # self.wheelEvent = self.wheelEvent
        # self.canvas.wheelEvent = self.wheelEvent

    def set_figure(self, fig: Figure):
        # self.canvas.figure.clf()
        # self.canvas.figure.axes.clear()
        self.canvas = FigureCanvas(fig)
        self.canvas.sizePolicy().setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setWidget(self.canvas)
        self.widget().setStyleSheet("background-color:white;");

        self.bm = BlitManager(self.canvas)
    
    def eventFilter(self, obj: QObject, event: QEvent):
        if isinstance(event, QWheelEvent):
            vangle = event.angleDelta().y()
            vbar = self.verticalScrollBar()
            if vangle > 0:
                vbar.setValue(max(vbar.minimum(), vbar.value() - vangle / 2))
            else:
                vbar.setValue(min(vbar.maximum(), vbar.value() - vangle / 2))
            return True
        return super().eventFilter(obj, event)
    

class ResonatorCanvas(QWidget):

    def __init__(self, parent=None, fig: Figure | None=None):
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(fig)
        self.canvas.figure = fig
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.canvas)

        # self.setLayout(QGridLayout())
        # self.layout().addWidget(self.canvas, 1, 1)
        # self.stacked_layout.setCurrentIndex(1)
        # self.layout().addWidget(self.canvas)

        # self.edit_toolButton = QToolButton(self)
        # self.edit_toolButton.setObjectName(u"edit_toolButton")
        # self.edit_toolButton.setGeometry(QRect(750, 10, 27, 26))
        # self.edit_toolButton.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        # self.edit_toolButton.setAutoFillBackground(False)
        # icon = QIcon()
        # icon.addFile(u":/icons/edit.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        # self.edit_toolButton.setIcon(icon)
        # self.edit_toolButton.setIconSize(QSize(20, 20))

        # self.layout().addWidget(self.edit_toolButton, 0, 1)

    
    def update_figure(self):
        print(self.line.get_xydata())
        self.update()
    
    def set_figure(self, fig: Figure | None):
        self.canvas.figure = fig
        if fig is not None:
            # self.bm = BlitManager(self.canvas)
            ax = fig.get_axes()[0]
            self.line = ax.get_lines()[1]
            # print(self.line.get_xydata())
            # self.bm.add_artist(ax, self.line)
    

class DiagnosticsCanvas(ScrollableCanvas):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_axes: plt.Axes | None = None

    def set_figure(self, fig: Figure, flagged: npt.NDArray | None=None):
        if flagged is None:
            self.unflagged = fig.axes.copy()
        else:
            self.unflagged = np.delete(fig.axes, flagged)
        super().set_figure(fig)
        for ax in self.canvas.figure.axes:
            self.bm.add_artist(fig, ax.patch)
            self.bm.add_artist(fig, ax)
        # self.canvas.blit()
        # self.canvas.flush_events()
        # self.canvas.figure.canvas.mpl_connect('button_press_event', self.click_plot)

    def show_all(self):
        for ax in self.unflagged:
            # self.canvas.restore_region(self.bg, ax.bbox)
            ax.set_visible(True)
            ax.patch.set_visible(True)
            # self.canvas.figure.draw_artist(ax.patch)
            # self.canvas.figure.draw_artist(ax)
            # ax.draw_artist(ax.patch)
            # self.canvas.blit(ax.bbox)
            # ax.draw(self.canvas.get_renderer())
            # self.canvas.blit(ax.patch.get_clip_box())
        # self.canvas.figure.canvas.draw()
        # self.canvas.figure.canvas.blit()
        # self.canvas.figure.canvas.flush_events()
        self.bm.update()

    def hide_unflagged(self): 
        # self.canvas.restore_region(self.bg)
        for ax in self.unflagged:
            ax.set_visible(False)
            ax.patch.set_visible(False)
            # self.canvas.figure.draw_artist(ax.patch)
            # self.canvas.figure.draw_artist(ax)

        # self.canvas.restore_region(self._bg)
        # self._draw_animated()
        # self.canvas.blit()
            # self.canvas.figure.draw_artist(ax.patch)
            # ax.draw_artist(ax)
            # ax.draw(self.canvas.get_renderer())
            # self.canvas.blit(ax.patch.get_clip_box())
        # self.canvas.figure.draw(self.canvas.get_renderer())
        # self.canvas.figure.canvas.draw()
        # self.canvas.figure.canvas.blit()
        # self.canvas.figure.canvas.flush_events()
        self.bm.update()

    def select_axis(self, axes: plt.Axes | None):
        # Deselect previous axes
        fig = self.canvas.figure
        if self.selected_axes is not None:
            # bbox = self.selected_axes.patch.get_clip_box()
            # self.canvas.restore_region(self._bg, bbox)
            self.selected_axes.patch.set_linewidth(6)
            self.selected_axes.patch.set_edgecolor('w')
            # self.selected_axes.patch.draw(self.canvas.get_renderer())
            fig.draw_artist(self.selected_axes.patch)
            self.selected_axes.patch.set_linewidth(0)
            # self.selected_axes.patch.draw(self.canvas.get_renderer())
            fig.draw_artist(self.selected_axes.patch)
            fig.draw_artist(self.selected_axes)
            # self.selected_axes.set_facecolor(self.selected_axes.get_facecolor())
            # self.selected_axes.draw(self.canvas.get_renderer())
            # self.canvas.blit(bbox)
        if axes is not None:
            # self.canvas.restore_region(self._bg, axes.patch.get_clip_box())
            axes.patch.set_linewidth(5)
            axes.patch.set_edgecolor('cornflowerblue')
            # axes.patch.draw(self.canvas.get_renderer())
            fig.draw_artist(axes.patch)
            fig.draw_artist(axes)
            # axes.draw(self.canvas.get_renderer())
            # self.canvas.blit(axes.patch.get_clip_box())
        self.canvas.blit()
        self.canvas.flush_events()
        # self.canvas.figure.canvas.blit()
        # self.canvas.figure.canvas.flush_events()
        self.selected_axes = axes
