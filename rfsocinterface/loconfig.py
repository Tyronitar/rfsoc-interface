"""GUI Elements dealing with Configuring the LO Sweep."""

from rfsocinterface.ui.loconfig_ui import Ui_MainWindow as Ui_LOConfigWindow
from PySide6.QtWidgets import QMainWindow, QRadioButton, QApplication, QFileDialog
from pathlib import Path

DEFAULT_FILENAME = 'YYYYMMDD_rfsocN_LO_Sweep_hourHH'

class LOConfigWindow(QMainWindow, Ui_LOConfigWindow):
    """Window for configuring the LO sweep."""

    def __init__(self) -> None:
        """Initialize the LO configuration window."""
        super().__init__()
        self.setupUi(self)
        self.active_suffix = 'none'

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)
        self.second_sweep_checkBox.clicked.connect(self.check_second_sweep)
        self.show_diagnostics_checkBox.clicked.connect(self.check_diagnostics)
        self.tone_list_pushButton.clicked.connect(self.choose_tone_file)
        self.filename_temperature_lineEdit.textEdited.connect(self.update_filename_example)
        self.filename_elevation_lineEdit.textEdited.connect(self.update_filename_example)
    
    def choose_tone_file(self):
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
        if self.show_diagnostics_checkBox.isChecked():
            self.only_flag_checkBox.show()
        else:
            self.only_flag_checkBox.hide()
            
    def check_second_sweep(self):
        if self.second_sweep_checkBox.isChecked():
            self.second_sweep_df_label.show()
            self.second_sweep_df_lineEdit.show()
        else:
            self.second_sweep_df_label.hide()
            self.second_sweep_df_lineEdit.hide()

    def swap_filename_suffix(self, button: QRadioButton):
        match button:
            case self.filename_none_radioButton:
                self.active_suffix = 'none'
                self.filename_temperature_lineEdit.setEnabled(False)
                self.filename_elevation_lineEdit.setEnabled(False)
            case self.filename_temperature_radioButton:
                self.active_suffix = 'temperature'
                self.filename_temperature_lineEdit.setEnabled(True)
                self.filename_elevation_lineEdit.setEnabled(False)
            case self.filename_elevation_radioButton:
                self.active_suffix = 'elevation'
                self.filename_temperature_lineEdit.setEnabled(False)
                self.filename_elevation_lineEdit.setEnabled(True)

        self.update_filename_example()
    
    def update_filename_example(self):
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
                raise RuntimeError(f'Invalid `active_suffix` encountered: {self.active_suffix}')

if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()