
import numpy as np
import numpy.typing as npt
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from copy import deepcopy
from matplotlib.backend_bases import MouseEvent, MouseButton
import matplotlib.pyplot as plt

from rfsocinterface.losweep import plot_lo_fit

class ScrollableCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # self.scroll_area.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.scroll_area.setStyleSheet("QScrollArea {background-color:white;}");

        self.set_figure(Figure(figsize=(5, 5)))

        # self.nav = NavigationToolbar(self.canvas, self)
        
        self.setLayout(QVBoxLayout(self))
        # self.layout().addWidget(self.nav)
        self.layout().addWidget(self.scroll_area)

    def set_figure(self, fig: Figure):
        # self.canvas.figure.clf()
        # self.canvas.figure.axes.clear()
        self.canvas = FigureCanvas(fig)
        self.canvas.sizePolicy().setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.widget().setStyleSheet("background-color:white;");
        self.canvas.draw()

    
class ResonatorCanvas(QWidget):

    def __init__(self, parent=None, fig: Figure | None=None):
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(fig)
        self.set_figure(fig)

        self.setLayout(QVBoxLayout(self))
        self.layout().addWidget(self.canvas)
    
    def set_figure(self, fig: Figure):
        self.canvas.figure = fig
        self.canvas.draw()
    
    def set_axes(self, ax: plt.Axes):
        if len(self.canvas.figure.get_axes()) == 0:
            self.canvas.figure.add_axes(ax)
        else:
            self.canvas.figure.axes[0] = ax
        self.canvas.draw()


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
        self.canvas.figure.canvas.mpl_connect('button_press_event', self.click_plot)
    
    def show_all(self):
        for ax in self.unflagged:
            ax.set_visible(True)
            ax.draw(self.canvas.get_renderer())
        self.canvas.blit()

    def hide_unflagged(self): 
        for ax in self.unflagged:
            ax.set_visible(False)
        self.canvas.figure.draw(self.canvas.get_renderer())
        self.canvas.blit()
    
    def click_plot(self, event: MouseEvent):
        axes = event.inaxes
        if axes is None or event.button == MouseButton(3):
            self.select_axis(None)
        elif event.button == MouseButton(1):
            if event.dblclick:
                print('Double Clicked')
            else:
                self.select_axis(axes)
                print(f'({event.x}, {event.y}) in ax {axes}')

    def select_axis(self, axes: plt.Axes | None):
        # Deselect previous axes
        if self.selected_axes is not None:
            self.selected_axes.patch.set_linewidth(6)
            self.selected_axes.patch.set_edgecolor('w')
            self.selected_axes.patch.draw(self.canvas.get_renderer())
            self.selected_axes.patch.set_linewidth(0)
            self.selected_axes.patch.draw(self.canvas.get_renderer())
            # self.selected_axes.set_facecolor(self.selected_axes.get_facecolor())
            self.selected_axes.draw(self.canvas.get_renderer())
        if axes is not None:
            axes.patch.set_linewidth(5)
            axes.patch.set_edgecolor('cornflowerblue')
            axes.patch.draw(self.canvas.get_renderer())
            axes.draw(self.canvas.get_renderer())
            # self.canvas.blit(axes.patch.get_clip_box())
        self.canvas.blit()
        self.canvas.flush_events()
        self.selected_axes = axes
