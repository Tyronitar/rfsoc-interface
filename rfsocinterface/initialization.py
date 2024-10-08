from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from rfsocinterface.ui.initialization_ui import Ui_InitializationTabWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit

from rfsocinterface.utils import get_num_value

class InitializationWidget(QWidget, Ui_InitializationTabWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)

        self.tone_list_browse_pushButton.clicked.connect(self.choose_tone_file)
        self.chanmask_browse_pushButton.clicked.connect(self.choose_channel_mask)
        self.tone_list_lineEdit.textChanged.connect(self.enable_tone_upload)
        self.udp_lineEdits = [
            self.socket1_destLineEdit,
            self.socket1_sourceLineEdit,
            self.socket2_destLineEdit,
            self.socket2_sourceLineEdit,
        ]
        for edit in self.udp_lineEdits:
            edit.textChanged.connect(self.enable_udp_button)
        self.atten_lineEdit = [
            self.system1_rfin_lineEdit,
            self.system1_rfout_lineEdit,
            self.system2_rfin_lineEdit,
            self.system2_rfout_lineEdit,
        ]
        self.validator = QDoubleValidator(0, 31.75, 2, parent=self)
        for edit in self.atten_lineEdit:
            edit.setValidator(self.validator)
            edit.textChanged.connect(self.change_attenuation)
    

    def change_attenuation(self):
        source: QLineEdit = self.sender()
        valid = self.validator.validate(source.text(), 0)[0]

        # val = get_num_value(source, float)

        if valid != QDoubleValidator.State.Acceptable:  # Value is invalid
            # Highlight in red
            source.setStyleSheet(
                'background-color: "#FFCCCC"; border: 1px solid red;'
            )

            # # Create the error_label if needed
            # if self.error_label is None:
            #     self.error_label = QLabel(self)
            #     self.error_label.setText(
            #         f'New frequency must be in the range [{freq_range[0]:.3f}, {freq_range[1]:.3f}]'
            #     )
            #     self.error_label.setStyleSheet('color: red;')
            #     self.formLayout.insertRow(2, None, self.error_label)
        else:  # Value is valid
            # Remove the error label since the value is valid
            # if self.error_label is not None:
            #     self.new_freq_lineEdit.setStyleSheet('')
            #     self.formLayout.removeRow(self.error_label)
            #     self.error_label = None
            source.setStyleSheet('')


    def enable_tone_upload(self):
        if self.tone_list_lineEdit.text() != '':
            self.tone_list_uploadPushButton.setEnabled(True)
        else:
            self.tone_list_uploadPushButton.setEnabled(False)
    
    def enable_udp_button(self):
        filled = [edit.text() != '' for edit in self.udp_lineEdits]
        if all(filled):
            self.udp_openPushButton.setEnabled(True)
        else:
            self.udp_openPushButton.setEnabled(False)
    
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
    
    def choose_channel_mask(self):
        """Open a file dialog to select the channel mask file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Channel Mask',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.chanmask = Path(fname)
            self.chanmask_lineEdit.setText(fname)