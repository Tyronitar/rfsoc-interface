from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication, QSize, QRect, Slot
from PySide6.QtGui import QDoubleValidator, QIcon
from rfsocinterface.ui.channel_settings_ui import Ui_ChannelSettingsWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit, QVBoxLayout, QSizePolicy, QGroupBox, QGridLayout

from PySide6.QtWidgets import (QFormLayout,
    QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QAbstractButton, QDialogButtonBox,
    QWidget)

import numpy.typing as npt

import time
import json
import redis
import configparser
from kidpy import checkBlastCli, wait_for_free, wait_for_reply, kidpy
import numpy as np
from transceiver import Transceiver
import yaml

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.section import Section
from rfsocinterface.ui.lineedit import ClickableLineEdit
from rfsocinterface.utils import get_num_value


ONR_REPO_DIR = Path('~').expanduser() / 'onrkidpy'
DEFAULT_CONFIG = 'defaults.yaml'

class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    def __init__(self, kpy: kidpy, cfg: str=DEFAULT_CONFIG, parent: QWidget | None = None):
        super().__init__(parent)
        self.kpy = kpy
        self.comport = '/dev/IF1Attenuators'
        self.transceiver = Transceiver(self.comport)
        with open(cfg) as f:
            self.cfg = yaml.safe_load(f)

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

        # Redis and stuff from kidpy
        self.firmware_file_upload_widget.uploaded.connect(self.upload_firmware)
        # self.firmware_file_upload_widget.toolButton.clicked.connect(self.upload_firmware)
        self.tone_list_file_upload_widget.uploaded.connect(self.upload_tone_list)
        self.tone_power_file_upload_widget.uploaded.connect(self.upload_tone_powers)
        self.udp_openPushButton.clicked.connect(self.setup_udp)
        self.rfin_uploadToolButton.clicked.connect(lambda: self.set_attenuation('in'))
        self.rfout_uploadToolButton.clicked.connect(lambda: self.set_attenuation('out'))
        self.buttonBox.clicked.connect(self.restore_defaults)
        self.set_defaults()

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

        self.udp_sourceLineEdit = ClickableLineEdit(self.udp_GroupBox)
        self.udp_sourceLineEdit.setObjectName(u"udp_sourceLineEdit")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.udp_sourceLineEdit.sizePolicy().hasHeightForWidth())
        self.udp_sourceLineEdit.setSizePolicy(sizePolicy6)

        self.udp_formLayout.addRow(QCoreApplication.translate('ChannelSettingsWidget', 'Source:', None), self.udp_sourceLineEdit)

        self.udp_destLineEdit = ClickableLineEdit(self.udp_GroupBox)
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

        self.chanmask_lineEdit = ClickableLineEdit(self.advanced_section)
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
        source: ClickableLineEdit = self.sender()
        src_txt = source.text() if source.text() else source.placeholderText()
        valid = self.validator.validate(src_txt, 0)[0]

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
    
    @Slot(str)
    def upload_firmware(self, bitstream: str):
        cmd = {"cmd": "ulBitstream", "args": []}
        cmdstr = json.dumps(cmd)
        self.kpy.r.publish("picard", cmdstr)
        self.kpy.r.set("status", "busy")
        print("Waiting for the RFSOC to upload it's bitstream...")
        if wait_for_free(self.kpy.r, 0.75, 25):
            print("Done")
    
    def setup_udp(self):
        print("Initializing System and UDP Connection")
        cmd = {"cmd": "initRegs", "args": []}
        cmdstr = json.dumps(cmd)
        self.kpy.r.publish("picard", cmdstr)
        if wait_for_free(self.kpy.r, 0.5, 5):
            print("Done")
    
    def write_fList(self, fList: npt.ArrayLike, ampList: npt.ArrayLike):
        """
        Function for writing tones to the rfsoc. Accepts both numpy arrays and lists.
        :param fList: List of desired tones
        :type fList: list
        :param ampList: List of desired amplitudes
        :type ampList: list
        .. note::
            fList and ampList must be the same size
        """
        f = fList
        a = ampList

        # Convert to numpy arrays as needed
        if isinstance(fList, np.ndarray):
            f = fList.tolist()
        if isinstance(ampList, np.ndarray):
            a = ampList.tolist()

        # Format Command based on provided parameters
        cmd = {}
        if len(f) == 0:
            cmd = {"cmd": "ulWaveform", "args": []}
        elif len(f) > 0 and len(a) == 0:
            a = np.ones_like(f).tolist()
            cmd = {"cmd": "ulWaveform", "args": [f, a]}
        elif len(f) > 0 and len(a) > 0:
            assert len(a) == len(
                f
            ), "Frequency list and Amplitude list must be the same dimmension"
            cmd = {"cmd": "ulWaveform", "args": [f, a]}
        else:
            print("Weird edge case, something went very wrong.....")
            return

        cmdstr = json.dumps(cmd)
        self.kpy.r.publish("picard", cmdstr)
        success, _ = wait_for_reply(self.kpy.p, "ulWaveform", max_timeout=10)
        if success:
            print("Wrote waveform.")
        else:
            print("FAILED TO WRITE WAVEFORM")
    
    @Slot(str)
    def upload_tone_list(self, tone_file: str):
        # see if the user wants the default list or something different:
        freqfile = np.load(tone_file)
        fList = np.ndarray.tolist(freqfile)
        aList = []
        # aList = np.ndarray.tolist(np.load(amplitude_file)) # doesnt exist yet...

        print(
            "Waiting for the RFSOC to finish writing the custom frequency list"
        )
        self.write_fList(fList, aList)
    
    @Slot(str)
    def upload_tone_powers(self, max_power_file: str):
        fList = self.kpy.get_last_flist()
        if max_power_file != '':
            power_dB = np.load(max_power_file)
            # power_dB = np.load(ONR_REPO_DIR + '/params/' + max_power_file + '_max_readout_power_dB.npy')
            fAmps = np.exp(power_dB/10.)
        else:
            fAmps = np.ones(np.size(fList))
        self.write_fList(fList, fAmps)
    
    def set_attenuation(self, attenuation: str):
        match attenuation:
            case 'in':
                addr = 1
                att = get_num_value(self.rfin_lineEdit)
            case 'out':
                addr = 2
                att = get_num_value(self.rfout_lineEdit)
            case _:
                raise ValueError(f'Function `set_attenuation` called with illegal argument "{attenuation}"; must be in ["in", "out"]')
        self.transceiver.set_atten(addr, att)
    
    def set_defaults(self):
        self.tone_list_file_upload_widget.lineEdit.setText(self.cfg['RFSOC2']['tone_list'])
        self.tone_power_file_upload_widget.lineEdit.setText(self.cfg['RFSOC2']['tone_powers'])
        self.firmware_file_upload_widget.lineEdit.setText(self.cfg['RFSOC2']['bitstream'])
        self.chanmask_lineEdit.setText(self.cfg['RFSOC2']['chanmask'])
        self.udp_sourceLineEdit.setText(self.cfg['RFSOC2']['ethernet_config']['udp_data_sourceip'])
        self.udp_destLineEdit.setText(self.cfg['RFSOC2']['ethernet_config']['udp_data_destip'])
        self.rfin_lineEdit.setText(str(self.cfg['RFSOC2']['rfin']))
        self.rfout_lineEdit.setText(str(self.cfg['RFSOC2']['rfout']))
    
    @Slot(QAbstractButton)
    def restore_defaults(self, button: QAbstractButton):
        std_btn = self.buttonBox.standardButton(button)
        if std_btn == QDialogButtonBox.StandardButton.RestoreDefaults:
            self.set_defaults()
