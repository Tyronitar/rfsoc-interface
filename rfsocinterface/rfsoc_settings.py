from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication, QSize, QRect, Slot
from PySide6.QtGui import QDoubleValidator, QIcon, QRegularExpressionValidator
from rfsocinterface.ui.channel_settings_ui import Ui_ChannelSettingsWidget
from rfsocinterface.ui.rfsoc_advanced_settings_ui import Ui_RFSOCAdvancedSettingsWidget
from rfsocinterface.ui.icon_label import IconLabel
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
from kidpy3.hardware import Transceiver321, Transceiver320d, Valon5009
import numpy as np
from transceiver import Transceiver
import yaml

from rfsocinterface.ui.file_upload import FileUploadWidget
from rfsocinterface.ui.section import Section
from rfsocinterface.ui.lineedit import ClickableLineEdit
from rfsocinterface.utils import get_num_value, get_lineEdit_text, IPV4_REGEX, MAC_REGEX, QPathValidator
from rfsocinterface.ui.icon_label import IconLabel, verify_lineEdit, ERROR_ICON_CODE
from rfsocinterface.rfsoc import RFSOCWrapper


ONR_REPO_DIR = Path('~').expanduser() / 'onrkidpy'
DEFAULT_CONFIG = 'defaults.yaml'

class RFSOCSettingsWidget(QWidget):
    def __init__(self, rfsoc: RFSOCWrapper, parent: QWidget | None = None):
        super().__init__(parent)
        self.rfsoc = rfsoc
        self.setupUi()
    
    def setupUi(self):
        layout = QVBoxLayout(self)

        channel1_layout = QVBoxLayout()
        self.channel1_widget = ChannelSettingsWidget(self.rfsoc, 1, parent=self)
        channel1_layout.addWidget(self.channel1_widget)
        self.channel1_section = Section(self)
        self.channel1_section.setTitle('Channel 1')
        self.channel1_section.setContentLayout(channel1_layout)
        layout.addWidget(self.channel1_section)

        channel2_layout = QVBoxLayout()
        self.channel2_widget = ChannelSettingsWidget(self.rfsoc, 2, parent=self)
        channel2_layout.addWidget(self.channel2_widget)
        self.channel2_section = Section(self)
        self.channel2_section.setTitle('Channel 2')
        self.channel2_section.setContentLayout(channel2_layout)
        layout.addWidget(self.channel2_section)

        advanced_layout = QVBoxLayout()
        self.advanced_widget = AdvancedSettingsWidget(self.rfsoc, parent=self)
        advanced_layout.addWidget(self.advanced_widget)
        self.advanced_section = Section(self)
        self.advanced_section.setTitle('Advanced')
        self.advanced_section.setContentLayout(advanced_layout)
        layout.addWidget(self.advanced_section)



class AdvancedSettingsWidget(QWidget, Ui_RFSOCAdvancedSettingsWidget):
    def __init__(self, rfsoc: RFSOCWrapper, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        self.rfsoc = rfsoc
        # # Redis and stuff from kidpy
        # self.firmware_file_upload_widget.uploaded.connect(self.upload_firmware)
        # # self.firmware_file_upload_widget.toolButton.clicked.connect(self.upload_firmware)
        # self.tone_list_file_upload_widget.uploaded.connect(self.upload_tone_list)
        # # self.tone_power_file_upload_widget.uploaded.connect(self.upload_tone_powers)
        # self.udp_openPushButton.clicked.connect(self.setup_udp)
        # self.buttonBox.clicked.connect(self.restore_defaults)

class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    def __init__(self, rfsoc: RFSOCWrapper, channel: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.rfsoc = rfsoc
        self.channel = channel
        self.comport = rfsoc.settings[f'channel{self.channel}']['lo_comport']
        # self.transceiver = Transceiver320d(self.comport)
        self.transceiver = None

        self.setupUi(self)
        # # self._additional_setup()

        # Resonator Settings Connections
        self.tone_list_pushButton.clicked.connect(self.choose_tone_list)
        self.tone_power_pushButton.clicked.connect(self.choose_tone_powers)
        self.path_validator = QPathValidator(parent=self)
        self.tone_list_lineEdit.setValidator(self.path_validator)
        self.tone_power_lineEdit.setValidator(self.path_validator)
        self.upload_tones_pushButton.clicked.connect(self.upload_tone_list)
        # self.tone_list_lineEdit.textChanged.connect(self.enable_tone_upload)
        # self.tone_power_lineEdit.textChanged.connect(self.enable_tone_upload)
        # TODO: Add upload functionality

        self.chanmask_pushButton.clicked.connect(self.choose_channel_mask)

        # IF Settings Validation and Connections
        self.atten_validator = QDoubleValidator(0, 31.75, 2, parent=self)
        self.rfin_lineEdit.setValidator(self.atten_validator)
        self.rfout_lineEdit.setValidator(self.atten_validator)
        self.rfin_uploadToolButton.clicked.connect(lambda: self.set_attenuation('in'))
        self.rfout_uploadToolButton.clicked.connect(lambda: self.set_attenuation('out'))
        self.lo_validator = QDoubleValidator(parent=self)
        self.lo_freq_lineEdit.setValidator(self.lo_validator)
        self.lo_freq_uploadToolButton.clicked.connect(self.set_lo_freq)

        # Ethernet Settings Validation and Connections
        self.ip_validator = QRegularExpressionValidator(self)
        self.ip_validator.setRegularExpression(IPV4_REGEX)
        self.eth_source_lineEdit.setValidator(self.ip_validator)
        self.eth_dest_lineEdit.setValidator(self.ip_validator)
        self.mac_validator = QRegularExpressionValidator(MAC_REGEX)
        self.eth_mac_lineEdit.setValidator(self.mac_validator)
        self.eth_lineEdits = [
            self.eth_source_lineEdit,
            self.eth_dest_lineEdit,
            self.eth_mac_lineEdit,
            self.eth_port_lineEdit
        ]
        for edit in self.eth_lineEdits:
            edit.textChanged.connect(self.enable_udp_button)
        
        # Error Labels
        self.make_error_labels()
        # self.error_labels = [
        #     self.rfin_error_label,
        #     self.rfout_error_label,
        #     self.tone_list_error_label,
        #     self.tone_power_error_label,
        #     self.eth_source_error_label,
        #     self.eth_dest_error_label,
        #     self.eth_mac_error_label,
        # ]
        # for label in self.error_labels:
        #     label.setVisible(False)

        # self.set_defaults()

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

    def make_error_labels(self):
        # Attenuation Error Labels
        att_err_str = 'Attenuation must be in range [0.0, 31.75]'
        self.if_gridLayout.removeWidget(self.rfout_error_label)
        self.rfout_error_label= IconLabel(ERROR_ICON_CODE, att_err_str, color='red', parent=self)
        self.if_gridLayout.addWidget(self.rfout_error_label, 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.rfout_error_label.setVisible(False)
        
        self.if_gridLayout.removeWidget(self.rfin_error_label)
        self.rfin_error_label = IconLabel(ERROR_ICON_CODE, att_err_str, color='red', parent=self)
        self.if_gridLayout.addWidget(self.rfin_error_label, 3, 1, Qt.AlignmentFlag.AlignLeft)
        self.rfin_error_label.setVisible(False)

        # Resonator Error Labels
        file_err_str = 'Specified file does not exist'
        self.resonator_gridLayout.removeWidget(self.tone_list_error_label)
        self.tone_list_error_label = IconLabel(ERROR_ICON_CODE, file_err_str, color='red', parent=self)
        self.resonator_gridLayout.addWidget(self.tone_list_error_label, 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.tone_list_error_label.setVisible(False)

        self.resonator_gridLayout.removeWidget(self.tone_power_error_label)
        self.tone_power_error_label= IconLabel(ERROR_ICON_CODE, file_err_str, color='red', parent=self)
        self.resonator_gridLayout.addWidget(self.tone_power_error_label, 3, 1, Qt.AlignmentFlag.AlignLeft)
        self.tone_power_error_label.setVisible(False)

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
    
    def choose_tone_list(self):
        """Open a file dialog to select the tone list file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Tone List',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.tone_list_lineEdit.setText(fname)

    def choose_tone_powers(self):
        """Open a file dialog to select the tone power file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Tone Powers',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.tone_power_lineEdit.setText(fname)
    
    
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
        self.rfsoc.bitstream = bitstream
        self.rfsoc.upload_bitstream()
        # cmd = {"cmd": "ulBitstream", "args": []}
        # cmdstr = json.dumps(cmd)
        # self.rfsoc.r.publish("picard", cmdstr)
        # self.rfsoc.r.set("status", "busy")
        # print("Waiting for the RFSOC to upload it's bitstream...")
        # if wait_for_free(self.rfsoc.r, 0.75, 25):
        #     print("Done")

    def update_ethernet_config(self):
        # TODO: Make this use the correct line edits
        self.rfsoc.eth.udp_data_a_sourceip = get_lineEdit_text(self.udp_sourceLineEdit)
        self.rfsoc.eth.udp_data_a_destip = get_lineEdit_text(self.udp_destLineEdit)
        self.rfsoc.eth.udp_data_b_sourceip = get_lineEdit_text(self.udp_sourceLineEdit)
        self.rfsoc.eth.udp_data_b_destip = get_lineEdit_text(self.udp_destLineEdit)
        # TODO: Add destmac
        # TODO: Add ports
    
    def setup_udp(self):
        self.update_ethernet_config()
        self.rfsoc.config_hardware()
        # print("Initializing System and UDP Connection")
        # cmd = {"cmd": "initRegs", "args": []}
        # cmdstr = json.dumps(cmd)
        # self.rfsoc.r.publish("picard", cmdstr)
        # if wait_for_free(self.rfsoc.r, 0.5, 5):
        #     print("Done")
    
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
        self.rfsoc.r.publish("picard", cmdstr)
        success, _ = wait_for_reply(self.rfsoc.p, "ulWaveform", max_timeout=10)
        if success:
            print("Wrote waveform.")
        else:
            print("FAILED TO WRITE WAVEFORM")

    def upload_tone_list(self):
        # see if the user wants the default list or something different:
        tone_valid = verify_lineEdit(self.tone_list_lineEdit, self.tone_list_error_label)
        power_valid = verify_lineEdit(self.tone_power_lineEdit, self.tone_power_error_label)
        if not (tone_valid and power_valid):
            return
        tone_file = get_lineEdit_text(self.tone_list_lineEdit)
        amp_file = get_lineEdit_text(self.tone_power_lineEdit)
        tone_list = np.ndarray.tolist(np.load(tone_file))
        # tone_powers = np.ndarray.tolist(np.load(amp_file))
        tone_powers = np.ones_like(tone_list)
        self.rfsoc.set_tone_list(chan=self.channel, tonelist=tone_list, amplitudes=tone_powers)

    def set_attenuation(self, attenuation: str):
        # TODO: Make this work for two channels
        match attenuation:
            case 'in':
                addr = 1
                lineEdit = self.rfin_lineEdit
                error_label = self.rfin_error_label
            case 'out':
                addr = 2
                lineEdit = self.rfout_lineEdit
                error_label = self.rfout_error_label
            case _:
                raise ValueError(f'Function `set_attenuation` called with illegal argument "{attenuation}"; must be in ["in", "out"]')
        
        if verify_lineEdit(lineEdit, error_label):
            att = get_num_value(lineEdit)
            # self.transceiver.set_atten(addr, att)
            print('Succesfully set attenuation')
    
    def set_lo_freq(self):
        lo_freq = get_num_value(self.lo_freq_lineEdit)
        valon = Valon5009(str(self.comport))
        valon.set_frequency(self.channel, lo_freq)
    
    def set_defaults(self):
        self.tone_list_file_upload_widget.lineEdit.setText(self.settings['tone_list'])
        self.tone_list_file_upload_widget.lineEdit.setPlaceholderText(self.settings['tone_list'])
        if 'tone_powers' in self.settings:
            self.tone_power_file_upload_widget.lineEdit.setText(self.settings['tone_powers'])
            self.tone_power_file_upload_widget.lineEdit.setPlaceholderText(self.settings['tone_powers'])
        self.firmware_file_upload_widget.lineEdit.setText(self.settings['bitstream'])
        self.firmware_file_upload_widget.lineEdit.setPlaceholderText(self.settings['bitstream'])
        if 'tone_powers' in self.settings:
            self.chanmask_lineEdit.setText(self.settings['chanmask'])
            self.chanmask_lineEdit.setPlaceholderText(self.settings['chanmask'])
        self.udp_sourceLineEdit.setText(self.settings['ethernet']['sourceip_a'])
        self.udp_sourceLineEdit.setPlaceholderText(self.settings['ethernet']['sourceip_a'])
        self.udp_destLineEdit.setText(self.settings['ethernet']['destip_a'])
        self.udp_destLineEdit.setPlaceholderText(self.settings['ethernet']['destip_a'])
        self.rfin_lineEdit.setText(str(self.settings['rfin']))
        self.rfin_lineEdit.setPlaceholderText(str(self.settings['rfin']))
        self.rfout_lineEdit.setText(str(self.settings['rfout']))
        self.rfout_lineEdit.setPlaceholderText(str(self.settings['rfout']))
    
    @Slot(QAbstractButton)
    def restore_defaults(self, button: QAbstractButton):
        std_btn = self.buttonBox.standardButton(button)
        if std_btn == QDialogButtonBox.StandardButton.RestoreDefaults:
            self.set_defaults()
