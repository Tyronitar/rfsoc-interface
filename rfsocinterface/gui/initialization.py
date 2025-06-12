from typing import TYPE_CHECKING, Iterator
from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QDoubleValidator
from rfsocinterface.gui.uic.initialization_ui import Ui_InitializationTabWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit
from PySide6.QtWidgets import (QApplication, QGridLayout, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget)

from rfsocinterface.gui.utils import get_num_value
from rfsocinterface.gui.widgets.section import Section
from rfsocinterface.gui.rfsoc_settings import ChannelSettingsWidget, RFSOCSettingsWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.main_widget import MainWidget

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class InitializationWidget(MainWidget, Ui_InitializationTabWidget):

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None = None):
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.items: list[tuple[Section, RFSOCSettingsWidget]] = []
        self.active_section = None

        self.scrollArea.setStyleSheet('QScrollArea {background-color:white;}')
        self.scrollAreaWidgetContents.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        n_rfsocs = len(settings['rfsocs'])
        for i, rfsoc in enumerate(rfsocs):
            self.add_section(rfsoc, toggle=i == n_rfsocs - 1)

        self.add_toolButton.clicked.connect(lambda: self.add_section(toggle=True))
        self.delete_toolButton.clicked.connect(self.remove_section)
    
    def add_section(self, rfsoc: RFSOCWrapper, toggle: bool=False):
        # channel_settings = dict(self.settings['defaults']['channel'], **chan_dict)
        section_id = len(self.items) + 1
        section = Section(self.scrollAreaWidgetContents, animationDuration=100)
        section.setObjectName(f'section_{section_id}')
        # TODO: Make the channel dynamic
        rfsoc_widget = RFSOCSettingsWidget(rfsoc, self)
        # channel_widget = ChannelSettingsWidget(self.rfsocs[0], 1, channel_settings, parent=channel_section)
        rfsoc_widget.setObjectName(f'section_{section_id}_widget')
        vertical_layout = QVBoxLayout()
        vertical_layout.setObjectName(f'section_{section_id}_verticalLayout')
        vertical_layout.addWidget(rfsoc_widget)
        # channel_section.setContentLayout(vertical_layout)
        section.setContentLayout(rfsoc_widget.layout())
        section.setTitle(rfsoc.settings['name'])

        self.verticalLayout.addWidget(section, alignment=Qt.AlignmentFlag.AlignTop)
        self.items.append((section, rfsoc_widget))
        if toggle:
            section.set_duration(0)
            section.toggleButton.toggle()
            section.set_duration(100)
        self._enable_delete()
        
        self.set_active_section(section)
        section.clicked.connect(self.section_clicked)
    
    @property
    def sections(self) -> Iterator[Section]:
        for section, _ in self.items:
            yield section   
    
    @property
    def rfsoc_widgets(self) -> Iterator[RFSOCSettingsWidget]:
        for _, widget in self.items:
            yield widget
    
    def collapse_all(self, recursive: bool=False):
        for section in self.sections:
            section.collapse(recursive=recursive)
    
    def _enable_delete(self):
        if len(self.items) > 1:
            self.delete_toolButton.setEnabled(True)
        else:
            self.delete_toolButton.setEnabled(False)
    
    def set_active_section(self, rfsoc_section: Section):
        if self.active_section is not None:
            self.active_section.set_active('false')

        self.active_section = rfsoc_section
        if self.active_section is not None:
            self.active_section.set_active('true')

    def section_clicked(self):
        section: Section = self.sender()
        if section in self.items:
            self.set_active_section(section)

    def remove_section(self):
        if len(self.items) == 0:
            return
        section_id = self.items.index(self.active_section)
        self.verticalLayout.removeWidget(self.active_section)
        self.items.remove(self.active_section)
        self.active_section.deleteLater()
        self.set_active_section(self.items[section_id - 1][0])
        self._enable_delete()
