from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from rfsocinterface.ui.file_upload_ui import Ui_FileUploadWidget
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit
from typing import Callable, Any

from rfsocinterface.utils import get_num_value

class FileUploadWidget(QWidget, Ui_FileUploadWidget):
    uploaded = Signal(Any)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.setupUi(self)

        self.browse_dialog_options = {
            'caption': 'Select File',
            'dir': './',
            'filter': 'All Files(*.*)',
            'selectedFilter': 'All Files(*.*)',
        }
        self.lineEdit.textChanged.connect(self.enable_upload)
        self.pushButton.clicked.connect(self.choose_file)
        self.toolButton.clicked.connect(self.upload)

    def choose_file(self):
        """Open a file dialog to select the tone file."""
        fname, _ = QFileDialog.getOpenFileName(self, **self.browse_dialog_options)
        if fname:
            self.lineEdit.setText(fname)
        
    def get_text(self) -> str:
        txt = self.lineEdit.text()
        if not txt:
            txt = self.lineEdit.placeholderText()
        return txt
    
    def upload(self):
        self.uploaded.emit(self.get_text())
    
    def set_caption(self, caption: str):
        self.browse_dialog_options['caption'] = caption

    def set_filter(self, filt: str):
        self.browse_dialog_options['filter'] = filt

    def set_dir(self, directory: str):
        self.browse_dialog_options['dir'] = directory

    def set_selected_filter(self, filt: str):
        all_filters = self.browse_dialog_options['filter']
        if filt not in all_filters:
            raise ValueError(f'Filter {filt} not found in {all_filters.split(";;")}')
        self.browse_dialog_options['selectedFilter'] = filt
    
    def enable_upload(self):
        if self.lineEdit.text() != '':
            self.toolButton.setEnabled(True)
        else:
            self.toolButton.setEnabled(False)
    