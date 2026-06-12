"""Module for handling parallelization."""
from __future__ import annotations

import traceback
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from typing import Any, Callable, Iterable

import psutil
from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

from rfsocinterface.core.utils import (
    CombinedFuture,
    P,
    R,
    Result,
    ResultStatus,
    iter_chunks,
)


class JobPool:
    def __init__(self, max_workers: int | None=None, use_logical: bool=False, close_timeout: int | None=None):
        n_cpu = psutil.cpu_count(logical=use_logical)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.futures = []
        self.executor: QJobPool = None
        self.close_timeout = close_timeout

    def _unqueue_future(self, f: Future):
        self.futures.remove(f)

    @property
    def active(self) -> bool:
        return self.executor.active and len(self.futures) > 0

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
    ) -> CombinedFuture:
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
        self.stop()
        if wait:
            self.join()

    def stop(self):
        self.executor.stop()

    def join(self, timeout: float=None):
        self.executor.join(timeout=timeout)

    def close(self):
        self.executor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()
        self.join(self.close_timeout)


def execute(function: Callable, *args, **kwargs):
    try:
        # _logger.debug(f'Executing function with args: {args} and kwargs: {kwargs}')
        return Result(ResultStatus.SUCCESS, function(*args, **kwargs))
    except BaseException as error:
        # _logger.error(error)
        try:
            error.traceback = traceback.format_exc()
        except AttributeError:  # Frozen exception
            pass

        return Result(ResultStatus.FAILURE, error)


def process_chunk(function: Callable, chunk: list, **kwargs) -> list:
    """Processes a chunk of the iterable passed to map dealing with errors."""
    return [execute(function, *args, **kwargs) for args in chunk]

class QPoolExecutor(QObject):
    progress = Signal(int)
    error = Signal(BaseException)
    job_finished = Signal()
    result = Signal(object)
    pool: ThreadPoolExecutor | ProcessPoolExecutor

    def __init__(self, max_workers: int=None, parent=None):
        QObject.__init__(self, parent=parent)
        n_cpu = psutil.cpu_count(logical=True)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)

    def handle_future_done(self, f: Future):
        if f.cancelled():
            return
        self.job_finished.emit()
        try:
            res = f.result()
            if isinstance(res, list):
                if all(isinstance(r, Result) for r in res):
                    for r in res:
                        self.progress.emit(-1)
                        if r.status == ResultStatus.SUCCESS:
                            self.result.emit(r.value)
                        else:
                            self.error.emit(r.value)
                            break
                    return
            self.result.emit(res)
            self.progress.emit(-1)
        except BaseException as e:
            self.error.emit(e)

    def schedule(self, fn: Callable[P, R], args: tuple, kwargs: dict, timeout: float=None) -> Future[R]:
        f = self.pool.submit(fn, *args, **kwargs)

        f.add_done_callback(self.handle_future_done)
        return f

    def map(self, fn: Callable[..., R], *iterables: Iterable, timeout: float | None=None, chunksize: int=1) -> CombinedFuture[Iterable[R]]:
        if chunksize < 1:
            raise ValueError('chunksize must be >= 1')
        futures = [self.schedule(process_chunk, (fn, chunk), {})
                   for chunk in iter_chunks(zip(*iterables), chunksize)]
        return CombinedFuture(futures)

    def stop(self):
        self.pool.shutdown(cancel_futures=True)

    def close(self):
        self.pool.shutdown(cancel_futures=False)

    def join(self, timeout: int=None):
        self.pool.shutdown(wait=True)

    @property
    def active(self) -> bool:
        raise NotImplementedError

class QThreadPoolExecutor(QPoolExecutor):

    def __init__(self, max_workers: int=None, parent=None):
        super().__init__(max_workers=max_workers, parent=parent)
        self.pool = ThreadPoolExecutor(self.max_workers)

    @property
    def active(self) -> bool:
        return not self.pool._shutdown

class QProcessPoolExecutor(QPoolExecutor):
    def __init__(self, max_workers: int=None, parent=None):
        super().__init__(max_workers=max_workers, parent=parent)
        self.pool = ProcessPoolExecutor(self.max_workers)

    @property
    def active(self) -> bool:
        with self.pool._shutdown_lock:
            return not self.pool._shutdown_thread


# NOTE: This must have a QEventLoop already running or the signals won't work
class QJobPool(JobPool, QObject):
    progress = Signal(int)
    error = Signal(BaseException)
    job_finished = Signal()
    result = Signal(object)

    def __init__(self, max_workers: int | None=None, close_timeout: int | None=None, parent=None):
        QObject.__init__(self, parent=parent)  # Initialize QObject
        JobPool.__init__(self, max_workers=max_workers, use_logical=True, close_timeout=close_timeout)

    def _setup_signals(self):
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

class QThreadJobPool(QJobPool):
    def __init__(self, max_workers: int | None=None, close_timeout: int | None=None, parent=None):
        super().__init__(max_workers=max_workers, close_timeout=close_timeout, parent=parent)
        self.executor = QThreadPoolExecutor(max_workers=self.max_workers, parent=self)
        self._setup_signals()

class QProcessJobPool(QJobPool):
    def __init__(self, max_workers: int | None=None, close_timeout: int | None=None, parent=None):
        super().__init__(max_workers=max_workers, close_timeout=close_timeout, parent=parent)
        self.executor = QProcessPoolExecutor(max_workers=self.max_workers, parent=self)
        self._setup_signals()
