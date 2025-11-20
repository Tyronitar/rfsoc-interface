"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, TYPE_CHECKING
import logging
from threading import Thread

import matplotlib.pyplot as plt

from PySide6.QtWidgets import QApplication, QRadioButton, QWidget, QDialog, QProgressDialog
from PySide6.QtCore import Signal

from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.uic.loconfig_ui import Ui_LoConfigWidget as Ui_LOConfigWidget
from rfsocinterface.core.losweep import LoSweepData, LoSweep
from rfsocinterface.gui.lodiagnostics import DiagnosticsDialog
from rfsocinterface.gui.utils import get_num_value
from rfsocinterface.gui.widgets.progress_bar import QThreadJobProgressDialog
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.widgets.icon_label import IconLabel, ERROR_ICON_CODE
from rfsocinterface.core.utils import ensure_path, get_filename, TabName
from rfsocinterface.gui.main_widget import MainWidget

import time
import numpy as np

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)

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
    start_fit = Signal(object, QThreadJobProgressDialog, object, object, int, bool)
    start_plot = Signal(object, DiagnosticsDialog, QThreadJobProgressDialog)

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        """Initialize the LO configuration window."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.start_fit.connect(self._save_and_fit_sweep)
        self.start_plot.connect(self._plot_fit)

        self.channel_comboBox.set_default_title('Select Channels...')

        self.set_defaults()
        self.make_error_labels()    
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.second_sweep_checkBox.clicked.connect(self.check_second_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.filename_temperature_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        self.filename_elevation_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        
        self.run_pushButton.clicked.connect(self.run_sweeps)
        self.restore_defaults_pushButton.clicked.connect(self.set_defaults)
        self.channel_toolButton.clicked.connect(self.open_channels_in_initialization_tab)    
    
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
    
    def open_channels_in_initialization_tab(self):
        try:
            init_tab = self.main_window.tabs[TabName.INITIALIZATION]
        except KeyError:
            return
        init_tab.collapse_all(recursive=True)
        for rfsoc, chan in self.get_selected_channels(self.channel_comboBox):
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
        self.main_window.set_active_tab(TabName.INITIALIZATION)
    
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
        chan_name = rfsoc.get_channel_name(chan)

        # Get values from GUI, converting KHz to Hz
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3
        diff_to_flag = get_num_value(self.flagging_lineEdit, float) * 1e3
        freq_step = get_num_value(self.df_lineEdit)  * 1e3
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3

        savefile = get_filename(
            file_type="LO", chan_name=chan_name, mkdir=True
        )
        match self.buttonGroup.checkedButton():
            case self.filename_elevation_radioButton:
                savefile = savefile.with_stem(f'{savefile.stem}_elev_{self.filename_elevation_lineEdit.text()}')
            case self.filename_temperature_radioButton:
                savefile = savefile.with_stem(f'{savefile.stem}_temp_{self.filename_temperature_lineEdit.text()}')
            case _:
                pass

        pd = QProgressDialog(
            'Setting Up LO Sweep...',
            'Cancel',
            0,
            100,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.show()
        QApplication.processEvents()
        
        # For running on ONR compupter
        sweep = LoSweep(
            rfsoc,
            chan,
            savefile,
            tone_shift,
            freq_step,
            full_span,
            diff_to_flag=diff_to_flag,
        )
        pd.canceled.connect(sweep.cancel)
        pd.setValue(0)
        pd.setMinimum(0)
        pd.setMaximum(sweep.n_steps)

        def increment_progress():
            nonlocal pd
            pd.setValue(pd.value() + 1)

        pd.setLabelText('Running LO Sweep...')
        sweep_thread = Thread(target=sweep.run_sweep, args=(increment_progress,))
        sweep_thread.start()

        while pd.value() < pd.maximum() and not sweep._cancel:
            QApplication.processEvents()
            time.sleep(0.1)
        
        sweep_thread.join()

        # TODO
        # Fit sweep if requested...
        #    Multiprocessing???
        # Show diagnostics dialog if requested...

    @ensure_path(3)
    def _save_and_fit_sweep(self, sweep: LoSweep, pd: QThreadJobProgressDialog, savefile: Path, rfsoc: RFSOCWrapper, chan: int, second_sweep: bool=False):
        sweep_data = self._wait_and_save(sweep, savefile, rfsoc, chan)
        
        # Make diagnostics window and setup connections
        dw = DiagnosticsDialog(sweep_data, savefile, parent=self)
        dw.finished.connect(lambda result: self._finish_sweep(result, savefile, sweep_data, rfsoc, chan, dw, second_sweep))
        dw.upload_pushButton.clicked.connect(lambda: self._write_new_tones(sweep_data, rfsoc, chan))

        pd.setValue(0)
        pd.setLabelText('Fitting sweep results...')
        pd.setMaximum(sweep_data.ngoodchan)
        QApplication.processEvents()
        pd.make_pool()
        future = sweep_data.fit(pd=pd)
        future.add_done_callback(lambda _: self.start_plot.emit(sweep_data, dw, pd))
    
    def _plot_fit(self, sweep_data: LoSweepData, dw: DiagnosticsDialog, pd: QThreadJobProgressDialog):
        pd.setValue(0)
        pd.setLabelText('Plotting fit results...')
        pd.setMaximum(sweep_data.nchan)
        pd.setAutoClose(True)
        QApplication.processEvents()
        fig, future = dw.plot(pd=pd)
        dw.set_figure(fig)
        future.add_done_callback(lambda _: fig.tight_layout())
        future.add_done_callback(lambda _: dw.update_median_shift())
        future.add_done_callback(lambda _: dw.show())
    
    @ensure_path(2)
    def _finish_sweep(self, result: int, savefile: Path, sweep_data: LoSweepData, rfsoc: RFSOCWrapper, chan: int, dw: DiagnosticsDialog, second_sweep: bool=False):
        # If the sweep was discarded, close without saving changes
        if result == QDialog.DialogCode.Rejected:
            _logger.debug(f'Diagnostics dialog rejected.')
            return
        self.save_sweep(savefile, sweep_data)
        if not second_sweep:
            if self.save_plots_CheckBox.isChecked():
                _logger.debug(f'Saving LO sweep plots')
                dw.save_plots()
                plt.close('all')
            if self.second_sweep_checkBox.isChecked():
                self._write_new_tones(sweep_data, rfsoc, chan)
                self.second_sweep(savefile, rfsoc, chan)
            elif self.upload_checkBox.isChecked():
                self._write_new_tones(sweep_data, rfsoc, chan)
        else:
            if self.second_sweep_save_plots_checkBox.isChecked():
                _logger.debug(f'Saving LO sweep plots')
                dw.save_plots()
                plt.close('all')
            
    @ensure_path(1)
    def second_sweep(self, first_sweep_savefile: Path, rfsoc: RFSOCWrapper, chan: int):
        """Perform second LO sweep."""
        _logger.debug(f'Performing second LO sweep...')
        filename = first_sweep_savefile.stem + '_high_res.h5'
        savefile = first_sweep_savefile.with_name(filename)

        valon = rfsoc.get_valon(chan)

        # For running on ONR Computer
        lo_freq = rfsoc.get_channel(chan).lo_freq
        rfsoc.set_frequency(chan, lo_freq)

        rfchan = rfsoc.get_channel(chan)
        tone_list = rfsoc.get_tone_list(chan)[0]
        sweep = LoSweep(
            valon,
            rfchan,
            tone_list,
            lo_freq,
        )
        freq_step = get_num_value(self.second_sweep_df_lineEdit)  * 1e3  # KHz to Hz
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3 / 5  # KHz to Hz
        n_steps = full_span / freq_step

        pd = QThreadJobProgressDialog(labelText='Running Second LO Sweep...',  maximum=n_steps, max_workers=1, parent=self)
        pd.setAutoClose(False)
        pd.show()
        QApplication.processEvents()

        sweep_data_future = sweep.run_sweep(rfsoc.get_channel(chan).chanmask, tone_list, N_steps=n_steps, freq_step=freq_step, pd=pd)
        sweep_data_future.add_done_callback(lambda _: self.start_fit.emit(sweep, pd, savefile, rfsoc, chan, True))

    def _wait_and_save(self, sweep: LoSweep, savefile: Path, rfsoc: RFSOCWrapper, chan: int):
        counter = 0
        while not sweep._processed:
            counter += 1
            if counter % 500 == 0:
                _logger.debug('Waiting for sweep to finish...')
            QApplication.processEvents()
            time.sleep(0.1)
        _logger.debug(f'LoConfigWidget finished waiting for LO Sweep processing. Saving to {str(savefile)}.')
        sweep_data = sweep.data
        sweep_data.set_diff_to_flag(get_num_value(self.flagging_lineEdit, float) * 1e3)
        self.save_sweep(savefile, sweep_data)
        return sweep_data
    
    def _write_new_tones(self, sweep_data: LoSweepData, rfsoc: RFSOCWrapper, chan: int):
        """Write the new tones from fitting an LO Sweep to the RFSoC"""
        tone_file = get_filename(file_type='tonelist', chan_name=rfsoc.get_channel_name(chan))
        sweep_data.save_new_tone_list(tone_file)
        _, curr_amp_list = rfsoc.get_tone_list(chan)  # Keep current amplitudes
        rfsoc.set_tone_list(chan, sweep_data.new_tone_list, amplitudes=curr_amp_list)
        _logger.info('Wrote new tone list to RFSoC')

    @ensure_path(1)
    def save_sweep(self, savefile: Path, sweep_data: LoSweepData):
        sweep_data.saveh5(savefile)
        sweep_data.savenp(savefile)
        _logger.info(f'Saved LO sweep data to {savefile}')
    
    def check_diagnostics(self):
        """Callback for when the "show diagnostics" box is clicked."""
        if self.show_diagnostics_checkBox.isChecked():
            self.only_flag_checkBox.show()
            self.review_tones_checkbox.show()
            self.save_plots_CheckBox.show()
        else:
            self.only_flag_checkBox.hide()
            self.review_tones_checkbox.hide()
            self.save_plots_CheckBox.hide()

    def check_second_sweep(self):
        """Callback for when the "perform second sweep" box is clicked."""
        if self.second_sweep_checkBox.isChecked():
            self.second_sweep_df_label.show()
            self.second_sweep_df_lineEdit.show()
            self.second_sweep_save_plots_checkBox.show()
        else:
            self.second_sweep_df_label.hide()
            self.second_sweep_df_lineEdit.hide()
            self.second_sweep_save_plots_checkBox.hide()

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

