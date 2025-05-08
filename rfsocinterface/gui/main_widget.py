from typing import TYPE_CHECKING, Iterator
from functools import partial

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt

from rfsocinterface.core.rfsoc import RFSOCWrapper, get_channel_from_text
from rfsocinterface.core.settings import SettingsError
from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow
    from multiprocessing import Queue
    from threading import Thread

class MainWidget(QWidget):

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings
    
    @property
    def _telescope_queue(self) -> Queue | None:
        """Return the telescope queue for communication with the telescope controller."""
        return self.main_window.telescope_queue

    def update_channel_choices(self, combo_box: CheckableComboBox):
        total = 0
        for rfsoc in self.rfsocs:
            for i in range(2):
                combo_box.addItem(rfsoc.channel_as_text(i + 1))
                item = combo_box.model().item(total, 0)
                item.setCheckState(Qt.CheckState.Unchecked)
                total += 1

    def get_selected_channels(self, combob_box: CheckableComboBox) -> Iterator[tuple[RFSOCWrapper, int]]:
        checked_ids = combob_box.checked_indices()
        checked_text = [combob_box.itemText(i) for i in checked_ids]
        if not checked_text:
            raise SettingsError('No channel selected')
        return map(partial(get_channel_from_text, rfsocs=self.rfsocs), checked_text)
    
    def closeEvent(self, event):
        return super().closeEvent(event)