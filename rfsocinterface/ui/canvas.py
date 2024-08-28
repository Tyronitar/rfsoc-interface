
import numpy as np
import numpy.typing as npt
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from copy import deepcopy

from rfsocinterface.losweep import plot_lo_fit

class ScrollableCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.canvas = FigureCanvas(Figure(figsize=(5, 5)))
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.canvas)

        # self.nav = NavigationToolbar(self.canvas, self)
        
        self.setLayout(QVBoxLayout(self))
        # self.layout().addWidget(self.nav)
        self.layout().addWidget(self.scroll_area)

    def set_figure(self, fig: Figure):
        # self.canvas.figure.clf()
        # self.canvas.figure.axes.clear()
        self.canvas = FigureCanvas(fig)
        self.scroll_area.setWidget(self.canvas)
        self.canvas.draw()


class DiagnosticsCanvas(ScrollableCanvas):
    def __init__(self, parent=None):
        super().__init__(parent)

    def set_figure(self, fig: Figure, flagged: npt.NDArray):
        self.fig = fig
        self.unflagged = np.delete(self.fig.axes, flagged)
        super().set_figure(fig)
    
    def show_all(self):
        for ax in self.unflagged:
            ax.set_visible(True)
        self.canvas.draw()

    def hide_unflagged(self): 
        for ax in self.unflagged:
            ax.set_visible(False)
        self.canvas.draw()