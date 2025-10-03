from __future__ import annotations

import matplotlib as mpl

mpl.use('QtAgg')

from typing import Callable
from pathlib import Path
from concurrent.futures import Future
import logging

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, SignalInstance
from PySide6.QtGui import QDoubleValidator, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QWidget,
    QDialog,
    QMessageBox,
    QLayout,
    QPushButton,
    QSizeGrip,
    QFileDialog,
    QAbstractButton
)

from rfsocinterface.core.losweep import LoSweepData, ResonatorData, get_tone_list
from rfsocinterface.gui.uic.lodiagnostics_ui import Ui_Dialog as Ui_DiagnosticsDialog
from rfsocinterface.gui.uic.loresonator_ui import Ui_Dialog as Ui_ResonatorDialog
from rfsocinterface.gui.widgets.progress_bar import QThreadJobProgressDialog
from rfsocinterface.core.utils import ensure_path

_logger = logging.getLogger(__name__)

DPI = 100

EPSILON = 1e-6  # Max x difference in Hz to count as the mouse being close to the line


class ResonatorDialog(QDialog, Ui_ResonatorDialog):
    """Window displaying information about the resonator.

    Attributes:
        resonator (ResonatorData): The data for the resonator corresponding to this
            window.
        dragging (bool): Whether the line is currently being dragged.
        ax (plt.Axes): The axes in which the data is plotted.
        figcanvas (matplotlib.backends.backend_qtagg.FigureCanvasQTAgg): The canvas
            responsible for drawing / displaying the plot.
        error_label (QLabel | None): The error label to display when the provided
            frequency is outside of the bounds of the plot. If None, then there is no
            error.
    """

    def __init__(self, resonator: ResonatorData, parent: QWidget | None = None):
        """Initialize a ResonatorWindow."""
        super().__init__(parent=parent)
        self.setupUi(self)
        self.layout().addWidget(QSizeGrip(self))
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.resonator = resonator
        self.dragging = False
        self.error_label = None

        self.setWindowTitle(f'Resonator {self.resonator.idx}')

        # Setup the plot
        fig = self.resonator.plot()
        self.set_figure(fig)
        self.canvas.line.set_label('New Frequency')
        self.ax.axvline(
            self.resonator.tone,
            0,
            1,
            color='gray',
            linestyle='--',
            label='Old Frequency',
        )
        self.ax.legend()

        # Fill in the necessary values in the UI
        self.old_freq_value_label.setText(f'{self.resonator.tone * 1e-6:.5f}')
        self.depth_value_label.setText('N/A')  # TODO: Resonance depth

        # Temporary values for saving / undoing changes
        self.temp_fit_f0 = resonator.fit_f0
        self.temp_fit_qc = resonator.fit_qc
        self.temp_fit_qi = resonator.fit_qi

        # Setup text validator
        freq_range = self.ax.get_xlim()
        self.validator = QDoubleValidator(
            freq_range[0] * 1e-6, freq_range[1] * 1e-6 + 0.001, 9, parent=self
        )
        self.new_freq_lineEdit.setValidator(self.validator)

        # Setup connections to signals
        self.buttonBox.accepted.connect(self.accept_changes)
        # self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self.reset_freq
        )
        self.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject_changes
        )
        self.refit_pushButton.clicked.connect(self.refit)
        self.new_freq_lineEdit.textEdited.connect(self.change_freq)

        # This line will call change_freq since the signal has been connected
        self.move_line(self.resonator.fit_f0)

    
    @property
    def _editing(self) -> bool:
        """Return whether the plot is in editing mode."""
        return self.canvas.manager.toolmanager.active_toggle['default'] == 'edit'

    def accept_changes(self):
        """Handle accepting changes."""
        self.resonator.fit_f0 = self.temp_fit_f0
        self.resonator.fit_qc = self.temp_fit_qc
        self.resonator.fit_qi = self.temp_fit_qi
        plt.close(self.canvas.canvas.figure)
        self.accept()

    def reject_changes(self):
        """Handle rejecting changes."""
        plt.close(self.canvas.canvas.figure)
        self.reject()
    
    def move_line(self, x: float, update_line_edit: bool=True):
        """Move the line to the specified x value."""
        self.temp_fit_f0 = x
        self.canvas.line.set_xdata([x, x])
        self.figcanvas.draw_idle()
        self.delta_value_label.setText(
            f'{(x - self.resonator.tone) * 1e-3:.3f}'
        )
        if update_line_edit:
            self.new_freq_lineEdit.setText(f'{x * 1e-6:.9f}')

    def refit(self):
        """Refit the resonator."""
        fit_f0, fit_qc, fit_qi = self.resonator.fit(
            self.resonator.data.df, self.temp_fit_f0
        )
        self.temp_fit_f0 = fit_f0
        self.temp_fit_qc = fit_qc
        self.temp_fit_qi = fit_qi
        self.move_line(np.real(fit_f0))

    def reset_freq(self):
        """Reset the line to the initial frequency."""
        self.move_line(self.resonator.fit_f0)

    def change_freq(self):
        """Handle changes to the frequency in the lineEdit."""
        freq_range = self.ax.get_xlim()
        new_freq = self.new_freq_lineEdit.text() 

        valid = self.validator.validate(new_freq, 0)[0]

        if valid != QDoubleValidator.State.Acceptable:  # Value is invalid
            # Highlight in red
            self.new_freq_lineEdit.setStyleSheet(
                'background-color: "#FFCCCC"; border: 1px solid red;'
            )

            # Create the error_label if needed
            if self.error_label is None:
                self.error_label = QLabel(self)
                self.error_label.setText(
                    f'New frequency must be in the range [{freq_range[0] * 1e-6:.3f}, {freq_range[1] * 1e-6:.3f}] MHz'
                )
                self.error_label.setStyleSheet('color: red;')
                self.formLayout.insertRow(2, None, self.error_label)
        else:  # Value is valid
            # Remove the error label since the value is valid
            if self.error_label is not None:
                self.new_freq_lineEdit.setStyleSheet('')
                self.formLayout.removeRow(self.error_label)
                self.error_label = None
            self.new_freq_lineEdit.setStyleSheet('')

            # Update the line's position
            new_freq = float(new_freq) * 1e6  # Convert MHz to Hz
            self.move_line(new_freq, update_line_edit=False)

    def set_figure(self, fig: Figure):
        """Change the figure in the canvas."""
        self.canvas.set_figure(fig)

        self.ax = fig.axes[0]
        self.figcanvas = self.canvas.canvas

        # Setup the event handling logic to click and drag the line
        self.figcanvas.mpl_connect('button_press_event', self.mouse_press)
        self.figcanvas.mpl_connect('button_release_event', self.mouse_release)
        self.figcanvas.mpl_connect('motion_notify_event', self.mouse_move)

    def close_to_line(self, xdata: float, epsilon: float = EPSILON) -> bool:
        """Return whether a value is close to the line."""
        return np.allclose(self.canvas.line.get_xdata()[0], xdata, rtol=epsilon)
    
    def mouse_release(self, event: MouseEvent):
        """Handle releasing a mouse button."""
        if not self._editing:
            return 
        if event.button != 1:
            return  # Not left click
        if event.inaxes != self.ax:
            return  # Not inside the plot

        if self.dragging:
            # Stop dragging and update the line's position
            self.dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.move_line(event.xdata)

    def mouse_press(self, event: MouseEvent):
        """Handle left clicking."""
        if not self._editing:
            return 
        if event.button != 1:
            return  # Not left button
        if event.inaxes != self.ax:
            return  # Not in the plot

        # Move the line to the mouse when double clicking
        if event.dblclick:
            self.move_line(event.xdata)

        # Begin dragging if close to the line
        if self.close_to_line(event.xdata):
            self.dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouse_move(self, event: MouseEvent):
        """Handle mouse movement."""
        if not self._editing:
            return 
        # If mouse moves out of plot, unhighlight the line and stop dragging
        if event.inaxes != self.ax:
            self.canvas.line.set_linewidth('1.5')
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.dragging = False
            self.figcanvas.draw_idle()
            return
        if not self.dragging:
            # Check if the mouse is close to the line and highlight it if so
            if self.close_to_line(event.xdata):
                self.canvas.line.set_linewidth('3')
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.canvas.line.set_linewidth('1.5')
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.figcanvas.draw_idle()
            return

        # Moving while holding left mouse and dragging, so update the line's position
        self.move_line(event.xdata)


class DiagnosticsDialog(QDialog, Ui_DiagnosticsDialog):
    """Window displaying all resonator plots.

    Attributes:
        sweep (LoSweepData): The relevant LO sweep data.
    """

    def __init__(self, sweep: LoSweepData, savefile: PathLike, parent: QWidget | None = None):
        """Initialize a DiagnosticsWindow."""
        super().__init__(parent=parent)
        self.setupUi(self)
        self.set_sweep(sweep)
        self.savefile = Path(savefile)
        self.flagged_checkBox.clicked.connect(self.toggle_unflagged)
        self.buttonBox.clicked.connect(self.click_button_box)
        self.save_plots_pushButton.clicked.connect(self.save_plots_as)

        self.edited = False
    
    def click_button_box(self, button: QAbstractButton):
        if self.buttonBox.buttonRole(button) == QDialogButtonBox.ButtonRole.DestructiveRole:
            self.close_without_saving()
        elif self.buttonBox.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
            self.accept()
    
    def set_sweep(self, sweep: LoSweepData):
        self.sweep = sweep
        self.update_median_shift()
    
    def save_plots(self):
        savefile = self.savefile.with_suffix('.png')
        self.get_figure().savefig(savefile)
        _logger.info(f'Saved plots to {savefile}')

    def save_plots_as(self):
        folder = self.savefile.parent
        fname, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption='Save Plot',
            dir=str(folder),
            filter='Images (*.png *.jpg *.xpm);;PDF (*.pdf);;All Files (*)'
        )
        if fname:
            fig = self.get_figure()
            if Path(fname).suffix == 'pdf':
                with PdfPages(fname) as pdf:
                    pdf.savefig(fig)
            else:
                fig.savefig(fname)
    
    def closeEvent(self, event: QCloseEvent):
        if self.edited:
            if not self.close_without_saving():
                event.ignore()
                return
        event.accept()

    def close_without_saving(self) -> bool:
        if not self.edited:
            self.reject()
            return True

        msg = QMessageBox(
            QMessageBox.Icon.Warning,
            f'Do you want to save the changes you made to {self.savefile.stem}?',
            'Your changes will be lost if you don\'t save them',
            parent=self
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        ret = msg.exec()
        match ret:
            case QMessageBox.StandardButton.Save:
                self.accept()
                return True
            case QMessageBox.StandardButton.Cancel:
                return False  # Don't close
            case QMessageBox.StandardButton.Discard:
                self.reject()
                return True
            case _:
                raise RuntimeError(f'Unexpected option returned from QMessageBox: {ret}')


    def click_plot(self, event: MouseEvent):
        """Handle clicking the plots."""
        axes = event.inaxes
        if axes is None or event.button == MouseButton(3):
            self.canvas.select_axis(None)  # Deselect the currently selected plot
        elif event.button == MouseButton(1):
            self.canvas.select_axis(axes)  # Select the clicked axes

            # If double clicking, open a new resonator window
            if event.dblclick:
                idx = self.canvas.canvas.figure.axes.index(axes)
                resonator = self.sweep.resonator_data[idx]
                self.make_resonator_window(resonator, axes)

    def redraw_axes(self, resonator: ResonatorData, ax: plt.Axes):
        """Redraw the specified axes."""
        ax.cla()
        resonator.plot(ax)
        self.get_figure().draw_artist(ax.patch)
        self.get_figure().draw_artist(ax)
        self.canvas.select_axis(self.canvas.selected_axes)
        self.update_median_shift()
    
    def update_median_shift(self):
        self.median_shift_label.setText(
            f'Median shift (KHz): {np.median(self.sweep.difference[self.sweep.onres_ind]) * 1e-3:.2f}'
        )
    
    def set_edited(self):
        self.edited = True
        self.setWindowTitle('*LO Sweep Diagnostics')


    def make_resonator_window(self, resonator: ResonatorData, ax: plt.Axes):
        """Create and open a ResonatorWindow using the provided ResonatorData."""

        rw = ResonatorDialog(resonator, parent=self)
        rw.finished.connect(lambda _: self.redraw_axes(resonator, ax))
        rw.accepted.connect(self.set_edited)

        rw.show()

    def set_figure(self, fig: Figure):
        fig.canvas.mpl_connect('button_press_event', self.click_plot)
        self.canvas.set_figure(fig)
        self.canvas.set_flagged(self.sweep.flagged)

    def plot(self, fig_width=15, pd: QThreadJobProgressDialog | None=None) -> tuple[Figure, Future]:
        """Plot all of the resonators."""
        return self.make_plot(fig_width=fig_width, pd=pd)
        fig = self.make_plot(fig_width=fig_width, pd=pd)
        self.set_figure(fig)
    
    def make_plot(self, fig_width=15, pd: QThreadJobProgressDialog | None=None) -> tuple[Figure, Future]:
        return self.sweep.plot(ncols=fig_width, pd=pd)

    def toggle_unflagged(self):
        """Toggle whether the unflagged resonator plots are shown."""
        self.canvas.set_flagged(self.sweep.flagged)
        if self.flagged_checkBox.isChecked():
            self.canvas.hide_unflagged()
        else:
            self.canvas.show_all()

    def get_figure(self) -> Figure:
        """Return the window's figure."""
        return self.canvas.canvas.figure
    
    @classmethod
    @ensure_path(1)
    def from_h5(cls, filepath: Path, parent: QWidget | None = None) -> DiagnosticsDialog:
        """Create a DiagnosticsDialog from an HDF5 file."""
        sweep = LoSweepData.from_h5(filepath)
        dialog = cls(sweep, savefile=filepath, parent=parent)

        pd = QThreadJobProgressDialog(labelText='Plotting LO Sweep...', maximum=sweep.nchan, parent=parent)
        pd.show()

        fig, future = dialog.plot(pd=pd)
        dialog.set_figure(fig)

        future.add_done_callback(lambda _: fig.tight_layout())
        future.add_done_callback(lambda _: dialog.update_median_shift())
        # future.add_done_callback(lambda _: dial.set_figure(fig))
        return dialog


if __name__ == '__main__':
    from concurrent.futures import wait
    import pdb
    app = QApplication()
    sweep = LoSweepData.from_h5('/data/20250916/20250916_Be231102p2_100_tones_LO_Sweep_hour15p8722_high_res.npy')
    pdb.set_trace()


    win = QMainWindow()
    pbutt = QPushButton('Start', parent=win)
    win.setCentralWidget(pbutt)

    def fit(sweep):
        pd = QThreadJobProgressDialog(labelText='Fitting LO Sweep...',  maximum=sweep.ngoodchan, parent=win)
        pd.setAutoClose(False)
        pd.show()
        QApplication.processEvents()

        # future = sweep.fit(pd=pd)
        # wait([future])
        # future.result()
        plot(sweep, pd)
        # future.add_done_callback(lambda _: plot(sweep, pd))
    
    def plot(sweep, pd):
        pd.setValue(0)
        pd.setLabelText('Plotting fit results...')
        pd.setMaximum(sweep.nchan)
        pd.setAutoClose(True)
        QApplication.processEvents()
        dw = DiagnosticsDialog(sweep, 'test.h5', parent=win)
        fig, future = dw.plot(pd=pd)
        dw.set_figure(fig)
        future.result()
        plt.tight_layout()
        QApplication.processEvents()
        dw.show()
        # future.add_done_callback(lambda _: dw.show())
    

    # pd.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
    # pd.move(self.geometry().center() - pd.geometry().center())
    pbutt.clicked.connect(lambda: fit(sweep))



    win.show()
    app.exec()
