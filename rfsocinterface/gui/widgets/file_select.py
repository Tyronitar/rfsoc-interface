"""Widget for selecting and uploading files."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QMetaObject, QSize, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QWidget,
)

from rfsocinterface.gui.widgets.lineedit import ClickableLineEdit

DEFAULT_DIR = Path('./')
DEFAULT_BROWSE_OPTIONS = {
    'caption': 'Select File',
    'dir': './',
    'filter': 'All Files(*.*)',
    'selectedFilter': 'All Files(*.*)',
}


class FileSelectWidget(QWidget):
    """Widget for selecting files."""

    clicked = Signal()
    cursor_position_changed = Signal(int, int)
    editing_finished = Signal()
    input_rejected = Signal()
    return_pressed = Signal()
    selection_changed = Signal()
    text_changed = Signal(str)
    text_edited = Signal(str)

    def __init__(self, parent=None):
        """Initialize a FileSelectWidget."""
        super().__init__(parent=parent)
        self.setup_ui()

        self.browse_dialog_options = DEFAULT_BROWSE_OPTIONS
        self.setup_connections()

    def setup_connections(self):
        """Create all the signal connections."""
        self.pushButton.clicked.connect(self.choose_file)
        self.lineEdit.clicked.connect(self.clicked.emit)
        self.lineEdit.cursorPositionChanged.connect(self.cursor_position_changed.emit)
        self.lineEdit.editingFinished.connect(self.editing_finished.emit)
        self.lineEdit.inputRejected.connect(self.input_rejected.emit)
        self.lineEdit.returnPressed.connect(self.return_pressed.emit)
        self.lineEdit.selectionChanged.connect(self.selection_changed.emit)
        self.lineEdit.textChanged.connect(self.text_changed.emit)
        self.lineEdit.textEdited.connect(self.text_edited.emit)

    def setup_ui(self):
        """Setup the UI for this widget."""
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.lineEdit = ClickableLineEdit(parent=self)
        self.lineEdit.setObjectName('lineEdit')
        self.horizontalLayout.addWidget(self.lineEdit)

        self.pushButton = QPushButton(parent=self)
        self.pushButton.setObjectName('pushButton')
        self.horizontalLayout.addWidget(self.pushButton)

        self.setLayout(self.horizontalLayout)

        self.retranslate_ui()

        QMetaObject.connectSlotsByName(self)

    @Slot()
    def choose_file(self):
        """Open a file dialog to select the tone file."""
        fname, _ = QFileDialog.getOpenFileName(self, **self.browse_dialog_options)
        if fname:
            self.lineEdit.setText(fname)
            self.set_dir(str(Path(fname).parent))

    def retranslate_ui(self):
        """Retranslate the text in the widget."""
        self.setWindowTitle(
            QCoreApplication.translate('FileSelectWidget', 'FileSelectWidget', None)
        )
        self.pushButton.setText(
            QCoreApplication.translate('FileSelectWidget', 'Browse...', None)
        )

    def text(self) -> str:
        """Return the text in the widget's QLineEdit."""
        return self.lineEdit.text()

    def set_text(self, text: str):
        """Set the text in the widget's QLineEdit."""
        self.lineEdit.setText(text)

    def clear(self):
        """Clear all text in the widget's QLineEdit."""
        self.lineEdit.clear()

    def set_caption(self, caption: str):
        """Set the caption for the file browsing dialog."""
        self.browse_dialog_options['caption'] = caption

    def set_filter(self, filt: str):
        """Set the filter for the file browsing dialog."""
        self.browse_dialog_options['filter'] = filt

    def set_dir(self, directory: str):
        """Set the directory for the file browsing dialog."""
        self.browse_dialog_options['dir'] = directory

    def set_placeholder_text(self, text: str):
        """Set the placeholder text for the QLineEdit."""
        self.lineEdit.setPlaceholderText(text)

    def set_selected_filter(self, filt: str):
        """Set the selected filter for the file browsing dialog."""
        all_filters = self.browse_dialog_options['filter']
        if filt not in all_filters:
            raise ValueError(f'Filter {filt} not found in {all_filters.split(";;")}')
        self.browse_dialog_options['selectedFilter'] = filt


class FileUploadWidget(FileSelectWidget):
    """FileSelectWidget that includes a button for "uploading" the selected file."""

    uploaded = Signal(str)

    def __init__(self, parent=None):
        """Initialize a FileUploadWidget."""
        super().__init__(parent)

        self.toolButton = QToolButton(self)
        self.toolButton.setObjectName('toolButton')
        self.toolButton.setEnabled(False)
        icon = QIcon()
        icon.addFile(':/icons/upload.png', QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.toolButton.setIcon(icon)

        self.horizontalLayout.addWidget(self.toolButton)

        self.lineEdit.textChanged.connect(self.enable_upload)
        self.toolButton.clicked.connect(self.upload)

    @Slot()
    def upload(self):
        """Emit a signal with the curent text.."""
        self.uploaded.emit(self.text())

    @Slot(str)
    def enable_upload(self, text: str):
        """Change whether the upload button is enabled."""
        if text != '':
            self.toolButton.setEnabled(True)
        else:
            self.toolButton.setEnabled(False)
