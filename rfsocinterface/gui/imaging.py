from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.main_widget import MainWidget
from rfsocinterface.core.rfsoc import RFSOCWrapper

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class ImagingWidget(MainWidget, Ui_ImagingWidget):
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None=None) -> None:
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)

        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
