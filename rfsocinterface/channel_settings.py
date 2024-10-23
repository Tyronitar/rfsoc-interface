from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from rfsocinterface.ui.channel_settings_ui import Ui_ChannelSettingsWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit

from rfsocinterface.utils import get_num_value

class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)

        self.tone_list_file_upload_widget.set_caption('Select Tone File')
        self.tone_list_file_upload_widget.set_dir('./')
        self.tone_list_file_upload_widget.set_filter('Numpy (*.npy);;All Files(*.*)')
        self.tone_list_file_upload_widget.set_selected_filter('Numpy (*.npy)')
        # TODO: Add upload functionality

        self.tone_power_file_upload_widget.set_caption('Select Tone Power File')
        self.tone_power_file_upload_widget.set_dir('./')
        self.tone_power_file_upload_widget.set_filter('Numpy (*.npy);;All Files(*.*)')
        self.tone_power_file_upload_widget.set_selected_filter('Numpy (*.npy)')
        # TODO: Add upload functionality

        # TODO: create collapseable widget for the "advanced" settings
        self.chanmask_pushButton.clicked.connect(self.choose_channel_mask)

        self.udp_lineEdits = [
            self.udp_sourceLineEdit,
            self.udp_destLineEdit,
        ]
        for edit in self.udp_lineEdits:
            edit.textChanged.connect(self.enable_udp_button)
        # TODO: Add opening UDP socket functionality

        self.atten_lineEdit = [
            self.rfin_lineEdit,
            self.rfout_lineEdit,
        ]
        self.validator = QDoubleValidator(0, 31.75, 2, parent=self)
        for edit in self.atten_lineEdit:
            edit.setValidator(self.validator)
            edit.textChanged.connect(self.change_attenuation)
        # TODO: Add upload functionality for attenuation
    

    def change_attenuation(self):
        source: QLineEdit = self.sender()
        valid = self.validator.validate(source.text(), 0)[0]

        # val = get_num_value(source, float)

        if valid != QDoubleValidator.State.Acceptable:  # Value is invalid
            # Highlight in red
            source.setStyleSheet(
                'background-color: "#FFCCCC"; border: 1px solid red;'
            )
            match source:
                case self.rfin_lineEdit:
                    self.rfin_uploadToolButton.setEnabled(False)
                case self.rfout_lineEdit:
                    self.rfout_uploadToolButton.setEnabled(False)

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
            match source:
                case self.rfin_lineEdit:
                    self.rfin_uploadToolButton.setEnabled(True)
                case self.rfout_lineEdit:
                    self.rfout_uploadToolButton.setEnabled(True)

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
            self.chanmask_lineEdit.setText(fname)