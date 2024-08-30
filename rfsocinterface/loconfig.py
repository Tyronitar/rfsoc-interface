"""GUI Elements dealing with Configuring the LO Sweep."""

from rfsocinterface.ui.loconfig_uic import Ui_MainWindow as Ui_LOConfigWindow
from PySide6.QtWidgets import QMainWindow, QRadioButton, QApplication


class LOConfigWindow(QMainWindow, Ui_LOConfigWindow):
    """Window for configuring the LO sweep."""

    def __init__(self) -> None:
        """Initialize the LO configuration window."""
        super().__init__()
        self.setupUi(self)

        self.buttonGroup.buttonClicked.connect(self.swap_filename_suffix)

    def swap_filename_suffix(self, button: QRadioButton):
        match button:
            case self.filename_none_radioButton:
                self.filename_temperature_lineEdit.setDisabled(True)
                self.filename_temperature_lineEdit.clear()
                self.filename_elevation_lineEdit.setDisabled(True)
                self.filename_elevation_lineEdit.clear()
            case self.filename_temperature_radioButton:
                self.filename_temperature_lineEdit.setEnabled(True)
                self.filename_elevation_lineEdit.setDisabled(True)
                self.filename_elevation_lineEdit.clear()
            case self.filename_elevation_radioButton:
                self.filename_elevation_lineEdit.setEnabled(True)
                self.filename_temperature_lineEdit.setDisabled(True)
                self.filename_temperature_lineEdit.clear()

if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()