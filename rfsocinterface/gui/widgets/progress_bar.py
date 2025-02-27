from PySide6.QtWidgets import QDialog, QWidget, QApplication, QProgressDialog
from PySide6.QtCore import Signal, Qt, QCoreApplication, Slot
from typing import Callable, Any, Iterable
from concurrent.futures import Future
from pebble import MapFuture, ProcessMapFuture
import time

from rfsocinterface.gui.uic.progress_bar_ui import Ui_Dialog
from rfsocinterface.core.utils import Job, P, JobQueue, SequentialJobQueue, R, tr
from rfsocinterface.core.pool import QThreadJobPool, QProcessJobPool


class QJobProgressDialog(QProgressDialog):

    def __init__(
            self,
            labelText: str='',
            cancelButtonText='Cancel',
            minimum: int=0,
            maximum: int=100,
            max_workers: int=1,
            parent: QWidget | None=None,
            flags: Qt.WindowType=Qt.WindowType.Dialog):
        super().__init__(labelText, cancelButtonText, minimum, maximum, parent=parent, flags=flags)
        self.setValue(0)
    
    @Slot(int)
    def handle_progress(self, val: int):
        if val < 0:
            new_val = self.value() + 1
        else:
            new_val = val
        self.setValue(new_val)
        # print(f'Progress: {new_val}/{self.maximum()}')
        if new_val >= self.maximum():
            self.pool.close()
            self.pool.join()
    
    def schedule(
            self,
            fn: Callable[P, R],
            *args: P.args,
            done_callbacks: list[Callable[[Future], None]]=[],
            **kwargs: P.kwargs,
    ) -> Future[R]:
        return self.pool.schedule(fn, *args, done_callbacks=done_callbacks, **kwargs)
    
    def map(
            self,
            fn: Callable[..., R],
            *iterables: Iterable[Any],
            done_callbacks: list[Callable[[Future], None]]=[],
            timeout: float | None=None,
            chunksize: int=1,
    ) -> MapFuture | ProcessMapFuture:
        return self.pool.map(fn, *iterables, done_callbacks=done_callbacks, timeout=timeout, chunksize=chunksize)
    
    @Slot()
    def on_cancel(self):
        self.pool.shutdown(wait=True)
    
    @property
    def active(self) -> bool:
        return self.pool.active
    
    def _setup_connections(self):
        self.canceled.connect(self.on_cancel)
        self.pool.progress.connect(self.handle_progress)
        self.pool.error.connect(print)
        self.pool.result.connect(print)
    

class QThreadJobProgressDialog(QJobProgressDialog):

    def __init__(
            self,
            labelText: str='',
            cancelButtonText='Cancel',
            minimum: int=0,
            maximum: int=100,
            max_workers: int=1,
            parent: QWidget | None=None,
            flags: Qt.WindowType=Qt.WindowType.Dialog):
        super().__init__(labelText, cancelButtonText, minimum, maximum, max_workers=max_workers, parent=parent, flags=flags)
        self.pool = QThreadJobPool(max_workers=max_workers, track_progress=True, parent=self)
        self._setup_connections()

class QProcessJobProgressDialog(QJobProgressDialog):

    def __init__(
            self,
            labelText: str='',
            cancelButtonText='Cancel',
            minimum: int=0,
            maximum: int=100,
            max_workers: int=1,
            parent: QWidget | None=None,
            flags: Qt.WindowType=Qt.WindowType.Dialog):
        super().__init__(labelText, cancelButtonText, minimum, maximum, max_workers=max_workers, parent=parent, flags=flags)
        self.pool = QProcessJobPool(max_workers=max_workers, track_progress=True, parent=self)
        self._setup_connections()
