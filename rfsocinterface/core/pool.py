"""Module for handling parallelization."""
from concurrent.futures import Future, as_completed, wait
from multiprocessing import Queue
from threading import Thread, Lock
from pebble import ProcessPool, ThreadPool, waitforthreads, MapFuture, ProcessMapFuture
from pebble.pool.base_pool import map_results
from abc import abstractmethod
from typing import Callable, Any, Iterable, Iterator
import time
import traceback
import sys

import psutil
from PySide6.QtCore import QThread, QThreadPool, Signal, QObject, QRunnable, QEventLoop
from PySide6.QtWidgets import QApplication
from rfsocinterface.core.utils import P, R, T

class JobPool:
    def __init__(self, max_workers: int | None=None, use_logical: bool=False):
        n_cpu = psutil.cpu_count(logical=use_logical)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.futures = []
        self.executor: ProcessPool | ThreadPool | QThreadJobPool = None

    def _unqueue_future(self, f: Future):
        self.futures.remove(f)
    
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
            timeout: float | None=None,
    ) -> MapFuture | ProcessMapFuture:
        """Apply `fn` to every item of `iterable` and return an iterator of the results.

        If additional iterable arguments are passed, `fn` must take that many
        arguments and is applied to the items from all iterables in parallel.

            Arguments:
                fn (Callable[..., R]): Function to execute
                *iterables (Iterable[Any]): Iterables for every positional argument to
                    pass to `fn`
                timeout (float): Maximum number of seconds to wait before aborting
                    execution. If None, then there is no time limit.

            Returns:
                (Iterator[R]): An iterator containig all calls to `fn`. Equivalent to the
                    output of `map(fn, *iterables)`.

            Raises:
                TimeoutError: If the execution didn't finish before the time limit.
            """
        f = self.executor.map(fn, *iterables, timeout=timeout)
        self.futures.append(f)
        f.add_done_callback(self._unqueue_future)
        return f
        # return self.starmap(fn, zip(iterable, *iterables, strict=False), done_callbacks=done_callbacks, ordered=ordered, timeout=timeout)

    def starmap(
            self,
            fn: Callable[..., R],
            iterable: Iterable[tuple],
            done_callbacks: list[Callable[[Future], None]]=[],
            ordered: bool=True,
            timeout: float | None=None,
    ) -> Iterator[Future[R]]:
        """Return an iterator containing the results of `fn` for every set of arguments.

            Arguments:
                fn (Callable[..., R]): Function to execute
                iterable (Iterable[tuple]): Tuples of positional arguments to pass to `fn`
                ordered (bool): Whether the output order should be the same. Defaults to
                    True.
                timeout (float): Maximum number of seconds to wait before aborting
                    execution. If None, then there is no time limit.
                done_callbacks (list[Callable[[Future], None]]): Callback functions
                    to be called when the future is finished. Defaults to [].

            Returns:
                (Iterator[R]): An iterator containig all calls to `fn`. Equivalent to the
                    output of `itertools.starmap(fn, iterable)`.

            Raises:
                TimeoutError: If the execution didn't finish before the time limit.
            """
        if timeout is not None:
            timer = time.monotonic
            end_time = timeout + timer()

        # futures: list[Future] | set[Future] = []
        if ordered:
            futures = [
                self.schedule(
                    fn,
                    *args,
                    done_callbacks=done_callbacks,
                )
            for args in iterable]
        else:
            futures = {
                self.schedule(
                    fn,
                    *args,
                    done_callbacks=done_callbacks,
                )
            for args in iterable}

        def result(future: Future, timeout: float | None=None):
            try:
                try:
                    return future.result(timeout)
                finally:
                    future.cancel()
            finally:
                del future

        # try:
        if isinstance(futures, list):
            futures.reverse()
            while futures:
                to = timeout if timeout is None else end_time - timer()
                yield result(futures.pop(), to)
        else:
            # assert isinstance(futures, set)  # So MyPy is happy
            to = timeout if timeout is None else end_time - timer()
            for f in as_completed(futures, to):
                futures.remove(f)
                yield result(f)
        # finally:
        #     while futures:
        #         futures.pop().cancel()
            
        # try:
        #     if ordered:
        #         assert isinstance(futures, list)  # So MyPy is happy

        #         futures.reverse()
        #         while futures:
        #             res = result(futures.pop()) if timeout is None else \
        #                 result(futures.pop(), end_time - timer())
        #             yield res
        #     else:
        #         assert isinstance(futures, set)  # So MyPy is happy

        #         iterator = as_completed(futures) if timeout is None else \
        #             as_completed(futures, end_time - timer())
        #         for f in iterator:
        #             futures.remove(f)
        #             yield result(f)
        # finally:
        #     while futures:
        #         futures.pop().cancel()
    
    def cancel_all(self) -> bool:
        """Cancel all currently running jobs.
        
        Returns:
            (bool): Whether all jobs were succesfully canceled.
        """
        all_canceled = True
        for f in self.futures:
            all_canceled |= self.cancel(f)
        return all_canceled
    
    def cancel(self, f: Future) -> bool:
        """Cancel a future."""
        return f.cancel()

    def shutdown(self, wait: bool=False):
        """Shutdown the executor and wait for all threads to finish."""
        self.executor.stop()
        if wait:
            self.executor.join()

    def stop(self):
        self.executor.stop()
        self.join()

    def join(self, timeout: float=None):
        self.executor.join(timeout=timeout)
    
    def close(self):
        self.executor.close()
        self.join()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        # if self.executor.active:
        self.close()

class ProcessJobPool(JobPool):

    def __init__(self, max_workers: int | None=None):
        super().__init__(max_workers=max_workers, use_logical=False)
        self.executor = ProcessPool(self.max_workers)
    

class ThreadJobPool(JobPool):

    def __init__(self, max_workers: int | None=None):
        super().__init__(max_workers=max_workers, use_logical=True)
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
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int)

class Worker(QRunnable):

    #This is the signal that will be emitted during the processing.
    #By including int as an argument, it lets the signal know to expect
    #an integer argument when emitting.

    #You can do any extra things in this init you need, but for this example
    #nothing else needs to be done expect call the super's init
    def __init__(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs):
        super().__init__(self)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        """Run the target function with the provided args and kwargs.

        Partially adapted from: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/
        """
        track_progress = self.kwargs.pop('track_progress')
        if track_progress:
            self.kwargs['progress_callback'] = self.signals.progress.emit
        try:
            res = self.func(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(res)
        finally:
            self.signals.finished.emit()


class QThreadPoolExecutor(QObject):
    progress = Signal(int)
    error = Signal(tuple)
    job_finished = Signal()

    def __init__(self, max_workers: int=None):
        QObject.__init__(self)
        n_cpu = psutil.cpu_count(logical=True)
        if max_workers is None:
            max_workers = n_cpu
        self.max_workers = min(max_workers, n_cpu)
        self.closed = False
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(self.max_workers)
        self.active_workers: list[Worker] = []
    
    @property
    def active(self) -> bool:
        return self.thread_pool.activeThreadCount() > 0
    
    def schedule(self, fn: Callable[P, R], args: tuple, kwargs: dict) -> Future[R]:
        if self.closed:
            raise RuntimeError('Attempted to schedule work to QThreadPoolExecutor that\'s already closed')
        f = Future()
        worker = Worker(fn, *args, **kwargs)

        # Connect all signals
        worker.signals.result.connect(f.set_result)
        worker.signals.finished.connect(self.job_finished.emit)
        worker.signals.error.connect(self.error.emit)
        worker.signals.progress.connect(self.progress.emit)

        self.active_workers.append(worker)
        self.thread_pool.start(worker)
        return f
    
    def map(self, fn: Callable[..., R], *iterables: Iterable, timeout: float | None=None) -> MapFuture:
        iters = list(iterables)
        track_progress = iters[0]
        all_args = zip(*iters[1:], strict=False)
        all_futures = [self.schedule(fn, args, {'track_progress': track_progress})
                       for args in zip(*iters[1:], strict=False)]
        return map_results(MapFuture(all_futures), timeout=timeout)
    
    def _consume_queue(self):
        self.thread_pool.clear()
    
    def stop(self):
        self._consume_queue()
    
    def join(self, timeout: int=None):
        if timeout is None:
            timeout = -1e-3
        print(int(timeout * 1000))
        if not self.thread_pool.waitForDone(int(timeout * 1000)):
            raise TimeoutError(f'Timeout {timeout} exceeded waiting for QThreadPoolExecutor to join')
    
    def close(self):
        self.closed = True


# NOTE: This must have a QEventLoop already running or the signals won't work
class QThreadJobPool(QObject, JobPool):
    progress = Signal(int)
    error = Signal(tuple)
    job_finished = Signal()

    def __init__(self, max_workers: int | None=None, track_progress: bool=False):
        QObject.__init__(self)  # Initialize QObject
        JobPool.__init__(self, max_workers=max_workers, use_logical=True)
        self.executor = QThreadPoolExecutor(max_workers=self.max_workers)
        self.executor.progress.connect(self.progress.emit)
        self.executor.error.connect(self.error.emit)
        self.executor.job_finished.connect(self.job_finished.emit)
        self.track_progress = track_progress

    def start_event_loop(self):
        self.event_loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

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
            timeout: float | None=None,
    ) -> MapFuture | ProcessMapFuture:
        return JobPool.map(self, fn, self.track_progress, *iterables, timeout=timeout)
    
    # def emit_result(self, future: Future):
    #     if not future.cancelled():
    #         self.result.emit(future.result())
    #         print(f'Emitted {future.result()}')
    
    def close(self):
        super().close()


def square(n: int) -> int:
    return n ** 2

def counting(n: int, progress_callback: Callable):
    if n == 7:
        raise ValueError('Fuck 7')
    progress_callback(1)
    return n

def handle_res(val: Any):
    print(val)

def print_future_result(f: Future):
    print(f.result())

def print_future_results(f: Future[Iterable]):
    print(list(f.result()))

count = 0
total = 10
def count_progress(i: int):
    global count
    count += i
    print(f'Progress: {100 * count / total:.2f}%')


if __name__ == '__main__':
    # TODO: Check that this actually works at all. It needs to have an event
    # loop for proper functioning...

    # app = QApplication()
    # with QThreadJobPool(max_workers=4, track_progress=True) as pool:
        # pool.result.connect(print)
        # pool.progress.connect(count_progress)
        # for i in range(total):
        #     f = pool.schedule(counting, i)
        # pool.progress.connect(count_progress)
        # future = pool.map(counting, range(total))
        # print(list(future.result()))
    # print('stall')
    with ProcessJobPool(max_workers=4) as pool:
        for i in range(total):
            f = pool.schedule(square, i, done_callbacks=[print_future_result])
        future = pool.map(square, range(total))
        print(list(future.result()))
    with ThreadJobPool(max_workers=4) as pool:
        for i in range(total):
            f = pool.schedule(square, i, done_callbacks=[print_future_result])
        future = pool.map(square, range(total))
        print(list(future.result()))
    # time.sleep(1)

    # print(pool.cancel_all())
    # pool.cancel(f)