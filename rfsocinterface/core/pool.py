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
from PySide6.QtCore import QThread, QThreadPool, Signal, QObject, QRunnable, QEventLoop, QMutex, QMutexLocker, QCoreApplication, QTimer, Qt
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


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Code from: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    '''
    finished = Signal()  # QtCore.Signal
    error = Signal(BaseException)
    result = Signal(object)
    progress = Signal(float)


class Worker(QRunnable):

    def __init__(self, future: Future, context: PoolContext, func: Callable[P, R], counter: list[int], mutex: QMutex, *args: P.args, parent=None, **kwargs: P.kwargs):
        super().__init__(self)
        # self.setAutoDelete(False)
        self.future = future
        self.context = context
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.counter = counter
        self.mutex = mutex
        self.signals = WorkerSignals(parent=parent)

        track_progress = self.kwargs.pop('track_progress')
        if track_progress:
            self.kwargs['progress_callback'] = self.emit_progress
    
    def emit_progress(self, n: int | None=None):
        if n is None:
            n = -1
        self.signals.progress.emit(n)
    
    def set_running_or_notify_cancel(self):
        if hasattr(self.future, 'map_future'):
            if not self.future.map_future.done():
                try:
                    self.future.map_future.set_running_or_notify_cancel()
                except RuntimeError:
                    pass

        try:
            self.future.set_running_or_notify_cancel()
        except RuntimeError:
            pass
    
    def check_cancelled(self):
        return self.future.cancelled()

    def run(self):
        """Run the target function with the provided args and kwargs.

        Partially adapted from: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/
        """

        print('start run')

        with QMutexLocker(self.mutex):
            self.counter[0] -= 1

        print(get_native_id(), self.context.status, self.counter)
        if not self.context.alive:
            print('Returning because context is not alive')
            return

        with QMutexLocker(self.mutex):
            self.counter[1] += 1

        print('start working')
        try:
            if self.check_cancelled():
                print('canceled')
                self.set_running_or_notify_cancel()
            else:
                    self.set_running_or_notify_cancel()
                    print('Executing function')
                    res = execute(self.func, *self.args, **self.kwargs)

                    print('assigning result')
                    if res.status == ResultStatus.SUCCESS:
                        print('Before emitting result')
                        self.signals.result.emit(res.value)
                        print('Before assigning result')
                        self.future.set_result(res.value)
                        print('After assigning result')
                    else:
                        print('Before emitting exception')
                        self.signals.error.emit(res.value)
                        print('Before assigning exception')
                        self.future.set_exception(res.value)
                        print('After assigning exception')
                    print('result assigned')
        finally:
            print('emitting finished signal')
            self.signals.finished.emit()

            print('done working')
            with QMutexLocker(self.mutex):
                self.counter[1] -= 1
                print('Decremented counter of active jobs')


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
    progress = Signal(float)
    error = Signal(tuple)
    job_finished = Signal()

    def __init__(self, max_workers: int=None, parent=None):
        QObject.__init__(self, parent=parent)
        n_cpu = psutil.cpu_count(logical=True)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.thread_pool = QThreadPool(parent=self)
        self.thread_pool.setMaxThreadCount(self.max_workers)
        self.task_counter = [0, 0]  # List used as a mutable counter
        self.mutex = QMutex()
        self._context = PoolContext(self.max_workers)
        self.workers: list[Worker] = []

    def handle_progress(self, n: float):
        # print(f'Handling progress {n}')
        self.progress.emit(n)
    
    def _start_pool(self):
        with self._context.status_mutex:
            if self._context.status == PoolStatus.CREATED:
                self._context.status = PoolStatus.RUNNING

    def _stop_pool(self):
        return
        # print('Deleted QThreadPool')
        # self.thread_pool.clear()
        # with QMutexLocker(self.mutex):
        #     self.task_counter[0] = 0
        #     self.task_counter[1] = 0
        # self.thread_pool.deleteLater()
        # # self.thread_pool = None
        # print('Deleted QThreadPool')
        # if self._pool_manager_loop is not None:
        #     self._pool_manager_loop.join()
        # self._pool_manager.stop()
    
    @property
    def active(self) -> bool:
        self._update_pool_status()
        return self._context.status in (PoolStatus.CLOSED, PoolStatus.RUNNING)
    
    def schedule(self, fn: Callable[P, R], args: tuple, kwargs: dict) -> Future[R]:
        self._check_pool_status()
        f = Future()
        worker = Worker(f, self._context, fn, self.task_counter, self.mutex, *args, parent=self, **kwargs)
        with QMutexLocker(self.mutex):
            self.task_counter[0] += 1

        # Connect all signals
        worker.signals.finished.connect(self.handle_job_finish)
        worker.signals.error.connect(self.handle_error)
        # worker.signals.progress.connect(self.progress.emit)
        worker.signals.progress.connect(self.handle_progress)
        worker.signals.result.connect(print)

        self.thread_pool.start(worker)
        return f
    
    def handle_job_finish(self):
        # QCoreApplication.processEvents()
        # worker.deleteLater()
        self.job_finished.emit()
    
    def handle_error(self, e: BaseException):
        self.error.emit(e)
    
    @property
    def queue_size(self) -> int:
        # with QMutexLocker(self.mutex):
            # print(f'Current counts: {self.task_counter[0]}, {self.thread_pool.activeThreadCount()}')
        return self.task_counter[0]
            # res = self.task_counter[0]
            # res = max(0, self.task_counter[0])
        # return res
    
    @property
    def active_jobs(self) -> int:
        # with QMutexLocker(self.mutex):
            # print(f'Current counts: {self.task_counter[0]}, {self.thread_pool.activeThreadCount()}')
        return self.task_counter[1]
        #     res = self.task_counter[1]
        # return res
    
    @property
    def unfinished_tasks(self) -> int:
        # with QMutexLocker(self.mutex):
        return self.task_counter[0] + self.task_counter[1]

    def map(self, fn: Callable[..., R], *iterables: Iterable, timeout: float | None=None, chunksize: int=1) -> MapFuture:
        self._check_pool_status()
        iters = list(iterables)
        track_progress = iters[0]
        kwargs = {'track_progress': track_progress}
        if chunksize < 1:
            raise ValueError("chunksize must be >= 1")
        futures = [self.schedule(process_chunk, (fn, chunk), kwargs)
                   for chunk in iter_chunks(zip(*iters[1:]), chunksize)]
        return map_results(MapFuture(futures), timeout=timeout)
    
    def _clear_queue(self):
        self.thread_pool.clear()
        print('Cleared thread pool')
        with QMutexLocker(self.mutex):
            self.task_counter[0] = 0
        print('Cleared task counter')

    def stop(self):
        with self._context.status_mutex:
            self._context.status = PoolStatus.STOPPED
        # self._clear_queue()
    
    def close(self):
        with self._context.status_mutex:
            self._context.status = PoolStatus.CLOSED
    
    def _wait_for_jobs(self):
        while self.active_jobs:
            # print(self.active_jobs, self.thread_pool.activeThreadCount())
            time.sleep(0.1)

    def _wait_queue_depletion(self, timeout: float | None=None):
        tick = time.time()
        while self.active:
            # print(self.active_jobs)
            # QApplication.processEvents()
            if timeout is not None and time.time() - tick > timeout:
                # print(2.1)
                raise TimeoutError("Tasks are still being executed")
            elif self.unfinished_tasks:
                # print(2.2)
                # QTimer.singleShot(100, lambda : self._wait_queue_depletion(timeout))
                time.sleep(0.1)
            else:
                # print(2.3)
                return

    def _check_pool_status(self):
        self._update_pool_status()

        if self._context.status == PoolStatus.ERROR:
            raise RuntimeError('Unexpected error within the Pool')
        elif self._context.status != PoolStatus.RUNNING:
            raise RuntimeError('The Pool is not active')

    def _update_pool_status(self):
        if self._context.status == PoolStatus.CREATED:
            self._start_pool()
    
    def join(self, timeout: int=None):
        if self._context.status == PoolStatus.RUNNING:
            # print(1)
            raise RuntimeError('The Pool is still running')
        if self._context.status == PoolStatus.CLOSED:
            # print(2)
            print('Waiting for jobs to finish...')
            self._wait_queue_depletion(timeout)
            print('...Done!')
            self.stop()
            self.join()
        else:
            # print(3)
            self._clear_queue()
            self._stop_pool()
    
    # def cancel(self):
    #     self._consume_queue()
    #     self.stop()
    #     self.join()
    

# NOTE: This must have a QEventLoop already running or the signals won't work
class QThreadJobPool(JobPool, QObject):
    progress = Signal(int)
    error = Signal(tuple)
    job_finished = Signal()

    def __init__(self, max_workers: int | None=None, track_progress: bool=False, close_timeout: int | None=None, parent=None):
        QObject.__init__(self, parent=parent)  # Initialize QObject
        JobPool.__init__(self, max_workers=max_workers, use_logical=True, close_timeout=close_timeout) 
        # QObject.__init__(self, parent=parent)  # Initialize QObject
        # if close_timeout is None:
        #     close_timeout = -1
        # JobPool.__init__(self, max_workers=max_workers, use_logical=True, close_timeout=close_timeout)
        self.executor = QThreadPoolExecutor(max_workers=self.max_workers, parent=self)
        self.executor.progress.connect(self.handle_progress)
        # self.executor.progress.connect(self.progress.emit)
        self.executor.error.connect(self.handle_error)
        self.executor.job_finished.connect(self.handle_job_finished)
        self.track_progress = track_progress
    
    def handle_progress(self, n: float):
        # print(f'Handling progress {n}')
        self.progress.emit(n)

    def handle_error(self, e: BaseException):
        self.error.emit(e)
    
    def handle_job_finished(self):
        self.job_finished.emit()

    def schedule(
            self,
            fn: Callable[P, R],
            *args: P.args,
            done_callbacks: list[Callable[[Future], None]]=[],
            **kwargs: P.kwargs,
    ) -> Future[R]:
        kwargs['track_progress'] = self.track_progress
        return JobPool.schedule(self, fn, *args, done_callbacks=done_callbacks, **kwargs)

    def map(
            self,
            fn: Callable[..., R],
            *iterables: Iterable[Any],
            done_callbacks: list[Callable[[Future], None]]=[],
            timeout: float | None=None,
            chunksize: int=1,
    ) -> MapFuture | ProcessMapFuture:
        return JobPool.map(
            self,
            fn,
            self.track_progress,
            *iterables,
            done_callbacks=done_callbacks,
            timeout=timeout,
            chunksize=chunksize,
        )
    
    # def cancel_all(self):
    #     print('Cancelling QThreadJobPool')
    #     JobPool.cancel_all(self)
    #     print('Cancelled all futures')
    #     self.shutdown(True)
    #     print('Succesfully shutdown pool')
