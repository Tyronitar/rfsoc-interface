"""Module for handling parallelization."""
from concurrent.futures import Future, as_completed, wait, CancelledError, ThreadPoolExecutor
from multiprocessing import Queue
from threading import Thread, Lock, RLock, get_native_id
from pebble import ProcessPool, ThreadPool, waitforthreads, MapFuture, ProcessMapFuture
from pebble.pool.base_pool import map_results, PoolContext, PoolStatus, iter_chunks, MapResults
from pebble.common.types import Result, ResultStatus
from abc import abstractmethod
from typing import Callable, Any, Iterable, Iterator
import time
import traceback
import sys
import itertools

import psutil
from PySide6.QtCore import QThread, QThreadPool, Signal, QObject, QRunnable, QEventLoop, QMutex, QMutexLocker, QCoreApplication, QTimer, Qt, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QProgressDialog
from rfsocinterface.core.utils import P, R, T, print_future_result

class PoolContext:
    def __init__(self, max_workers: int):
        self._status = PoolStatus.CREATED
        self.status_mutex = RLock()

    @property
    def status(self) -> int:
        return self._status

    @status.setter
    def status(self, status: int):
        with self.status_mutex:
            if self.alive:
                self._status = status

    @property
    def alive(self) -> bool:
        return self.status not in (PoolStatus.ERROR, PoolStatus.STOPPED)


class JobPool:
    def __init__(self, max_workers: int | None=None, use_logical: bool=False, close_timeout: int | None=None):
        n_cpu = psutil.cpu_count(logical=use_logical)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.futures = []
        self.executor: ProcessPool | ThreadPool | QThreadJobPool = None
        self.close_timeout = close_timeout

    def _unqueue_future(self, f: Future):
        self.futures.remove(f)
    
    def active(self) -> bool:
        return self.executor.active
    
    def schedule(
            self,
            fn: Callable[P, R],
            *args: P.args,
            done_callbacks: list[Callable[[Future], None]]=[],
            **kwargs: P.kwargs,
    ) -> Future[R]:
        """Schedule a function to be computed by the JobPool.

        Arguments:
            fn (Callable[P, R]): Function to execute
            *args (P.args): Postiional arguments to pass to `fn`.
            **kwargs (P.kwargs): Keyword arguments to pass to `fn`.
            done_callbacks (list[Callable[[Future], None]]): Callback functions
                to be called when the future is finished. Defaults to [].
        
        Returns:
            (Future[R]): Future representing the result of calling `fn`.
        """
        f = self.executor.schedule(fn, args, kwargs)
        self.futures.append(f)
        f.add_done_callback(self._unqueue_future)
        for callback in done_callbacks:
            f.add_done_callback(callback)
        return f
    
    def map(
            self,
            fn: Callable[..., R],
            *iterables: Iterable[Any],
            done_callbacks: list[Callable[[Future], None]]=[],
            timeout: float | None=None,
            chunksize: int=1,
    ) -> MapFuture | ProcessMapFuture:
        """Apply `fn` to every item of `iterable` and return an iterator of the results.

        If additional iterable arguments are passed, `fn` must take that many
        arguments and is applied to the items from all iterables in parallel.

        Arguments:
            fn (Callable[..., R]): Function to execute
            *iterables (Iterable[Any]): Iterables for every positional argument to
                pass to `fn`
            done_callbacks (list[Callable[[Future], None]]): Callback functions
                to be called when the future is finished. Defaults to [].
            timeout (float): Maximum number of seconds to wait before aborting
                execution. If None, then there is no time limit.

        Returns:
            (Iterator[R]): An iterator containig all calls to `fn`. Equivalent to the
                output of `map(fn, *iterables)`.

        Raises:
            TimeoutError: If the execution didn't finish before the time limit.
        """
        f = self.executor.map(fn, *iterables, timeout=timeout, chunksize=chunksize)
        self.futures.append(f)
        f.add_done_callback(self._unqueue_future)
        for callback in done_callbacks:
            for fut in f.futures:
                fut.add_done_callback(callback)
        return f

    def cancel_all(self) -> bool:
        """Cancel all currently running jobs.
        
        Returns:
            (bool): Whether all jobs were succesfully canceled.
        """
        all_canceled = True
        for f in self.futures:
            all_canceled |= f.cancel()
        return all_canceled
    
    def shutdown(self, wait: bool=False):
        """Shutdown the executor and wait for all threads to finish."""
        self.executor.stop()
        if wait:
            self.executor.join()

    def stop(self):
        self.executor.stop()

    def join(self, timeout: float=None):
        self.executor.join(timeout=timeout)
    
    def close(self):
        self.executor.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        # if self.executor.active:
        self.close()
        self.join(self.close_timeout)


class ProcessJobPool(JobPool):

    def __init__(self, max_workers: int | None=None, close_timeout: int | None=None):
        super().__init__(max_workers=max_workers, use_logical=False, close_timeout=close_timeout)
        self.executor = ProcessPool(self.max_workers)
    

class ThreadJobPool(JobPool):

    def __init__(self, max_workers: int | None=None, close_timeout: int | None=None):
        super().__init__(max_workers=max_workers, use_logical=True, close_timeout=close_timeout)
        self.executor = ThreadPool(self.max_workers)


def execute(function: Callable, *args, **kwargs):
    try:
        return Result(ResultStatus.SUCCESS, function(*args, **kwargs))
    except BaseException as error:
        try:
            error.traceback = traceback.format_exc()
        except AttributeError:  # Frozen exception
            pass

        return Result(ResultStatus.FAILURE, error)


def process_chunk(function: Callable, chunk: list, **kwargs) -> list:
    """Processes a chunk of the iterable passed to map dealing with errors."""
    return [execute(function, *args, **kwargs) for args in chunk]

class QThreadPoolExecutor(QObject):
    progress = Signal(int)
    error = Signal(BaseException)
    job_finished = Signal()
    result = Signal(object)

    def __init__(self, max_workers: int=None, track_progress: bool=False, parent=None):
        QObject.__init__(self, parent=parent)
        n_cpu = psutil.cpu_count(logical=True)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.pool = ThreadPoolExecutor(self.max_workers)
        self.track_progress= track_progress
    
    def emit_progress(self, n: int | None=None):
        if n is None:
            n = -1
        self.progress.emit(n)
    
    def handle_future_done(self, f: Future):
        self.job_finished.emit()
        if f.cancelled():
            return
        try:
            res = f.result()
            self.result.emit(res)
        except BaseException as e:
            self.error.emit(e)
    
    @property
    def active(self) -> bool:
        return not self.pool._shutdown
    
    def schedule(self, fn: Callable[P, R], args: tuple, kwargs: dict) -> Future[R]:
        f = Future()
        if self.track_progress:
            kwargs['progress_callback'] = self.emit_progress
        f = self.pool.submit(fn, *args, **kwargs)

        f.add_done_callback(self.handle_future_done)
        return f
    
    def map(self, fn: Callable[..., R], *iterables: Iterable, timeout: float | None=None, chunksize: int=1) -> MapFuture:
        if chunksize < 1:
            raise ValueError("chunksize must be >= 1")
        futures = [self.schedule(process_chunk, (fn, chunk), {})
                   for chunk in iter_chunks(zip(*iterables), chunksize)]
        return map_results(MapFuture(futures), timeout=timeout)
    
    def stop(self):
        self.pool.shutdown(cancel_futures=True)
    
    def close(self):
        self.pool.shutdown(cancel_futures=False)

    def join(self, timeout: int=None):
        return

    

# NOTE: This must have a QEventLoop already running or the signals won't work
class QThreadJobPool(JobPool, QObject):
    progress = Signal(int)
    error = Signal(BaseException)
    job_finished = Signal()
    result = Signal(object)

    def __init__(self, max_workers: int | None=None, track_progress: bool=False, close_timeout: int | None=None, parent=None):
        QObject.__init__(self, parent=parent)  # Initialize QObject
        JobPool.__init__(self, max_workers=max_workers, use_logical=True, close_timeout=close_timeout) 
        self.track_progress = track_progress
        self.executor = QThreadPoolExecutor(max_workers=self.max_workers, track_progress=self.track_progress, parent=self)
        self.executor.progress.connect(self.handle_progress)
        self.executor.error.connect(self.handle_error)
        self.executor.job_finished.connect(self.handle_job_finished)
        self.executor.result.connect(self.handle_result)
    
    @Slot(object)
    def handle_result(self, res: Any):
        self.result.emit(res)
    
    @Slot(int)
    def handle_progress(self, n: int):
        self.progress.emit(n)

    @Slot(BaseException)
    def handle_error(self, e: BaseException):
        self.error.emit(e)
    
    @Slot()
    def handle_job_finished(self):
        self.job_finished.emit()
