import functools
import os
from pathlib import Path
import json
from typing import Callable, ParamSpec, TypeVar, Iterable, overload, Any, Type, Literal
from datetime import datetime
import logging
import numpy as np
import numpy.typing as npt
from kidpy import wait_for_free, wait_for_reply, kidpy
import redis
from PySide6.QtCore import QThread, Signal, QObject, QRunnable, QThreadPool, Qt, QPoint, QSize
from PySide6.QtWidgets import QLineEdit, QWidget, QLayout, QToolTip, QLabel
from PySide6.QtGui import QValidator
import time
from collections.abc import Mapping
import qtawesome as qta
import onrkidpy

IPV4_REGEX = r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$'
MAC_REGEX = r'^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$'

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
    updateProgress = Signal()
    started = Signal(str)
    finished = Signal(Any)
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
            res = self.func(*self.args, signal=self.updateProgress, **self.kwargs)
            self.finished.emit(res)
        except JobInterrupt as e:
            self.canceled.emit(e)
        #Notice this is the same thing you were doing in your progress() function


class JobQueue(QThreadPool):
    cancelAll = Signal()

    def __init__(self, max_threads: int = 0, parent: QObject | None=None):
        super().__init__(parent)
        self.setMaxThreadCount(max_threads)
        self.queue: list[tuple[Job, bool]] = []
        self.results = []
    
    def __len__(self) -> int:
        return len(self.queue)
    
    @overload
    def add_job(self, func: Callable[P, None], *args: P.args, **kwargs: P.kwargs): ...
    
    @overload
    def add_job(self, job: Job): ...

    def add_job(self, arg: Job | Callable[P, None], *args: P.args, use_main_thread=False, **kwargs: P.kwargs):
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
                QThreadPool.globalInstance().start(job)
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
                QThreadPool.globalInstance().start(job)
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


def get_lineEdit_text(line_edit: QLineEdit) -> str:
    val = line_edit.text()
    if val == '':
        val = line_edit.placeholderText()
    return val

def get_num_value(line_edit: QLineEdit, num_type: Type[Number]=float) -> Number:
    """Get the value from a QLineEdit and convert to a number."""
    val = get_lineEdit_text(line_edit)
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

def analog_to_digital(a: int, min: float, max: float, bits: int) -> int:
    """Convert an analog number to digital.
    
    Needed because DAQ inputs/outputs have different resolutions.

    Arguments:
        a (int): The analog number
        min (float): The minimum possible digital number
        max (float): The maximum possible digital number
        bits (int): The number of bits for representing the numbers.
    Returns:
        (int): The digital equivalent number.
    """
    vals = np.linspace(min, max, (2**bits) - 1)
    d = int(np.argmin(np.abs(vals - a)))
    # TODO: This method is only needed for windows? Email Dan
    d = a
    return d

def digital_to_analog(d: int, min: float, max: float, bits: int) -> int:
    """Convert a digital number to analog.
    
    Needed because DAQ inputs/outputs have different resolutions.

    Arguments:
        d (int): The digital number
        min (float): The minimum possible analog number
        max (float): The maximum possible analog number
        bits (int): The number of bits for representing the numbers.
    Returns:
        (int): The analog equivalent number.
    """
    vals = np.linspace(min, max, (2**bits) - 1)
    a = vals[d]
    return a

class SettingsError(Exception):
    def __init__(self, message: str):
        super().__init__("Error in settings file: " + message)
    

def convert_to_kidy_format(rfsoc_config: dict) -> dict:
    kidpy_config = {}
    kidpy_config['rfsoc_name'] = rfsoc_config['name']
    kidpy_config['bitstream'] = rfsoc_config['bitstream']
    kidpy_config['redis_ip'] = rfsoc_config['redis']['ip']
    kidpy_config['redis_port'] = rfsoc_config['redis']['port']
    kidpy_config['ethernet_config'] = {
        'udp_data_a_sourceip': rfsoc_config['channel1']['sourceip'],
        'udp_data_b_sourceip': rfsoc_config['channel2']['sourceip'],
        'udp_data_a_destip': rfsoc_config['channel1']['destip'],
        'udp_data_b_destip': rfsoc_config['channel2']['destip'],
        'port_a': rfsoc_config['channel1']['port'],
        'port_b': rfsoc_config['channel2']['port'],
    }
    return {'rfsoc_config': kidpy_config}


def recursive_update(d: Mapping, u: Mapping):
    for k, v in u.items():
        if isinstance(v, Mapping):
            d[k] = recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class PathValidator(QValidator):

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent=parent)
    
    @ensure_path(1)
    def validate(self, text: str, pos) -> QValidator.State:
        if not Path.is_file(text):
            return QValidator.State.Intermediate
        return QValidator.State.Acceptable

   
# From onrkidpy.py
def get_yymmdd():
    """Return today's date string in YYYYMMDD format."""
    return datetime.today().strftime('%Y%m%d')

def get_chanmask(chanmask_file=''):

    if chanmask_file=='':
        chanmask_file = '/home/onrkids/onrkidpy/params/chanmask.npy'
    chanmask = np.load(chanmask_file)
    return chanmask

FileType = Literal['lo', 'tonelist', 'tod', 'azel', 'attenuator']

def get_filename(base_dir: Path=Path('/data/'), file_type='lo', chan_name="", attenuation=0.):
    #see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = base_dir / yymmdd
    date_folder.mkdir(exist_ok=True)
    if chan_name:
        chan_name += '_' 
    date_folder = date_folder / (yymmdd + '_')

    #provide the name of the file
    match file_type.lower():
        case 'lo' | 'tonelist':
            hour = float(datetime.now().strftime('%H')) \
                + float(datetime.now().strftime('%M'))/60. \
                + float(datetime.now().strftime('%S'))/3600.
            hour_str = f'hour{hour:04.4f}'.replace('.', 'p')
            match file_type.lower():
                case 'lo':
                    savefile = date_folder / f"{chan_name}LO_Sweep_{hour_str}"
                case 'tonelist':
                    savefile = date_folder / f"{chan_name}tone_list_{hour_str}"
        case 'tod' | 'azel':
            this_dir_files = list(date_folder.glob(f'*TOD_set*'))
            if not this_dir_files:
                setnum = 1001
            else:
                this_dir_files.sort()
                offset = 1 if file_type == 'tod' else 0
                setnum = int(this_dir_files[-1].name[-7:-3]) + offset
            savefile = date_folder / f'chan_name{file_type.upper()}_set{setnum}'
        case 'attenuator':
            savefile = date_folder / f"{chan_name}attenuator{attenuation:02d}"
        case _:
            raise ValueError(f'Invalid file type: "{file_type.lower()}"; must be one of {FileType}')
    return savefile


if __name__ == '__main__':
    def test_fun():
        for i in range(5):
            print(i)
    
    add_callbacks(lambda: print('hello'))(test_fun)()

