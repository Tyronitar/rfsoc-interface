"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, TYPE_CHECKING
import logging
from threading import Thread
import pdb

import matplotlib.pyplot as plt
from matplotlib .figure import Figure
from PySide6.QtWidgets import QApplication, QRadioButton, QWidget, QDialog, QProgressDialog
from PySide6.QtCore import Signal, Slot
from kidpy3.measure import ResonatorFinder

from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.uic.loconfig_ui import Ui_LoConfigWidget as Ui_LOConfigWidget
from rfsocinterface.core.losweep import LoSweepData, LoSweep, DEFAULT_NCOLS, PowerSweep
from rfsocinterface.gui.lodiagnostics import DiagnosticsDialog
from rfsocinterface.gui.widgets import (
    get_num_value,
    IncrementalProgressDialog,
    make_progress_dialog_incrementer,
    IconLabel,
    ERROR_ICON_CODE
)
from rfsocinterface.core.rfsoc import RFSOCWrapper
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
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        """Initialize the LO configuration window."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self._sweep_dialog_results = []
        self._second_sweep_ran = False

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
        
        self.run_pushButton.clicked.connect(self.perform_sweep)
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
    
    @Slot()
    def perform_sweep(self):
        try:
            selected_channels = self.get_selected_channels(self.channel_comboBox)
        except SettingsError:
            self.channel_error_label.show()
            return
        self.channel_error_label.hide()

        # Always have to upload the new tones before the second sweep
        do_second_sweep = self.second_sweep_checkBox.isChecked()
        do_upload = True if do_second_sweep else self.upload_checkBox.isChecked()

        _logger.info('Beginning LO sweep...')
        sweep_succesful = self.run_sweeps(
            selected_channels,
            show_diagnostics=self.show_diagnostics_checkBox.isChecked(),
            upload_all_new_tone_lists=do_upload,
            second_sweep=False,
        )

        if not sweep_succesful:
            _logger.info('Cancelling after first sweep...')
            return

        if do_second_sweep:
            _logger.info('Beginning Second LO sweep...')
            self.run_sweeps(
                selected_channels,
                show_diagnostics=False,
                upload_all_new_tone_lists=False,
                second_sweep=True,
            )
    
    def run_sweeps(
            self,
            selected_channels: list[tuple[RFSOCWrapper, int]],
            show_diagnostics: bool=True,
            upload_all_new_tone_lists: bool=True,
            second_sweep: bool=False,
    ) -> bool:

        pd = IncrementalProgressDialog(
            f'Setting Up{" Second" if second_sweep else ""} LO Sweep...',
            'Cancel',
            0,
            100,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.show()
        QApplication.processEvents()
        increment_progress = make_progress_dialog_incrementer(pd)


        # Setup sweeps for each selected channel
        sweeps = self.setup_sweeps(selected_channels, second_sweep=second_sweep)

        # Update progress dialog values
        pd.setValue(0)
        pd.setMinimum(0)
        pd.setMaximum(sum(sweep.n_steps for sweep in sweeps))

        # Create separate thread for each sweep
        sweep_threads = []
        for sweep in sweeps:
            pd.canceled.connect(sweep.cancel)
            sweep_threads.append(Thread(target=sweep.run_sweep, args=(increment_progress,)))

        pd.setLabelText(f'Running LO Sweep{"s" if len(sweep_threads) > 1 else ""}...')
        for sweep_thread in sweep_threads:
            sweep_thread.start()

        # Wait for all sweeps to finish or cancel
        while not all ((sweep._processed or sweep._cancel) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for sweep_thread in sweep_threads:
            sweep_thread.join()

        QApplication.processEvents()

        if pd.wasCanceled():
            _logger.info('LO Sweep Cancelled')
            return False
        
        pd.close()

        if second_sweep:
            return True  # No fitting or plotting for second sweep

        # Below this comment, we're only dealing with the first sweep

        fit_complete = self.fit_sweeps(sweeps)
        if not fit_complete:
            return False

        if show_diagnostics:
            plot_complete = self.plot_sweeps(selected_channels, sweeps)
            if not plot_complete:
                return False

        # Upload new tone lists as needed
        # If a second sweep is going to happen (i.e `upload_all_new_tone_lists` = True),
        # all tone liusts are updated. Otherwise, only for sweeps that were acxcepted.
        for i, ((rfsoc, chan), sweep) in enumerate(zip(selected_channels, sweeps)):
            if upload_all_new_tone_lists or self._sweep_dialog_results[i] == QDialog.DialogCode.Accepted:
                self._write_new_tones(sweep.data, rfsoc, chan)

        return True
    
    def setup_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]], second_sweep: bool=False) -> list[LoSweep]:
        # Get values from GUI, converting KHz to Hz
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3
        diff_to_flag = get_num_value(self.flagging_lineEdit, float) * 1e3
        freq_step = get_num_value(self.df_lineEdit)  * 1e3
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3
        
        sweeps = []
        for rfsoc, chan in selected_channels:
            chan_name = rfsoc.get_channel_name(chan)


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
            
            if second_sweep:
                savefile = savefile.with_stem(f'{savefile.stem}_high_res')
            sweeps.append(LoSweep(
                rfsoc,
                chan,
                savefile,
                tone_shift,
                freq_step,
                full_span / 5 if second_sweep else full_span,
                diff_to_flag=diff_to_flag,
            ))
        return sweeps

    def fit_sweeps(self, sweeps: list[LoSweep]):
        # Setup progress dialog 
        total_steps = sum(sweep.data.ngoodchan for sweep in sweeps)
        pd = IncrementalProgressDialog(
            f'Fitting LO Sweep{"s" if len(sweeps) > 1 else ""}...',
            'Cancel',
            0,
            total_steps,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.setValue(0)
        pd.show()
        increment_progress = make_progress_dialog_incrementer(pd)

        fitting_threads = []
        for sweep in sweeps:
            sweep_data = sweep.data
            thread = Thread(target=sweep_data.fit, kwargs={'callback': increment_progress})
            fitting_threads.append(thread)
            pd.canceled.connect(sweep_data.cancel_fit)

        for thread in fitting_threads:
            thread.start()

        # Wait for all fits to finish or cancel
        while not all ((sweep.data._fitted or sweep.data._fit_cancelled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in fitting_threads:
            thread.join()

        QApplication.processEvents()

        if pd.wasCanceled():
            _logger.info('LO Sweep Cancelled')
            return False

        pd.close()

        # Save over sweeps now that fitting is completed
        for sweep in sweeps:
            sweep.data.saveh5(sweep.savefile)
        
        return True
    
    def plot_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]], sweeps: list[LoSweep]):
        # Setup progress dialog 
        total_steps = sum(sweep.data.nchan for sweep in sweeps)
        pd = IncrementalProgressDialog(
            f'Setting up plotting for LO sweep{"s" if len(sweeps) > 1 else ""}...',
            'Cancel',
            0,
            total_steps,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.setValue(0)
        pd.show()

        QApplication.processEvents()
        increment_progress = make_progress_dialog_incrementer(pd)

        plotting_threads = []
        dialogs: list[DiagnosticsDialog] = []
        figs: list[Figure] = []
        for (rfsoc, chan), sweep in zip(selected_channels, sweeps):
            sweep_data = sweep.data

            # Make diagnostics window and setup connections
            dw = DiagnosticsDialog(sweep_data, sweep.savefile, parent=self)
            dw.set_window_name(rfsoc.get_channel(chan).tile_name)
            # dw.finished.connect(lambda result: self._finish_sweep(result, sweep.savefile, sweep_data, rfsoc, chan, dw, False))
            dw.finished.connect(self.handle_diagnostic_window_finished)
            dw.upload_pushButton.clicked.connect(lambda: self._write_new_tones(sweep_data, rfsoc, chan))
            dialogs.append(dw)

            QApplication.processEvents()

            ncols = DEFAULT_NCOLS
            nrows = int(np.ceil(sweep_data.nchan / ncols))
            fig = plt.figure(figsize=(ncols, nrows), dpi=100)
            for i in range(1, sweep_data.nchan + 1):
                fig.add_subplot(nrows, ncols, i, aspect='equal', xticks=[], yticks=[])
            figs.append(fig)
            thread = Thread(target=dw.plot, kwargs={'fig': fig, 'callback': increment_progress})
            plotting_threads.append(thread)
            pd.canceled.connect(sweep_data.cancel_plot)
        
        pd.setLabelText(f'Plotting LO sweep{"s" if len(sweeps) > 1 else ""}...')
        QApplication.processEvents()

        for thread in plotting_threads:
            thread.start()

        # Wait for all fits to finish or cancel
        while not all ((sweep.data._plotted or sweep.data._plot_cancelled) for sweep in sweeps):
            pd.show()
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in plotting_threads:
            thread.join()

        QApplication.processEvents()
        
        if pd.wasCanceled():
            # TODO: Handle cancel (i.e. destroy the plots and the dialogs)
            _logger.info('LO Sweep Plotting Cancelled')
            return False
        pd.close()

        for dw, fig in zip(dialogs, figs):
            dw.set_figure(fig)
            QApplication.processEvents()
            # fig.tight_layout()
            dw.show()
        
        self._wait_for_sweep_dialogs(dialogs)
        return True

    @Slot(int)
    def handle_diagnostic_window_finished(self, result: int):
        source = self.sender()
        index = self._dialogs.index(source)
        self._sweep_dialog_results[index] = result
    
    def _wait_for_sweep_dialogs(self, dialogs: list[DiagnosticsDialog]):
        _logger.debug('Wiating for LO diagnostics dialogs to finish...')
        self._dialogs = dialogs
        n_sweeps = len(dialogs)
        self._sweep_dialog_results = [None for _ in range(n_sweeps)]
        while self._sweep_dialog_results.count(None) > 0:
            QApplication.processEvents()
            time.sleep(0.1)
        _logger.debug('All LO diagnostics dialogs finished')
        
    def run_blind_sweep(self, rfsoc: RFSOCWrapper, chan: int):
        chan_name = rfsoc.get_channel_name(chan)

        # Get values from GUI, converting KHz to Hz
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3
        diff_to_flag = get_num_value(self.flagging_lineEdit, float) * 1e3
        freq_step = get_num_value(self.df_lineEdit)  * 1e3
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3

        savefile = get_filename(
            file_type="LO", chan_name=chan_name, mkdir=True
        )
        savefile = savefile.with_stem(f'{savefile.stem}')
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
        # sweep = LoSweep(
        sweep = PowerSweep(
            rfsoc,
            chan,
            savefile,
            [-2, 0, 2],
            tone_shift,
            freq_step,
            full_span,
            # diff_to_flag=diff_to_flag,
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

        while not (sweep._processed or sweep._cancel):
            QApplication.processEvents()
            time.sleep(0.1)
        
        sweep_thread.join()
        if sweep._cancel:
            _logger.info('LO Sweep Cancelled')
            return

        # TODO
        # Fit sweep if requested...
        #    Multiprocessing???
        # Show diagnostics dialog if requested...
        sweep_data = sweep.data
        self.save_sweep(savefile, sweep_data)

        sfreq, z = sweep_data.data
        s21_sqrd = z.real ** 2 + z.imag ** 2
        s21_pow = 10 * np.log10(s21_sqrd)
        for i in range(sweep_data.nchan):
            plt.plot(sfreq[i] / 1e6, s21_pow[i])
        plt.xticks(fontsize=16)
        plt.yticks(fontsize=16)
        plt.xlabel("Frequency (MHz)", fontsize=18)
        plt.ylabel("dB", fontsize=18)
        plt.legend(["S21 of resonator sweep"], fontsize=18)
        plt.show()



        # finder.plot()

        finder = ResonatorFinder(
            sweep_data.data,
            sweep_data.f_center,
            freq_step,
        )
        freqs, depths = finder.find_resonators()
        pdb.set_trace()
    
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

