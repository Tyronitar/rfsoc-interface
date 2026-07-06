from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import QWidget

from rfsocinterface.core.utils import PERMISSIONS_ALL_FULL, get_filename
from rfsocinterface.gui.uic.save_location_ui import Ui_SaveLocationWidget


class SaveLocationWidget(QWidget, Ui_SaveLocationWidget):
    def __init__(self, parent=None, file_type: str = 'tod'):
        super().__init__(parent)
        self.setupUi(self)

        self.file_type = file_type

        self.checkBox.checkStateChanged.connect(self.handle_click_default_box)
        self.checkBox.setCheckState(Qt.CheckState.Checked)
        self.change_save_location_visibility(False)
        self.update_default_save_location()
        self.directory_file_select.text_edited.connect(self.update_save_locale_label)
        self.filename_file_select.text_edited.connect(self.update_save_locale_label)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_default_save_location)
        self.update_timer.start(10000)

    def change_save_location_visibility(self, visible: bool):
        self.directory_label.setVisible(visible)
        self.directory_file_select.setVisible(visible)
        self.filename_label.setVisible(visible)
        self.filename_file_select.setVisible(visible)

    def get_chosen_save_location(
        self,
        chan_name: str = '',
        mkdir: bool = False,
        touch_file: bool = False,
        mode: int = PERMISSIONS_ALL_FULL,
    ) -> Path:
        if self.checkBox.isChecked():
            save_path = get_filename(
                file_type=self.file_type, tile_name=chan_name, mkdir=mkdir
            ).with_suffix('.h5')
        else:
            directory = self.directory_file_select.text()
            filename = self.filename_file_select.text()
            save_path = Path(f'{directory}/{filename}')
        if touch_file:
            save_path.touch(mode, exist_ok=True)
        return save_path

    @Slot(str)
    def update_save_locale_label(self, text: str):
        if self.checkBox.isChecked():
            self._default_path = get_filename(file_type=self.file_type).with_suffix(
                '.h5'
            )
            self.save_locale_label.setText(f'Saving to "{self._default_path}"')
        else:
            save_path = self.get_chosen_save_location()
            self.save_locale_label.setText(f'Saving to "{save_path}"')

    @Slot(Qt.CheckState)
    def handle_click_default_box(self, state: Qt.CheckState):
        save_path = self.get_chosen_save_location()
        self.save_locale_label.setText(f'Saving to "{save_path}"')
        self.change_save_location_visibility(state == Qt.CheckState.Unchecked)

    @Slot()
    def update_default_save_location(self):
        self._default_path = get_filename(
            file_type=self.file_type, tile_name='<TILE>'
        ).with_suffix('.h5')
        if self.checkBox.isChecked():
            self.save_locale_label.setText(f'Saving to "{self._default_path}"')
