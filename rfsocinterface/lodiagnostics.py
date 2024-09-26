import matplotlib as mpl

mpl.use('QtAgg')

from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QWidget,
)

from rfsocinterface.losweep import LoSweepData, ResonatorData, get_tone_list
from rfsocinterface.ui.lodiagnostics_ui import Ui_MainWindow as Ui_DiagnosticsWindow
from rfsocinterface.ui.loresonator_ui import Ui_MainWindow as Ui_ResonatorWindow

DPI = 100

EPSILON = 1e-4  # Max x difference to count as the mouse being close to the line


class ResonatorWindow(QMainWindow, Ui_ResonatorWindow):
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
        self.resonator = resonator
        self.dragging = False
        self.error_label = None

        self.setWindowTitle(f'Resonator {self.resonator.idx}')

        # Setup the plot
        fig = self.resonator.plot()
        self.set_figure(fig)
        self.canvas.line.set_label('New Frequency')
        self.ax.axvline(
            self.resonator.tone * 1e-6,
            0,
            1,
            color='gray',
            linestyle='--',
            label='Old Frequency',
        )
        self.ax.legend()

        # Fill in the necessary values in the UI
        self.old_freq_value_label.setText(f'{self.resonator.tone * 1e-6:.3f}')
        self.depth_value_label.setText('N/A')  # TODO: Resonance depth

        # Temporary values for saving / undoing changes
        self.temp_fit_f0 = resonator.fit_f0
        self.temp_fit_qc = resonator.fit_qc
        self.temp_fit_qi = resonator.fit_qi

        # Setup text validator
        freq_range = self.ax.get_xlim()
        self.validator = QDoubleValidator(
            freq_range[0], freq_range[1] + 0.001, 5, parent=self
        )
        self.new_freq_lineEdit.setValidator(self.validator)

        # Setup connections to signals
        self.buttonBox.accepted.connect(self.accept)
        # self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self.reset_freq
        )
        self.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject
        )
        self.refit_pushButton.clicked.connect(self.refit)
        self.new_freq_lineEdit.textChanged.connect(self.change_freq)

        # This line will call change_freq since the signal has been connected
        self.new_freq_lineEdit.setText(f'{self.resonator.fit_f0 * 1e-6:.3f}')

    def accept(self):
        """Handle accepting changes."""
        self.resonator.fit_f0 = self.temp_fit_f0
        self.resonator.fit_qc = self.temp_fit_qc
        self.resonator.fit_qi = self.temp_fit_qi
        self.close()

    def reject(self):
        """Handle rejecting changes."""
        self.close()

    def refit(self):
        """Refit the resonator."""
        fit_f0, fit_qc, fit_qi = self.resonator.fit(
            self.resonator.data.df, self.temp_fit_f0
        )
        self.temp_fit_f0 = fit_f0
        self.temp_fit_qc = fit_qc
        self.temp_fit_qi = fit_qi
        self.new_freq_lineEdit.setText(f'{np.real(fit_f0) * 1e-6:.3f}')

    def reset_freq(self):
        """Reset the line to the initial frequency."""
        self.new_freq_lineEdit.setText(f'{self.resonator.fit_f0 * 1e-6:.3f}')

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
                    f'New frequency must be in the range [{freq_range[0]:.3f}, {freq_range[1]:.3f}]'
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
            new_freq = float(new_freq)
            self.temp_fit_f0 = new_freq * 1e6
            self.canvas.line.set_xdata([new_freq, new_freq])
            self.figcanvas.draw_idle()
            self.delta_value_label.setText(
                f'{(new_freq - self.resonator.tone * 1e-6) * 1e3:.3f}'
            )

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
        return np.allclose(self.canvas.line.get_xdata()[0], xdata, atol=epsilon)

    def mouse_release(self, event: MouseEvent):
        """Handle releasing a mouse button."""
        if event.button != 1:
            return  # Not left click
        if event.inaxes != self.ax:
            return  # Not inside the plot

        if self.dragging:
            # Stop dragging and update the line's position
            self.dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.new_freq_lineEdit.setText(f'{event.xdata:.5f}')
            self.canvas.line.set_xdata([event.xdata, event.xdata])
            self.temp_fit_f0 = event.xdata * 1e6
            self.figcanvas.draw_idle()

    def mouse_press(self, event: MouseEvent):
        """Handle left clicking."""
        if event.inaxes != self.ax:
            return  # Not in the plot
        if event.button != 1:
            return  # Not left button

        # Begin dragging if close to the line
        if self.close_to_line(event.xdata):
            self.dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouse_move(self, event: MouseEvent):
        """Handle mouse movement."""
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
        if event.button != 1:
            return  # Not left clicking

        # Moving while holding left mouse and dragging, so update the line's position
        self.new_freq_lineEdit.setText(f'{event.xdata:.5f}')
        self.canvas.line.set_xdata([event.xdata, event.xdata])
        self.temp_fit_f0 = event.xdata * 1e6
        self.figcanvas.draw_idle()


class DiagnosticsWindow(QMainWindow, Ui_DiagnosticsWindow):
    """Window displaying all resonator plots.

    Attributes:
        sweep (LoSweepData): The relevant LO sweep data.
    """

    def __init__(self, sweep: LoSweepData, parent: QWidget | None = None):
        """Initialize a DiagnosticsWindow."""
        super().__init__(parent=parent)
        self.setupUi(self)
        self.sweep = sweep
        self.flagged_checkBox.clicked.connect(self.toggle_unflagged)
        self.plot()

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

    def make_resonator_window(self, resonator: ResonatorData, ax: plt.Axes):
        """Create and open a ResonatorWindow using the provided ResonatorData."""

        def wrap_func(f: Callable):
            def override_close(*args):
                f(*args)

                # Redraw the plot when closing the resonator window
                ax.cla()
                resonator.plot(ax)
                self.get_figure().draw_artist(ax.patch)
                self.get_figure().draw_artist(ax)
                self.canvas.select_axis(self.canvas.selected_axes)

            return override_close

        rw = ResonatorWindow(resonator, parent=self)
        rw.closeEvent = wrap_func(rw.closeEvent)

        rw.show()

    def plot(self, fig_width=15):
        """Plot all of the resonators."""
        fig = self.sweep.plot(ncols=fig_width)
        fig.canvas.mpl_connect('button_press_event', self.click_plot)
        self.canvas.set_figure(fig)
        self.canvas.set_flagged(self.sweep.flagged)

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


if __name__ == '__main__':
    app = QApplication()

    sweep = LoSweepData(
        get_tone_list('Default_tone_list.npy'),
        '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
        chanmask_file='chanmask.npy',
    )
    sweep.fit(do_print=False)

    w = DiagnosticsWindow(sweep)

    w.show()
    app.exec()
