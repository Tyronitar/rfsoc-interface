from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt

from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

class MainWidget(QWidget):

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.main_window = main_window
        self.rfsocs = rfsocs
        self.settings = settings

    def update_channel_choices(self, combo_box: CheckableComboBox):
        total = 0
        for rfsoc in self.rfsocs:
            for i in range(2):
                combo_box.addItem(rfsoc.channel_as_text(i + 1))
                item = combo_box.model().item(total, 0)
                item.setCheckState(Qt.CheckState.Unchecked)
                total += 1