from typing import override
from PySide6.QtWidgets import QWidget, QProgressDialog, QErrorMessage
from PySide6.QtCore import Qt, Slot
from typing import Callable, Any, Iterable
from concurrent.futures import Future
import time

from rfsocinterface.core.utils import P, R, CombinedFuture
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
        self.setValue(minimum)
        self.em = QErrorMessage(parent=self)
        self.pool = None
        self.max_workers=max_workers
        self.canceled.connect(self.on_cancel)
    
    def make_pool(self, max_workers: int | None=None):
        raise NotImplementedError
    
    def reset(self):
        # print('resetting')
        super().reset()
        self.setValue(self.minimum())
        # print(self.minimum(), self.value())
        # assert False
    
    @Slot(int)
    def handle_progress(self, val: int):
        if val < 0:
            new_val = self.value() + 1
        else:
            new_val = val
        # print(f'Progress: {new_val}/{self.maximum()}')
        if new_val >= self.maximum():
            if self.autoClose():
                self.pool.close()
                self.pool.join()
                self.close()
            if self.autoReset():
                self.reset()
        self.setValue(new_val)
    
    @Slot(BaseException)
    def handle_error(self, e: BaseException):
        if hasattr(e, 'message'):
            self.em.showMessage(e.message)
        else:
            self.em.showMessage(str(e))
    
    @Slot(object)
    def handle_result(self, val: Any):
        pass
    
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
    ) -> CombinedFuture[Iterable[R]]:
        return self.pool.map(fn, *iterables, done_callbacks=done_callbacks, timeout=timeout, chunksize=chunksize)
    
    @Slot()
    def on_cancel(self):
        self.pool.shutdown(wait=True)
    
    @property
    def active(self) -> bool:
        return self.pool.active
    
    def _setup_connections(self):
        self.pool.progress.connect(self.handle_progress)
        self.pool.error.connect(self.handle_error)
        self.pool.result.connect(self.handle_result)
    

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
        self.make_pool(max_workers=max_workers)
        # self.pool = QThreadJobPool(max_workers=max_workers, parent=self)
    
    def make_pool(self, max_workers: int | None=None):
        if self.pool is not None:
            self.pool.shutdown(wait=True)
            self.pool.deleteLater()
        self.reset()
        self.pool = QThreadJobPool(max_workers=max_workers, parent=self)
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
        self.make_pool(max_workers=max_workers)
        # self.pool = QProcessJobPool(max_workers=max_workers, parent=self)
    
    def make_pool(self, max_workers: int | None=None):
        if self.pool is not None:
            self.pool.shutdown(wait=True)
            self.pool.deleteLater()
        self.reset()
        self.pool = QProcessJobPool(max_workers=max_workers, parent=self)
        self._setup_connections()
