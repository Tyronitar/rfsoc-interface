from pathlib import Path
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QDoubleValidator, QRegularExpressionValidator, QIntValidator
from rfsocinterface.gui.uic.channel_settings_ui import Ui_ChannelSettingsWidget
from rfsocinterface.gui.uic.rfsoc_advanced_settings_ui import Ui_RFSOCAdvancedSettingsWidget
from rfsocinterface.gui.utils import PathValidator, get_lineEdit_text, get_num_value
from rfsocinterface.gui.widgets.icon_label import IconLabel
from PySide6.QtWidgets import QWidget, QFileDialog, QVBoxLayout

from PySide6.QtWidgets import (
    QAbstractButton,
    QDialogButtonBox,
    QWidget,
)
import tables


import numpy as np

from rfsocinterface.gui.widgets.section import Section
from rfsocinterface.core.utils import IPV4_REGEX, MAC_REGEX
from rfsocinterface.gui.widgets.icon_label import IconLabel, verify_lineEdit, ERROR_ICON_CODE, highlight_error_line_edit
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.utils import DEFAULT_PARAMS_DIRECTORY

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_logger = logging.getLogger(__name__)

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
    
    def update_channel_names(self):
        """Update the channel names in the sections."""
        self.channel1_section.setTitle(self.rfsoc.get_channel_name(1))
        self.channel2_section.setTitle(self.rfsoc.get_channel_name(2))
    
    def setupUi(self):
        layout = QVBoxLayout(self)

        channel1_layout = QVBoxLayout()
        self.channel1_widget = ChannelSettingsWidget(self.rfsoc, 1, parent=self)
        channel1_layout.addWidget(self.channel1_widget)
        self.channel1_section = Section(self)
        self.channel1_section.setTitle(self.rfsoc.get_channel_name(1))
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
        self.channel2_section.setTitle(self.rfsoc.get_channel_name(2))
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
        self.redis_ip_lineEdit.setText(settings['redis']['IP'])
        self.redis_port_lineEdit.setText(str(settings['redis']['port']))

        # Comports
        self.comport_atten_fileUploadWidget.lineEdit.setText(str(settings['attenComport']))
        self.comport_channel1_fileUploadWidget.lineEdit.setText(str(settings['channels'][0]['loComport']))
        self.comport_channel2_fileUploadWidget.lineEdit.setText(str(settings['channels'][1]['loComport']))


class ChannelSettingsWidget(QWidget, Ui_ChannelSettingsWidget):
    height_updated = Signal()
    def __init__(self, rfsoc: RFSOCWrapper, channel: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.rfsoc = rfsoc
        self.channel = channel

        self.setupUi(self)

        # Resonator Settings Connections
        # TODO: Make params checkbox toggle the other options
        self.params_fileSelectWidget.set_dir(DEFAULT_PARAMS_DIRECTORY)
        # self.params_fileSelectWidget.editingFinished.connect(self.load_params_file)
        self.upload_params_pushButton.clicked.connect(self.load_params_file)
        # self.params_fileSelectWidget.textChanged.connect(self.load_params_file)
        # self.upload_tones_pushButton.clicked.connect(self.upload_tone_list)

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

    
    @property
    def main_window(self) -> 'MainWindow':
        """Return the main window of the application."""
        return self.get_all_parents()[-1]
    
    def get_all_parents(self) -> list[QWidget]:
        """Return a list of all parent widgets."""
        parents = []
        widget = self.parent()
        while widget:
            parents.append(widget)
            widget = widget.parent()
        return parents
    
    def load_params_file(self):
        params_file = self.params_fileSelectWidget.text()
        if params_file and Path(params_file).exists():
            self.setCursor(Qt.CursorShape.WaitCursor)
            try:
                _logger.debug(f'ChannelSettingsWidget calling `load_params_file` of RFSoC {self.rfsoc.name} with ({self.channel}, {params_file})')
                self.rfsoc.load_params_file(self.channel, params_file)
                self.main_window.channelNamesUpdated.emit()
                self.lo_freq_lineEdit.setText(f'{self.rfsoc.get_channel(self.channel).lo_freq / 1e6:.3f}')
            finally:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            
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
            self.eth_source_error_label,
            self.eth_dest_error_label,
            self.eth_mac_error_label,
            self.eth_port_error_label,
        ]
    
    def clear_form(self):
        self.params_fileSelectWidget.clear()
        self.eth_source_lineEdit.clear()
        self.eth_dest_lineEdit.clear()
        self.eth_mac_lineEdit.clear()
        self.eth_port_lineEdit.clear()
        self.rfin_lineEdit.clear()
        self.rfout_lineEdit.clear()
        self.lo_freq_lineEdit.clear()
        self.hide_error_labels()
    
    @Slot(str)
    def upload_firmware(self, bitstream: str):
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            _logger.debug(f'ChannelSettingsWidget calling `upload_bitstream` of RFSoC {self.rfsoc.name} with {bitstream}')
            self.rfsoc.upload_bitstream(bitstream)
        finally:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    @Slot()
    def update_ethernet_config(self):
        chan_settings = self.rfsoc.channel_settings(self.channel)
        chan_settings['sourceIP'] = get_lineEdit_text(self.eth_source_lineEdit)
        chan_settings['destIP'] = get_lineEdit_text(self.eth_dest_lineEdit)
        chan_settings['destMAC'] = get_lineEdit_text(self.eth_mac_lineEdit)
        chan_settings['port'] = get_num_value(self.eth_port_lineEdit, int)
        _logger.debug(f'ChannelSettingsWidget calling `update_kidpy_rfsoc` of RFSoC {self.rfsoc.name}')
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
            try:
                self.update_ethernet_config()
                _logger.debug(f'ChannelSettingsWidget calling `configure_hardware` of RFSoC {self.rfsoc.name}')
                self.rfsoc.configure_hardware()
            finally:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_attenuation(self, attenuation: str):
        match attenuation:
            case 'in':
                addr = 2 if self.channel == 1 else 4
                lineEdit = self.rfin_lineEdit
                error_label = self.rfin_error_label
            case 'out':
                addr = 1 if self.channel == 1 else 3
                lineEdit = self.rfout_lineEdit
                error_label = self.rfout_error_label
            case _:
                raise ValueError(f'Function `set_attenuation` called with illegal argument "{attenuation}"; must be in ["in", "out"]')
        
        valid, toggled = verify_lineEdit(lineEdit, error_label)
        if toggled:
            self.height_updated.emit()
        elif valid:
            self.setCursor(Qt.CursorShape.WaitCursor)
            try:
                att = get_num_value(lineEdit)
                _logger.debug(f'ChannelSettingsWidget setting attenuation of rf{attenuation} for RFSoC {self.rfsoc.name} channel {self.channel} to {att:.2f} dB')
                self.rfsoc.set_atten(addr, att)
            finally:
                self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def set_lo_freq(self):
        lo_freq = get_num_value(self.lo_freq_lineEdit) * 1e6  # MHz to Hz
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            _logger.debug(f'ChannelSettingsWidget setting LO freq for RFSoC {self.rfsoc.name} channel {self.channel} to {lo_freq * 1e-6:.3f} MHz')
            self.rfsoc.set_frequency(self.channel, lo_freq)
        finally:
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def set_defaults(self):
        chan_settings = self.rfsoc.channel_settings(self.channel)

        if 'paramsFile' in chan_settings:
            self.params_fileSelectWidget.setText(str(chan_settings['paramsFile']))

        # Ethernet Settings
        self.eth_source_lineEdit.setText(chan_settings['sourceIP'])
        self.eth_dest_lineEdit.setText(chan_settings['destIP'])
        self.eth_mac_lineEdit.setText(chan_settings['destMAC'])
        self.eth_port_lineEdit.setText(str(chan_settings['port']))

        # IF Settings
        self.rfin_lineEdit.setText(str(chan_settings['rfin']))
        self.rfout_lineEdit.setText(str(chan_settings['rfout']))
        self.lo_freq_lineEdit.setText(f'{chan_settings["dsp"]["loFreq"] * 1e-6}')
    
    @Slot(QAbstractButton)
    def restore_defaults(self, button: QAbstractButton):
        std_btn = self.buttonBox.standardButton(button)
        if std_btn == QDialogButtonBox.StandardButton.RestoreDefaults:
            self.set_defaults()
