from __future__ import annotations

import matplotlib as mpl

mpl.use('QtAgg')

from typing import Callable, Concatenate, Any
from pathlib import Path
from concurrent.futures import Future
import logging
import pdb
from matplotlib.artist import Artist

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton, MouseEvent, PickEvent
from matplotlib.backend_tools import Cursors
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, SignalInstance, Slot, QCoreApplication
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
    QAbstractButton,
    QVBoxLayout,
)

from rfsocinterface.core.losweep import LoSweepData, ResonatorData, get_tone_list, LoSweep, DEFAULT_NCOLS
from rfsocinterface.core.params import update_params_file, initialize_params_file
from rfsocinterface.gui.uic.lodiagnostics_ui import Ui_Dialog as Ui_DiagnosticsDialog
from rfsocinterface.gui.uic.loresonator_ui import Ui_Dialog as Ui_ResonatorDialog
from rfsocinterface.gui.widgets.progress_bar import IncrementalProgressDialog
from rfsocinterface.core.utils import ensure_path, PathLike, reset_axes, P, PERMISSIONS_USR_RW
from rfsocinterface.gui.widgets.progress_bar import make_progress_dialog_incrementer
from rfsocinterface.gui.uic.blind_sweep_ui import Ui_Dialog as Ui_BlindSweepDialog
from rfsocinterface.gui.widgets.canvas import ToolbarCanvas

_logger = logging.getLogger(__name__)

DPI = 100

# Max x difference in Hz to count as the mouse being close to the line
RTOL_EPSILON = 1e-6  
ATOL_EPSILON = 50e3  # 50 KHz


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
        self.setSizeGripEnabled(True)

        self.resonator = resonator
        self.dragging = False
        self.error_label = None

        self.setWindowTitle(f'Resonator {self.resonator.idx}')

        # Setup the plot
        self.setup_connections()
        self.replot_figure(self.resonator.plot)
        # fig = self.resonator.plot()
        # self.set_figure(fig)
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
    def figure_canvas(self) -> FigureCanvas:
        return self.canvas.figure_canvas

    @property
    def figure(self) -> Figure:
        return self.canvas.figure
    
    @property
    def ax(self) -> plt.Axes:
        return self.figure.axes[0]
    
    @property
    def _editing(self) -> bool:
        """Return whether the plot is in editing mode."""
        return self.canvas.manager.toolmanager.active_toggle['default'] == 'edit'

    def accept_changes(self):
        """Handle accepting changes."""
        self.resonator.fit_f0 = self.temp_fit_f0
        self.resonator.fit_qc = self.temp_fit_qc
        self.resonator.fit_qi = self.temp_fit_qi
        plt.close(self.figure)
        self.accept()

    def reject_changes(self):
        """Handle rejecting changes."""
        plt.close(self.figure)
        self.reject()
    
    def move_line(self, x: float, update_line_edit: bool=True):
        """Move the line to the specified x value."""
        self.temp_fit_f0 = x
        self.canvas.line.set_xdata([x, x])
        self.figure_canvas.draw_idle()
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
    
    def setup_connections(self):
        # Setup the event handling logic to click and drag the line
        self.figure_canvas.mpl_connect('button_press_event', self.mouse_press)
        self.figure_canvas.mpl_connect('button_release_event', self.mouse_release)
        self.figure_canvas.mpl_connect('motion_notify_event', self.mouse_move)

    def set_figure(self, fig: Figure):
        """Change the figure in the canvas."""
        self.canvas.set_figure(fig)

        self.ax = fig.axes[0]
        # self.figcanvas = self.canvas.canvas

        self.setup_connections()


        self.adjustSize()

    def replot_figure(self, plotting_function: Callable[Concatenate[Figure, P], None], *args: P.args, **kwargs: P.kwargs):
        self.canvas.replot_figure(plotting_function, *args, **kwargs)

    def close_to_line(self, xdata: float, epsilon: float = RTOL_EPSILON) -> bool:
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
            self.figure_canvas.set
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
            self.figure_canvas.draw_idle()
            return
        if not self.dragging:
            # Check if the mouse is close to the line and highlight it if so
            if self.close_to_line(event.xdata):
                self.canvas.line.set_linewidth('3')
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.canvas.line.set_linewidth('1.5')
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.figure_canvas.draw_idle()
            return

        # Moving while holding left mouse and dragging, so update the line's position
        self.move_line(event.xdata)


class DiagnosticsDialog(QDialog, Ui_DiagnosticsDialog):
    """Window displaying all resonator plots.

    Attributes:
        sweep (LoSweepData): The relevant LO sweep data.
    """

    def __init__(self, sweep_data: LoSweepData, savefile: PathLike, parent: QWidget | None = None):
        """Initialize a DiagnosticsWindow."""
        super().__init__(parent=parent)
        self.setupUi(self)
        self.setSizeGripEnabled(True)
        self.set_sweep(sweep_data)
        self.savefile = Path(savefile)
        self.flagged_checkBox.clicked.connect(self.toggle_unflagged)
        self.buttonBox.clicked.connect(self.click_button_box)
        self.save_plots_pushButton.clicked.connect(self.save_plots_as)

        self.edited = False

    def set_window_name(self, name: str):
        self.setWindowTitle(QCoreApplication.translate("Dialog", f'LO Sweep Diagnostics - {name}', None))
    
    def click_button_box(self, button: QAbstractButton):
        if self.buttonBox.buttonRole(button) == QDialogButtonBox.ButtonRole.DestructiveRole:
            self.close_without_saving()
        elif self.buttonBox.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
            self.accept()
    
    def set_sweep(self, sweep_data: LoSweepData):
        self.sweep_data = sweep_data
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
                resonator = self.sweep_data.resonator_data[idx]
                self.make_resonator_window(resonator, axes)

    def redraw_axes(self, resonator: ResonatorData, ax: plt.Axes):
        """Redraw the specified axes."""
        reset_axes(ax)
        resonator.plot(ax=ax)
        # ax.set_box_aspect(1.0)

        fig = self.get_figure()
        fig.draw_artist(ax.patch)
        fig.draw_artist(ax)

        self.canvas.select_axis(self.canvas.selected_axes)
        self.update_median_shift()
    
    def update_median_shift(self):
        self.median_shift_label.setText(
            f'Median shift (KHz): {np.median(self.sweep_data.difference[self.sweep_data.onres_ind]) * 1e-3:.2f}'
        )
    
    def set_edited(self):
        self.edited = True
        self.setWindowTitle('*LO Sweep Diagnostics')
    
    def get_ax_by_index(self, idx: int) -> plt.Axes:
        return self.get_figure().get_axes()[idx]
    
    @Slot(int)
    def handle_resonator_window_finish(self, result: int):
        dialog: ResonatorDialog = self.sender()
        resonator = dialog.resonator
        ax = self.get_ax_by_index(resonator.idx)
        if result == QDialog.DialogCode.Accepted:
            self.set_edited()
        self.redraw_axes(resonator, ax)

    def make_resonator_window(self, resonator: ResonatorData, ax: plt.Axes):
        """Create and open a ResonatorWindow using the provided ResonatorData."""

        rw = ResonatorDialog(resonator, parent=self)
        rw.finished.connect(self.handle_resonator_window_finish)
        # rw.accepted.connect(self.set_edited)

        rw.show()

    def set_figure(self, fig: Figure):
        fig.canvas.mpl_connect('button_press_event', self.click_plot)
        self.canvas.set_figure(fig)
        self.canvas.set_flagged(self.sweep_data.flagged)
    
    def get_width_in_inches(self) -> float:
        width_pixels = self.canvas.width()
        screen_dpix = self.screen().logicalDotsPerInchX()
        return width_pixels / screen_dpix

    def plot(self, callback: Callable | None=None, fig: Figure | None=None) -> Figure | None:
        """Plot all of the resonators."""
        if not self.isHidden():
            # Get the width of the window and determine how many columns will fit
            width = self.get_width_in_inches()
            ncols = int(np.floor(width))
        else:
            ncols = DEFAULT_NCOLS

        if fig is None:
            nrows = int(np.ceil(self.sweep_data.nchan / ncols))
            fig = plt.figure(figsize=(ncols, nrows))
            for i in range(1, self.sweep_data.nchan + 1):
                ax = fig.add_subplot(nrows, ncols, i, xticks=[], yticks=[])
                # ax.set_aspect('equal', adjustable='box')
                ax.set_box_aspect(1.0)

        res = self.sweep_data.plot(ncols, callback=callback, fig=fig)
        
        # Only continue it if the plotting wasn't canceled
        if res is not None:
        #     # self.set_figure(res)
            return res
    
    def make_plot(self, fig_width=15, pd: QThreadJobProgressDialog | None=None) -> tuple[Figure, Future]:
        return self.sweep_data.plot(ncols=fig_width, pd=pd)

    def toggle_unflagged(self):
        """Toggle whether the unflagged resonator plots are shown."""
        self.canvas.set_flagged(self.sweep_data.flagged)
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
        sweep_data = LoSweepData.from_h5(filepath)
        dialog = cls(sweep_data, savefile=filepath, parent=parent)

        pd = IncrementalProgressDialog(
            f'Plotting LO sweep...',
            'Cancel',
            0,
            sweep_data.nchan,
            parent=parent,
        )
        pd.setAutoClose(True)
        pd.setValue(0)
        pd.show()

        QApplication.processEvents()
        increment_progress = make_progress_dialog_incrementer(pd)

        fig = dialog.plot(callback=increment_progress)
        dialog.set_figure(fig)

        return dialog


def line_picker(line: plt.Line2D, event: MouseEvent, epsilon: float=ATOL_EPSILON):
    res = np.allclose(line.get_xdata()[0], event.xdata, atol=epsilon), {}
    return res

class BlindSweepDialog(QDialog):
    def __init__(self, data: LoSweepData, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi()
        self.setSizeGripEnabled(True)
        # self.canvas.add_edit_button()
        # self.canvas.add_add_button(self.add_line)
        # self.canvas.add_remove_button(self.remove_line)
        # self.canvas.add_undo_button(self.undo)
        # self.canvas.add_redo_button(self.redo)
        self.setup_connections()

        self.data = data
        self.selected_line = None
        self.dragging = False
        self.action_stack: list[tuple[str, Any]]= []
        self.stack_pointer = -1
    
    def setupUi(self):
        layout = QVBoxLayout(self)

        self.canvas = ToolbarCanvas(
            parent=self,
            add_edit=True,
            add_function=self.add_line,
            add_description='Add a vertical line to the plot.',
            remove_function=self.remove_line,
            remove_description='Remove the currently selected line from the plot.',
            undo_function=self.undo,
            redo_function=self.redo
        )
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(self.canvas)
        layout.addWidget(button_box)
        self.setLayout(layout)


    def set_window_name(self, name: str):
        self.setWindowTitle(QCoreApplication.translate("Dialog", f'Fitted Resonance Adjustment - {name}', None))
    
    def accept(self):
        fname, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption='Save Tones to Parameters File',
            dir='/data/params',
            filter='HDF5 (*.h5);;All Files (*)'
        )
        if fname:
            f0 = [line.get_xdata()[0] for line in self.get_vlines()]
            path = Path(fname).with_suffix('.h5')
            if not path.exists():
                # TODO: Get the actual tile name
                tile_name = path.stem[12:]
                initialize_params_file(tile_name, f0, self.data.f_center)
            else:
                update_params_file(path, baseband_freqs=f0)
            return super().accept()

    @property
    def figure_canvas(self) -> FigureCanvas:
        return self.canvas.figure_canvas

    @property
    def figure(self) -> Figure:
        return self.canvas.figure
    
    @property
    def ax(self) -> plt.Axes:
        return self.figure.axes[0]
    
    @property
    def _editing(self) -> bool:
        """Return whether the plot is in editing mode."""
        return self.canvas.editing
    
    @property
    def n_tones(self) -> int:
        return self.data.nchan

    def get_vlines(self) -> list[plt.Line2D]:
        """Get the vertical lines in the plot."""
        # The first n_tones lines should be the S21 traces for each tone
        return self.ax.lines[self.n_tones:]
    
    def plot(self, **kwargs):
        f0, depths = self.data.find_resonances(**kwargs)
        self.f0 = f0
        self.depths = depths
        
        self.data.plot_new_resonances('blind_sweep', f0)
        self.replot_figure(self.data.plot_blind_sweep, f0)
        # fig = self.data.plot_blind_sweep(f0)
        # self.set_figure(fig)
    
    def closest_vline(self, x: float) -> tuple[int, plt.Line2D]:
        lines = self.get_vlines()
        x_pos = [line.get_xdata()[0] for line in lines]
        closest_idx = np.argmin(np.abs(np.subtract(x_pos, x)))
        return closest_idx, lines[closest_idx]

    def setup_connections(self):
        # Setup the event handling logic to click and drag the line
        self.figure_canvas.mpl_connect('button_press_event', self.mouse_press)
        self.figure_canvas.mpl_connect('button_release_event', self.mouse_release)
        self.figure_canvas.mpl_connect('motion_notify_event', self.mouse_move)
        self.figure_canvas.mpl_connect('pick_event', self.pick_line)

    def replot_figure(self, plotting_function: Callable[Concatenate[Figure, P], None], *args: P.args, **kwargs: P.kwargs):
        self.canvas.replot_figure(plotting_function, *args, **kwargs)
        for l in self.get_vlines():
            l.set_picker(line_picker)
            l.set_pickradius(10)

    def set_figure(self, fig: Figure):
        """Change the figure in the canvas."""
        self.canvas.set_figure(fig)

        self.ax = fig.axes[0]
        self.figure_canvas = self.canvas.scrollable_canvas

        self.ax = fig.axes[0]
        
        self.setup_connections()

        self.adjustSize()

    def move_selected_line(self, x: float, add_to_stack: bool=False):
        """Move the currentyl selected line to the specified x value."""
        if add_to_stack:
            self.push_to_stack('move_line', self.selected_line, self.selected_line_start, x)

        self.selected_line.set_xdata([x, x])
        self.ax.draw_artist(self.selected_line)
        self.figure_canvas.draw_idle()
        

    def close_to_line(self, line: plt.Line2D, xdata: float, epsilon: float=ATOL_EPSILON) -> bool:
        """Return whether a value is close to a line."""
        return np.allclose(line.get_xdata()[0], xdata, atol=epsilon)
    
    def add_line(self):
        if not self._editing:
            return
        xlims = self.ax.get_xlim()
        x = (xlims[0] + xlims[1]) / 2
        l = self.ax.axvline(x, color='red')
        self.figure_canvas.draw_idle()
        l.set_picker(line_picker)
        l.set_pickradius(10)

        self.push_to_stack('add_line', l, x)
    
    def push_to_stack(self, action: str, *data):
        self.stack_pointer += 1
        self.action_stack = self.action_stack[:self.stack_pointer]
        self.action_stack.append((action, *data))
        # print(f'Pushed action "{action}" to stack with data {data}')
    
    def undo(self):
        # print(f'Called UNDO. Current stack: {self.action_stack}, pointer = {self.stack_pointer}')
        # If nothing to undo return
        if len(self.action_stack[:self.stack_pointer + 1]) == 0:
            return
        action, *data = self.action_stack[self.stack_pointer]
        # print(f'UNDO: action={action} with data {data}')
        match action:
            case 'move_line':
                line, old_x, new_x = data
                line.set_xdata([old_x, old_x])
            case 'add_line':
                line, x, = data
                line.remove()
            case 'remove_line':
                line, x = data
                self.ax.add_artist(line)
                # line.set_picker(line_picker)
                # line.set_pickradius(10)
            case _:
                raise NotImplementedError(f'Undoing action "{action}" is not yet supported.')
        
        self.figure_canvas.draw_idle()
        self.stack_pointer -= 1

    def redo(self):
        # print(f'Called REDO. Current stack: {self.action_stack}, pointer = {self.stack_pointer}')
        # If nothing to redo return
        if self.stack_pointer + 2 > len(self.action_stack):
            return
        action, *data = self.action_stack[self.stack_pointer + 1]
        # print(f'REDO: action={action} with data {data}')
        match action:
            case 'move_line':
                line, old_x, new_x = data
                line.set_xdata([new_x, new_x])
            case 'add_line':
                line, x = data
                self.ax.add_artist(line)
                # line.set_picker(line_picker)
                # line.set_pickradius(10)
                # line.set_xdata([old_x, old_x])
            case 'remove_line':
                line, x = data
                line.remove()
            case _:
                raise NotImplementedError(f'Redoing action "{action}" is not yet supported.')
        
        self.figure_canvas.draw_idle()
        self.stack_pointer += 1

    def set_selected_line(self, line: plt.Line2D):
        # Reset previously selected line
        if self.selected_line is not None:
            self.selected_line.set_linewidth('1.5')
            self.selected_line.set_linestyle('-')

        self.selected_line = line

        if line is not None:
            self.selected_line_start = self.selected_line.get_xdata()[0]
            self.selected_line.set_linewidth('3')
            self.selected_line.set_linestyle('--')
    
    def remove_line(self):
        if not self._editing:
            return
        if self.selected_line is not None:
            self.push_to_stack('remove_line', self.selected_line, self.selected_line.get_xdata()[0])
            self.selected_line.remove()
            self.selected_line = None
    
    def pick_line(self, event: PickEvent):
        if not self._editing:
            return
        
        self.set_selected_line(event.artist)
        # self.dragging = True
        QApplication.restoreOverrideCursor()

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
            # self.figure_canvas.set_cursor(Cursors.HAND)
            QApplication.restoreOverrideCursor()
            # QApplication.setOverrideCursor(Qt.CursorShape.OpenHandCursor)
            self.move_selected_line(event.xdata, add_to_stack=True)
    
    def mouse_press(self, event: MouseEvent):
        if not self._editing:
            return 
        if event.button != 1:
            return  # Not left click
        if event.inaxes != self.ax:
            return  # Not inside the plot

        # clicking far away from lines deselects the current line
        i, closest_line = self.closest_vline(event.xdata)
        if not self.close_to_line(closest_line, event.xdata):
            self.set_selected_line(None)
            closest_line.set_linewidth('1.5')


    def mouse_move(self, event: MouseEvent):
        """Handle mouse movement."""
        if not self._editing:
            return 
        # If mouse moves out of plot, unhighlight the line and stop dragging
        if event.inaxes != self.ax:
            # if self.selected_line is not None:
            #     self.selected_line.set_linewidth('1.5')
            # self.setCursor(Qt.CursorShape.ArrowCursor)
            # QApplication.restoreOverrideCursor()
            self.dragging = False
            self.figure_canvas.draw_idle()
            return
        if event.button == MouseButton.LEFT and self.selected_line is not None:
            self.dragging = True
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
        if not self.dragging:
            # Check if the mouse is close to a line and highlight it if so
            i, closest_line = self.closest_vline(event.xdata)
            if self.close_to_line(closest_line, event.xdata):
                closest_line.set_linewidth('3')
                QApplication.setOverrideCursor(Qt.CursorShape.OpenHandCursor)
            else:
                # TODO: The highlighting isn't quite right but ah well

                # Not close to any lines, so unhighlight all lines and reset the cursor
                # for line in self.get_vlines():
                #     if line != self.selected_line:
                #         line.set_linewidth('1.5')
                # if self.selected_line is not None:
                #     self.selected_line.set_linewidth('1.5')
                if closest_line != self.selected_line:
                    closest_line.set_linewidth('1.5')
                QApplication.restoreOverrideCursor()
            self.figure_canvas.draw_idle()
        else:
            # Moving while holding left mouse and dragging, so update the line's position
            self.move_selected_line(event.xdata)



if __name__ == '__main__':

    from concurrent.futures import wait
    import pdb

    app = QApplication()

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt import FigureManagerQT
    from matplotlib.backend_tools import ToolToggleBase
    from rfsocinterface.gui.widgets.canvas import ToolbarCanvas
    def plot_fn(fig: Figure, size: int=10):
        if len(fig.axes) == 0:
            ax = fig.add_subplot()
        else:
            ax = fig.axes[0]
        ax.plot(np.arange(size), np.random.random(size))

    # class MainWindow(QDialog):
    #     def __init__(self, parent=None):
    #         super().__init__(parent)

    #         self.canvas = ToolbarCanvas(self)
    #         self.canvas.add_edit_button()
    #         self.canvas.replot_figure(plot_fn)
    #         # self.canvas = FigureCanvas(fig)
    #         # self.manager = FigureManagerQT(self.canvas, 1)
    #         # self.canvas.manager = self.manager
    #         # self.nav = self.manager.toolbar

    #         layout = QVBoxLayout(self)
    #         layout.setContentsMargins(0, 0, 0, 0)
    #         self.setLayout(layout)
    #         # layout.addWidget(self.nav)
    #         layout.addWidget(self.canvas)

    # win = MainWindow()
    # win.show()
    # dw = DiagnosticsDialog.from_h5('/data/20260203/20260203_Device_aSi1_Channel3_blind_LO_Sweep_hour13p9728.h5')
    # dw = DiagnosticsDialog.from_h5('/data/20260204/20260204_1000_tone_uniform_202050829_LO_Sweep_hour13p2042.h5')
    data = LoSweepData.from_h5('/data/20260420/20260420_ONR_Blind_180_to_620MHz_1000_tones_LO_Sweep_hour14p7439.h5')
    win = BlindSweepDialog(data)
    win.plot(
        min_resonance_depth_dB=0.3,
        spacing_threshold_Hz=3e3,
        min_samples_per_resonance=4,
        max_noise_fluctuation_dB=0.05,
    )
    win.show()

    # dw.show()
    app.exec()
