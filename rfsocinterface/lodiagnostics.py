import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtWidgets import QMainWindow, QApplication
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from rfsocinterface.ui.lodiagnostics_uic import Ui_MainWindow as Ui_DiagnosticsWindows
from rfsocinterface.ui.canvas import ScrollableCanvas
from rfsocinterface.losweep import fit_lo_sweep, get_tone_list, plot_lo_fit

DPI = 100

class DiagnosticsWindow(QMainWindow, Ui_DiagnosticsWindows):

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.flagged_checkBox.clicked.connect(self.toggle_flagged)
    
    def create_lo_plot(
        self,
        tone_list: npt.NDArray,
        sweep_file: str,
        chanmask_file: str,
        fit_f0: npt.NDArray,
    ):
        fig, flagged = plot_lo_fit(tone_list, sweep_file, chanmask_file, fit_f0, fig_width=10)
        self.canvas.set_figure(fig, flagged)
    
    def toggle_flagged(self):
        if self.flagged_checkBox.isChecked():
            self.canvas.hide_unflagged()
        else:
            self.canvas.show_all()


if __name__ == '__main__':
    app = QApplication()
    w = DiagnosticsWindow()

    # fit_f0, _, _,= fit_lo_sweep(
    #     get_tone_list('Default_tone_list.npy'),
    #     '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
    #     chanmask_file='chanmask.npy',
    #     do_print=True,
    # )

    # w.create_lo_plot(
    #     get_tone_list('Default_tone_list.npy'),
    #     '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
    #     'chanmask.npy',
    #     fit_f0,
    # )

    fig, axes = plt.subplots(2, 2)
    for ax in axes.ravel():
        ax.plot(np.arange(10), np.arange(10))
    w.canvas.set_figure(fig, np.argwhere(1 == 1))

    w.show()
    app.exec()
