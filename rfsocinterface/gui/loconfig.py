"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, Type, Callable, TYPE_CHECKING, Iterator
from functools import partial
from concurrent.futures import Future

import matplotlib.pyplot as plt
from matplotlib.pyplot import Figure

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QRadioButton, QLineEdit, QWidget, QProgressDialog, QTabWidget, QDialogButtonBox, QPushButton
from PySide6.QtCore import Qt, Signal, Slot

from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.uic.loconfig_ui import Ui_LoConfigWidget as Ui_LOConfigWidget
from rfsocinterface.core.losweep import LoSweepData, get_tone_list, LoSweep
from rfsocinterface.gui.lodiagnostics import DiagnosticsDialog
from rfsocinterface.gui.widgets.progress_bar import QThreadJobProgressDialog
from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.gui.widgets.icon_label import IconLabel, ERROR_ICON_CODE
from rfsocinterface.gui.initialization import InitializationWidget
from rfsocinterface.core.utils import get_num_value, ensure_path
from rfsocinterface.gui.main_widget import MainWidget

# from kidpy3 import RFSOC
from kidpy3.hardware.Valon5009 import Valon5009, SYNTH_A, SYNTH_B
import time
# import valon5009
import numpy as np
import onrkidpy
import sweeps
import h5py

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

DEFAULT_FILENAME = 'YYYYMMDD_rfsocN_LO_Sweep_hourHH'
DEFAULT_F_CENTER = 400.0
DEFAULT_CHANMASK = '/home/onrkids/readout/host/params/chanmask_rfsoc2.npy'
FILE_SUFFIXES = {'none', 'temperature', 'elevation'}


class LoConfigWidget(MainWidget, Ui_LOConfigWidget):
    """Window for configuring the LO sweep.

    Attributes:
        active_suffix (Literal['none', 'temperature', 'elevation]): The currently
            selected suffix to append to the filename. Can be 'none', 'temperature',
            or 'elevation'.
        tone_path (Path): The path to the selected tone list file.
    """
    start_fit = Signal(object, QThreadJobProgressDialog)
    start_plot = Signal(QThreadJobProgressDialog)

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        """Initialize the LO configuration window."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.start_fit.connect(self._fit_sweep)
        self.start_plot.connect(self._plot_fit)

        self.channel_comboBox.set_default_title('Select Channels...')

        self.set_defaults()
        self.make_error_labels()    
        self.update_channel_choices(self.channel_comboBox)

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.second_sweep_checkBox.clicked.connect(self.check_second_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.filename_temperature_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        self.filename_elevation_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        
        self.dialog_button_box.accepted.connect(self.run_sweeps)
        self.dialog_button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.set_defaults)   
        self.channel_toolButton.clicked.connect(self.open_channel_in_initialization_tab)    
    
    def set_defaults(self):
        defaults = self.settings['defaults']['loSweep']
        self.global_shift_lineEdit.setText(str(defaults['globalShift']))
        self.df_lineEdit.setText(str(defaults['df']))
        self.deltaf_lineEdit.setText(str(defaults['deltaf']))
        self.flagging_lineEdit.setText(str(defaults['flaggingThreshold']))

        file_suffix = defaults.get('file_suffix', 'none')
        if  file_suffix not in FILE_SUFFIXES:
            raise SettingsError(f'Invalid value for defaults.losweep.file_suffix: "{file_suffix}; valid values are: {FILE_SUFFIXES}')
        self.active_suffix: Literal['none', 'temperature', 'elevation'] = file_suffix

        self.second_sweep_df_lineEdit.setText(str(defaults['secondSweep']['df']))

        self.channel_comboBox.deselect_all()

    def make_error_labels(self):
        # Attenuation Error Labels
        channel_err_str = 'No channel selected'
        # self.formLayout.removeWidget(self.channel_error_label)
        self.lo_gridLayout.removeWidget(self.channel_error_label)
        self.channel_error_label.deleteLater()
        self.channel_error_label = IconLabel(ERROR_ICON_CODE, channel_err_str, color='red', wrap_text=False, parent=self)
        self.lo_gridLayout.addWidget(self.channel_error_label, 1, 1)
        self.channel_error_label.hide()
    
    def open_channel_in_initialization_tab(self):
        # TODO: Fix this
        channels = self.get_selected_channels(self.channel_comboBox)
        rfsoc, chan = self.get_selected_channels(self.channel_comboBox)
        tab_idx = self.main_window.tabWidget.indexOf(self.main_window.initialization_tab)
        if 'initialization' in self.main_window.tabs:
            init_tab: InitializationWidget = self.main_window.tabs['initialization']
            tab_idx = self.main_window.index('initialization')
        init_tab.collapse_all(recursive=True)
        rfsoc_idx = self.rfsocs.index(rfsoc)
        rfsoc_section, rfsoc_wid = init_tab.items[rfsoc_idx]
        rfsoc_section.expand()
        match chan:
            case 1:
                rfsoc_wid.channel1_section.expand()
            case 2:
                rfsoc_wid.channel2_section.expand()
            case _:
                raise ValueError(f'Invalid channel number: {chan}')
        init_tab.set_active_section(rfsoc_section)
        self.main_window.tabWidget.setCurrentIndex(tab_idx)
    
    def run_sweeps(self):
        try:
            selected_channels = self.get_selected_channels(self.channel_comboBox)
        except SettingsError:
            self.channel_error_label.show()
            return
        self.channel_error_label.hide()
        # TODO: Run sweeps in parallel
        for rfsoc, chan in selected_channels:
            self.run_sweep(rfsoc, chan)
    
    def run_sweep(self, rfsoc: RFSOCWrapper, chan: int):
        channel_settings = rfsoc.settings[f'channel{chan}']
        valon = rfsoc.valon_a if chan == 1 else rfsoc.valon_b

        chan_name = 'rfsoc2'

        # For running on ONR Computer
        # TODO: Fix this
        lo_freq = channel_settings['dsp']['loFreq']  # MHz
        valon.set_frequency(2, lo_freq)
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3  # KHz to Hz
        if tone_shift != 0:
            lo_freq = valon.get_frequency(SYNTH_B) * 1e6  # MHz to Hz
            curr_tone_list, curr_amp_list = rfsoc.get_tone_list(chan)
            new_tones = np.ndarray.tolist(
                curr_tone_list
                + float(tone_shift)
                * (curr_tone_list + lo_freq)
                / np.median(curr_tone_list + lo_freq)
            )
            print(
                "Waiting for the RFSOC to finish writing the updated frequency list"
            )
            rfsoc.set_tone_list(chan, new_tones, curr_amp_list.tolist())
            
        self.savefile = onrkidpy.get_filename(
            type="LO", chan_name=chan_name
        )
        match self.buttonGroup.checkedButton():
            case self.filename_elevation_radioButton:
                self.savefile += f'_elev_{self.filename_elevation_lineEdit.text()}'
            case self.filename_temperature_radioButton:
                self.savefile += f'_temp_{self.filename_temperature_lineEdit.text()}'
            case _:
                pass

        # For running on ONR compupter
        match chan:
            case 1:
                rfchan = rfsoc.rfsoc.rf1
            case 2:
                rfchan = rfsoc.rfsoc.rf2
            case _:
                raise ValueError(f'Invalid channel number: {chan}')
        sweep = LoSweep(
            valon,
            rfchan,
            rfsoc.get_tone_list()[0],
            valon.get_frequency(SYNTH_B) * 1e6,  # MHZ to Hz
        )
        tone_list = rfsoc.get_tone_list()[0]
        chanmask = DEFAULT_CHANMASK
        # chanmask = rfsoc.settings['chanmask']
        freq_step = get_num_value(self.df_lineEdit)  * 1e3  # KHz to Hz
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3  # KHz to Hz
        n_steps = full_span / freq_step

        pd = QThreadJobProgressDialog(labelText='Running LO Sweep...',  maximum=n_steps, max_workers=1, parent=self)
        pd.setAutoClose(False)
        # pd.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        # pd.move(self.geometry().center() - pd.geometry().center())
        pd.show()
        QApplication.processEvents()
        # pd.canceled.connect(self.cancel_sweep)

        self.dw = DiagnosticsDialog(None, self.savefile, parent=self)
        self.dw.accepted.connect(lambda: self.save_sweep(self.savefile))
        self.dw.setWindowModality(Qt.WindowModality.WindowModal)

        sweep_data_future = sweep.run_sweep(chanmask, tone_list, N_steps=n_steps, freq_step=freq_step, pd=pd)
        # sweep_data_future.add_done_callback(lambda _: self._fit_sweep(sweep, pd))
        sweep_data_future.add_done_callback(lambda _: self.start_fit.emit(sweep, pd))

        # For running on local computer
        # sweep_file = '20240822_rfsoc2_LO_Sweep_hour16p3294.npy'
        # tone_list = 'Default_tone_list.npy'
        # chanmask = 'chanmask.npy'
        # savefile = Path(savefile).name
        # sweep_data = LoSweepData.from_file(tone_list, sweep_file, chanmask)

    def _fit_sweep(self, sweep: LoSweep, pd: QThreadJobProgressDialog):
        while not sweep._processed:
            QApplication.processEvents()
            time.sleep(0.1)
        self.sweep_data = sweep.data
        self.sweep_data.set_diff_to_flag(get_num_value(self.flagging_lineEdit, float) * 1e3)
        self.dw.sweep = self.sweep_data

        # pb = SequentialProgressBarDialog(parent=self)
        # pb.move(self.geometry().center() - pb.geometry().center())
        # # pb.canceled.connect(self.cancel_sweep)
        nchan = self.sweep_data.ngoodchan
        # pd = QThreadJobProgressDialog(labelText='Fitting sweep results...', parent=self, maximum=nchan)
        # pd = QThreadJobProgressDialog(labelText='...',  maximum=nchan, parent=self)
        pd.setValue(0)
        pd.setLabelText('Fitting sweep results...')
        pd.setMaximum(self.sweep_data.ngoodchan)
        QApplication.processEvents()
        pd.make_pool()
        future = self.sweep_data.fit(pd=pd)
        # future.add_done_callback(lambda _: self._plot_fit(pd))
        future.add_done_callback(lambda _: self.start_plot.emit(pd))
    
    def _plot_fit(self, pd: QThreadJobProgressDialog):
        nchan = self.sweep_data.ngoodchan
        # pd = QThreadJobProgressDialog(labelText='Plotting fit results...', parent=self, maximum=nchan)
        pd.setValue(0)
        pd.setLabelText('Plotting fit results...')
        pd.setMaximum(self.sweep_data.nchan)
        pd.setAutoClose(True)
        QApplication.processEvents()
        fig, future = self.dw.plot(pd=pd)
        self.dw.set_figure(fig)
        future.add_done_callback(lambda _: self._show_diagnostics())
        # future.add_done_callback(lambda _: pd.close())
    
    def _show_diagnostics(self):
        plt.tight_layout()
        QApplication.processEvents()
        # self.dw.set_figure(fig)
        self.dw.show()

        # # pb.add_job(dw.plot, num_tasks=0, start_message='Plotting fit results...')
        # pb.show()
        # # self.pb = pb
        # # pb.allFinished.connect(lambda: dw.set_figure(pb.get_result(1)))
        # pb.allFinished.connect(lambda: self.plot_sweep(sweep_data, dw, pb))
        # # pb.allFinished.connect(dw.show)
        # # pb.allFinished.connect(pb.close)
        # pb.start()
    
    @ensure_path(1)
    def save_sweep(self, savefile: Path):
        self.sweep_data.saveh5(savefile)
        self.sweep_data.savenp(savefile)
    
    # def plot_sweep(self, sweep: LoSweepData, dw: DiagnosticsDialog, pb: SequentialProgressBarDialog):
    #     pb.setLabelText('Plotting fit results...')
    #     pb.reset()
    #     pb.setMaximum(sweep.nchan)
    #     # pb.set_total_tasks(sweep.nchan)
    #     dw.plot(signal=pb.incrementSignal)
    #     pb.close()
    #     dw.show()
    
    def save_LO_sweep(self, sweep: LoSweepData):
        fname, _ = QFileDialog.getSaveFileName(
            self,
            'Save Tone File',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            np.save(fname, self.swee)
            self.tone_list_lineEdit.setText(fname)


    def check_diagnostics(self):
        """Callback for when the "show diagnostics" box is clicked."""
        if self.show_diagnostics_checkBox.isChecked():
            self.only_flag_checkBox.show()
        else:
            self.only_flag_checkBox.hide()

    def check_second_sweep(self):
        """Callback for when the "perform second sweep" box is clicked."""
        if self.second_sweep_checkBox.isChecked():
            self.second_sweep_df_label.show()
            self.second_sweep_df_lineEdit.show()
        else:
            self.second_sweep_df_label.hide()
            self.second_sweep_df_lineEdit.hide()

    def swap_filename_suffix(self, button: QRadioButton):
        """Callback for when the filename suffix is changed."""
        match button:
            # No suffix
            case self.filename_none_radioButton:
                self.active_suffix = 'none'
                self.filename_temperature_lineEdit.setEnabled(False)
                self.filename_elevation_lineEdit.setEnabled(False)
            # Temperatue suffix
            case self.filename_temperature_radioButton:
                self.active_suffix = 'temperature'
                self.filename_temperature_lineEdit.setEnabled(True)
                self.filename_elevation_lineEdit.setEnabled(False)
            # Elevation suffix
            case self.filename_elevation_radioButton:
                self.active_suffix = 'elevation'
                self.filename_temperature_lineEdit.setEnabled(False)
                self.filename_elevation_lineEdit.setEnabled(True)

        self.update_filename_example()

    def update_filename_example(self):
        """Update the example filename box to reflect the chosen suffix."""
        match self.active_suffix:
            case 'none':
                self.filename_example_lineEdit.setText(DEFAULT_FILENAME)
            case 'temperature':
                self.filename_example_lineEdit.setText(
                    f'{DEFAULT_FILENAME}_temp{self.filename_temperature_lineEdit.text()}'
                )
            case 'elevation':
                self.filename_example_lineEdit.setText(
                    f'{DEFAULT_FILENAME}_elev{self.filename_elevation_lineEdit.text()}'
                )
            case _:
                raise RuntimeError(
                    f'Invalid `active_suffix` encountered: {self.active_suffix}'
                )

