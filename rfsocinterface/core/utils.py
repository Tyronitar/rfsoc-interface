import logging

import functools
import pdb
import os
from pathlib import Path
import json
from enum import EnumMeta, IntEnum, StrEnum
from dataclasses import dataclass
from typing import Callable, ParamSpec, TypeVar, Iterable, overload, Any, Literal
from datetime import datetime
import logging
from concurrent.futures import Future, CancelledError, ProcessPoolExecutor
import itertools
from itertools import islice
import copy
import sys
from multiprocessing.connection import Connection
import stat
import subprocess
import git
from typing import Iterator
import warnings

import io
from copy import deepcopy
from PIL import Image
from functools import partial
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.figure import Figure
import h5py

import numpy as np
import numpy.typing as npt
from scipy import ndimage
from scipy.signal import sosfilt, sosfilt_zi, cheby1, group_delay, sos2tf
from scipy.signal import resample_poly
import redis

import time
from collections.abc import Mapping

DEFAULT_DATA_DIRECTORY = '/data'
DEFAULT_PARAMS_DIRECTORY = DEFAULT_DATA_DIRECTORY + '/params/'


_tele_logger = logging.getLogger('telescopeControl')

IPV4_REGEX = r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$'
MAC_REGEX = r'^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$'


GLOBAL_SETTINGS_PATH = Path('/etc/rfsocinterface/settings.json')
USER_SETTINGS_PATH = Path('~/.rfsocinterface/settings.json')

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)
# Number = TypeVar('Number', int, float, complex, bytes)
FileType = Literal['lo', 'tonelist', 'tod', 'azel', 'attenuator']
H5pyObject = TypeVar('H5pyObject', h5py.Dataset, h5py.Group)

GAUSSIAN_SIGMA = (0.5, 0.33)
BUTTER_ORDER = 2

# Generic types for type hints
T = TypeVar('T')
R = TypeVar('R')

P = ParamSpec('P')
Q = ParamSpec('Q')

PERMISSIONS_USR_RW = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
PERMISSIONS_ALL_RW = PERMISSIONS_USR_RW | stat.S_IWGRP | stat.S_IWOTH
PERMISSIONS_ALL_FULL = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | PERMISSIONS_ALL_RW

DEFAULT_CHUNK_SIZE = 100

class TabName(StrEnum):
    """Possible tab names for the GUI."""
    INITIALIZATION = 'initialization'
    LOSWEEP = 'losweep'
    TELESCOPE = 'telescope'
    DATA = 'data'
    IMAGING = 'imaging'

class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


def convert_path(path: PathLike) -> Path | None:
    """Ensure that a Path is a Path object."""
    if path is None:
        return path
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
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Function decorator factory for converting PathLike's to Path's.

    Arguments:
        *targets (int | str): The arguments to convert to Path's before evaluating the
            function. If a target is an integer, it indicates the index of the
            positional argument. If it is a string, it indicates the key in kwargs to
            convert.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
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

def get_git_hash() -> str:
    try:
        repo = git.Repo(search_parent_directories=True)
        return repo.head.object.hexsha
    except Exception:
        return "unknown"


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
        date_folder.mkdir(PERMISSIONS_ALL_FULL, exist_ok=True)

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

def pad_to_length(x: npt.NDArray, target_length: int, axis: int=-1, constant_values=0) -> npt.NDArray:
    """Pad an array with zeros along an axis to a target length.

    Parameters:
        x (npt.NDArray): The input array.
        target_length (int): The target length along the specified axis.
        axis (int): The axis along which to pad.

    Returns:
        npt.NDArray: The padded array.
    """
    pad_widths = [(0, 0)] * x.ndim
    pad_amount = target_length - x.shape[axis]
    if pad_amount < 0:
        raise ValueError(f'Target length {target_length} is less than current length {x.shape[axis]} along axis {axis}.')
    pad_widths[axis] = (0, pad_amount)
    return np.pad(x, pad_widths, mode='constant', constant_values=constant_values)


def list_datasets(group: h5py.Group, full_names: bool=False) -> list[tuple[str, h5py.Dataset]]:
    """Recursively list all datasets in the specified group."""
    datasets = []
    def search_fn(name: str, obj: H5pyObject):
        if isinstance(obj, h5py.Dataset):
            if full_names:
                datasets.append((obj.name, obj))
            else:
                datasets.append((name, obj))
    group.visititems(search_fn)
    return datasets


def search(src: h5py.Group, name: str, full_name: bool=True, exact_match: bool=False) -> tuple[str, H5pyObject] | None:
    """Search recursively through an HDF5 group for the specified name.
    
    This function will return the first object found whose name matches `name`.
    Returns `None` if no match is found.

    Arguments:
        src (h5py.Group): The group to search within.
        name (str): The target name to search for.
        full_name (bool): Whether to return the full name of the object. Defaults to True.
        exact_match (bool): Whether to only accept exact name matches. If False, this
            function will succeed if an object is found whose name contains `name`. 
            Defaults to False.

    
    Returns:
        obj_name (str): The name of the found object.
        obj (h5py.Group | h5py.Dataset): The object matching the search query.
    
    """
    def search_fn(obj_name: str, obj: H5pyObject):
        success = name == obj_name if exact_match else name in obj_name
        if success:
            if full_name:
                return obj.name, obj
            return obj_name, obj
    return src.visititems(search_fn)

#
# Chunked array handling utils
#
def compute_chunk_shape(data_shape: tuple[int, ...], dtype_size: int, target_mb: float=4, max_chunk_size: int=None):
    """Compute the chunk shape to have the target chunk size in MB.
    
    Arguments:
        data_shape (tuple[int, ...]): The shape of the data excluding the chunked dimension
    
    """

    target_bytes = target_mb * 1024 * 1024
    time_chunk = target_bytes // (np.prod(data_shape) * dtype_size)
    if max_chunk_size is not None:
        time_chunk = min(time_chunk, max_chunk_size)

    return (*data_shape, int(time_chunk))


def chunked_downsample(
    dset: h5py.Dataset,
    out_dset: h5py.Dataset,
    q: int,
    chunk_size: int,
    axis: int=-1,
    use_filter: bool=True,
):

    overlap = 32 * q
    N = dset.shape[axis]

    out_index = 0
    downsampled_equiv = lambda x: int((x + q - 1) / q)

    for start in range(0, N, chunk_size):
        if use_filter:
            read_start = max(0, start - overlap)
            read_stop = min(N, start + chunk_size + overlap)

            chunk = axis_slice(dset, start=read_start, stop=read_stop, axis=axis)

            dec = resample_poly(chunk, up=1, down=q, axis=axis)
        else:
            read_start = max(0, start)
            # read_start = int(q * np.ceil(start / q))  # Start reading at multiple of q
            read_stop = min(N, start + chunk_size)
            chunk = axis_slice(dset, start=read_start, stop=read_stop, axis=axis)
            # dec = axis_slice(chunk, step=q, axis=axis)
            dec_start = int(q * np.ceil(start / q)) - start  # Make sure we start on a multiple of q
            dec = axis_slice(chunk, start=dec_start, step=q, axis=axis)

        valid_start = downsampled_equiv(start - read_start)
        valid_stop = valid_start + min(downsampled_equiv(min(chunk_size, N - start)), out_dset.shape[axis] - out_index)

        valid = axis_slice(dec, start=valid_start, stop=valid_stop, axis=axis)

        write_slice = get_axis_slice(out_dset, start=out_index, stop=out_index+valid.shape[axis], axis=axis)
        out_dset[write_slice] = valid

        out_index += valid.shape[axis]

def build_interp_map(x: npt.ArrayLike, x_new: npt.ArrayLike):
    """Compute the indices and wieghts to interpolate x_new to x."""

    idx = np.searchsorted(x_new, x) - 1
    idx = np.clip(idx, 0, len(x_new) - 2)

    t0 = x_new[idx]
    t1 = x_new[idx + 1]

    w = (x - t0) / (t1 - t0)

    return idx, w

def apply_interp(y: npt.ArrayLike, idx: int, w: float):
    return (1 - w) * y[idx] + w * y[idx + 1]





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

def get_axis_slice(a, start=None, stop=None, step=None, axis: int | Iterable[int]=-1) -> tuple[slice, ...]:
    """Return the slice to use in order to slice along axis 'axis' from 'a'.

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
    if isinstance(axis, Iterable):
        if start is None:
            start = [None for _ in range(len(axis))]
        if stop is None:
            stop = [None for _ in range(len(axis))]
        if step is None:
            step = [None for _ in range(len(axis))]
        for ax in axis:
            a_slice[ax] = slice(start[ax], stop[ax], step[ax])
    else:
        a_slice[axis] = slice(start, stop, step)
    return tuple(a_slice)


def axis_slice(a, start=None, stop=None, step=None, axis=-1, direct_read: bool=False) -> npt.NDArray:
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
    a_slice = get_axis_slice(a, start, stop, step, axis)
    if direct_read:
        buf_shape = list(a.shape)
        start = 0 if start is None else start
        stop = buf_shape[axis] if stop is None else stop
        step = 1 if step is None else step
        buf_shape[axis] = np.ceil((stop - start) / step).astype(int)
        buf = np.empty(buf_shape)
        h5py.Dataset.read_direct(a, buf, source_sel=a_slice)
        return buf
    return a[a_slice]


def axis_index(a: npt.NDArray, indices: npt.ArrayLike | tuple[npt.ArrayLike, ...], axis: int | tuple[int, ...]=-1):
    """Index `a` along axis `axis` with `indices`.

    Parameters
    ----------
    a : numpy.ndarray
        The array to be indexed.
    indices : array-like
        The indices to use for indexing.
    axis : int, optional
        The axis of `a` to be indexed.

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.signal._arraytools import axis_index
    >>> a = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    >>> axis_index(a, [0, 2], axis=1)
    array([[1, 3],
           [4, 6],
           [7, 9]])
    >>> axis_index(a, [1, 2], axis=0)
    array([[4, 5, 6],
           [7, 8, 9]])
    """
    if isinstance(axis, tuple):
        if len(indices) != len(axis):
            raise ValueError("If axis is a tuple, indices must be a tuple of the same length.")
    a_index = [slice(None)] * a.ndim
    if isinstance(axis, tuple):
        for i, ax in enumerate(axis):
            a_index[ax] = indices[i]
    else:
        a_index[axis] = indices
    b = a[tuple(a_index)]
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
    # y0 = axis_slice(y, start=-1, axis=axis)
    # zf = y0 * zi
    # sosfilt_in_chunks(sos, axis_reverse(y, axis=axis), n_chunks=q, zi=zf, axis=axis, out=(axis_reverse(y, axis=axis), zf))
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

def new_decimate_in_chunks(dset: h5py.Dataset, out_dset, q: int, axis=-1, chunk_shape=None):
    N = dset.shape[axis]

    if chunk_shape is None:
        chunk_shape = dset.chunks
    chunk_size = chunk_shape[axis]
    if q == 1:
        for start in range(0, N, chunk_size):
            stop = min(start + chunk_size, N)
            out_sl = get_axis_slice(out_dset, start=start, stop=stop, axis=axis)
            out_dset[out_sl] = axis_slice(dset, start, stop, axis=axis)
        return

    # Create buffer for storing chunks
    chunk = np.empty(chunk_shape, dtype=dset.dtype)
    y = np.empty_like(chunk)

    # Copmpute values to account for phase lag from the filter
    wc = 0.8 / q
    sos = cheby1(8, 0.05, wc, output="sos")
    b, a = sos2tf(sos)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', r'^The filter\'s denominator')
        w, gd = group_delay((b, a))
    passband = w <= wc * np.pi
    gd_passband = gd[passband]
    delay = int(np.ceil(np.median(gd_passband)))
    delay_out = int(np.round(delay / q))

    n_sections = sos.shape[0]

    # initialize filter state
    zi = sosfilt_zi(sos)

    zi_shape = [1] * dset.ndim
    zi_shape[axis] = 2
    zi = zi.reshape((n_sections, *zi_shape))
    x0 = axis_slice(dset, stop=1, axis=axis)
    zi = x0 * zi


    out_pos = 0
    out_pos -= delay_out

    for start in range(0, N, chunk_size):

        stop = min(start + chunk_size, N)
        if stop - start < chunk.shape[axis]:
            shape = list(dset.chunks)
            shape[axis] = stop - start
            chunk = np.empty(shape, dtype=dset.dtype)
            y = np.empty_like(chunk)

        chunk[:] = axis_slice(dset, start, stop, axis=axis)

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', r'^Invalid value encountered in')
            y[:], zi = sosfilt(sos, chunk, axis=axis, zi=zi)

        # decimate
        dec_start = int(q * np.ceil(start / q)) - start  # Make sure we start on a multiple of q
        dec = axis_slice(y, start=dec_start, step=q, axis=axis)

        n_out = dec.shape[axis]

        write_start = out_pos
        if write_start < 0:
            # Skip the fisrt `delay_out` samples
            dec = axis_slice(dec, start=delay_out, axis=axis)
            write_start = 0
            out_pos = 0
            n_out = dec.shape[axis]
        write_stop = min(out_pos + n_out, out_dset.shape[axis])

        out_sl = get_axis_slice(out_dset, start=write_start, stop=write_stop, axis=axis)

        out_dset[out_sl] = axis_slice(dec, stop=write_stop-write_start, axis=axis)

        out_pos += n_out

    # Use reflect padding for the last `delay_out` samples
    same_slice = get_axis_slice(out_dset, start=out_pos, axis=axis)
    last_values = np.take(out_dset, np.arange(out_pos - 1, out_pos - delay_out - 1, -1), axis=axis)
    out_dset[same_slice] = last_values


def iterate_chunks(x: npt.NDArray | h5py.Dataset, chunk_size: int=None, axis: int=-1) -> Iterator[tuple[int, int, npt.NDArray]]:
    """Return an iterator over the array in chunks."""

    n = x.shape[axis]
    if chunk_size is None:
        if isinstance(x, h5py.Dataset):
            chunk_size = x.chunks[-1]
        else:
            chunk_size = DEFAULT_CHUNK_SIZE

    for chunk_start in range(0, n, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n)
        yield chunk_start, chunk_end, axis_slice(x, chunk_start, chunk_end, axis=axis)


def linregress_in_chunks(
    x: npt.ArrayLike | h5py.Dataset,
    y: npt.ArrayLike | h5py.Dataset,
    chunk_size: int=None,
) -> tuple[float, float]:
    """Compute linear regression using x and y in chunks.
    
    Assumes x and y are 1D arrays.
    """

    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_xy = 0.0
    N = 0

    for c0, c1, x_chunk in iterate_chunks(x, chunk_size=chunk_size):
        y_chunk = y[c0:c1]

        sum_x += np.sum(x_chunk)
        sum_y += np.sum(y_chunk)
        sum_x2 += np.sum(x_chunk * x_chunk)
        sum_xy += np.sum(x_chunk * y_chunk)

        N += x_chunk.size

    a = (N * sum_xy - sum_x * sum_y) / (N * sum_x2 - sum_x**2)
    b = (sum_y - a * sum_x) / N
    return a, b



#
# File Templates
#

def get_tod_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY, chan_name: str=None) -> str:
    if chan_name is None:
        chan_name = '*'
    return f'{data_dir}/{date}/{date}_{chan_name}_TOD_set{setnum}.h5'


def get_azel_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_AZEL_set{setnum}.h5'
    # return f'{data_dir}/{date}/{date}_set{setnum}_AZEL.h5'


def get_optcam_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY, old: bool=False) -> str:
    if old:
        return f'{data_dir}/{date}/{date}_optcam_set{setnum}.h5'
    return f'{data_dir}/{date}/{date}_set{setnum}_optcam.h5'

def get_processed_file_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_set{setnum}_processed_data.h5'


def get_consolidated_file_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_set{setnum}_consolidated_data.h5'


def get_file_stub(date: str, setnum: int) -> str:
    return f'{date}_set{setnum}'


def get_params_file_template(tile_name: str, params_dir: str=DEFAULT_PARAMS_DIRECTORY) -> str:
    return f'{params_dir}/params_tile_{tile_name}.h5'

#
# Parallelized Plotting
#

def rasterize(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=200, pad_inches=0)
    buf.seek(0)
    pil_img = deepcopy(Image.open(buf))
    buf.close()
    
    return pil_img

def _parallel_plot_worker(*args, plot_fn):
    fig = plt.figure(figsize=(1,1))
    mpl.font_manager._get_font.cache_clear()  # necessary to reduce text corruption artifacts
    ax = fig.add_subplot(xticks=[], yticks=[])
    
    plot_fn(fig, ax, *args)
    pil_img = rasterize(fig)
    plt.close()
    
    return pil_img

def parallel_plot(fig: Figure, axes: plt.Axes, plot_fn: Callable, *iterables, callback: Callable | None=None):
    with ProcessPoolExecutor(max_workers=8) as executor:
        plots = executor.map(
            partial(_parallel_plot_worker, plot_fn=plot_fn),
            *iterables,
        )
        for ax, rastered in zip(np.ravel(axes), plots):
            im = ax.imshow(rastered)
            
            ax.draw_artist(ax.patch)
            ax.draw_artist(im)
            # ax.set_aspect('equal', adjustable='box')
            fig.canvas.update()
            fig.canvas.flush_events()
            if callback is not None:
                callback()

    # fig.subplots_adjust(left=0, right=1, top=1, bottom=0, hspace=0, wspace=0)
    fig.tight_layout()
    
    return fig


def reset_axes(ax: plt.Axes):
    """Restore a Matplotlib Axes to a clean, default state.
    
    Useful after imshow(), pcolormesh(), etc. cine they change state that isn't reset
    by ax.cla().
    """
    ax.cla()

    # Reset aspect and layout
    ax.set_aspect('auto', adjustable='box')

    # Autoscaling
    ax.autoscale(enable=True, axis="both", tight=False)
    ax.set_autoscale_on(True)

    # Remove fixed limits (important after imshow)
    ax.set_xlim(auto=True)
    ax.set_ylim(auto=True)

    # Turn off image-style behavior
    for im in ax.images:
        im.remove()

    # Reset scale (in case log/symlog was used)
    ax.set_xscale("linear")
    ax.set_yscale("linear")

    # Reset margins to Matplotlib defaults
    ax.margins(x=0.05, y=0.05)

    # Grid & ticks (optional, but predictable)
    ax.grid(False)

def add_colorbar_outside(mappable, ax: plt.Axes, position='right', orientation=None):
    if orientation is None:
        if position in ['right', 'left']:
            orientation = 'vertical'
        else:
            orientation = 'horizontal'
    fig = ax.get_figure()
    bbox = ax.get_position()
    cax = fig.add_axes([bbox.x1 + 0.01, bbox.y0, 0.01, bbox.height])
    fig.colorbar(mappable, cax=cax, location='right', orientation='vertical')
    

def closest(x: npt.NDArray, y: float) -> float:
    """Find the closest value in x to y."""
    return x[np.argmin(np.abs(x - y))]

def argclosest(x: npt.NDArray, y: float) -> int:
    """Find the index of the closest value in x to y."""
    return np.argmin(np.abs(x - y))



if __name__ == '__main__':
    def plot_function(fig, ax, x, y):
        ax.plot(x, y)
    
    grid_shape = (3, 2)
    callback = lambda: print('hi')
    fig, axes = plt.subplots(*grid_shape)

    fig = parallel_plot(
        fig,
        axes,
        plot_function,
        np.random.random((6, 10)),
        np.random.random((6, 10)),
        callback=callback,
    )
    fig.show()
    plt.show()
    exit()

    import timeit, functools
    from scipy.signal import decimate
    n = 100000000
    x = np.random.randn(n)
    q = 10
    # y = decimate(x, q)
    y = decimate_in_chunks(x, q)
    y = np.zeros(n // q)

    # decimate_in_chunks(x, q, out=y)

    # n_repeats = 20
    # timer = timeit.Timer(functools.partial(decimate, x, q))
    # print(f'Time for SciPy decimate: {timer.timeit(n_repeats)}')

    # timer = timeit.Timer(functools.partial(decimate_in_chunks, x, q))
    # print(f'Time for decimate in chunks (no output array): {timer.timeit(n_repeats)}')

    # timer = timeit.Timer(functools.partial(decimate_in_chunks, x, q, out=y))
    # print(f'Time for decimate in chunks (with output array): {timer.timeit(n_repeats)}')
