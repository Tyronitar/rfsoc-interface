from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication, QSize, QRect, Slot, Signal
from PySide6.QtGui import QDoubleValidator, QIcon, QRegularExpressionValidator, QIntValidator
from rfsocinterface.gui.uic.channel_settings_ui import Ui_ChannelSettingsWidget
from rfsocinterface.gui.uic.rfsoc_advanced_settings_ui import Ui_RFSOCAdvancedSettingsWidget
from rfsocinterface.gui.widgets.icon_label import IconLabel
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

from rfsocinterface.gui.widgets.file_upload import FileUploadWidget
from rfsocinterface.gui.widgets.section import Section
from rfsocinterface.gui.widgets.lineedit import ClickableLineEdit
from rfsocinterface.core.utils import get_num_value, get_lineEdit_text, IPV4_REGEX, MAC_REGEX, PathValidator
from rfsocinterface.gui.widgets.icon_label import IconLabel, verify_lineEdit, ERROR_ICON_CODE, highlight_error_line_edit
from rfsocinterface.core.rfsoc import RFSOCWrapper


ONR_REPO_DIR = Path('~').expanduser() / 'onrkidpy'
DEFAULT_CONFIG = 'defaults.yaml'

class RFSOCSettingsWidget(QWidget):
    def __init__(self, rfsoc: RFSOCWrapper, parent: QWidget | None = None):
        super().__init__(parent)
        self.rfsoc = rfsoc
        self.setupUi()
    
    def collapse(self, recursive: bool=False):
        self.channel1_section.collapse(recursive=recursive)
        self.channel2_section.collapse(recursive=recursive)
        self.advanced_section.collapse(recursive=recursive)
    
    def setupUi(self):
        layout = QVBoxLayout(self)

        channel1_layout = QVBoxLayout()
        self.channel1_widget = ChannelSettingsWidget(self.rfsoc, 1, parent=self)
        channel1_layout.addWidget(self.channel1_widget)
        self.channel1_section = Section(self)
        self.channel1_section.setTitle('Channel 1')
        self.channel1_section.setContentLayout(channel1_layout)
        layout.addWidget(self.channel1_section)
        # for label in self.channel1_widget.error_labels:
        #     label.made_visible.connect(self.channel1_section.height_changed)
        # self.channel1_widget.hide_error_labels()
        self.channel1_widget.height_updated.connect(self.channel1_section.height_changed)

        channel2_layout = QVBoxLayout()
        self.channel2_widget = ChannelSettingsWidget(self.rfsoc, 2, parent=self)
        channel2_layout.addWidget(self.channel2_widget)
        self.channel2_section = Section(self)
        self.channel2_section.setTitle('Channel 2')
        self.channel2_section.setContentLayout(channel2_layout)
        layout.addWidget(self.channel2_section)
        self.channel2_widget.height_updated.connect(self.channel2_section.height_changed)
        # self.channel2_widget.hide_error_labels()

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
        self._additional_setup()
        self.set_defaults()
        # # Redis and stuff from kidpy
        # self.firmware_file_upload_widget.uploaded.connect(self.upload_firmware)
        # # self.firmware_file_upload_widget.toolButton.clicked.connect(self.upload_firmware)
        # self.tone_list_file_upload_widget.uploaded.connect(self.upload_tone_list)
        # # self.tone_power_file_upload_widget.uploaded.connect(self.upload_tone_powers)
        # self.udp_openPushButton.clicked.connect(self.setup_udp)
        # self.buttonBox.clicked.connect(self.restore_defaults)
    
    def _additional_setup(self):
        self.bitstream_fileUploadWidget.set_placeholder_text('/path/to/filename.bit')
        self.bitstream_fileUploadWidget.uploaded.connect(self.upload_bitstream)

        self.comport_atten_fileUploadWidget.set_placeholder_text('/path/to/filename')
        self.comport_atten_fileUploadWidget.uploaded.connect(self.upload_atten_comport)

        self.comport_channel1_fileUploadWidget.set_placeholder_text('/path/to/filename')
        self.comport_channel1_fileUploadWidget.uploaded.connect(self.upload_channel1_comport)

        self.comport_channel2_fileUploadWidget.set_placeholder_text('/path/to/filename')
        self.comport_channel2_fileUploadWidget.uploaded.connect(self.upload_channel2_comport)
    
    @Slot(str)
    def upload_bitstream(self, bitstream: str):
        self.rfsoc.upload_bitstream(bitstream)
    
    @Slot(str)
    def upload_atten_comport(self, comport: str):
        self.rfsoc.set_atten_comport(comport)
    
    @Slot(str)
    def upload_channel1_comport(self, comport: str):
        self.rfsoc.set_lo_comport(0, comport)
    
    @Slot(str)
    def upload_channel2_comport(self, comport: str):
        self.rfsoc.set_lo_comport(1, comport)
    
    def set_defaults(self):
        settings = self.rfsoc.settings

        # Bitstream
        self.bitstream_fileUploadWidget.lineEdit.setText(str(settings['bitstream']))

        # Redis
        self.redis_ip_lineEdit.setText(settings['redis']['ip'])
        self.redis_port_lineEdit.setText(str(settings['redis']['port']))

        # Comports
        self.comport_atten_fileUploadWidget.lineEdit.setText(str(settings['atten_comport']))
        self.comport_channel1_fileUploadWidget.lineEdit.setText(str(settings['channel1']['lo_comport']))
        self.comport_channel2_fileUploadWidget.lineEdit.setText(str(settings['channel2']['lo_comport']))



class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    height_updated = Signal()
    def __init__(self, rfsoc: RFSOCWrapper, channel: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.rfsoc = rfsoc
        self.channel = channel

        self.setupUi(self)

        # Resonator Settings Connections
        self.tone_list_pushButton.clicked.connect(self.choose_tone_list)
        self.tone_power_pushButton.clicked.connect(self.choose_tone_powers)
        self.path_validator = PathValidator(parent=self)
        self.tone_list_lineEdit.setValidator(self.path_validator)
        self.tone_power_lineEdit.setValidator(self.path_validator)
        self.upload_tones_pushButton.clicked.connect(self.upload_tone_list)
        self.tone_list_checkBox.stateChanged.connect(self.check_equal_tones)
        self.tone_power_checkBox.stateChanged.connect(self.check_equal_power)
        self.baseband_validator = QDoubleValidator(0, 256, 3, parent=self)
        self.tone_list_baseband_max_lineEdit.setValidator(self.baseband_validator)
        self.tone_list_baseband_min_lineEdit.setValidator(self.baseband_validator)
        self.n_tone_validator = QIntValidator(1, 10000, parent=self)
        self.tone_list_ntones_lineEdit.setValidator(self.n_tone_validator)

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
        self.port_validator = QDoubleValidator(0, 65535, 0, parent=self)
        self.eth_port_lineEdit.setValidator(self.port_validator)
        self.eth_lineEdits = [
            self.eth_source_lineEdit,
            self.eth_dest_lineEdit,
            self.eth_mac_lineEdit,
            self.eth_port_lineEdit
        ]
        self.eth_pushButton.clicked.connect(self.configure_hardware)
        
        # Error Labels
        self.make_error_labels()
        self.hide_error_labels()

        self.set_defaults()
        self.buttonBox.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.set_defaults)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self.clear_form)

        self.check_equal_tones(self.tone_list_checkBox.checkState())
        self.check_equal_power(self.tone_power_checkBox.checkState())
        self.tone_list_baseband_min_lineEdit.textEdited.connect(self.update_bandwidth_label)
        self.tone_list_baseband_max_lineEdit.textEdited.connect(self.update_bandwidth_label)
        self.tone_list_ntones_lineEdit.textEdited.connect(self.update_bandwidth_label)
    
    @Slot(str)
    def update_bandwidth_label(self, new_text: str):
        show_label = True
        try:
            min_base = get_num_value(self.tone_list_baseband_min_lineEdit)
            max_base = get_num_value(self.tone_list_baseband_max_lineEdit)
            n = get_num_value(self.tone_list_ntones_lineEdit, int)
        except ValueError:
            show_label = False
        show_changed = self.tone_list_equal_label.isVisible() != show_label
        self.tone_list_equal_label.setVisible(show_label)
        if show_label:
            self.tone_list_equal_label.setText(
                f'Generating {n / 2} tones from {-max_base} MHz to {-min_base} MHz'
                f'and {n / 2} tones from {min_base} MHz to {max_base} MHz'
            )
        if show_changed:
            self.height_updated.emit()
    
    @Slot(int)
    def check_equal_tones(self, state: int):
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        self.tone_list_lineEdit.setVisible(not checked)
        self.tone_list_lineEdit.setStyleSheet('')
        self.tone_list_pushButton.setVisible(not checked)

        self.tone_list_baseband_max_label.setVisible(checked)
        self.tone_list_baseband_max_lineEdit.setVisible(checked)
        self.tone_list_baseband_max_lineEdit.setStyleSheet('')

        self.tone_list_baseband_min_label.setVisible(checked)
        self.tone_list_baseband_min_lineEdit.setVisible(checked)
        self.tone_list_baseband_min_lineEdit.setStyleSheet('')

        self.tone_list_ntones_label.setVisible(checked)
        self.tone_list_ntones_lineEdit.setVisible(checked)
        self.tone_list_ntones_lineEdit.setStyleSheet('')
        self.tone_list_error_label.setVisible(False)
        self.tone_list_equal_label.setVisible(checked)
        self.update_bandwidth_label('')
        self.height_updated.emit()

    @Slot(int)
    def check_equal_power(self, state: int):
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        self.tone_power_lineEdit.setVisible(not checked)
        self.tone_power_lineEdit.setStyleSheet('')
        self.tone_power_pushButton.setVisible(not checked)
        self.tone_power_error_label.setVisible(False)
        self.height_updated.emit()

    def hide_error_labels(self):
        for label in self.error_labels:
            label.setVisible(False)

    def make_error_labels(self):
        # Attenuation Error Labels
        att_err_str = 'Attenuation must be in range [0.0, 31.75]'
        self.if_gridLayout.removeWidget(self.rfout_error_label)
        self.rfout_error_label.deleteLater()
        self.rfout_error_label= IconLabel(ERROR_ICON_CODE, att_err_str, color='red', wrap_text=True, parent=self)
        self.if_gridLayout.addWidget(self.rfout_error_label, 1, 1, Qt.AlignmentFlag.AlignLeft)
        
        self.if_gridLayout.removeWidget(self.rfin_error_label)
        self.rfin_error_label.deleteLater()
        self.rfin_error_label = IconLabel(ERROR_ICON_CODE, att_err_str, color='red', wrap_text=True, parent=self)
        self.if_gridLayout.addWidget(self.rfin_error_label, 3, 1, Qt.AlignmentFlag.AlignLeft)

        # Resonator Error Labels
        file_err_str = 'Specified file does not exist'
        self.resonator_gridLayout.removeWidget(self.tone_list_error_label)
        self.tone_list_error_label.deleteLater()
        self.tone_list_error_label = IconLabel(ERROR_ICON_CODE, file_err_str, color='red', parent=self)
        self.resonator_gridLayout.addWidget(self.tone_list_error_label, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.resonator_gridLayout.removeWidget(self.tone_power_error_label)
        self.tone_power_error_label.deleteLater()
        self.tone_power_error_label= IconLabel(ERROR_ICON_CODE, file_err_str, color='red', parent=self)
        self.resonator_gridLayout.addWidget(self.tone_power_error_label, 3, 1, Qt.AlignmentFlag.AlignLeft)

        # Ethernet Error Labels
        ip_err_str = 'Please enter a valid IPv4 address'
        mac_err_str = 'Please enter a valid MAC address'
        self.eth_gridLayout.removeWidget(self.eth_source_error_label)
        self.eth_source_error_label.deleteLater()
        self.eth_source_error_label = IconLabel(ERROR_ICON_CODE, ip_err_str, color='red', parent=self)
        self.eth_gridLayout.addWidget(self.eth_source_error_label, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.eth_gridLayout.removeWidget(self.eth_dest_error_label)
        self.eth_dest_error_label.deleteLater()
        self.eth_dest_error_label = IconLabel(ERROR_ICON_CODE, ip_err_str, color='red', parent=self)
        self.eth_gridLayout.addWidget(self.eth_dest_error_label, 3, 1, Qt.AlignmentFlag.AlignLeft)

        self.eth_gridLayout.removeWidget(self.eth_mac_error_label)
        self.eth_mac_error_label.deleteLater()
        self.eth_mac_error_label = IconLabel(ERROR_ICON_CODE, mac_err_str, color='red', parent=self)
        self.eth_gridLayout.addWidget(self.eth_mac_error_label, 5, 1, Qt.AlignmentFlag.AlignLeft)

        self.eth_gridLayout.removeWidget(self.eth_port_error_label)
        self.eth_port_error_label.deleteLater()
        self.eth_port_error_label = IconLabel(ERROR_ICON_CODE, 'Please enter a valid port number [0, 65535]', color='red', parent=self)
        self.eth_gridLayout.addWidget(self.eth_port_error_label, 7, 1, Qt.AlignmentFlag.AlignLeft)

        self.error_labels = [
            self.rfout_error_label,
            self.rfin_error_label,
            self.tone_list_error_label,
            self.tone_power_error_label,
            self.eth_source_error_label,
            self.eth_dest_error_label,
            self.eth_mac_error_label,
            self.eth_port_error_label,
        ]
    
    def clear_form(self):
        self.tone_list_lineEdit.clear()
        self.tone_power_lineEdit.clear()
        self.tone_list_baseband_max_lineEdit.clear()
        self.tone_list_baseband_min_lineEdit.clear()
        self.tone_list_ntones_lineEdit.clear()
        self.chanmask_lineEdit.clear()
        self.eth_source_lineEdit.clear()
        self.eth_dest_lineEdit.clear()
        self.eth_mac_lineEdit.clear()
        self.eth_port_lineEdit.clear()
        self.rfin_lineEdit.clear()
        self.rfout_lineEdit.clear()
        self.lo_freq_lineEdit.clear()
        self.hide_error_labels()

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
            self.rfsoc.set_chanmask(fname)
            # TODO: Add updating for when the file is typed in manually
    
    @Slot(str)
    def upload_firmware(self, bitstream: str):
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.rfsoc.upload_bitstream(bitstream)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    @Slot()
    def update_ethernet_config(self):
        chan_settings = self.rfsoc.settings[f'channel{self.channel}']
        chan_settings['sourceip'] = get_lineEdit_text(self.eth_source_lineEdit)
        chan_settings['destip'] = get_lineEdit_text(self.eth_dest_lineEdit)
        chan_settings['destmac'] = get_lineEdit_text(self.eth_mac_lineEdit)
        chan_settings['port'] = get_num_value(self.eth_port_lineEdit, int)
        self.rfsoc.update_kidpy_rfsoc()

    @Slot()
    def configure_hardware(self):
        # TODO: This implicitly requires both channels to have the proper settings
        source_ok, source_toggled = verify_lineEdit(self.eth_source_lineEdit, self.eth_source_error_label)
        dest_ok, dest_toggled = verify_lineEdit(self.eth_dest_lineEdit, self.eth_dest_error_label)
        mac_ok, mac_toggled = verify_lineEdit(self.eth_mac_lineEdit, self.eth_mac_error_label)
        port_ok, port_toggled = verify_lineEdit(self.eth_port_lineEdit, self.eth_port_error_label)

        if any([source_toggled, dest_toggled, mac_toggled, port_toggled]):
            self.height_updated.emit()
        elif all([source_ok, dest_ok, mac_ok, port_ok]):
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.update_ethernet_config()
            self.rfsoc.configure_hardware()
            self.setCursor(Qt.CursorShape.ArrowCursor)

    @Slot()
    def upload_tone_list(self):
        # see if the user wants the default list or something different:
        # if tone_toggled or power_toggled:
        #     self.height_updated.emit()
        # if not (tone_valid and power_valid):
        #     return
        tones_valid = True
        if self.tone_list_checkBox.isChecked():
            n_valid, _ = verify_lineEdit(self.tone_list_ntones_lineEdit)
            bb_min_valid, _ = verify_lineEdit(self.tone_list_baseband_min_lineEdit)
            bb_max_valid, _ = verify_lineEdit(self.tone_list_baseband_max_lineEdit)
            tones_valid &= n_valid
            tones_valid &= bb_min_valid
            tones_valid &= bb_max_valid
            if tones_valid:
                n = get_num_value(self.tone_list_ntones_lineEdit, int)
                bb_min = get_num_value(self.tone_list_baseband_min_lineEdit) * 1e6
                bb_max = get_num_value(self.tone_list_baseband_max_lineEdit) * 1e6
                if bb_max <= bb_min:
                    tones_valid = False
                    highlight_error_line_edit(self.tone_list_baseband_max_lineEdit)
                else:
                    freq_low = np.linspace(-bb_max, -bb_min, n // 2)
                    freq_hi = np.linspace(bb_min, bb_max, n // 2)
                    tone_list = np.append(freq_low, freq_hi)
            # TODO: Ask Cody about this
            # Cody's code for equally spaced tones
            # Nover2 = 500 # number of tones to make  
            # freqs_up = -1.0*np.linspace(251.0e6,1.0e6,Nover2)  
            # freqs_lw = 1.0*np.linspace(2.25e6,252.25e6,Nover2)  
            # tone_list = np.append(freqs_up,freqs_lw)
        else:
            tone_list_valid, tone_toggled = verify_lineEdit(self.tone_list_lineEdit, self.tone_list_error_label)
            tones_valid &= tone_list_valid
            if tone_toggled:
                self.height_updated.emit()
            if tones_valid:
                tone_file = get_lineEdit_text(self.tone_list_lineEdit)
                tone_list = np.ndarray.tolist(np.load(tone_file))

        if self.tone_power_checkBox.isChecked():
            if tones_valid:
                tone_powers = np.ones_like(tone_list)
        else:
            power_valid, power_toggled = verify_lineEdit(self.tone_power_lineEdit, self.tone_power_error_label)
            tones_valid &= power_valid
            if power_toggled:
                self.height_updated.emit()
            if tones_valid:
                amp_file = get_lineEdit_text(self.tone_power_lineEdit)
                tone_powers = np.ndarray.tolist(np.load(amp_file))

        if tones_valid:
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.rfsoc.set_tone_list(chan=self.channel, tonelist=tone_list, amplitudes=tone_powers)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_attenuation(self, attenuation: str):
        match attenuation:
            case 'in':
                addr = self.channel + 0
                lineEdit = self.rfin_lineEdit
                error_label = self.rfin_error_label
            case 'out':
                addr = self.channel + 1
                lineEdit = self.rfout_lineEdit
                error_label = self.rfout_error_label
            case _:
                raise ValueError(f'Function `set_attenuation` called with illegal argument "{attenuation}"; must be in ["in", "out"]')
        
        valid, toggled = verify_lineEdit(lineEdit, error_label)
        if toggled:
            self.height_updated.emit()
        elif valid:
            att = get_num_value(lineEdit)
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.rfsoc.atten_transceiver.set_atten(addr, att)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            print('Succesfully set attenuation')
    
    def set_lo_freq(self):
        lo_freq = get_num_value(self.lo_freq_lineEdit)
        self.setCursor(Qt.CursorShape.WaitCursor)
        valon = self.rfsoc.valon_a if self.channel == 1 else self.rfsoc.valon_b
        self.setCursor(Qt.CursorShape.ArrowCursor)
        valon.set_frequency(self.channel, lo_freq)
    
    def set_defaults(self):
        chan_settings = self.rfsoc.settings[f'channel{self.channel}']

        # Resonator Settings
        self.tone_list_lineEdit.setText(str(chan_settings['tone_list']))
        # self.tone_list_lineEdit.setPlaceholderText(self.rfsoc.settings['tone_list'])
        if 'tone_powers' in chan_settings:
            self.tone_power_lineEdit.setText(str(chan_settings['tone_powers']))
        # self.tone_power_lineEdit.setPlaceholderText(self.rfsoc.settings['tone_powers'])
        if 'chanmask' in chan_settings:
            self.chanmask_lineEdit.setText(str(chan_settings['chanmask']))
            # self.chanmask_lineEdit.setPlaceholderText(self.settings['chanmask'])

        # Ethernet Settings
        self.eth_source_lineEdit.setText(chan_settings['sourceip'])
        self.eth_dest_lineEdit.setText(chan_settings['destip'])
        self.eth_mac_lineEdit.setText(chan_settings['destmac'])
        self.eth_port_lineEdit.setText(str(chan_settings['port']))

        # IF Settings
        self.rfin_lineEdit.setText(str(chan_settings['rfin']))
        self.rfout_lineEdit.setText(str(chan_settings['rfout']))
        self.lo_freq_lineEdit.setText(f'{chan_settings['dsp']['lo_freq']:.3e}')
    
    @Slot(QAbstractButton)
    def restore_defaults(self, button: QAbstractButton):
        std_btn = self.buttonBox.standardButton(button)
        if std_btn == QDialogButtonBox.StandardButton.RestoreDefaults:
            self.set_defaults()
