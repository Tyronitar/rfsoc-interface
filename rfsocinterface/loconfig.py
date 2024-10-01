"""GUI Elements dealing with Configuring the LO Sweep."""

from pathlib import Path
from typing import Literal, Type

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QRadioButton, QLineEdit

from rfsocinterface.ui.loconfig_ui import Ui_MainWindow as Ui_LOConfigWindow
from rfsocinterface.losweep import LoSweepData, get_tone_list
from rfsocinterface.lodiagnostics import DiagnosticsWindow
from kidpy import kidpy
import valon5009
import numpy as np
import onrkidpy
import sweeps
from rfsocinterface.utils import write_fList, Number, test_connection

DEFAULT_FILENAME = 'YYYYMMDD_rfsocN_LO_Sweep_hourHH'
DEFAULT_F_CENTER = 400.0


class LOConfigWindow(QMainWindow, Ui_LOConfigWindow):
    """Window for configuring the LO sweep.

    Attributes:
        active_suffix (Literal['none', 'temperature', 'elevation]): The currently
            selected suffix to append to the filename. Can be 'none', 'temperature',
            or 'elevation'.
        tone_path (Path): The path to the selected tone list file.
    """

    def __init__(self) -> None:
        """Initialize the LO configuration window."""
        super().__init__()
        self.setupUi(self)
        self.active_suffix: Literal['none', 'temperature', 'elevation'] = 'none'

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.second_sweep_checkBox.clicked.connect(self.check_second_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.tone_list_pushButton.clicked.connect(self.choose_tone_file)
        self.filename_temperature_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        self.filename_elevation_lineEdit.textEdited.connect(
            self.update_filename_example
        )
        
        self.dialog_button_box.accepted.connect(self.run_sweep)
        self.init_kidpy()
    
    def get_num_value(self, line_edit: QLineEdit, num_type: Type[Number]=float) -> Number:
        """Get the value from a QLineEdit and convert to a number."""
        val = line_edit.text()
        if val == '':
            val = line_edit.placeholderText()
        try:
            return num_type(val)
        except ValueError  as e:
            raise ValueError(f'Could not convert value {val} to type "{num_type}"')
    
    def init_kidpy(self):
        self.kpy = kidpy()
        conStatus = test_connection(self.kpy.r)
        if conStatus:
            print("\033[0;36m" + "\r\nConnected" + "\033[0m")
        else:
            print(
                "\033[0;31m"
                + "\r\nCouldn't connect to redis-server double check it's running and the generalConfig is correct"
                + "\033[0m"
            )
        if conStatus == False:
            exit(1)

    def run_sweep(self):

        self.kpy.valon.set_frequency(2, DEFAULT_F_CENTER)
        chan_name = 'rfsoc2'

        tone_shift = self.get_num_value(self.deltaf_lineEdit)
        if tone_shift != 0:
            lo_freq = valon5009.Synthesizer.get_frequency(
                self.kpy.valon,
                valon5009.SYNTH_B,
            )
            curr_tone_list = self.kpy.get_tone_list()
            fList = np.ndarray.tolist(
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
            fAmps = self.kpy.get_last_alist() #amplitudes
            write_fList(self.kpy, fList, np.ndarray.tolist(fAmps))
            
#                                write_fList(self, fList, [])
        savefile = onrkidpy.get_filename(
            type="LO", chan_name=chan_name
        )

        # TODO: Replace with the actual LO sweep code from kidpy
        sweep_data = '20240822_rfsoc2_LO_Sweep_hour16p3294.npy'
        tone_list = get_tone_list('Default_tone_list.npy')

        sweeps.loSweep(
            self.kpy.valon,
            self.kpy.__udp,
            self.kpy.get_last_flist(),
            valon5009.Synthesizer.get_frequency(
                self.kpy.valon, valon5009.SYNTH_B
            ),
            N_steps=200,
            freq_step=0.001,
            savefile=savefile,
        )

        sweep = LoSweepData(
            tone_list,
            sweep_data,
            chanmask_file='chanmask.npy',
        ) 
        sweep.fit()
        dw = DiagnosticsWindow(sweep)
        dw.show()
        self.close()


    def choose_tone_file(self):
        """Open a file dialog to select the tone file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Tone File',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.tone_path = Path(fname)
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


if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()
