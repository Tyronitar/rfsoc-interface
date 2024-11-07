from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QDoubleValidator
from rfsocinterface.ui.initialization_ui import Ui_InitializationTabWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit
from PySide6.QtWidgets import (QApplication, QGridLayout, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget)

from rfsocinterface.utils import get_num_value
from rfsocinterface.ui.section import Section
from rfsocinterface.channel_settings import ChannelSettingsWidget
from kidpy import kidpy

class InitializationWidget(QWidget, Ui_InitializationTabWidget):

    def __init__(self, kpy: kidpy, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        self.kpy = kpy
        self.channels: list[Section] = []
        self.active_channel = None

        self.scrollArea.setStyleSheet('QScrollArea {background-color:white;}')
        self.scrollAreaWidgetContents.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        n_chan = 1
        for i in range(n_chan):
            self.add_channel(toggle=i == n_chan - 1)

        self.add_toolButton.clicked.connect(lambda: self.add_channel(toggle=True))
        self.delete_toolButton.clicked.connect(self.remove_channel)
    
    def add_channel(self, toggle: bool=False):
        channel_id = len(self.channels) + 1
        channel_section = Section(self.scrollAreaWidgetContents, animationDuration=100)
        channel_section.setObjectName(f'channel_{channel_id}_section')
        channel_widget = ChannelSettingsWidget(self.kpy, parent=channel_section)
        channel_widget.setObjectName(f'channel_{channel_id}_widget')
        vertical_layout = QVBoxLayout()
        vertical_layout.setObjectName(f'channel_{channel_id}_verticalLayout')
        vertical_layout.addWidget(channel_widget)
        channel_section.setContentLayout(vertical_layout)
        channel_section.setTitle(f'Channel {channel_id}')

        self.verticalLayout.addWidget(channel_section, alignment=Qt.AlignmentFlag.AlignTop)
        self.channels.append(channel_section)
        if toggle:
            channel_section.set_duration(0)
            channel_section.toggleButton.toggle()
            channel_section.set_duration(100)
        self._enable_delete()
        
        self._set_active_channel(channel_section)
        channel_section.clicked.connect(self.channel_clicked)
    
    def _enable_delete(self):
        if len(self.channels) > 1:
            self.delete_toolButton.setEnabled(True)
        else:
            self.delete_toolButton.setEnabled(False)
    
    def _set_active_channel(self, channel_section: Section):
        if self.active_channel is not None:
            self.active_channel.set_active('false')

        self.active_channel = channel_section
        self.active_channel.set_active('true')

    def channel_clicked(self):
        channel: Section = self.sender()
        if channel in self.channels:
            self._set_active_channel(channel)

    def remove_channel(self):
        if len(self.channels) == 0:
            return
        channel_id = self.channels.index(self.active_channel)
        self.verticalLayout.removeWidget(self.active_channel)
        self.channels.remove(self.active_channel)
        self.active_channel.deleteLater()
        self._set_active_channel(self.channels[channel_id - 1])
        self._enable_delete()
