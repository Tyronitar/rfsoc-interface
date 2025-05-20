import functools
import os
from pathlib import Path
import json
from enum import IntEnum, StrEnum
from dataclasses import dataclass
from typing import Callable, ParamSpec, TypeVar, Iterable, overload, Any, Type, Literal
from datetime import datetime
import logging
from concurrent.futures import Future, CancelledError
import itertools
from itertools import islice
from numbers import Number
import copy
import sys
from multiprocessing.connection import Connection

import numpy as np
import numpy.typing as npt
from scipy import ndimage
import redis
from PySide6.QtCore import QThread, Signal, QObject, QRunnable, QThreadPool, Qt, QPoint, QSize, QCoreApplication
from PySide6.QtWidgets import QLineEdit, QWidget, QLayout, QToolTip, QLabel
from PySide6.QtGui import QValidator

import time
from collections.abc import Mapping
import qtawesome as qta
import onrkidpy

IPV4_REGEX = r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$'
MAC_REGEX = r'^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$'
BAD_RFSOC_TONE_START_INDEX = 8  # First 8 ones are bad...

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)
# Number = TypeVar('Number', int, float, complex, bytes)
FileType = Literal['lo', 'tonelist', 'tod', 'azel', 'attenuator']

GAUSSIAN_SIGMA = (0.5, 0.33)
class TabName(StrEnum):
    """Possible tab names for the GUI."""
    INITIALIZATION = 'initialization'
    LOSWEEP = 'losweep'
    TELESCOPE = 'telescope'
    DATA = 'data'
    IMAGING = 'imaging'

# Generic types for type hints
T = TypeVar('T')
R = TypeVar('R')

P = ParamSpec('P')
Q = ParamSpec('Q')


# Useful Aliases
tr = QCoreApplication.translate


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


def get_lineEdit_text(line_edit: QLineEdit, use_placeholder_text: bool=False) -> str:
    val = line_edit.text()
    if val == '' and use_placeholder_text:
        val = line_edit.placeholderText()
    return val


def get_num_value(line_edit: QLineEdit, num_type: Type[Number]=float, use_placeholder_text: bool=False) -> Number:
    """Get the value from a QLineEdit and convert to a number."""
    val = get_lineEdit_text(line_edit, use_placeholder_text=use_placeholder_text)
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
    def validate(self, text: Path, pos) -> QValidator.State:
        if not text.is_file():
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


def get_filename(base_dir: Path=Path('/data/'), file_type='lo', chan_name='', attenuation=0.):
    #see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = base_dir / yymmdd
    date_folder.mkdir(exist_ok=True)

    #provide the name of the file
    match file_type.lower():
        case 'lo' | 'tonelist':
            hour = float(datetime.now().strftime('%H')) \
                + float(datetime.now().strftime('%M'))/60. \
                + float(datetime.now().strftime('%S'))/3600.
            hour_str = f'hour{hour:04.4f}'.replace('.', 'p')
            match file_type.lower():
                case 'lo':
                    strings = [yymmdd, chan_name, 'LO_Sweep', hour_str]
                case 'tonelist':
                    strings = [yymmdd, chan_name, 'tone_list', hour_str]
        case 'tod' | 'azel' | 'optcam':
            this_dir_files = list(date_folder.glob(f'*TOD_set*'))
            if not this_dir_files:
                setnum = 1001
            else:
                this_dir_files.sort()
                offset = 1 if file_type == 'tod' else 0
                setnum = int(this_dir_files[-1].name[-7:-3]) + offset
            if file_type.lower() == 'optcam':
                strings = [yymmdd, 'optcam', f'set{setnum}']
            else:
                strings = [yymmdd, chan_name, file_type.upper(), f'set{setnum}']
        case 'attenuator':
            strings = [yymmdd, chan_name, f'attenuator{attenuation:02d}']
        case _:
            raise ValueError(f'Invalid file type: "{file_type.lower()}"; must be one of {FileType}')
    return date_folder / '_'.join(filter(None, strings))

def cartesian(*arrays: npt.ArrayLike, out: npt.NDArray | None=None):
    """
    Generate a Cartesian product of input arrays.

    Code from: https://stackoverflow.com/a/1235363

    Parameters
    ----------
    arrays : list of array-like
        1-D arrays to form the Cartesian product of.
    out : ndarray
        Array to place the Cartesian product in.

    Returns
    -------
    out : ndarray
        2-D array of shape (M, len(arrays)) containing Cartesian products
        formed of input arrays.

    Examples
    --------
    >>> cartesian(([1, 2, 3], [4, 5], [6, 7]))
    array([[1, 4, 6],
           [1, 4, 7],
           [1, 5, 6],
           [1, 5, 7],
           [2, 4, 6],
           [2, 4, 7],
           [2, 5, 6],
           [2, 5, 7],
           [3, 4, 6],
           [3, 4, 7],
           [3, 5, 6],
           [3, 5, 7]])

    """
    arr = []
    for x in arrays:
        arr.append(np.asarray(x))
    # arrays = [np.asarray(x) for x in arrays]
    arrays = arr
    dtype = arrays[0].dtype

    n = np.prod([x.size for x in arrays])
    if out is None:
        out = np.zeros([n, len(arrays)], dtype=dtype)

    #m = n / arrays[0].size
    m = int(n / arrays[0].size)
    out[:,0] = np.repeat(arrays[0], m)
    if arrays[1:]:
        cartesian(*arrays[1:], out=out[0:m, 1:])
        for j in range(1, arrays[0].size):
        #for j in xrange(1, arrays[0].size):
            out[j*m:(j+1)*m, 1:] = out[0:m, 1:]
    return out

def ordinal(n: int) -> str:
    """Append the english ordinal suffix to an integer.
    
    From https://stackoverflow.com/a/20007730.
    """
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    return str(n) + suffix

#
# Utils for parallelized code
#

def print_future_result(f: Future):
    try:
        res = f.result()
        if isinstance(res, list) and isinstance(res[0], Result):
            print([r.value for r in res])
        elif isinstance(f, CombinedFuture):
            print(list(res))
        else:
            print(res)
    except CancelledError:
        return
    except BaseException as e:
        print(e)


# Code borrowed from the Pebble library: https://pypi.org/project/Pebble/
class ResultStatus(IntEnum):
    """Status of results of a function execution."""
    SUCCESS = 0
    FAILURE = 1
    ERROR = 2


@dataclass
class Result:
    """Result of a function execution."""
    status: ResultStatus
    value: Any


def batched(iterable, n):
    "Batch data into lists of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be >= 1')
    it = iter(iterable)
    while (batch := list(islice(it, n))):
        yield batch


def iter_chunks(iterable: iter, chunksize: int) -> iter:
    """Iterates over zipped iterables in chunks."""
    if sys.version_info < (3, 12):
        yield from batched(iterable, chunksize)
    else:
        yield from itertools.batched(iterable, chunksize)

# End Pebble code

class CombinedFuture(Future[Iterable[R]]):
    """Class representing the result of multiple function calls.

    It's a Future that returns an iterator over the results of each Future.
    """

    def __init__(self, futures: Iterable[Future[list[Result]]]):
        self._futures = list(futures)
        self._completed_futures = [False for _ in range(len(self))]
        self._results: list[list[Any]] = [[] for _ in range(len(self))]

        super().__init__()

        for future in self._futures:
            future.add_done_callback(self._future_completed_callback)
    
    def __len__(self) -> int:
        return len(self._futures)
    
    def cancel(self):
        all_cancelled = super().cancel()
        for future in self._futures:
            all_cancelled |= future.cancel()
        return all_cancelled

    def _future_completed_callback(self, future: Future[list[Result]]) -> None:

        if self.cancelled() or self.done():
            return

        id = self._futures.index(future)
        self._completed_futures[id] = True
        if future.cancelled():
            super().cancel()
            return
        
        res = future.result()
        for r in res:
            if r.status == ResultStatus.SUCCESS:
                self._results[id].append(r.value)
            else:
                self.set_exception(r.value)
                return

        if all(self._completed_futures):
            self._coallesce_results()

    def _coallesce_results(self):
        self._results = itertools.chain.from_iterable(self._results)
        self.set_result(self._results)

def gaussian_filter(x: npt.NDArray, sigma: tuple[float, float]) -> npt.NDArray:
    return ndimage.gaussian_filter(
        x,
        sigma,
        mode='reflect',
        truncate=1. / sigma[1],
    )

def wait_for_telescope_command(conn: Connection, id: str, command: str, err_msg: str=''):
    if not err_msg:
        err_msg = f'Error occured while waiting for command "{command}": '
    while True:
        response, *data = conn.recv()
        # print(f'{id} got response: "{response}", data: {data}')
        if response.lower() == f'{command}':
            break
        elif response.lower() == 'err':
            raise RuntimeError(f'{err_msg}: {data}')