from typing import Callable

from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import QCoreApplication, Signal, Slot

class IncrementalProgressDialog(QProgressDialog):
    incremented = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.incremented.connect(self.increment)

    @Slot()
    def increment(self):
        self.setValue(self.value() + 1)


def make_progress_dialog_incrementer(pd: IncrementalProgressDialog) -> Callable:
    """Create a function that increments a progress dialog by 1."""
    def incrementer():
        pd.incremented.emit()
        QCoreApplication.processEvents()
    return incrementer
