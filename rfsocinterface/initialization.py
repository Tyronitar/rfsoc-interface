from pathlib import Path
from PySide6.QtCore import Qt
from rfsocinterface.ui.initialization_ui import Ui_InitializationTabWidget
from PySide6.QtWidgets import QWidget, QFileDialog


class InitializationWidget(QWidget, Ui_InitializationTabWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)

        self.tone_list_browse_pushButton.clicked.connect(self.choose_tone_file)
        self.chanmask_browse_pushButton.clicked.connect(self.choose_channel_mask)

    def choose_tone_file(self):
        """Open a file dialog to select the tone file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Tone File',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.tone_path = Path(fname)
            self.tone_list_lineEdit.setText(fname)
    
    def choose_channel_mask(self):
        """Open a file dialog to select the channel mask file."""
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Select Channel Mask',
            './',
            'Numpy (*.npy);;All Files(*.*)',
            'Numpy (*.npy)',
        )
        if fname:
            self.chanmask = Path(fname)
            self.chanmask_lineEdit.setText(fname)