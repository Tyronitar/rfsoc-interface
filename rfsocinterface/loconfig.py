"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, Type, Callable, TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QRadioButton, QLineEdit, QWidget, QProgressDialog, QTabWidget
from PySide6.QtCore import Qt

from rfsocinterface.ui.loconfig_ui import Ui_LoConfigWidget as Ui_LOConfigWidget
from rfsocinterface.losweep import LoSweepData, get_tone_list, LoSweep
from rfsocinterface.lodiagnostics import DiagnosticsDialog
from rfsocinterface.progress_bar import ProgressBarDialog, SequentialProgressBarDialog
from rfsocinterface.rfsoc import RFSOCWrapper
from rfsocinterface.ui.icon_label import IconLabel, ERROR_ICON_CODE
from rfsocinterface.initialization import InitializationWidget

from kidpy import kidpy
# from kidpy3 import RFSOC
from kidpy3.hardware.Valon5009 import Valon5009, SYNTH_A, SYNTH_B
import time
# import valon5009
import numpy as np
import onrkidpy
import sweeps
import h5py
from rfsocinterface.utils import write_fList, Number, test_connection, add_callbacks, Job, get_num_value, PathLike, ensure_path, JobInterrupt, SettingsError

if TYPE_CHECKING:
    from rfsocinterface.main_window import MainWindow

DEFAULT_FILENAME = 'YYYYMMDD_rfsocN_LO_Sweep_hourHH'
DEFAULT_F_CENTER = 400.0
DEFAULT_CHANMASK = '/home/onrkids/readout/host/params/chanmask_rfsoc2.npy'
FILE_SUFFIXES = {'none', 'temperature', 'elevation'}


class LoConfigWidget(QWidget, Ui_LOConfigWidget):
    """Window for configuring the LO sweep.

    Attributes:
        active_suffix (Literal['none', 'temperature', 'elevation]): The currently
            selected suffix to append to the filename. Can be 'none', 'temperature',
            or 'elevation'.
        tone_path (Path): The path to the selected tone list file.
    """

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        """Initialize the LO configuration window."""
        super().__init__(parent)
        self.setupUi(self)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings

        self.set_defaults()
        self.make_error_labels()    
        self.update_channel_choices()

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.second_sweep_checkBox.clicked.connect(self.check_second_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.filename_temperature_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        self.filename_elevation_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        
        self.dialog_button_box.accepted.connect(self.run_sweep)
        self.channel_toolButton.clicked.connect(self.open_channel_in_initialization_tab)    
    
    def set_defaults(self):
        defaults = self.settings['defaults']['losweep']
        self.global_shift_lineEdit.setPlaceholderText(str(defaults['global_shift']))
        self.df_lineEdit.setPlaceholderText(str(defaults['df']))
        self.deltaf_lineEdit.setPlaceholderText(str(defaults['deltaf']))
        self.flagging_lineEdit.setPlaceholderText(str(defaults['flagging_threshold']))

        file_suffix = defaults.get('file_suffix', 'none')
        if  file_suffix not in FILE_SUFFIXES:
            raise SettingsError(f'Invalid value for defaults.losweep.file_suffix: "{file_suffix}; valid values are: {FILE_SUFFIXES}')
        self.active_suffix: Literal['none', 'temperature', 'elevation'] = file_suffix

        self.second_sweep_df_lineEdit.setPlaceholderText(str(defaults['second_sweep']['df']))

    def make_error_labels(self):
        # Attenuation Error Labels
        channel_err_str = 'No channel selected'
        # self.formLayout.removeWidget(self.channel_error_label)
        self.lo_gridLayout.removeWidget(self.channel_error_label)
        self.channel_error_label.deleteLater()
        self.channel_error_label = IconLabel(ERROR_ICON_CODE, channel_err_str, color='red', wrap_text=False, parent=self)
        self.lo_gridLayout.addWidget(self.channel_error_label, 1, 1)
        self.channel_error_label.hide()
    
    def update_channel_choices(self):
        for rfsoc in self.rfsocs:
            self.channel_comboBox.addItems([f'{rfsoc.settings['name']} - Channel {i+1}' for i in range(2)])
    
    def cancel_sweep(self):
        raise JobInterrupt('LO Sweep Cancelled') 
    
    def get_selected_channel(self) -> tuple[RFSOCWrapper, int]:
        text = self.channel_comboBox.currentText()
        if text == '':
            raise SettingsError('No channel selected')
        rfsoc_name = text.split(' - ')[0]
        rfsoc = self.rfsocs[0]
        for rf in self.rfsocs:
            if rf.settings['name'] == rfsoc_name:
                rfsoc = rf
                break
        chan = int(text.split(' - ')[1].split(' ')[-1])
        return rfsoc, chan
    
    def open_channel_in_initialization_tab(self):
        rfsoc, chan = self.get_selected_channel()
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
    
    def run_sweep(self):
        try:
            rfsoc, chan = self.get_selected_channel()
        except SettingsError as e:
            self.channel_error_label.show()
            return
        self.channel_error_label.hide()
        channel_settings = rfsoc.settings[f'channel{chan}']
        valon = rfsoc.valon_a if chan == 1 else rfsoc.valon_b

        chan_name = 'rfsoc2'
        pd = QProgressDialog('Running...', 'Cancel', 0, 100, self)
        # pd.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        pd.move(self.geometry().center() - pd.geometry().center())
        pd.show()
        QApplication.processEvents()
        # pd.canceled.connect(self.cancel_sweep)

        # For running on ONR Computer
        # TODO: Fix this
        lo_freq = channel_settings['dsp']['lo_freq']
        valon.set_frequency(2, lo_freq)
        tone_shift = get_num_value(self.global_shift_lineEdit)
        if tone_shift != 0:
            lo_freq = valon.get_frequency(SYNTH_B)
            curr_tone_list, curr_amp_list = rfsoc.get_tone_list(chan)
            new_tones = np.ndarray.tolist(
                curr_tone_list
                + float(tone_shift)
                * curr_tone_list
                / np.median(curr_tone_list)
                * 1.0e3
                - lo_freq * 1.0e6
            )
            print(
                "Waiting for the RFSOC to finish writing the updated frequency list"
            )
            rfsoc.set_tone_list(chan, new_tones, curr_amp_list.tolist())
            
        savefile = onrkidpy.get_filename(
            type="LO", chan_name=chan_name
        )
        match self.buttonGroup.checkedButton():
            case self.filename_elevation_radioButton:
                savefile += f'_elev_{self.filename_elevation_lineEdit.text()}'
            case self.filename_temperature_radioButton:
                savefile += f'_temp_{self.filename_temperature_lineEdit.text()}'
            case _:
                pass

        # For running on ONR compupter
        sweep = LoSweep(
            valon,
            rfsoc.rfsoc.rf1,
            rfsoc.get_tone_list()[0],
            valon.get_frequency(SYNTH_B),
        )
        tone_list = rfsoc.get_tone_list()[0]
        chanmask = DEFAULT_CHANMASK
        sweep_data = sweep.run_sweep(chanmask, tone_list, N_steps=200, freq_step=0.001, pd=pd)

        # For running on local computer
        # sweep_file = '20240822_rfsoc2_LO_Sweep_hour16p3294.npy'
        # tone_list = 'Default_tone_list.npy'
        # chanmask = 'chanmask.npy'
        # savefile = Path(savefile).name
        # sweep_data = LoSweepData.from_file(tone_list, sweep_file, chanmask)

        self.sweep_data = sweep_data
        dw = DiagnosticsDialog(sweep_data, savefile, parent=self)
        dw.accepted.connect(lambda: self.save_sweep(savefile))
        dw.setWindowModality(Qt.WindowModality.WindowModal)

        pb = SequentialProgressBarDialog(parent=self)
        pb.move(self.geometry().center() - pb.geometry().center())
        # pb.canceled.connect(self.cancel_sweep)
        nchan = sweep_data.nchan
        pb.add_job(sweep_data.fit, num_tasks=nchan, start_message='Fitting sweep data...', do_print=True)

        # pb.add_job(dw.plot, num_tasks=0, start_message='Plotting fit results...')
        pb.show()
        # self.pb = pb
        # pb.allFinished.connect(lambda: dw.set_figure(pb.get_result(1)))
        pb.allFinished.connect(lambda: self.plot_sweep(sweep_data, dw, pb))
        # pb.allFinished.connect(dw.show)
        # pb.allFinished.connect(pb.close)
        pb.start()
    
    @ensure_path(1)
    def save_sweep(self, savefile: Path):
        self.sweep_data.saveh5(savefile)
        self.sweep_data.savenp(savefile)
    
    def plot_sweep(self, sweep: LoSweepData, dw: DiagnosticsDialog, pb: SequentialProgressBarDialog):
        pb.setLabelText('Plotting fit results...')
        pb.reset()
        pb.setMaximum(sweep.nchan)
        # pb.set_total_tasks(sweep.nchan)
        dw.plot(signal=pb.incrementSignal)
        pb.close()
        dw.show()
    
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

