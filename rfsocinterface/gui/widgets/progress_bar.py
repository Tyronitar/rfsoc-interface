"""Progress-tracking related widgets."""

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, Signal, Slot
from PySide6.QtWidgets import QProgressDialog


class IncrementalProgressDialog(QProgressDialog):
    """QProgressDialog that increments its value by 1 at a time."""

    incremented = Signal()

    def __init__(self, *args, **kwargs):
        """Initialize an IncrementalProgressDialog."""
        super().__init__(*args, **kwargs)
        self.incremented.connect(self.increment)

    @Slot()
    def increment(self):
        """Increase the progress by 1."""
        self.setValue(self.value() + 1)


def make_progress_dialog_incrementer(pd: IncrementalProgressDialog) -> Callable:
    """Create a function that increments an IncrementalProgressDialog by 1."""

    def incrementer():
        pd.incremented.emit()
        QCoreApplication.processEvents()

    return incrementer
