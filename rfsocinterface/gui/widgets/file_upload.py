from pathlib import Path
from PySide6.QtCore import Qt, Signal, QCoreApplication, QMetaObject, QSize
from PySide6.QtGui import QDoubleValidator, QIcon
from PySide6.QtWidgets import QWidget, QFileDialog, QLineEdit, QHBoxLayout, QPushButton, QToolButton
from typing import Callable, Any

from rfsocinterface.core.utils import get_num_value
from rfsocinterface.gui.uic.file_upload_ui import Ui_FileUploadWidget
from rfsocinterface.gui.widgets.lineedit import ClickableLineEdit

DEFAULT_DIR = Path('./')
DEFAULT_BROWSE_OPTIONS = {
    'caption': 'Select File',
    'dir': './',
    'filter': 'All Files(*.*)',
    'selectedFilter': 'All Files(*.*)',
}

class FileSelectWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi()

        self.browse_dialog_options = DEFAULT_BROWSE_OPTIONS
        self.pushButton.clicked.connect(self.choose_file)

    def setupUi(self):
        self.horizontalLayout = QHBoxLayout(parent=self)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.lineEdit = ClickableLineEdit(parent=self)
        self.lineEdit.setObjectName(u"lineEdit")
        self.horizontalLayout.addWidget(self.lineEdit)

        self.pushButton = QPushButton(parent=self)
        self.pushButton.setObjectName(u"pushButton")
        self.horizontalLayout.addWidget(self.pushButton)

        self.retranslateUi()

        QMetaObject.connectSlotsByName(self)

    def choose_file(self):
        """Open a file dialog to select the tone file."""
        fname, _ = QFileDialog.getOpenFileName(self, **self.browse_dialog_options)
        if fname:
            self.lineEdit.setText(fname)
            self.set_dir(str(Path(fname).parent))

    def retranslateUi(self):
        self.setWindowTitle(QCoreApplication.translate("FileSelectWidget", u"FileSelectWidget", None))
        self.pushButton.setText(QCoreApplication.translate("FileSelectWidget", u"Browse...", None))

    def get_text(self) -> str:
        txt = self.lineEdit.text()
        return txt
    
    def set_caption(self, caption: str):
        self.browse_dialog_options['caption'] = caption

    def set_filter(self, filt: str):
        self.browse_dialog_options['filter'] = filt

    def set_dir(self, directory: str):
        self.browse_dialog_options['dir'] = directory
    
    def set_placeholder_text(self, text: str):
        self.lineEdit.setPlaceholderText(text)

    def set_selected_filter(self, filt: str):
        all_filters = self.browse_dialog_options['filter']
        if filt not in all_filters:
            raise ValueError(f'Filter {filt} not found in {all_filters.split(";;")}')
        self.browse_dialog_options['selectedFilter'] = filt

class FileUploadWidget(FileSelectWidget):
    uploaded = Signal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.setupUi(self)

        self.toolButton = QToolButton(FileUploadWidget)
        self.toolButton.setObjectName(u"toolButton")
        self.toolButton.setEnabled(False)
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.toolButton.setIcon(icon)

        self.horizontalLayout.addWidget(self.toolButton)

        self.lineEdit.textChanged.connect(self.enable_upload)
        self.toolButton.clicked.connect(self.upload)

    def upload(self):
        self.uploaded.emit(self.get_text())
    
    def enable_upload(self):
        if self.get_text() != '':
            self.toolButton.setEnabled(True)
        else:
            self.toolButton.setEnabled(False)
    