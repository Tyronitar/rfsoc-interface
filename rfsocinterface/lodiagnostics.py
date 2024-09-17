import matplotlib
matplotlib.use('QtAgg')

from typing import Callable

from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QLabel, QSizePolicy, QGridLayout, QSpacerItem, QToolButton
from PySide6.QtCore import QPropertyAnimation, Qt, QRect, QSize
from PySide6.QtGui import QDoubleValidator, QIcon, QResizeEvent, QCursor
from matplotlib.figure import Figure
from matplotlib.backend_bases import MouseEvent, MouseButton, DrawEvent, PickEvent
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import time

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
        self.editing = False

        self.epsilon = 1e3  # Max x difference to count as a line hit
        self.dragging = False

        fig = self.resonator.plot()
        self.set_figure(fig)
        self.canvas.line.set_label('New Frequency')
        self.ax.axvline(self.resonator.tone, 0, 1, color='gray', linestyle='--', label='Old Frequency')
        self.ax.legend()

        # self.canvas.layout().addWidget(self.edit_toolButton)

        # self.canvas.stacked_layout.addWidget(ResonatorEditButton(self))
        # self.canvas.grid_layout.addWidget(self.edit_toolButton)
        # self.canvas.grid_layout.setCurrentIndex(1)
        # self.edit_toolButton.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        # self.edit_toolButton.raise_()
        # self.edit_toolButton.clicked.connect(self.toggle_edit)
        # self.edit_toolButton.setVisible(True)
        # self.canvas.lower()

        self.reset_pushButton.clicked.connect(self.reset_freq)

        self.old_freq_value_label.setText(f'{self.resonator.tone:.5f}')

        self.depth_value_label.setText('N/A')

        self.error_label = None
        freq_range = self.ax.get_xlim()
        self.validator = QDoubleValidator(freq_range[0], freq_range[1], 5, parent=self)
        self.new_freq_lineEdit.setValidator(self.validator)
        self.new_freq_lineEdit.textChanged.connect(self.change_freq)
        self.new_freq_lineEdit.setText(f'{self.resonator.fit_f0:.5f}')
    
    # def resizeEvent(self, event: QResizeEvent):

    #     super().resizeEvent(event)
    #     anchor_point = self.canvas.geometry().topRight()
    #     self.edit_toolButton.setGeometry(30, 30, anchor_point.x() - 40, anchor_point.y() - 40)
    #     self.edit_toolButton.update()

    def reset_freq(self):
        self.new_freq_lineEdit.setText(f'{self.resonator.fit_f0:.5f}')
    
    def change_freq(self):
        freq_range = self.ax.get_xlim()
        new_freq = self.new_freq_lineEdit.text()
        # print(new_freq)
        valid = self.validator.validate(new_freq, 0)[0]
        # if not self.new_freq_lineEdit.hasAcceptableInput():
        if not valid == QDoubleValidator.State.Acceptable:
            self.new_freq_lineEdit.setStyleSheet('background-color: "#FFCCCC"; border: 1px solid red;')
            if self.error_label is None:
                self.error_label = QLabel(self)
                self.error_label.setText(f'New frequency must be in the range [{freq_range[0]:.5f}, {freq_range[1]:.5f}]')
                self.error_label.setStyleSheet("color: red;")
                self.formLayout.insertRow(2, None, self.error_label)
        else:
            if self.error_label is not None:
                self.new_freq_lineEdit.setStyleSheet('')
                self.formLayout.removeRow(self.error_label)
                self.error_label = None
            new_freq = float(new_freq)
            self.new_freq_lineEdit.setStyleSheet("")
            self.canvas.line.set_xdata([new_freq, new_freq])
            self.figcanvas.draw_idle()
            self.delta_value_label.setText(f'{new_freq - self.resonator.tone:.5f}')

    def toggle_edit(self):
        print('clicked edit button')

    def set_figure(self, fig: Figure):
        self.canvas.set_figure(fig)

        self.ax = fig.axes[0]
        self.figcanvas = self.canvas.canvas

        self.figcanvas.mpl_connect('button_press_event', self.mouse_press)
        self.figcanvas.mpl_connect('button_release_event', self.mouse_release)
        self.figcanvas.mpl_connect('motion_notify_event', self.mouse_move)
    
    def is_close(self, xdata: float, epsilon: float=1e3) -> bool:
        d = np.abs(self.canvas.line.get_xdata()[0] - xdata)
        return d < self.epsilon


    def mouse_release(self, event: MouseEvent):
        if event.button != 1: return
        if event.inaxes != self.ax: return

        if self.dragging:
            self.dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.canvas.line.set_xdata([event.xdata, event.xdata])
            self.figcanvas.draw_idle()

    def mouse_press(self, event: MouseEvent):
        if event.inaxes != self.ax: return
        if event.button != 1: return

        if self.is_close(event.xdata):
            self.dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouse_move(self, event: MouseEvent):
        if event.inaxes != self.ax:
            self.canvas.line.set_linewidth('1.5')
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.dragging = False
            self.figcanvas.draw_idle()
            return
        if not self.dragging:
            if self.is_close(event.xdata):
                self.canvas.line.set_linewidth('3')
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.canvas.line.set_linewidth('1.5')
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.figcanvas.draw_idle()
            return
        if event.button != 1: return


        self.canvas.line.set_xdata([event.xdata, event.xdata])
        self.new_freq_lineEdit.setText(f'{event.xdata:.3f}')
        self.figcanvas.draw_idle()

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
        # rw.setWindowModality(Qt.WindowModality.ApplicationModal)
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
