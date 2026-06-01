"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, TYPE_CHECKING
import logging
from threading import Thread
import pdb

import matplotlib.pyplot as plt
from matplotlib .figure import Figure
from PySide6.QtWidgets import QApplication, QRadioButton, QWidget, QDialog, QProgressDialog
from PySide6.QtCore import Signal, Slot, Qt
from kidpy3.measure import ResonatorFinder

from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.uic.loconfig_ui import Ui_LoConfigWidget as Ui_LOConfigWidget
from rfsocinterface.core.sweeps import LoSweepData, LoSweep, DEFAULT_NCOLS, PowerSweep
from rfsocinterface.gui.lodiagnostics import DiagnosticsDialog, BlindSweepDialog
from rfsocinterface.gui.widgets import (
    get_num_value,
    IncrementalProgressDialog,
    make_progress_dialog_incrementer,
    IconLabel,
    ERROR_ICON_CODE
)
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import (
    ensure_path,
    get_filename,
    TabName,
    get_sweep_filename,
    dict_get_by_path,
    dict_set_by_path,
    dict_get_by_path_with_default,
    dict_get_with_default,
    load_dict_or_defaults,
)
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
    tab_name = TabName.LOSWEEP

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        """Initialize the LO configuration window."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self._sweep_dialog_results = []
        self._highres_sweep_ran = False

        self.channel_comboBox.set_default_title('Select Channels...')

        self.lo_sweep_widgets = [
            self.show_diagnostics_checkBox,
            self.upload_checkBox,
            self.save_plots_CheckBox,
            self.only_flag_checkBox,
            self.review_tones_checkbox,
            self.flagging_label,
            self.flagging_lineEdit,
            self.global_shift_label,
            self.global_shift_lineEdit
        ]

        self.highres_sweep_widgets = [
            self.highres_sweep_checkBox,
            self.highres_sweep_df_label,
            self.highres_sweep_df_lineEdit,
            self.highres_sweep_save_plots_checkBox,
            self.only_highres_checkBox,
        ]
        self.power_sweep_widgets = [
            self.power_levels_Label,
            self.power_levels_lineEdit,
            self.global_shift_label,
            self.global_shift_lineEdit
        ]
        self.blind_sweep_widgets = [
            self.show_diagnostics_checkBox,
            self.blind_groupBox,
        ]

        self.blind_sweep_lineEdits = [
            self.blind_res_depth_lineEdit,
            self.blind_spacing_lineEdit,
            self.blind_samples_lineEdit,
            self.blind_noise_fluc_lineEdit,
            self.blind_baseline_lineEdit,
        ]

        # This signal needs to be connected before loading the GUI state
        self.sweep_type_buttonGroup.buttonClicked.connect(self.select_sweep_type)  
        self.load_gui_state_from_settings()

        self.make_error_labels()    
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(lambda: self.update_channel_choices(self.channel_comboBox))
        self.filename_buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.highres_sweep_checkBox.clicked.connect(self.check_highres_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.only_highres_checkBox.clicked.connect(self.check_only_highres)
        self.filename_temperature_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        self.filename_elevation_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        
        self.run_pushButton.clicked.connect(self.perform_sweep)
        self.restore_defaults_pushButton.clicked.connect(self.restore_defaults)
        self.channel_toolButton.clicked.connect(self.open_channels_in_initialization_tab)    
    
    def get_current_gui_state(self):
        # Sweep type
        match self.sweep_type_buttonGroup.checkedButton():
            case self.lo_sweep_radioButton:
                self.gui_state['sweepType'] = 'lo'
            case self.power_sweep_radioButton:
                self.gui_state['sweepType'] = 'power'
            case self.blind_sweep_radioButton:
                self.gui_state['sweepType'] = 'blind'
            case _:
                pass
        
        # LO Parameters
        self.gui_state['globalShift'] = get_num_value(self.global_shift_lineEdit)
        self.gui_state['df'] = get_num_value(self.df_lineEdit)
        self.gui_state['deltaf'] = get_num_value(self.deltaf_lineEdit)
        self.gui_state['flaggingThreshold'] = get_num_value(self.flagging_lineEdit)
        self.gui_state['showDiagnostics'] = self.show_diagnostics_checkBox.isChecked()
        self.gui_state['uploadTones'] = self.upload_checkBox.isChecked()
        self.gui_state['savePlots'] = self.save_plots_CheckBox.isChecked()
        self.gui_state['onlyShowFlagged'] = self.only_flag_checkBox.isChecked()
        self.gui_state['reviewTones'] = self.review_tones_checkbox.isChecked()

        # Highres Parameters
        self.gui_state['onlyHighres'] = self.only_highres_checkBox.isChecked()
        self.gui_state['doHighres'] = self.highres_sweep_checkBox.isChecked()
        dict_set_by_path(self.gui_state, ('highres', 'df'), get_num_value(self.highres_sweep_df_lineEdit))
        dict_set_by_path(self.gui_state, ('highres', 'savePlots'), self.highres_sweep_save_plots_checkBox.isChecked())

        # Power Sweep Parameters
        self.gui_state['powerLevels'] = self.get_power_levels()

        # Blind Sweep Parameters
        blind_keys = [
            ('blindSweep', 'minResonanceDepth'),
            ('blindSweep', 'spacingThreshold'),
            ('blindSweep', 'minSamplesPerResonance'),
            ('blindSweep', 'maxNoiseFluctuation'),
            ('blindSweep', 'baselinePercentile'),
        ]
        blind_types = [float, float, int, float, int]
        for key, lineEdit, num_type in zip(blind_keys, self.blind_sweep_lineEdits, blind_types):
            try:
                dict_set_by_path(
                    self.gui_state,
                    key,
                    get_num_value(lineEdit, num_type=num_type),
                )
            except ValueError:
                continue

        # Filename Suffix
        self.gui_state['filenameSuffixMode'] = self.active_suffix
        self.gui_state['temperatureFilenameSuffix'] = self.filename_temperature_lineEdit.text()
        self.gui_state['elevationFilenameSuffix'] = self.filename_elevation_lineEdit.text()
    
    def load_gui_state_from_settings(self):
        defaults = self.settings['defaults'][self.tab_name]
        saved_gui_state = dict_get_by_path(self.settings, ('app', self.tab_name), {})

        items = [
            ('sweepType', 'lo'),
            # LO Parameters
            ('globalShift', 0.0),
            ('df', 1.0),
            ('deltaf', 100.0),
            ('flaggingThreshold', 3.0),
            ('showDiagnostics', True),
            ('uploadTones', False),
            ('savePlots', False),
            ('onlyShowFlagged', False),
            ('reviewTones', True),
            # Filename Suffix
            ('filenameSuffixMode', 'none'),
            ('temperatureFilenameSuffix', ''),
            ('elevationFilenameSuffix', ''),
            # Highres Parameters
            ('onlyHighres', False),
            ('doHighres', False),
            (('highres', 'df'), 1.0),
            (('highres', 'savePlots'), False),
            # Power Sweep Parameters
            ('powerLevels', []),
            # Blind Sweep Parameters
            (('blindSweep', 'minResonanceDepth'), 0.2),
            (('blindSweep', 'spacingThreshold'), 3000),
            (('blindSweep', 'minSamplesPerResonance'), 2),
            (('blindSweep', 'maxNoiseFluctuation'), 0.05),
            (('blindSweep', 'baselinePercentile'), 50),
        ]

        self.gui_state = load_dict_or_defaults(saved_gui_state, defaults, items)
        self._update_gui_to_match_settings()
    
    def _update_gui_to_match_settings(self):

        
        # LO Parameters
        self.global_shift_lineEdit.setText(str(self.gui_state['globalShift']))
        self.df_lineEdit.setText(str(self.gui_state['df']))
        self.deltaf_lineEdit.setText(str(self.gui_state['deltaf']))
        self.flagging_lineEdit.setText(str(self.gui_state['flaggingThreshold']))
        self.show_diagnostics_checkBox.setChecked(self.gui_state['showDiagnostics'])
        self.upload_checkBox.setChecked(self.gui_state['uploadTones'])
        self.save_plots_CheckBox.setChecked(self.gui_state['savePlots'])
        self.only_flag_checkBox.setChecked(self.gui_state['onlyShowFlagged'])
        self.review_tones_checkbox.setChecked(self.gui_state['reviewTones'])

        # Filename Suffix
        match self.gui_state['filenameSuffixMode']:
            case 'none':
                self.filename_none_radioButton.click()
            case 'temperature':
                self.filename_temperature_radioButton.click()
            case 'elevation':
                self.filename_elevation_radioButton.click()
        self.filename_temperature_lineEdit.setText(self.gui_state['temperatureFilenameSuffix'])
        self.filename_elevation_lineEdit.setText(self.gui_state['elevationFilenameSuffix'])
        self.active_suffix = self.gui_state['filenameSuffixMode']

        # Highres Parameters
        self.highres_sweep_save_plots_checkBox.setChecked(self.gui_state['highres']['savePlots'])
        self.highres_sweep_df_lineEdit.setText(str(self.gui_state['highres']['df']))
        self.highres_sweep_checkBox.setChecked(self.gui_state['doHighres'])
        self.only_highres_checkBox.setChecked(self.gui_state['onlyHighres'])

        # Power Sweep Parameters
        self.power_levels_lineEdit.setText(','.join(str(x) for x in self.gui_state['powerLevels']))

        # Blind Sweep Parameters
        blind_keys = [
            ('blindSweep', 'minResonanceDepth'),
            ('blindSweep', 'spacingThreshold'),
            ('blindSweep', 'minSamplesPerResonance'),
            ('blindSweep', 'maxNoiseFluctuation'),
            ('blindSweep', 'baselinePercentile'),
        ]
        for key, lineEdit in zip(blind_keys, self.blind_sweep_lineEdits):
            lineEdit.setText(str(dict_get_by_path(self.gui_state, key, default='')))

        # Sweep Type
        match self.gui_state['sweepType']:
            case 'lo':
                self.lo_sweep_radioButton.click()
            case 'power':
                self.power_sweep_radioButton.click()
            case 'blind':
                self.blind_sweep_radioButton.click()
        
    def restore_defaults(self):
        defaults = self.settings['defaults'][self.tab_name]
        self.gui_state.update(defaults)
        self._update_gui_to_match_settings()
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

        match self.sweep_type_buttonGroup.checkedButton():
            case self.lo_sweep_radioButton:
                if not self.only_highres_checkBox.isChecked():
                    # Always have to upload the new tones before the highres sweep
                    do_highres_sweep = self.highres_sweep_checkBox.isChecked()
                    do_upload = True if do_highres_sweep else self.upload_checkBox.isChecked()

                    _logger.info('Beginning LO sweep...')
                    sweep_succesful = self.run_sweeps(
                        selected_channels,
                        show_diagnostics=self.show_diagnostics_checkBox.isChecked(),
                        upload_all_new_tone_lists=do_upload,
                        high_res_sweep=False,
                    )

                    if not sweep_succesful:
                        _logger.info('Canceled after first sweep.')
                        return

                if self.only_highres_checkBox.isChecked() or do_highres_sweep:
                    _logger.info('Beginning High Resolution LO sweep...')
                    highres_sweep_succesful = self.run_sweeps(
                        selected_channels,
                        show_diagnostics=False,
                        upload_all_new_tone_lists=False,
                        high_res_sweep=True,
                    )
                    if not highres_sweep_succesful:
                        _logger.info('Canceled high resolution sweep.')
                        return
            case self.blind_sweep_radioButton:
                _logger.info('Beginning blind sweep...')
                sweep_succesful = self.run_sweeps(
                    selected_channels,
                    show_diagnostics=self.show_diagnostics_checkBox.isChecked(),
                    upload_all_new_tone_lists=False,
                    high_res_sweep=False,
                    sweep_type='blind',
                )

                if not sweep_succesful:
                    _logger.info('Blind sweep canceled.')
                    return
                
                # TODO: Use Blind sweep dialog

            case self.power_sweep_radioButton:
                _logger.info('Beginning power sweep...')
                sweep_succesful = self.run_power_sweeps(selected_channels)
                if not sweep_succesful:
                    _logger.info('Power sweep canceled.')
                
    def run_sweeps(
            self,
            selected_channels: list[tuple[RFSOCWrapper, int]],
            show_diagnostics: bool=True,
            upload_all_new_tone_lists: bool=True,
            high_res_sweep: bool=False,
            sweep_type: Literal['lo', 'blind']='lo',
    ) -> bool:

        blind_sweep = sweep_type == 'blind'

        pd = IncrementalProgressDialog(
            f'Setting Up{" High Resolution" if high_res_sweep else ""} {"Blind" if blind_sweep else "LO"} Sweep...',
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
        sweeps = self.setup_sweeps(selected_channels, high_res_sweep=high_res_sweep)

        # Update progress dialog values
        pd.setValue(0)
        pd.setMinimum(0)
        pd.setMaximum(sum(sweep.n_steps for sweep in sweeps))

        # Create separate thread for each sweep
        sweep_threads = []
        for sweep in sweeps:
            pd.canceled.connect(sweep.cancel)
            sweep_threads.append(Thread(target=sweep.run_sweep, args=(increment_progress,)))

        pd.setLabelText(f'Running{" High Resolution" if high_res_sweep else ""} {"Blind" if blind_sweep else "LO"} Sweep{"s" if len(sweep_threads) > 1 else ""}...')
        for sweep_thread in sweep_threads:
            sweep_thread.start()

        # Wait for all sweeps to finish or cancel
        while not all ((sweep._processed or sweep._canceled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for sweep_thread in sweep_threads:
            sweep_thread.join()

        QApplication.processEvents()

        if pd.wasCanceled() or any(sweep._canceled for sweep in sweeps):
            # _logger.info('LO Sweep Canceled')
            return False
        
        pd.close()

        if not blind_sweep and high_res_sweep:
            return True  # No fitting or plotting for highres sweep

        # Below this comment, we're only dealing with the first sweep

        if not blind_sweep:
            fit_complete = self.fit_sweeps(sweeps)
            if not fit_complete:
                return False

        # TODO: Finish handling the blind sweep case for plotting
        if show_diagnostics:
            if blind_sweep:
                plot_complete = self.plot_blind_sweeps(selected_channels, sweeps)
            else:
                plot_complete = self.plot_sweeps(selected_channels, sweeps)
            if not plot_complete:
                return False

        # Upload new tone lists as needed
        # If a highres sweep is going to happen (i.e `upload_all_new_tone_lists` = True),
        # all tone liusts are updated. Otherwise, only for sweeps that were acxcepted.
        for i, ((rfsoc, chan), sweep) in enumerate(zip(selected_channels, sweeps)):
            if upload_all_new_tone_lists or self._sweep_dialog_results[i] == QDialog.DialogCode.Accepted:
                self._write_new_tones(sweep.data, rfsoc, chan)

        return True
    
    def setup_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]], high_res_sweep: bool=False) -> list[LoSweep]:
        # Get values from GUI, converting KHz to Hz
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3
        diff_to_flag = get_num_value(self.flagging_lineEdit, float) * 1e3
        freq_step = get_num_value(self.df_lineEdit)  * 1e3
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3
        
        sweeps = []
        for rfsoc, chan in selected_channels:
            chan_name = rfsoc.get_channel_name(chan)


            suffix = ''
            match self.filename_buttonGroup.checkedButton():
                case self.filename_elevation_radioButton:
                    suffix += f'{savefile.stem}_elev_{self.filename_elevation_lineEdit.text()}'
                case self.filename_temperature_radioButton:
                    suffix += f'{savefile.stem}_temp_{self.filename_temperature_lineEdit.text()}'
                case _:
                    pass
            if high_res_sweep:
                suffix = '_'.join(filter(None, (suffix, 'high_res')))
            savefile = get_sweep_filename(
                sweep_type='lo',
                chan_name=chan_name,
                suffix=suffix,
                mkdir=True,
            )
            
            sweeps.append(LoSweep(
                rfsoc,
                chan,
                savefile,
                tone_shift,
                freq_step,
                full_span / 5 if high_res_sweep else full_span,
                diff_to_flag=diff_to_flag,
            ))
        return sweeps

    def fit_sweeps(self, sweeps: list[LoSweep]) -> bool:
        # Setup progress dialog 
        total_steps = sum(sweep.data.n_fits for sweep in sweeps)
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
        while not all ((sweep.data._fitted or sweep.data._fit_canceled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in fitting_threads:
            thread.join()

        QApplication.processEvents()

        if pd.wasCanceled() or any(sweep.data._fit_canceled for sweep in sweeps):
            # _logger.info('LO Sweep Canceled')
            return False

        pd.close()

        # Save over sweeps now that fitting is completed
        for sweep in sweeps:
            sweep.data.save(sweep.savefile)
        
        return True
    
    def plot_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]], sweeps: list[LoSweep]) -> bool:

        # for (rfsoc, chan), sweep in zip(selected_channels, sweeps):
        #     sweep_data = sweep.data
        #     dialog = BlindSweepDialog(sweep_data, parent=self)
        #     dialog.set_window_name(rfsoc.get_channel(chan).tile_name)
        #     dialog.plot()
        #     dialog.exec()
        

        # pdb.set_trace()


        # Setup progress dialog 
        total_steps = sum(sweep.data.n_plots for sweep in sweeps)
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
            nrows = int(np.ceil(sweep_data.n_tones / ncols))
            fig = plt.figure(figsize=(ncols, nrows), dpi=100)
            for i in range(1, sweep_data.n_tones + 1):
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
        while not all ((sweep.data._plotted or sweep.data._plot_canceled) for sweep in sweeps):
            pd.show()
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in plotting_threads:
            thread.join()

        QApplication.processEvents()
        
        if pd.wasCanceled() or any(sweep.data._plot_canceled for sweep in sweeps):
            # TODO: Handle cancel (i.e. destroy the plots and the dialogs)
            # _logger.info('LO Sweep Plotting Canceled')
            return False
        pd.close()

        for dw, fig in zip(dialogs, figs):
            dw.set_figure(fig)
            QApplication.processEvents()
            # fig.tight_layout()
            dw.show()
        
        self._wait_for_sweep_dialogs(dialogs)
        return True

    def plot_blind_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]], sweeps: list[LoSweep]) -> bool:
        # Setup progress dialog 
        total_tones = sum(sweep.data.n_tones for sweep in sweeps)
        pd = IncrementalProgressDialog(
            f'Setting up plotting for Blind sweep{"s" if len(sweeps) > 1 else ""}...',
            'Cancel',
            0,
            total_tones,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.setValue(0)
        pd.show()

        QApplication.processEvents()
        increment_progress = make_progress_dialog_incrementer(pd)

        # Get values from GUI
        min_res_depth = get_num_value(self.blind_res_depth_lineEdit, use_placeholder_text=True)
        spacing_threshold = get_num_value(self.blind_spacing_lineEdit, use_placeholder_text=True)
        min_samples = get_num_value(self.blind_samples_lineEdit, num_type=int, use_placeholder_text=True)
        max_noise = get_num_value(self.blind_noise_fluc_lineEdit, use_placeholder_text=True)
        baseline = get_num_value(self.blind_baseline_lineEdit, num_type=int, use_placeholder_text=True)

        plotting_threads = []
        dialogs: list[BlindSweepDialog] = []
        for (rfsoc, chan), sweep in zip(selected_channels, sweeps):
            sweep_data = sweep.data
            sweep_data.reset_stop_signals()

            # Make blind sweep window and setup connections
            dw = BlindSweepDialog(sweep_data, parent=self)
            dw.set_window_name(rfsoc.get_channel(chan).tile_name)
            dw.finished.connect(self.handle_diagnostic_window_finished)
            dialogs.append(dw)

            QApplication.processEvents()

            thread = Thread(
                target=dw.find_resonances_and_plot,
                kwargs={
                    'callback': increment_progress,
                    'min_resonance_depth_dB': min_res_depth,
                    'spacing_threshold_Hz': spacing_threshold,
                    'min_samples_per_resonance': min_samples,
                    'max_noise_fluctuation_dB': max_noise,
                    'baseline_percentile': baseline,
                },
            )
            plotting_threads.append(thread)
            pd.canceled.connect(dw.cancel)
        
        pd.setLabelText(f'Plotting LO sweep{"s" if len(sweeps) > 1 else ""}...')
        QApplication.processEvents()

        for thread in plotting_threads:
            thread.start()

        # Wait for all fits to finish or cancel
        while not all ((sweep.data._plotted or sweep.data._plot_canceled) for sweep in sweeps):
            pd.show()
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in plotting_threads:
            thread.join()

        QApplication.processEvents()
        
        if pd.wasCanceled() or any(sweep.data._plot_canceled for sweep in sweeps):
            # TODO: Handle cancel (i.e. destroy the plots and the dialogs)
            # _logger.info('Blind Sweep Plotting Canceled')
            return False
        pd.close()

        for dw in dialogs:
            dw.show()
        
        self._wait_for_sweep_dialogs(dialogs)
        return True

    @Slot(int)
    def handle_diagnostic_window_finished(self, result: int):
        source = self.sender()
        index = self._dialogs.index(source)
        self._sweep_dialog_results[index] = result
    
    def _wait_for_sweep_dialogs(self, dialogs: list[DiagnosticsDialog]):
        _logger.debug('Waiting for LO dialogs to finish...')
        self._dialogs = dialogs
        n_sweeps = len(dialogs)
        self._sweep_dialog_results = [None for _ in range(n_sweeps)]
        while self._sweep_dialog_results.count(None) > 0:
            QApplication.processEvents()
            time.sleep(0.1)
        _logger.debug('All LO dialogs finished')

    def run_power_sweeps(
            self,
            selected_channels: list[tuple[RFSOCWrapper, int]],
    ) -> bool:

        pd = IncrementalProgressDialog(
            f'Setting Up Power Sweep...',
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
        sweeps = self.setup_power_sweeps(selected_channels)

        # Update progress dialog values
        pd.setValue(0)
        pd.setMinimum(0)
        pd.setMaximum(sum(sweep.n_steps for sweep in sweeps))

        # Create separate thread for each sweep
        sweep_threads = []
        for sweep in sweeps:
            pd.canceled.connect(sweep.cancel)
            sweep_threads.append(Thread(target=sweep.run_sweep, args=(increment_progress,)))

        pd.setLabelText(f'Running Power Sweep{"s" if len(sweep_threads) > 1 else ""}...')
        for sweep_thread in sweep_threads:
            sweep_thread.start()

        # Wait for all sweeps to finish or cancel
        while not all ((sweep._processed or sweep._canceled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for sweep_thread in sweep_threads:
            sweep_thread.join()

        QApplication.processEvents()

        if pd.wasCanceled() or any(sweep._canceled for sweep in sweeps):
            # _logger.info('Power Sweep Canceled')
            return False
        
        pd.close()

        if not self.fit_power_sweeps(sweeps):
            return False

        return self.plot_power_sweeps(sweeps)
    
    def setup_power_sweeps(self, selected_channels: list[tuple[RFSOCWrapper, int]]) -> list[PowerSweep]:
        # Get values from GUI, converting KHz to Hz
        tone_shift = get_num_value(self.global_shift_lineEdit) * 1e3
        freq_step = get_num_value(self.df_lineEdit)  * 1e3
        full_span = get_num_value(self.deltaf_lineEdit)  * 1e3
        power_levels = self.get_power_levels()
        
        sweeps = []
        for rfsoc, chan in selected_channels:
            chan_name = rfsoc.get_channel_name(chan)


            savefile = get_filename(
                file_type="power", chan_name=chan_name, mkdir=True
            )
            match self.filename_buttonGroup.checkedButton():
                case self.filename_elevation_radioButton:
                    savefile = savefile.with_stem(f'{savefile.stem}_elev_{self.filename_elevation_lineEdit.text()}')
                case self.filename_temperature_radioButton:
                    savefile = savefile.with_stem(f'{savefile.stem}_temp_{self.filename_temperature_lineEdit.text()}')
                case _:
                    pass
            sweeps.append(PowerSweep(
                rfsoc,
                chan,
                tone_shift,
                freq_step,
                full_span,
                power_levels,
                savefile=savefile,
            ))
            
        return sweeps

    def fit_power_sweeps(self, sweeps: list[PowerSweep]) -> bool:
        # Setup progress dialog 
        total_steps = sum(sweep.data.n_fits for sweep in sweeps)
        pd = IncrementalProgressDialog(
            f'Fitting Power Sweep{"s" if len(sweeps) > 1 else ""}...',
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
        while not all ((sweep.data._fitted or sweep.data._fit_canceled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in fitting_threads:
            thread.join()

        QApplication.processEvents()

        if pd.wasCanceled() or any(sweep.data._fit_canceled for sweep in sweeps):
            # _logger.info('Power Sweep Canceled')
            return False

        pd.close()

        # Save over sweeps now that fitting is completed
        for sweep in sweeps:
            sweep.data.save(sweep.savefile)
        
        return True

    def plot_power_sweeps(self, sweeps: list[PowerSweep]) -> bool:
        # Setup progress dialog 
        total_steps = sum(sweep.data.n_plots for sweep in sweeps)
        pd = IncrementalProgressDialog(
            f'Plotting Power Sweep{"s" if len(sweeps) > 1 else ""}...',
            'Cancel',
            0,
            total_steps,
            parent=self,
        )
        pd.setAutoClose(True)
        pd.setValue(0)
        pd.show()
        increment_progress = make_progress_dialog_incrementer(pd)

        plotting_threads = []
        for sweep in sweeps:
            sweep_data = sweep.data
            thread = Thread(target=sweep_data.plot_optimal_readout_powers, kwargs={'callback': increment_progress})
            plotting_threads.append(thread)
            pd.canceled.connect(sweep_data.cancel_fit)

        for thread in plotting_threads:
            thread.start()

        # Wait for all plotting to finish or cancel
        while not all ((sweep.data._plotted or sweep.data._plot_canceled) for sweep in sweeps):
            QApplication.processEvents()
            time.sleep(0.1)
        
        for thread in plotting_threads:
            thread.join()

        QApplication.processEvents()

        if pd.wasCanceled() or any(sweep.data._plot_canceled for sweep in sweeps):
            # _logger.info('Power Sweep Canceled')
            return False

        pd.close()
        
        return True
    
    def get_power_levels(self) -> list[float]:
        levels = [float(x.strip()) for x in filter(None, self.power_levels_lineEdit.text().split(','))]
        if len(levels) == 0:
            levels = [0]
        return levels

    def _write_new_tones(self, sweep_data: LoSweepData, rfsoc: RFSOCWrapper, chan: int):
        """Write the new tones from fitting an LO Sweep to the RFSoC"""
        tone_file = get_filename(file_type='tonelist', chan_name=rfsoc.get_channel_name(chan))
        sweep_data.save_new_tone_list(tone_file)
        _, curr_amp_list = rfsoc.get_tone_list(chan)  # Keep current amplitudes
        rfsoc.set_tone_list(chan, sweep_data.new_baseband_freqs, amplitudes=curr_amp_list)
        _logger.info('Wrote new tone list to RFSoC')

    @ensure_path(1)
    def save_sweep(self, savefile: Path, sweep_data: LoSweepData):
        sweep_data.save(savefile)
        sweep_data.savenp(savefile)
        _logger.info(f'Saved LO sweep data to {savefile}')
    
    def check_diagnostics(self):
        """Callback for when the "show diagnostics" box is clicked."""
        self._diagnostics_visibility()
        self.gui_state['showDiagnostics'] = self.show_diagnostics_checkBox.isChecked()
    
    def _diagnostics_visibility(self):
        is_checked = self.show_diagnostics_checkBox.isChecked()
        self.only_flag_checkBox.setVisible(is_checked)
        self.review_tones_checkbox.setVisible(is_checked)
        self.save_plots_CheckBox.setVisible(is_checked)

    def check_highres_sweep(self):
        """Callback for when the "perform highres sweep" box is clicked."""
        self._highres_visibility()
        self.gui_state['doHighres'] = self.highres_sweep_checkBox.isChecked()
    
    def _highres_visibility(self):
        show = self.highres_sweep_checkBox.isChecked() and not self.only_highres_checkBox.isChecked()
        self.highres_sweep_df_label.setVisible(show)
        self.highres_sweep_df_lineEdit.setVisible(show)
        self.highres_sweep_save_plots_checkBox.setVisible(show)
    
    def check_only_highres(self):
        """Callback for when the "ONLY perform highres sweep" box is clicked."""
        self.gui_state['onlyHighres'] = self.only_highres_checkBox.isChecked()
        self._only_highres_visibility()
    
    def _only_highres_visibility(self):
        is_checked = self.only_highres_checkBox.isChecked()
        self._diagnostics_visibility()
        self._highres_visibility()

        self.only_flag_checkBox.setVisible(not is_checked)
        self.review_tones_checkbox.setVisible(not is_checked)
        self.save_plots_CheckBox.setVisible(not is_checked)
        self.show_diagnostics_checkBox.setVisible(not is_checked)
        self.highres_sweep_checkBox.setVisible(not is_checked)
        self.upload_checkBox.setVisible(not is_checked)

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

        self.gui_state['filenameSuffixMode'] = self.active_suffix

        self.update_filename_example()
    
    def select_sweep_type(self, button: QRadioButton):
        """Callback for when the sweep type is changed."""
        match button:
            case self.lo_sweep_radioButton:
                for widget in self.power_sweep_widgets:
                    widget.hide()
                for widget in self.blind_sweep_widgets:
                    widget.hide()
                for widget in self.lo_sweep_widgets + self.highres_sweep_widgets:
                    widget.show()
                self._diagnostics_visibility()
                # self._highres_visibility()
                self._only_highres_visibility()
                self.gui_state['sweepType'] = 'lo'
            case self.power_sweep_radioButton:
                for widget in self.lo_sweep_widgets + self.highres_sweep_widgets:
                    widget.hide()
                for widget in self.blind_sweep_widgets:
                    widget.hide()
                for widget in self.power_sweep_widgets:
                    widget.show()
                self.gui_state['sweepType'] = 'power'
            case self.blind_sweep_radioButton:
                for widget in self.lo_sweep_widgets + self.highres_sweep_widgets:
                    widget.hide()
                for widget in self.power_sweep_widgets:
                    widget.hide()
                for widget in self.blind_sweep_widgets:
                    widget.show()
                self.gui_state['sweepType'] = 'blind'
            case _:
                raise ValueError(f'Unexpected button {button} received.')

    def update_filename_example(self):
        """Update the example filename box to reflect the chosen suffix."""
        match self.active_suffix:
            case 'none':
                self.filename_example_lineEdit.setText(DEFAULT_FILENAME)
            case 'temperature':
                self.filename_example_lineEdit.setText(
                    f'{DEFAULT_FILENAME}_temp{self.filename_temperature_lineEdit.text()}'
                )
                self.gui_state['temperatureFilenameSuffix'] = self.filename_temperature_lineEdit.text()
            case 'elevation':
                self.filename_example_lineEdit.setText(
                    f'{DEFAULT_FILENAME}_elev{self.filename_elevation_lineEdit.text()}'
                )
                self.gui_state['elevationFilenameSuffix'] = self.filename_elevation_lineEdit.text()
            case _:
                raise RuntimeError(
                    f'Invalid `active_suffix` encountered: {self.active_suffix}'
                )
    
    def closeEvent(self, event):
        # Save current state of GUI
        self.get_current_gui_state()
        return super().closeEvent(event)

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication()
    win = QMainWindow()
    wid = LoConfigWidget(None, [], {})
    win.setCentralWidget(wid)
    win.show()

    app.exec()