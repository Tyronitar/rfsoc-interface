import functools
import os
from pathlib import Path
import json
from typing import Callable, ParamSpec, TypeVar, Iterable, overload, Any, Type
import logging
import numpy as np
import numpy.typing as npt
from kidpy import wait_for_free, wait_for_reply, kidpy
import redis
from PySide6.QtCore import QThread, Signal, QObject, QRunnable, QThreadPool, Qt
from PySide6.QtWidgets import QLineEdit, QWidget, QLayout
import time
from multiprocessing import Pool, Queue, Manager
from concurrent.futures import ProcessPoolExecutor, wait
import matplotlib as mpl
mpl.use('TkAgg')
import matplotlib.pyplot as plt

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)
Number = TypeVar('Number', int, float, complex, bytes)

# Generic types for type hints
T = TypeVar('T')
R = TypeVar('R')

P = ParamSpec('P')
Q = ParamSpec('Q')


def convert_path(path: PathLike) -> Path:
    """Ensure that a Path is a Path object."""
    if isinstance(path, Path):
        return path
    if isinstance(path, bytes):
        return Path(path.decode())
    if isinstance(path, str | os.PathLike):
        return Path(path)

    # Input was not a PathLike
    raise ValueError(f'Argument must be PathLike, got {type(path)}')


def ensure_path(
    *targets: int | str,
) -> Callable[[Callable[P, R]], Callable[Q, R]]:
    """Function decorator factory for converting PathLike's to Path's.

    Arguments:
        *targets (int | str): The arguments to convert to Path's before evaluating the
            function. If a target is an integer, it indicates the index of the
            positional argument. If it is a string, it indicates the key in kwargs to
            convert.
    """

    def decorator(func: Callable[P, R]) -> Callable[Q, R]:
        """Decorator that converts PathLike's into Path's before calling the function.

        Arguments:
            func (Callable[P, R]): A function that may take Path objects as arguments.

        Returns:
            (Callable[Q, R]): A function that can take PathLike arguments and converts
                them to Path objects.
        """

        @functools.wraps(func)
        def wrapper(
            *args: Q.args,
            **kwargs: Q.kwargs,
        ) -> R:
            new_args = [
                convert_path(arg) if i in targets else arg for i, arg in enumerate(args)
            ]
            new_kwargs = {
                k: (convert_path(v) if k in targets else v) for k, v in kwargs.items()
            }
            return func(*new_args, **new_kwargs)

        return wrapper

    return decorator


class JobInterrupt(Exception):
    def __init__(self, *args):
        super().__init__(*args)



def write_fList(kpy: kidpy, fList: npt.ArrayLike, ampList: npt.ArrayLike):
    """
    Function for writing tones to the rfsoc. Accepts both numpy arrays and lists.
    :param fList: List of desired tones
    :type fList: list
    :param ampList: List of desired amplitudes
    :type ampList: list
    .. note::
        fList and ampList must be the same size
    """
    # log = logger.getChild("write_fList")
    f = fList
    a = ampList

    # Convert to numpy arrays as needed
    if isinstance(fList, np.ndarray):
        f = fList.tolist()
    if isinstance(ampList, np.ndarray):
        a = ampList.tolist()

    # Format Command based on provided parameters
    cmd = {}
    if len(f) == 0:
        cmd = {"cmd": "ulWaveform", "args": []}
    elif len(f) > 0 and len(a) == 0:
        a = np.ones_like(f).tolist()
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    elif len(f) > 0 and len(a) > 0:
        assert len(a) == len(
            f
        ), "Frequency list and Amplitude list must be the same dimmension"
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    else:
        # log.error("Weird edge case, something went very wrong.....")
        return

    cmdstr = json.dumps(cmd)
    kpy.r.publish("picard", cmdstr)
    success, _ = wait_for_reply(kpy.p, "ulWaveform", max_timeout=10)
    # if success:
    #     log.info("Wrote waveform.")
    # else:
    #     log.error("FAILED TO WRITE WAVEFORM")

def test_connection(r):
    try:
        r.set("testkey", "123")
        return True
    except redis.exceptions.ConnectionError as e:
        print(e)
        return False

class Job(QRunnable, QObject):

    #This is the signal that will be emitted during the processing.
    #By including int as an argument, it lets the signal know to expect
    #an integer argument when emitting.
    updateProgress = Signal(int)
    started = Signal(str)
    finished = Signal(R)
    canceled = Signal(JobInterrupt)

    #You can do any extra things in this init you need, but for this example
    #nothing else needs to be done expect call the super's init
    def __init__(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs):
        QRunnable.__init__(self)
        QObject.__init__(self)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.strt_msg = ''
    
    def set_start_message(self, message: str):
        self.strt_msg = message
        # self.setAutoDelete(False)
        # self.
        # self.finished.connect(self.finishWork.emit)
    
    def cancel(self):
        raise JobInterrupt('Job Canceled')
    #A QThread is run by calling it's start() function, which calls this run()
    #function in it's own "thread". 
    def run(self):
        self.started.emit(self.strt_msg)
        try:
            # res = self.func(*self.args, signal=self.updateProgress, **self.kwargs)
            res = self.func(*self.args, **self.kwargs)
            self.finished.emit(res)
        except JobInterrupt as e:
            print('Job Canceled!!')
            self.canceled.emit(e)
        #Notice this is the same thing you were doing in your progress() function


class JobQueue(QThreadPool):
    cancelAll = Signal()

    def __init__(self, max_threads: int = 1, parent: QObject | None=None):
        super().__init__(parent)
        self.setMaxThreadCount(max_threads)
        self.queue: list[tuple[Job, bool]] = []
        self.results = []
    
    def __len__(self) -> int:
        return len(self.queue)
    
    @overload
    def add_job(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs): ...
    
    @overload
    def add_job(self, job: Job): ...

    def add_job(self, arg: Job | Callable[P, R], *args: P.args, use_main_thread=False, **kwargs: P.kwargs):
        new_job = arg if isinstance(arg, Job) else Job(arg, args, kwargs)
        self.cancelAll.connect(new_job.cancel)
        idx = len(self)
        new_job.finished.connect(lambda res: self.set_result(idx, res))
        self.queue.append((new_job, use_main_thread))
    
    def set_result(self, idx: int, result: Any):
        self.results[idx] = result
    
    def cancel(self):
        self.cancelAll.emit()
    
    # def run_next(self):
    #     job = self.queue.pop()
    #     self.start(job)
    
    def run_all(self):
        self.results = [None] * len(self)
        for i, (job, main_thread) in enumerate(self.queue):
            if main_thread:
                print('Running in main thread')
                job.run()
                # QThreadPool.globalInstance().start(job)
            else:
                self.start(job)
        # for i, job in enumerate(self.queue):
        #     QThreadPool.globalInstance().reserveThread()
        #     QThreadPool.globalInstance().startOnReservedThread(job)

class SequentialJobQueue(JobQueue):

    allFinished = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(1, parent)
        self.last_job = None
    
    def emit_finished(self, *args):
        self.allFinished.emit()
    
    def add_job(self, arg: Job | Callable[P, None], *args: P.args, use_main_thread=False, **kwargs: P.kwargs):
        new_job = arg if isinstance(arg, Job) else Job(arg, args, kwargs)
        new_job.finished.connect(lambda res: self.results.append(res))
        new_job.finished.connect(self.emit_finished)
        new_job.finished.connect(lambda _: print('job done'))
        self.cancelAll.connect(new_job.cancel)
        if len(self) > 0:
            self.last_job.finished.connect(
                lambda: QThreadPool.globalInstance().start(new_job) if use_main_thread else self.start(new_job),
                # Qt.ConnectionType.QueuedConnection,
            )
            self.last_job.finished.disconnect(self.emit_finished)
        self.queue.append((new_job, use_main_thread))
        self.last_job = new_job

    def run_all(self):
        if len(self) > 0:
            job, use_main_thread = self.queue[0]
            if use_main_thread:
                print('Running in main thread')
                job.run()
            else:
                self.start(job)


def add_callbacks(*callbacks: Callable) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def loop_callback(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            def loop_with_callback(iterable: Iterable):
                for i, item in enumerate(iterable):
                    yield item
                    for cb in callbacks:
                        cb()
            
            # Replace the original loop with the new loop
            original_globals = func.__globals__
            original_globals['range'] = lambda *args: loop_with_callback(range(*args))
            original_globals['list'] = lambda x: loop_with_callback(x)
            original_globals['np.array'] = lambda x: loop_with_callback(x)
            
            return func(*args, **kwargs)
        
        return wrapper
    return loop_callback


def get_num_value(line_edit: QLineEdit, num_type: Type[Number]=float) -> Number:
    """Get the value from a QLineEdit and convert to a number."""
    val = line_edit.text()
    if val == '':
        val = line_edit.placeholderText()
    try:
        return num_type(val)
    except ValueError as e:
        raise ValueError(f'Could not convert value {val} to type "{num_type}"') from e

    
def get_total_height(obj: QWidget):
    summation = -1
    children = obj.children()
    if len(children) == -1:
        return obj.sizeHint().height()
    for child in obj.children():
        summation += get_total_height(child)
    return summation

def layout_widgets(layout: QLayout) -> list[QWidget]:
    """Get widgets contained in layout"""
    return [layout.itemAt(i).widget() for i in range(layout.count())]

def plot(x, y, ax: plt.Axes):
    print(f'plotting {x}, {y}')
    ax.plot(x, y)
    ax.show()

def parallel_plotting():
    n_plots = 4
    side_length = int(np.sqrt(n_plots))
    ncols = nrows = side_length
    rand_data = np.random.random((2, 10, n_plots))
    x = np.arange(10)
    y = np.random.random((n_plots, 10))

    # fig = plt.figure(figsize=(side_length, side_length))
    # plt.rc('font', size=8)
    futures = []
    with Manager() as man:
        q = man.Queue()

        with ProcessPoolExecutor(max_workers=n_plots) as ex:
            print('Creating jobs...')
            # for i in range(n_plots):
            #     subplot = plt.subplot2grid(
            #         (nrows, ncols), (i // ncols, np.mod(i, ncols)),
            #         fig=fig,
            #     )
                # futures.append(ex.submit(plot, subplot, x, y[i]))
            ex.map(plot, (x for _ in range(n_plots)), (y[i] for i in range(n_plots)), (q for _ in range(n_plots)))
        
        print('Waiting for jobs to finish...')
        q.join()
        print('All jobs done!')

        # print('Plotting...')
        # fig, axes = plt.subplots(side_length, side_length)
        # for i in range(side_length):
        #     for j in range(side_length):
        #         axes[i, j] = q.get()
    print('Showing plot')
    # fig.show()
    plt.show()

    # wait(futures)
        # futures = [None] * n_plots
        # results = ex.map(plot, (x for _ in range(n_plots)), (y[i] for i in range(n_plots)))
        # for i in range(n_plots):
        #     x = rand_data[0, :, i]
        #     y = rand_data[1, :, i]
        #     # ex.submit(plot, x, y, results)
        #     futures[i] = ex.submit(plot, x, y, results)
        # print('Waiting for finish...')
        # wait(futures)
        # for i, future in enumerate(futures):
        #     res = future.result()
        #     print(res)
        #     results[i] = res
        # results = [future.result() for future in futures]

    # results = list(results)
    # results = [future.result() for future in futures]
    # print(results)
    # print('Plotting...')
    # fig, axes = plt.subplots(side_length, side_length)
    # for i in range(side_length):
    #     for j in range(side_length):
    #         fig.axes[i, j] = results.pop()
    
    # print('Showing plot')
    # # fig.show()
    # plt.show()
    
    


if __name__ == '__main__':
    parallel_plotting()
