from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication, QSize, QRect
from PySide6.QtGui import QDoubleValidator, QIcon
from rfsocinterface.ui.channel_settings_ui import Ui_ChannelSettingsWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit, QVBoxLayout, QSizePolicy, QGroupBox, QGridLayout

from PySide6.QtWidgets import (QFormLayout,
    QHBoxLayout, QLabel,
    QLineEdit, QPushButton, 
    QWidget)

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.section import Section

from rfsocinterface.utils import get_num_value

class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        self._additional_setup()


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

    def _additional_setup(self):

        self.advanced_verticalLayout = QVBoxLayout()
        self.advanced_verticalLayout.setObjectName(u"advanced_verticalLayout")        

        # Set up UDP Settings
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.rfoutLabel.sizePolicy().hasHeightForWidth())

        self.udp_GroupBox = QGroupBox(self)
        self.udp_GroupBox.setObjectName(u"udp_GroupBox")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.udp_GroupBox.sizePolicy().hasHeightForWidth())
        self.udp_GroupBox.setSizePolicy(sizePolicy5)
        self.udp_verticalLayout = QVBoxLayout(self.udp_GroupBox)
        self.udp_verticalLayout.setObjectName(u"verticalLayout")
        self.udp_formLayout = QFormLayout()
        self.udp_formLayout.setObjectName(u"udp_formLayout")

        self.udp_sourceLineEdit = QLineEdit(self.udp_GroupBox)
        self.udp_sourceLineEdit.setObjectName(u"udp_sourceLineEdit")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.udp_sourceLineEdit.sizePolicy().hasHeightForWidth())
        self.udp_sourceLineEdit.setSizePolicy(sizePolicy6)

        self.udp_formLayout.addRow(QCoreApplication.translate('ChannelSettingsWidget', 'Source:', None), self.udp_sourceLineEdit)

        self.udp_destLineEdit = QLineEdit(self.udp_GroupBox)
        self.udp_destLineEdit.setObjectName(u"udp_destLineEdit")

        self.udp_formLayout.addRow(QCoreApplication.translate('ChannelSettingsWidget', 'Destination:', None), self.udp_destLineEdit)

        self.udp_verticalLayout.addLayout(self.udp_formLayout)

        self.udp_openPushButton = QPushButton(self.udp_GroupBox)
        self.udp_openPushButton.setObjectName(u"udp_openPushButton")
        self.udp_openPushButton.setEnabled(False)
        self.udp_openPushButton.setMaximumSize(QSize(150, 16777215))
        self.udp_verticalLayout.addWidget(self.udp_openPushButton, 0, Qt.AlignmentFlag.AlignRight)


        self.udp_GroupBox.setTitle(QCoreApplication.translate("ChannelSettingsWidget", u"UDP Connection", None))
        self.udp_openPushButton.setText(QCoreApplication.translate("ChannelSettingsWidget", u"Open Socket", None))

        # Chanmask Settings
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")

        self.chanmask_lineEdit = QLineEdit(self.advanced_section)
        self.chanmask_lineEdit.setObjectName(u"chanmask_lineEdit")
        self.chanmask_lineEdit.setGeometry(QRect(211, 12, 133, 22))
        self.horizontalLayout.addWidget(self.chanmask_lineEdit)

        self.chanmask_pushButton = QPushButton(self.advanced_section)
        self.chanmask_pushButton.setObjectName(u"chanmask_pushButton")
        self.chanmask_pushButton.setGeometry(QRect(350, 11, 75, 24))
        self.chanmask_pushButton.setText(QCoreApplication.translate('ChannelSettingsWidget', u"Browse...", None))
        self.horizontalLayout.addWidget(self.chanmask_pushButton)

        # Firmware Settings
        self.firmware_file_upload_widget = FileUploadWidget(self.advanced_section)
        self.firmware_file_upload_widget.setObjectName(u"firmware_file_upload_widget")
        self.firmware_file_upload_widget.setGeometry(QRect(120, 41, 318, 16))

        # Wrapping everything up
        self.advanced_formLayout = QFormLayout()
        self.advanced_formLayout.setObjectName(u"advanced_formLayout")
        self.advanced_formLayout.addRow(QCoreApplication.translate('ChannelSettingsWidget', 'Channel mask:', None), self.horizontalLayout)
        self.advanced_formLayout.addRow(QCoreApplication.translate('ChannelSettingsWidget', 'Firmware bitstream:', None), self.firmware_file_upload_widget)
        self.advanced_verticalLayout.addLayout(self.advanced_formLayout)
        self.advanced_verticalLayout.addWidget(self.udp_GroupBox, 0)

        self.advanced_section.setContentLayout(self.advanced_verticalLayout)
        self.advanced_section.setTitle('Advanced Settings')
        self.retranslateUi(self)


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