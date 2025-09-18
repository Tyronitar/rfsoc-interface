import logging

import functools
import os
from pathlib import Path
import json
from enum import IntEnum, StrEnum
from dataclasses import dataclass
from typing import Callable, ParamSpec, TypeVar, Iterable, overload, Any, Literal
from datetime import datetime
import logging
from concurrent.futures import Future, CancelledError
import itertools
from itertools import islice
import copy
import sys
from multiprocessing.connection import Connection

import numpy as np
import numpy.typing as npt
from scipy import ndimage
from scipy.signal import sosfilt, sosfilt_zi, cheby1
import redis

import time
from collections.abc import Mapping

_tele_logger = logging.getLogger('telescopeControl')

IPV4_REGEX = r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$'
MAC_REGEX = r'^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$'

BAD_RFSOC_TONE_START_INDEX = 8  # First 8 ones are bad...

GLOBAL_SETTINGS_PATH = Path('/etc/rfsocinterface/settings.json')
USER_SETTINGS_PATH = Path('~/.rfsocinterface/settings.json')

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)
# Number = TypeVar('Number', int, float, complex, bytes)
FileType = Literal['lo', 'tonelist', 'tod', 'azel', 'attenuator']

GAUSSIAN_SIGMA = (0.5, 0.33)
BUTTER_ORDER = 6
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


# From onrkidpy.py
def get_yymmdd():
    """Return today's date string in YYYYMMDD format."""
    return datetime.today().strftime('%Y%m%d')


def get_chanmask(chanmask_file=''):

    if chanmask_file=='':
        chanmask_file = '/home/onrkids/onrkidpy/params/chanmask.npy'
    chanmask = np.load(chanmask_file)
    return chanmask


def get_filename(base_dir: Path=Path('/data/'), file_type='lo', chan_name='', attenuation=0., mkdir: bool=False):
    #see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = base_dir / yymmdd
    if mkdir:
        date_folder.mkdir(0o666, exist_ok=True)

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
                setnums = [f.name[-7:-3] for f in this_dir_files]
                setnums.sort()
                setnum = int(setnums[-1]) + offset
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
        if not conn.poll(1e-4):
            continue
        response, *data = conn.recv()
        _tele_logger.debug(f'{id} got response: "{response}", data: {data}')
        if response.lower() == f'{command}':
            break
        elif response.lower() == 'err':
            raise RuntimeError(f'{err_msg}: {data}')


#
# Scipy signal processing utils
#
def sosfilt_in_chunks(sos, x, n_chunks=1, zi=None, axis: int=-1, out: tuple[npt.NDArray, npt.NDArray] | None=None):
    """
    Apply a second-order section filter to data in chunks.
    
    Parameters:
    """
    do_return = True
    return_zi = False
    n_sections = sos.shape[0]
    zi_shape = list(x.shape)
    zi_shape[axis] = 2
    zi_shape = tuple([n_sections] + zi_shape)

    return_zi = zi is not None
    do_return = out is None

    if out is not None:
        if isinstance(out, tuple):
            if out[0].shape != x.shape:
                raise ValueError(f"Output array must have shape {x.shape}, but got {out[0].shape}.")
            if return_zi:
                if len(out) != 2:
                    raise ValueError("Output array must be a tuple of two arrays if zi is provided.")
                if out[1].shape != zi_shape:
                    print(f"zi_shape: {zi_shape}, out[1].shape: {out[1].shape}")
                    raise ValueError('Invalid zi output array shape. With axis=%r, an input with '
                                    'shape %r, and an sos array with %d sections, zi '
                                    'must have shape %r, got %r.' %
                                    (axis, x.shape, n_sections, zi_shape, out[1].shape))
        elif return_zi:
            raise ValueError("Output array must be a tuple of two arrays if zi is provided.")
        elif out.shape != x.shape:
            raise ValueError(f"Output array must have shape {x.shape}, but got {out.shape}.")
        else:  # Provided output array, and no zi provided
            out = (out, np.zeros(zi_shape))
    else:
        out = (np.empty_like(x), np.zeros(zi_shape))

    if zi is None:
        out[1][:] = np.zeros(zi_shape)
    elif zi.shape != zi_shape:
        raise ValueError('Invalid zi shape. With axis=%r, an input with '
                        'shape %r, and an sos array with %d sections, zi '
                        'must have shape %r, got %r.' %
                        (axis, x.shape, n_sections, zi_shape, zi.shape))
    else:
        out[1][:] = zi

    chunk_size = x.shape[axis] // n_chunks
    for i_chunk in range(n_chunks):
        start = i_chunk * chunk_size
        stop = (i_chunk + 1) * chunk_size

        # Account for rounding errors in the chunk size
        if i_chunk == n_chunks - 1:
            stop = x.shape[axis]

        chunk_slice = [slice(None)] * x.ndim
        chunk_slice[axis] = slice(start, stop)
        chunk_slice = tuple(chunk_slice)
        out[0][chunk_slice], out[1][:] = sosfilt(sos, x[chunk_slice], axis=axis, zi=out[1])
    
    if do_return and return_zi:
        return out
    elif do_return:
        return out[0]
    # if zi is not None:
    #     return out, zf
    # else:
    #     return out

def axis_slice(a, start=None, stop=None, step=None, axis=-1):
    """Take a slice along axis 'axis' from 'a'.

    Parameters
    ----------
    a : numpy.ndarray
        The array to be sliced.
    start, stop, step : int or None
        The slice parameters.
    axis : int, optional
        The axis of `a` to be sliced.

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.signal._arraytools import axis_slice
    >>> a = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    >>> axis_slice(a, start=0, stop=1, axis=1)
    array([[1],
           [4],
           [7]])
    >>> axis_slice(a, start=1, axis=0)
    array([[4, 5, 6],
           [7, 8, 9]])

    Notes
    -----
    The keyword arguments start, stop and step are used by calling
    slice(start, stop, step). This implies axis_slice() does not
    handle its arguments the exactly the same as indexing. To select
    a single index k, for example, use
        axis_slice(a, start=k, stop=k+1)
    In this case, the length of the axis 'axis' in the result will
    be 1; the trivial dimension is not removed. (Use numpy.squeeze()
    to remove trivial axes.)
    """
    a_slice = [slice(None)] * a.ndim
    a_slice[axis] = slice(start, stop, step)
    b = a[tuple(a_slice)]
    return b

def axis_reverse(a, axis=-1):
    """Reverse the 1-D slices of `a` along axis `axis`.

    Returns axis_slice(a, step=-1, axis=axis).
    """
    return axis_slice(a, step=-1, axis=axis)

def odd_ext(x, n, axis=-1):
    """
    Odd extension at the boundaries of an array

    Generate a new ndarray by making an odd extension of `x` along an axis.

    Parameters
    ----------
    x : ndarray
        The array to be extended.
    n : int
        The number of elements by which to extend `x` at each end of the axis.
    axis : int, optional
        The axis along which to extend `x`. Default is -1.

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.signal._arraytools import odd_ext
    >>> a = np.array([[1, 2, 3, 4, 5], [0, 1, 4, 9, 16]])
    >>> odd_ext(a, 2)
    array([[-1,  0,  1,  2,  3,  4,  5,  6,  7],
           [-4, -1,  0,  1,  4,  9, 16, 23, 28]])

    Odd extension is a "180 degree rotation" at the endpoints of the original
    array:

    >>> t = np.linspace(0, 1.5, 100)
    >>> a = 0.9 * np.sin(2 * np.pi * t**2)
    >>> b = odd_ext(a, 40)
    >>> import matplotlib.pyplot as plt
    >>> plt.plot(np.arange(-40, 140), b, 'b', lw=1, label='odd extension')
    >>> plt.plot(np.arange(100), a, 'r', lw=2, label='original')
    >>> plt.legend(loc='best')
    >>> plt.show()
    """
    if n < 1:
        return x
    if n > x.shape[axis] - 1:
        raise ValueError(("The extension length n (%d) is too big. " +
                         "It must not exceed x.shape[axis]-1, which is %d.")
                         % (n, x.shape[axis] - 1))
    left_end = axis_slice(x, start=0, stop=1, axis=axis)
    left_ext = axis_slice(x, start=n, stop=0, step=-1, axis=axis)
    right_end = axis_slice(x, start=-1, axis=axis)
    right_ext = axis_slice(x, start=-2, stop=-(n + 2), step=-1, axis=axis)
    ext = np.concatenate((2 * left_end - left_ext,
                          x,
                          2 * right_end - right_ext),
                         axis=axis)
    return ext

def _validate_pad(padlen, x, axis, ntaps):
    """Helper to validate padding for filtfilt"""

    if padlen is None:
        # Original padding; preserved for backwards compatibility.
        edge = ntaps * 3
    else:
        edge = padlen

    # x's 'axis' dimension must be bigger than edge.
    if x.shape[axis] <= edge:
        raise ValueError(
            f"The length of the input vector x must be greater than padlen, "
            f"which is {edge}."
        )

    if edge > 0:
        ext = odd_ext(x, edge, axis=axis)
    else:
        ext = x
    return edge, ext


def decimate_in_chunks(x: npt.NDArray, q: int, axis: int = -1, padlen: int | None=None, out: npt.NDArray | None=None) -> npt.NDArray:
    sos = cheby1(8, 0.05, 0.8 / q, output='sos')
    n_sections = sos.shape[0]
    do_return = False
    out_shape = list(x.shape)
    out_shape[axis] = x.shape[axis] // q
    out_shape = tuple(out_shape)

    # Handle output array
    if out is None:
        out = np.zeros(out_shape, dtype=x.dtype)
        do_return = True
    elif out.shape != out_shape:
        raise ValueError(
            f"Output array must have shape {out_shape}, "
            f"but got {out.shape}."
        )

    # NOTE: `y` and `ext` need to be stored in temporary arrays on disk.
    # Keeping them in memory is too large

    # `method` is "pad"...
    ntaps = 2 * n_sections + 1
    ntaps -= min((sos[:, 2] == 0).sum(), (sos[:, 5] == 0).sum())
    edge, ext = _validate_pad(padlen, x, axis,
                              ntaps=ntaps)
    
    y = np.zeros_like(ext)

    # Create zi
    zi = sosfilt_zi(sos)
    zi_shape = [1] * x.ndim
    zi_shape[axis] = 2
    zi.shape = [n_sections] + zi_shape

    # chunk_size = ext.shape[axis] // q

    # Forward pass...
    x0 = axis_slice(ext, stop=1, axis=axis)
    zf = x0 * zi
    sosfilt_in_chunks(sos, ext, n_chunks=q, zi=zf, axis=axis, out=(y, zf))
    # y, _ = sosfilt_in_chunks(sos, ext, n_chunks=q, zi=zi * x0, axis=axis)
    # for i_chunk in range(q):
    #     start = i_chunk * chunk_size
    #     stop = (i_chunk + 1) * chunk_size

    #     # Account for rounding errors in the chunk size
    #     if i_chunk == q - 1:
    #         stop = ext.shape[axis]

    #     chunk_slice = [slice(None)] * ext.ndim
    #     chunk_slice[axis] = slice(start, stop)
    #     chunk_slice = tuple(chunk_slice)
    #     y[chunk_slice], zf = sosfilt(sos, ext[chunk_slice], axis=axis, zi=zf)

    # Reverse pass...
    y0 = axis_slice(y, start=-1, axis=axis)
    zf = y0 * zi
    sosfilt_in_chunks(sos, axis_reverse(y, axis=axis), n_chunks=q, zi=zf, axis=axis, out=(axis_reverse(y, axis=axis), zf))
    # y = axis_reverse(z, axis=axis)
    # for i_chunk in range(q, 0, -1):
    #     start = i_chunk * chunk_size
    #     stop = (i_chunk - 1) * chunk_size

    #     # Account for rounding errors in the chunk size
    #     if i_chunk == q:
    #         start = y.shape[axis]

    #     chunk_slice = [slice(None)] * ext.ndim
    #     chunk_slice[axis] = slice(start, stop, -1)
    #     chunk_slice = tuple(chunk_slice)
    #     y[chunk_slice], zf = sosfilt(sos, y[chunk_slice], axis=axis, zi=zf)

    # Remove edge padding
    if edge > 0:
        y = axis_slice(y, start=edge, stop=-edge, axis=axis)
    if do_return:
        return axis_slice(y, step=q, axis=axis)
    else:
        out[...] = axis_slice(y, step=q, axis=axis)


if __name__ == '__main__':
    import timeit, functools
    from scipy.signal import decimate
    n = 100000000
    x = np.random.randn(n)
    q = 10
    # y = decimate(x, q)
    y = decimate_in_chunks(x, q)
    # y = np.zeros(n // q)
    # decimate_in_chunks(x, q, out=y)

    # n_repeats = 20
    # timer = timeit.Timer(functools.partial(decimate, x, q))
    # print(f'Time for SciPy decimate: {timer.timeit(n_repeats)}')

    # timer = timeit.Timer(functools.partial(decimate_in_chunks, x, q))
    # print(f'Time for decimate in chunks (no output array): {timer.timeit(n_repeats)}')

    # timer = timeit.Timer(functools.partial(decimate_in_chunks, x, q, out=y))
    # print(f'Time for decimate in chunks (with output array): {timer.timeit(n_repeats)}')
