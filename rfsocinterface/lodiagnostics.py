import matplotlib
matplotlib.use('QtAgg')

from typing import Callable

from PySide6.QtWidgets import QMainWindow, QApplication, QWidget
from PySide6.QtCore import QPropertyAnimation, Qt
from matplotlib.figure import Figure
from matplotlib.backend_bases import MouseEvent, MouseButton, DrawEvent
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from rfsocinterface.ui.lodiagnostics_ui import Ui_MainWindow as Ui_DiagnosticsWindow
from rfsocinterface.ui.loresonator_ui import Ui_MainWindow as Ui_ResonatorWindow
from rfsocinterface.ui.canvas import ScrollableCanvas, ResonatorCanvas
from rfsocinterface.ui.blit_manager import BlitManager
from rfsocinterface.losweep import fit_lo_sweep, get_tone_list, plot_lo_fit, LoSweep, ResonatorData

DPI = 100

class ResonatorWindow(QMainWindow, Ui_ResonatorWindow):
    def __init__(self, resonator: ResonatorData, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self.resonator = resonator

        fig = self.resonator.plot()
        self.canvas.set_figure(fig)


        self.figcanvas = self.canvas.canvas.figure.canvas
        self.ax = fig.axes[0]
        print(self.ax.get_lines())
        self.line = self.ax.get_lines()[1]
        # self.line.set_animated(True)

        self.bm = BlitManager(self.figcanvas)
        self.bm.add_artist(self.line)

        self.epsilon = 1e3  # Max x difference to count as a line hit
        self.dragging = False

        # self.figcanvas.mpl_connect('draw_event', self.on_draw)
        self.figcanvas.mpl_connect('button_press_event', self.mouse_press)
        self.figcanvas.mpl_connect('button_release_event', self.mouse_release)
        self.figcanvas.mpl_connect('motion_notify_event', self.mouse_move)

        # self.canvas.canvas.draw()
        # self.figcanvas.draw()
        self.bm.update()

    def on_draw(self, event: DrawEvent):
        self.background = self.figcanvas.copy_from_bbox(self.figcanvas.figure.bbox)
        self.ax.draw_artist(self.line)
        # do not need to blit here, this will fire before the screen is
        # updated

    def mouse_release(self, event: MouseEvent):
        if event.button != 1: return

        self.dragging = False

    def mouse_press(self, event: MouseEvent):
        if event.inaxes != self.ax: return
        if event.button != 1: return

        print(self.line.get_xydata())
        print(event.xdata)
        d = np.abs(self.line.get_xdata()[0] - event.xdata)
        print(d)
        if d < self.epsilon:
            print('now dragging')
            self.dragging = True


    def mouse_move(self, event):
        if not self.dragging: return
        if event.inaxes != self.ax: return
        if event.button != 1: return

        self.line.set_xdata([event.xdata] * 2)

        self.bm.update()

        # self.figcanvas.restore_region(self.background)
        # self.ax.draw_artist(self.line)
        # self.figcanvas.blit()
        # self.figcanvas.flush_events()
        # self.figcanvas.draw_idle()
        # self.figcanvas.draw()


class DiagnosticsWindow(QMainWindow, Ui_DiagnosticsWindow):

    def __init__(self, sweep: LoSweep, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self.sweep = sweep
        self.flagged_checkBox.clicked.connect(self.toggle_flagged)
        self.plot()
        self.rw: ResonatorWindow | None = None
    
    def click_plot(self, event: MouseEvent):
        axes = event.inaxes
        print(f'({event.x}, {event.y}) in ax {axes}')
        if axes is None or event.button == MouseButton(3):
            self.canvas.select_axis(None)
        elif event.button == MouseButton(1):
            self.canvas.select_axis(axes)
            if event.dblclick:
                print('Double Clicked')
                idx = self.canvas.canvas.figure.axes.index(axes)
                print(idx)
                resonator = self.sweep.resonator_data[idx]
                self.make_resonator_window(resonator)

    
    def make_resonator_window(self, resonator: ResonatorData):
        # def wrap_func(f: Callable):
        #     def override_close(*args):
        #         f(*args)
        #         # self.rw = None

        #     return override_close
        rw = ResonatorWindow(resonator, parent=self)
        rw.setWindowModality(Qt.WindowModality.ApplicationModal)
        # rw.closeEvent = wrap_func(rw.closeEvent)
            
        rw.show()

    
    def plot(self, fig_width=10):
        fig = self.sweep.plot(fig_width=fig_width)
        fig.canvas.mpl_connect('button_press_event', self.click_plot)
        self.canvas.set_figure(fig, self.sweep.flagged)
    
    def toggle_flagged(self):
        if self.flagged_checkBox.isChecked():
            self.canvas.hide_unflagged()
        else:
            self.canvas.show_all()
    
    def get_figure(self) -> Figure:
        return self.canvas.canvas.figure


if __name__ == '__main__':
    app = QApplication()

    sweep = LoSweep(
        get_tone_list('Default_tone_list.npy'),
        '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
        chanmask_file='chanmask.npy',
    )
    sweep.fit(do_print=True)

    w = DiagnosticsWindow(sweep)

    # ax = w.get_figure().axes[0]

    # fig, axes = plt.subplots(2, 2)
    # for ax in axes.ravel():
    #     ax.plot(np.arange(10), np.arange(10))
    # w.canvas.set_figure(fig, np.argwhere(1 == 1))

    w.show()
    # r.show()
    app.exec()
