"""Common functions to be used anywhere in the project."""

import functools
import io
import json
import logging
import os
import stat
import typing
import warnings
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from datetime import datetime
from enum import EnumMeta, StrEnum
from functools import partial
from multiprocessing.connection import Connection
from pathlib import Path
from typing import (
    Any,
    Literal,
    ParamSpec,
    TypeVar,
)

try:
    import thread  # type: ignore
except ImportError:
    import _thread as thread

import git
import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from git import GitError
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PIL import Image
from scipy import ndimage
from scipy.signal import cheby1, group_delay, resample_poly, sos2tf, sosfilt, sosfilt_zi

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

AMBER_HEX = '#ffbf00'
ON_RESONANCE_COLOR = 'white'
OFF_RESONANCE_COLOR = 'sandybrown'
BAD_RESONANCE_COLOR = 'lightgray'
FLAGGED_RESONANCE_COLOR = 'yellow'
SELECTED_RESONANCE_COLOR = 'dodgerblue'
EDITED_RESONANCE_COLOR = 'limegreen'

MAX_ATTENUATION = 31.75


class TabName(StrEnum):
    """Possible tab names for the GUI."""

    INITIALIZATION = 'initialization'
    LOSWEEP = 'losweep'
    TELESCOPE = 'telescope'
    DATA = 'data'
    IMAGING = 'imaging'


class MetaEnum(EnumMeta):
    """Enum class that has a contains method."""

    def __contains__(cls, item):
        """Check if item is a valid member of the enum."""
        try:
            cls(item)
        except ValueError:
            return False
        return True


@FuncFormatter
def mHz_axis_formatter(x: float, pos: int) -> str:  # noqa: ARG001
    """Format the x-axis labels for the resonator plot, converting to MHz.

    Arguments:
        x (float): The x value to format.
        pos (int): The position of the tick.

    Returns:
        str: The formatted string for the x-axis label.
    """
    return f'{x * 1e-6:.1f}'


def mHz_coordinate_formatter(x: float, y: float) -> str:
    """Format the actual coordinates in the axes to MHz, with higher precision."""
    return f'x={x * 1e-6:.5f}, y={y}'


def convert_path[PathLike: (str, Path, bytes, os.PathLike)](
    path: PathLike | None,
) -> Path | None:
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
    raise ValueError(f'Argument must be PathLike or None, got {type(path)}')


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


class PathJSONEncoder(json.JSONEncoder):
    """JSON encoder that converts Path objects to strings."""

    @typing.override
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


def analog_to_digital(a: int, minimum: float, maximum: float, bits: int) -> int:  # noqa: ARG001
    """Convert an analog number to digital.

    Needed because DAQ inputs/outputs have different resolutions.

    Arguments:
        a (int): The analog number
        minimum (float): The minimum possible digital number
        maximum (float): The maximum possible digital number
        bits (int): The number of bits for representing the numbers.

    Returns:
        (int): The digital equivalent number.
    """
    # vals = np.linspace(minimum, maximum, (2**bits) - 1)
    # d = int(np.argmin(np.abs(vals - a)))
    # TODO: This method is only needed for windows? Email Dan
    return a


def digital_to_analog(d: int, minimum: float, maximum: float, bits: int) -> int:
    """Convert a digital number to analog.

    Needed because DAQ inputs/outputs have different resolutions.

    Arguments:
        d (int): The digital number
        minimum (float): The minimum possible analog number
        maximum (float): The maximum possible analog number
        bits (int): The number of bits for representing the numbers.

    Returns:
        (int): The analog equivalent number.
    """
    vals = np.linspace(minimum, maximum, (2**bits) - 1)
    return vals[d]


def recursive_update(d: Mapping, u: Mapping):
    """Update a dictionary-like object recursively."""
    for k, v in u.items():
        if isinstance(v, Mapping):
            d[k] = recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def get_git_hash() -> str:
    """Get the current GIT hash of the repository."""
    try:
        repo = git.Repo(search_parent_directories=True)
    except GitError:
        return 'unknown'
    else:
        return repo.head.object.hexsha


# From onrkidpy.py
def get_yymmdd():
    """Return today's date string in YYYYMMDD format."""
    return datetime.today().strftime('%Y%m%d')


def get_filename(
    base_dir: Path = Path('/data/'),
    file_type='lo',
    tile_name='',
    attenuation=0.0,
    date: str | None = None,
    hour: str | None = None,
    mkdir: bool = False,
):
    """Get a file name with the appropriate formatting."""
    # see if we already have the parent folder for today's date
    if date is None:
        date = get_yymmdd()
    date_folder = base_dir / date
    if mkdir:
        date_folder.mkdir(mode=PERMISSIONS_ALL_FULL, exist_ok=True)

    # provide the name of the file
    match file_type.lower():
        case 'lo' | 'tonelist' | 'power':
            if hour is None:
                hour = get_current_lo_sweep_hour_string()
            match file_type.lower():
                case 'lo':
                    strings = [date, tile_name, 'LO_Sweep', hour]
                case 'tonelist':
                    strings = [date, tile_name, 'tone_list', hour]
                case 'power':
                    strings = [date, tile_name, 'Power_Sweep', hour]
        case 'tod' | 'azel' | 'optcam' | 'optcam_video':
            this_dir_files = list(date_folder.glob('*TOD_set*'))
            if not this_dir_files:
                setnum = 1001
            else:
                this_dir_files.sort()
                offset = 1 if file_type == 'tod' else 0
                setnums = [f.name[-7:-3] for f in this_dir_files]
                setnums.sort()
                setnum = int(setnums[-1]) + offset
            if file_type.lower() == 'optcam' or file_type.lower() == 'optcam_video':
                strings = [date, file_type.lower(), f'set{setnum}']
            else:
                strings = [date, tile_name, file_type.upper(), f'set{setnum}']
        case 'attenuator':
            strings = [date, tile_name, f'attenuator{attenuation:02d}']
        case _:
            raise ValueError(
                f'Invalid file type: "{file_type.lower()}"; must be one of {FileType}'
            )
    return date_folder / '_'.join(filter(None, strings))


def get_current_lo_sweep_hour_string() -> str:
    """Return the current time in the LO sweep filename format.

    The format is `hourHHpMMSS`
    """
    hour = (
        float(datetime.now().strftime('%H'))
        + float(datetime.now().strftime('%M')) / 60.0
        + float(datetime.now().strftime('%S')) / 3600.0
    )
    return f'hour{hour:04.4f}'.replace('.', 'p')


@ensure_path('data_dir')
def get_sweep_filename(
    data_dir: Path = Path(DEFAULT_DATA_DIRECTORY),
    sweep_type: Literal['lo', 'power', 'temperature', 'blind'] = 'lo',
    tile_name='',
    suffix: str = '',
    date: str | None = None,
    hour: str | None = None,
    mkdir: bool = False,
):
    """Get a sweep file name with the appropriate formatting."""
    # See if we already have the parent folder for today's date
    if date is None:
        date = get_yymmdd()
    date_folder = data_dir / date
    if mkdir:
        date_folder.mkdir(mode=PERMISSIONS_ALL_FULL, exist_ok=True)

    # provide the name of the file
    if hour is None:
        hour = get_current_lo_sweep_hour_string()
    match sweep_type.lower():
        case 'lo':
            sweep_name = 'LO_Sweep'
        case 'power':
            sweep_name = 'Power_Sweep'
        case 'temperature':
            sweep_name = 'Temperature_Sweep'
        case 'blind':
            sweep_name = 'Blind_Sweep'
        case _:
            raise ValueError(
                f'Invalid file type: "{sweep_type.lower()}"; must be one of {FileType}'
            )
    strings = [date, tile_name, sweep_name, hour, suffix]
    return date_folder / '_'.join(filter(None, strings))


def cartesian(*arrays: npt.ArrayLike, out: npt.NDArray | None = None):
    """Generate a Cartesian product of input arrays.

    Code from: https://stackoverflow.com/a/1235363

    Parameters
    ----------
    arrays : list of array-like
        1-D arrays to form the Cartesian product of.
    out : ndarray
        Array to place the Cartesian product in.

    Returns:
    -------
    out : ndarray
        2-D array of shape (M, len(arrays)) containing Cartesian products
        formed of input arrays.

    Examples:
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
    arrays = [np.asarray(x) for x in arrays]
    dtype = arrays[0].dtype

    n = np.prod([x.size for x in arrays])
    if out is None:
        out = np.zeros([n, len(arrays)], dtype=dtype)

    # m = n / arrays[0].size
    m = int(n / arrays[0].size)
    out[:, 0] = np.repeat(arrays[0], m)
    if arrays[1:]:
        cartesian(*arrays[1:], out=out[0:m, 1:])
        for j in range(1, arrays[0].size):
            # for j in xrange(1, arrays[0].size):
            out[j * m : (j + 1) * m, 1:] = out[0:m, 1:]
    return out


def ordinal(n: int) -> str:
    """Append the english ordinal suffix to an integer.

    From https://stackoverflow.com/a/20007730.
    """
    if 11 <= (n % 100) <= 13:  # noqa: PLR2004
        suffix = 'th'
    else:
        suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    return str(n) + suffix


def gaussian_filter(x: npt.NDArray, sigma: tuple[float, float]) -> npt.NDArray:
    """Apply a gaussian filter to an array."""
    return ndimage.gaussian_filter(
        x,
        sigma,
        mode='reflect',
        truncate=1.0 / sigma[1],
    )


def wait_for_telescope_command(
    conn: Connection, conn_id: str, command: str, err_msg: str = ''
):
    """Wait to receive a command from the telescope controller process."""
    if not err_msg:
        err_msg = f'Error occured while waiting for command "{command}": '
    while True:
        if not conn.poll(1e-4):
            continue
        response, *data = conn.recv()
        _tele_logger.debug(f'{conn_id} got response: "{response}", data: {data}')
        if response.lower() == f'{command}':
            break
        if response.lower() == 'err':
            raise RuntimeError(f'{err_msg}: {data}')


def list_datasets(
    group: h5py.Group, full_names: bool = False
) -> list[tuple[str, h5py.Dataset]]:
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


def search(
    src: h5py.Group, name: str, full_name: bool = True, exact_match: bool = False
) -> tuple[str, H5pyObject] | None:
    """Search recursively through an HDF5 group for the specified name.

    This function will return the first object found whose name matches `name`.
    Returns `None` if no match is found.

    Arguments:
        src (h5py.Group): The group to search within.
        name (str): The target name to search for.
        full_name (bool): Whether to return the full name of the object. Defaults to
            True.
        exact_match (bool): Whether to only accept exact name matches. If False, this
            function will succeed if an object is found whose name contains `name`.
            Defaults to False.


    Returns:
        obj_name (str): The name of the found object.
        obj (h5py.Group | h5py.Dataset): The object matching the search query.

    """

    def search_fn(obj_name: str, obj: H5pyObject):
        success = name == obj.name if exact_match else name in obj.name
        if success:
            if full_name:
                return obj.name, obj
            return obj_name, obj
        return None

    return src.visititems(search_fn)


#
# Chunked array handling utils
#
def compute_chunk_shape(
    data_shape: tuple[int, ...],
    dtype_size: int,
    target_mb: float = 4,
    max_chunk_size: int | None = None,
):
    """Compute the chunk shape to have the target chunk size in MB.

    Arguments:
        data_shape (tuple[int, ...]): The shape of the data excluding the chunked
            dimension.
        dtype_size (int): The size of the dtype in bytes.
        target_mb (float, optional): The target size of the chunk in MB. Defaults to 4.
        max_chunk_size (int, optional): The maximum size a chunk is allowed to be.
            Ignored if set to None. Defaults to None.

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
    axis: int = -1,
    use_filter: bool = True,
):
    """Downsample a dataset in chunks."""
    overlap = 32 * q
    n = dset.shape[axis]

    out_index = 0

    def downsampled_equiv(x):
        return int((x + q - 1) / q)

    for start in range(0, n, chunk_size):
        if use_filter:
            read_start = max(0, start - overlap)
            read_stop = min(n, start + chunk_size + overlap)

            chunk = axis_slice(dset, start=read_start, stop=read_stop, axis=axis)

            dec = resample_poly(chunk, up=1, down=q, axis=axis)
        else:
            read_start = max(0, start)
            # read_start = int(q * np.ceil(start / q))  # Start reading at multiple of q
            read_stop = min(n, start + chunk_size)
            chunk = axis_slice(dset, start=read_start, stop=read_stop, axis=axis)
            # dec = axis_slice(chunk, step=q, axis=axis)
            dec_start = (
                int(q * np.ceil(start / q)) - start
            )  # Make sure we start on a multiple of q
            dec = axis_slice(chunk, start=dec_start, step=q, axis=axis)

        valid_start = downsampled_equiv(start - read_start)
        valid_stop = valid_start + min(
            downsampled_equiv(min(chunk_size, n - start)),
            out_dset.shape[axis] - out_index,
        )

        valid = axis_slice(dec, start=valid_start, stop=valid_stop, axis=axis)

        write_slice = get_axis_slice(
            out_dset, start=out_index, stop=out_index + valid.shape[axis], axis=axis
        )
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
    """Apply the indices and weights to interpolate an array y."""
    return (1 - w) * y[idx] + w * y[idx + 1]


def get_axis_slice(
    a, start=None, stop=None, step=None, axis: int | Iterable[int] = -1
) -> tuple[slice, ...]:
    """Return the slice to use in order to slice along axis 'axis' from 'a'.

    Parameters
    ----------
    a : numpy.ndarray
        The array to be sliced.
    start, stop, step : int or None
        The slice parameters.
    axis : int, optional
        The axis of `a` to be sliced.

    Examples:
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

    Notes:
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


def axis_slice(
    a, start=None, stop=None, step=None, axis=-1, direct_read: bool = False
) -> npt.NDArray:
    """Take a slice along axis 'axis' from 'a'.

    Parameters
    ----------
    a : numpy.ndarray
        The array to be sliced.
    start, stop, step : int or None
        The slice parameters.
    axis : int, optional
        The axis of `a` to be sliced.

    Examples:
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

    Notes:
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


def axis_index(
    a: npt.NDArray,
    indices: npt.ArrayLike | tuple[npt.ArrayLike, ...],
    axis: int | tuple[int, ...] = -1,
):
    """Index `a` along axis `axis` with `indices`.

    Parameters
    ----------
    a : numpy.ndarray
        The array to be indexed.
    indices : array-like
        The indices to use for indexing.
    axis : int, optional
        The axis of `a` to be indexed.

    Examples:
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
    if isinstance(axis, tuple) and len(indices) != len(axis):
        raise ValueError(
            'If axis is a tuple, indices must be a tuple of the same length.'
        )
    a_index = [slice(None)] * a.ndim
    if isinstance(axis, tuple):
        for i, ax in enumerate(axis):
            a_index[ax] = indices[i]
    else:
        a_index[axis] = indices
    return a[tuple(a_index)]


def axis_reverse(a, axis=-1):
    """Reverse the 1-D slices of `a` along axis `axis`.

    Returns axis_slice(a, step=-1, axis=axis).
    """
    return axis_slice(a, step=-1, axis=axis)


def decimate_in_chunks(dset: h5py.Dataset, out_dset, q: int, axis=-1, chunk_shape=None):
    """Decimate a dataset in chunks."""
    n = dset.shape[axis]

    if chunk_shape is None:
        chunk_shape = dset.chunks
    chunk_size = chunk_shape[axis]
    if q == 1:
        for start in range(0, n, chunk_size):
            stop = min(start + chunk_size, n)
            out_sl = get_axis_slice(out_dset, start=start, stop=stop, axis=axis)
            out_dset[out_sl] = axis_slice(dset, start, stop, axis=axis)
        return

    # Create buffer for storing chunks
    chunk = np.empty(chunk_shape, dtype=dset.dtype)
    y = np.empty_like(chunk)

    # Copmpute values to account for phase lag from the filter
    wc = 0.8 / q
    sos = cheby1(8, 0.05, wc, output='sos')
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

    for start in range(0, n, chunk_size):
        stop = min(start + chunk_size, n)
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
        dec_start = (
            int(q * np.ceil(start / q)) - start
        )  # Make sure we start on a multiple of q
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

        out_dset[out_sl] = axis_slice(dec, stop=write_stop - write_start, axis=axis)

        out_pos += n_out

    # Use reflect padding for the last `delay_out` samples
    same_slice = get_axis_slice(out_dset, start=out_pos, axis=axis)
    last_values = np.take(
        out_dset, np.arange(out_pos - 1, out_pos - delay_out - 1, -1), axis=axis
    )
    out_dset[same_slice] = last_values


def iterate_chunks(
    x: npt.NDArray | h5py.Dataset, chunk_size: int | None = None, axis: int = -1
) -> Iterator[tuple[int, int, npt.NDArray]]:
    """Return an iterator over the array in chunks."""
    n = x.shape[axis]
    if chunk_size is None:
        chunk_size = x.chunks[-1] if isinstance(x, h5py.Dataset) else DEFAULT_CHUNK_SIZE

    for chunk_start in range(0, n, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n)
        yield chunk_start, chunk_end, axis_slice(x, chunk_start, chunk_end, axis=axis)


def linregress_in_chunks(
    x: npt.ArrayLike | h5py.Dataset,
    y: npt.ArrayLike | h5py.Dataset,
    chunk_size: int | None = None,
) -> tuple[float, float]:
    """Compute linear regression using x and y in chunks.

    Assumes x and y are 1D arrays.
    """
    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_xy = 0.0
    n = 0

    for c0, c1, x_chunk in iterate_chunks(x, chunk_size=chunk_size):
        y_chunk = y[c0:c1]

        sum_x += np.sum(x_chunk)
        sum_y += np.sum(y_chunk)
        sum_x2 += np.sum(x_chunk * x_chunk)
        sum_xy += np.sum(x_chunk * y_chunk)

        n += x_chunk.size

    a = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)
    b = (sum_y - a * sum_x) / n
    return a, b


#
# File Templates
#


def get_tod_template(
    date: str,
    setnum: int,
    data_dir: str = DEFAULT_DATA_DIRECTORY,
    chan_name: str | None = None,
) -> str:
    """Get a TOD filename in the proper format."""
    if chan_name is None:
        chan_name = '*'
    return f'{data_dir}/{date}/{date}_{chan_name}_TOD_set{setnum}.h5'


def get_azel_template(
    date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY
) -> str:
    """Get an AZEL filename in the proper format."""
    return f'{data_dir}/{date}/{date}_AZEL_set{setnum}.h5'
    # return f'{data_dir}/{date}/{date}_set{setnum}_AZEL.h5'


def get_optcam_template(
    date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY, old: bool = False
) -> str:
    """Get an optcam filename in the proper format."""
    if old:
        return f'{data_dir}/{date}/{date}_optcam_set{setnum}.h5'
    return f'{data_dir}/{date}/{date}_set{setnum}_optcam.h5'


def get_processed_file_template(
    date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY
) -> str:
    """Get a processed data filename in the proper format."""
    return f'{data_dir}/{date}/{date}_set{setnum}_processed_data.h5'


def get_consolidated_file_template(
    date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY
) -> str:
    """Get a consolidated data filename in the proper format."""
    return f'{data_dir}/{date}/{date}_set{setnum}_consolidated_data.h5'


def get_file_stub(date: str, setnum: int) -> str:
    """Get the file stub for filenames (i.e. "<date>_set<setnum>")."""
    return f'{date}_set{setnum}'


def get_params_file_template(
    tile_name: str, params_dir: str = DEFAULT_PARAMS_DIRECTORY
) -> str:
    """Get a parameters filename in the proper format."""
    return f'{params_dir}/params_tile_{tile_name}.h5'


def get_beammap_pdf_template(
    date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY
) -> str:
    """Get a beammap PDF filename in the proper format."""
    return str(Path(data_dir) / f'{date}/{date}_set{setnum}_beammap.pdf')


def get_detector_pos_pdf_template(
    date: str, tile_name: str, data_dir: str = DEFAULT_DATA_DIRECTORY
) -> str:
    """Get a detector positions PDF filename in the proper format."""
    return str(Path(data_dir) / f'{date}/{tile_name}_detector_pos.pdf')


#
# Parallelized Plotting
#


def rasterize(fig: Figure):
    """Rasterize a figure to an image."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=200, pad_inches=0)
    buf.seek(0)
    pil_img = deepcopy(Image.open(buf))
    buf.close()

    return pil_img


def _parallel_plot_worker(*args, plot_fn):
    """Perform parallelized plotting work."""
    fig = plt.figure(figsize=(1, 1))

    # Necessary to reduce text corruption artifacts
    mpl.font_manager._get_font.cache_clear()  # noqa: SLF001

    ax = fig.add_subplot(xticks=[], yticks=[])

    plot_fn(fig, ax, *args)
    pil_img = rasterize(fig)
    plt.close()

    return pil_img


def parallel_plot(
    fig: Figure,
    axes: plt.Axes,
    plot_fn: Callable,
    *iterables,
    callback: Callable | None = None,
):
    """Perform plotting code across parallel processes."""
    with ProcessPoolExecutor(max_workers=8) as executor:
        plots = executor.map(
            partial(_parallel_plot_worker, plot_fn=plot_fn),
            *iterables,
        )
        for ax, rastered in zip(np.ravel(axes), plots, strict=False):
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
    ax.autoscale(enable=True, axis='both', tight=False)
    ax.set_autoscale_on(True)

    # Remove fixed limits (important after imshow)
    ax.set_xlim(auto=True)
    ax.set_ylim(auto=True)

    # Turn off image-style behavior
    for im in ax.images:
        im.remove()

    # Reset scale (in case log/symlog was used)
    ax.set_xscale('linear')
    ax.set_yscale('linear')

    # Reset margins to Matplotlib defaults
    ax.margins(x=0.05, y=0.05)

    # Grid & ticks (optional, but predictable)
    ax.grid(False)


def add_colorbar_outside(mappable, ax: plt.Axes, position='right', orientation=None):
    """Add a colorbar outside of the axes."""
    if orientation is None:
        orientation = 'vertical' if position in ['right', 'left'] else 'horizontal'
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


def sigma_to_fwhm(sigma: float) -> float:
    """Convert the sigma of a Gaussian to FWHM."""
    return 2 * np.sqrt(2 * np.log(2)) * sigma


def dict_get_by_path(d: dict, keys: Sequence[str], default: Any = None) -> Any:
    """Get a value from a nested dictionary following the desired path."""
    root = d
    try:
        for key in keys[:-1]:
            root = root[key]
        return root[keys[-1]]
    except (KeyError, IndexError):
        return default


def dict_set_by_path(d: dict, keys: Sequence[str], val: Any):
    """Set a value in a nested dictionary following the desired path."""
    root = d
    for key in keys[:-1]:
        root = root.setdefault(key, {})
    root[keys[-1]] = val


def dict_del_by_path(d: dict, keys: Sequence[str]):
    """Remove a value from a nested dictionary following the desired path."""
    root = d
    for key in keys[:-1]:
        root = root[key]
    del root[keys[-1]]


def dict_get_by_path_with_default(
    keys: Sequence[str], d1: dict, defaults: dict, fallback_value: Any = None
) -> Any:
    """Get a value by path using a default dictionary for missing values."""
    return dict_get_by_path(
        d1, keys, default=dict_get_by_path(defaults, keys, default=fallback_value)
    )


def dict_get_with_default(
    key: str, d1: dict, defaults: dict, fallback_value: Any = None
) -> Any:
    """Get a value from a dictionary, using a default dictionary for missing values."""
    return d1.get(key, defaults.get(key, fallback_value))


def load_dict_or_defaults(
    d1: dict, d2: dict, items: list[tuple[str | tuple, Any]]
) -> dict:
    """Load the desired items from a dictionary (or fallback) into a new dictionary."""
    out_dict = {}
    for key, fallback in items:
        if isinstance(key, tuple):
            val = dict_get_by_path_with_default(key, d1, d2, fallback_value=fallback)
            dict_set_by_path(out_dict, key, val)
        else:
            val = dict_get_with_default(key, d1, d2, fallback_value=fallback)
            out_dict[key] = val
    return out_dict


def quit_function():
    """Quit/interrupt a thread."""
    thread.interrupt_main()  # raises KeyboardInterrupt
