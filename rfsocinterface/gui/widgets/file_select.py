from pathlib import Path
from PySide6.QtCore import Qt, Signal, QCoreApplication, QMetaObject, QSize, Slot
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
    clicked = Signal()
    cursorPositionChanged = Signal(int, int)
    editingFinished = Signal()
    inputRejected = Signal()
    returnPressed = Signal()
    selectionChanged = Signal()
    textChanged = Signal(str)
    textEdited = Signal(str)
    

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi()

        self.browse_dialog_options = DEFAULT_BROWSE_OPTIONS
        self.setup_connections()
    
    def setup_connections(self):
        self.pushButton.clicked.connect(self.choose_file)
        self.lineEdit.clicked.connect(self.clicked.emit)
        self.lineEdit.cursorPositionChanged.connect(self.cursorPositionChanged.emit)
        self.lineEdit.editingFinished.connect(self.editingFinished.emit)
        self.lineEdit.inputRejected.connect(self.inputRejected.emit)
        self.lineEdit.returnPressed.connect(self.returnPressed.emit)
        self.lineEdit.selectionChanged.connect(self.selectionChanged.emit)
        self.lineEdit.textChanged.connect(self.textChanged.emit)
        self.lineEdit.textEdited.connect(self.textEdited.emit)

    def setupUi(self):
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.lineEdit = ClickableLineEdit(parent=self)
        self.lineEdit.setObjectName(u"lineEdit")
        self.horizontalLayout.addWidget(self.lineEdit)

        self.pushButton = QPushButton(parent=self)
        self.pushButton.setObjectName(u"pushButton")
        self.horizontalLayout.addWidget(self.pushButton)

        self.setLayout(self.horizontalLayout)

        self.retranslateUi()

        QMetaObject.connectSlotsByName(self)

    @Slot()
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

        self.toolButton = QToolButton(self)
        self.toolButton.setObjectName(u"toolButton")
        self.toolButton.setEnabled(False)
        icon = QIcon()
        icon.addFile(u":/icons/upload.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.toolButton.setIcon(icon)

        self.horizontalLayout.addWidget(self.toolButton)

        self.lineEdit.textChanged.connect(self.enable_upload)
        self.toolButton.clicked.connect(self.upload)

    @Slot()
    def upload(self):
        self.uploaded.emit(self.get_text())
    
    @Slot(str)
    def enable_upload(self, text: str):
        if text != '':
            self.toolButton.setEnabled(True)
        else:
            self.toolButton.setEnabled(False)
    