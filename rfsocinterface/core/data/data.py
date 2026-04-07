"""Core functionality relating to data loading and processing."""


from __future__ import annotations
from pathlib import Path
import glob
import pdb
import time
import logging
from itertools import chain, batched
import typing
from typing import overload
from importlib.metadata import version
import shutil

# import tables
import h5py
# from tables.link import ExternalLink
import numpy as np
import numpy.typing as npt
from numpy.polynomial import polynomial as poly
from scipy.interpolate import make_interp_spline
from numpy.polynomial import Polynomial
from scipy.stats import linregress
from scipy import signal
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import kidpy3
from kidpy3.data_handler import RawDataFile
import json

from rfsocinterface import __version__ as VERSION
from rfsocinterface.core.losweep import LoSweepData
from rfsocinterface.core.utils import (
    gaussian_filter,
    GAUSSIAN_SIGMA,
    PERMISSIONS_ALL_FULL,
    get_tod_template,
    get_azel_template,
    get_optcam_template,
    get_processed_file_template,
    get_consolidated_file_template,
    get_file_stub,
    DEFAULT_DATA_DIRECTORY,
    PathLike,
    ensure_path,
    pad_to_length,
    list_datasets,
    search,
    H5pyObject,
    linregress_in_chunks,
    iterate_chunks,
    compute_chunk_shape,
    chunked_downsample,
    decimate_in_chunks,
    new_decimate_in_chunks,
    apply_interp,
    build_interp_map,
    get_git_hash,
)

_logger = logging.getLogger(__name__)

OPTCAM_OFFSET_AZ_PIX = 57
OPTCAM_OFFSET_ZA_PIX = 49
OPTCAM_PIX_SIZE_DEGREES = 0.0104
DEFAULT_MAP_DPIX = 0.03
# DATA_DIRECTORY = 'reference_data'  # For testing with local data files

N_POLARIZATION = 2

BUTTER_ORDER = 6
DECIMATE_ORDER = 5
AZ_TRIM = 2.3
ZA_TRIM = 0.2

RFSOC_TIME_OFFSET = -0.012  # -12 ms, empirically determined


TONES_TABLE_DTYPE = [
    ('baseband_freq', 'f8'),
    ('power', 'f8'),
    ('delta_x', 'f8'),
    ('delta_y', 'f8'),
    ('beam_amplitude', 'f8'),
    ('polarization', 'i1'),
    ('dfoverf_per_mK', 'f8'),
    ('chanmask', 'i1'),
]

CALIBRATION_TABLE_DTYPE = [
    ('adc_units_to_hz', 'f8'),
    ('IQ_to_gain_phase_angle', 'f8'),
    ('IQ_to_freq_diss_angle', 'f8'),
    ('df_per_mK', 'f8'),
]



def get_channel_group_name(idx: int) -> str:
    """Return the properly formatted group name for the channel with index `idx`"""
    return f'channel_{idx:03d}'


def get_step_group_name(idx: int, name: str) -> str:
    """Return the properly formatted group name for a step in the processing history or checkpoints."""
    return f'{idx:04d}_{name}'


#
# Outlier Removal and Flagging
#

def iteratively_reject_outliers(data: npt.ArrayLike, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Repeatedly perform outlier rejection until there are no more outliers.

    Args:
        data (npt.ArrayLike): Input data (expected to be 1 dimensional)
        sigma (float, optional): The standard deviation cutoff for outliers. Defaults
            to 2.
        axis (None or int or tuple of ints, optional): The axis or axes to perform the
            outlier rejection along. Deafults to None.

    Returns:
        (npt.NDArray, npt.NDArray, npt.NDArray): `data` with the outliers removed,
        indices in `data` of the inliers, and indices in `data` of the outliers .
    """
    ind = np.arange(np.size(data))
    # ind = np.ones_like(data, dtype=int)
    # ind = get_all_indices(data)
    if np.ndim(data) != 1:
        data = np.flatten(data)
    while True:
        good_data, good_ind = reject_outliers(data[ind], sigma=sigma, axis=axis)
        if np.size(ind) == np.size(good_ind):
            break
        ind = ind[good_ind]
    return data[ind], ind, np.setdiff1d(np.arange(np.size(data)), ind)


def flag(data: npt.NDArray, fs: float, sigma: float=2):
    """Flag data outliers."""
    first_dimension, n_chan, _ = data.shape
    n_flag = np.zeros((first_dimension, n_chan))

    filt_cut = 1. / (0.5 * fs)
    b, a = signal.butter(5, filt_cut, btype='high', analog=False)
    hpf_data = signal.filtfilt(b, a, data)
    for i_complex in range(first_dimension):
        for i_res in range(n_chan):
            inliers, _, _ = iteratively_reject_outliers(hpf_data[i_complex, i_res, :], sigma=sigma)
            n_flag[i_complex, i_res] = hpf_data.shape[-1] - np.size(inliers)
    return n_flag, np.std(hpf_data, axis=-1)


def flag_outliers(data: npt.NDArray, fs: float, chanmask: npt.NDArray, sigma: float=2) -> npt.NDArray:
    good_channels = np.where(chanmask == 1)[0]
    n_flag, timestream_rms = flag(data[:, good_channels], fs, sigma=sigma)
    med_flag = np.median(n_flag)
    chanmask[np.where(np.any(n_flag > 2. * med_flag, axis=0))] = -1
    _, _, bad_indices_0 = iteratively_reject_outliers(timestream_rms[0], sigma=sigma)
    if np.ndim(timestream_rms) == 3:
        _, _, bad_indices_1 = iteratively_reject_outliers(timestream_rms[1], sigma=sigma)
        bad_indices = np.union1d(bad_indices_0, bad_indices_1)
    else:
        bad_indices = bad_indices_0
    chanmask[bad_indices] = -1
    return chanmask


def reject_outliers(data: npt.NDArray, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Return the data without outliers and the rejected indices."""
    d = np.abs(data - np.median(data, axis=axis))
    std = np.std(data, axis=axis)
    ind = np.where(d < sigma * std)
    return data[ind], ind

#
# Data Processing
#

def compute_df_per_mK(beam_pol: npt.NDArray, detector_beam_amp: npt.NDArray, detector_f, dfoverf_per_mK):
    valid_index = np.ndarray.flatten(np.argwhere(beam_pol[:] >= 1))
    valid_amp = detector_beam_amp[valid_index]

    if np.size(valid_amp) > 1:
        min_amp = np.percentile(valid_amp, 10)
        valid_amp[valid_amp < min_amp] = min_amp
        valid_amp /= np.median(valid_amp)

    amps = detector_beam_amp[:]
    amps[valid_index] = valid_amp
    return dfoverf_per_mK * detector_f * amps


# TODO: Optimize this for chunked data
def rotate_basis(
        in_data: h5py.Dataset,
        out_data: h5py.Dataset,
        rotation_angle: npt.NDArray,
):
    """Compute change of basis, rotating with the specified angle."""

    out_data[0] = np.cos(rotation_angle)[:, np.newaxis] * in_data[0] - \
        np.sin(rotation_angle)[:, np.newaxis] * in_data[1]

    out_data[1] = np.sin(rotation_angle)[:, np.newaxis] * in_data[0] + \
        np.cos(rotation_angle)[:, np.newaxis] * in_data[1]


# TODO: Optimize this for chunked data
def generate_calibrated_data(
    data_IQ: h5py.Dataset,
    data_freq_diss: h5py.Dataset,
    data_mK: h5py.Dataset,
    IQ_to_freq_diss_angle: npt.NDArray,
    adc_units_to_hz: npt.NDArray,
    df_per_mK: npt.NDArray,
):
        
    # now use the derivatives to convert to a frequency shift
    # need to optimally weight the data based on the response
    # in each direction (assuming the noise is identical in I and Q)
    # this will then yield data_f
    rotate_basis(
        data_IQ[:] / adc_units_to_hz[np.newaxis, :, np.newaxis],
        data_freq_diss,
        IQ_to_freq_diss_angle,
    )
    # Finally, we need to get data_mK
    with np.errstate(divide='ignore', invalid='ignore'):
        data_mK[:] = np.divide(
            data_freq_diss[0],
            df_per_mK[:, np.newaxis],
        )

#
# Code for recitifying the timestamp
#
def find_missed_packets_with_indices(
        packet_idx: h5py.Dataset,
) -> npt.NDArray:
    missed_packets = np.empty((0, 2), dtype=int)

    for i in range(1, packet_idx.size):
        this_missed_packets = packet_idx[i] - packet_idx[i - 1] - 1
        if this_missed_packets > 0:
            missed_packets = np.vstack([missed_packets, [i, this_missed_packets]])

    _logger.debug(f'{np.sum(missed_packets[:, 1])} missed packets')
    return missed_packets


def find_missed_packets(
    raw_timestamp: h5py.Dataset,
    n_samples: int,
    window_size: int=5,
    sigma: float=3.0,
) -> npt.NDArray:
    dtime = np.diff(raw_timestamp)
    med_dtime = np.median(dtime)
    std_dtime = np.std(dtime)
    bad_samples = np.argwhere(np.abs(dtime - med_dtime) > sigma * std_dtime).flatten()

    missed_packets = np.empty((0, 2), dtype=int)
    i = 1
    while i < n_samples:
        dtime_idx = i - 1
        if dtime_idx in bad_samples:
            window_min_idx = max(0, i - window_size)
            window_max_idx = min(n_samples, i + window_size)
            window = raw_timestamp[window_min_idx:window_max_idx + 1]
            window_dtime = np.ptp(window)
            # Expected number of samples in time elapsed between start and end of window
            # In theory, this is 1 less than the number of actual samples in the window
            # i.e. (2 * window_size)
            expected_samples = int(window_dtime // med_dtime)  
            actual_samples = window_max_idx - window_min_idx
            # A packet was potentially missed
            if expected_samples > actual_samples:
                packets_missed = expected_samples - actual_samples + 1

                # Look in a larger window to avoid spurious problems
                # Look outside the window by number of supposed missed packets to 
                # verfiy that they were actually missed
                large_window_min_idx = max(0, i - window_size)
                large_window_max_idx = min(n_samples, i + window_size + packets_missed)
                large_window = raw_timestamp[large_window_min_idx:large_window_max_idx + 1]
                large_window_dtime = np.ptp(large_window)
                large_expected_samples = int(large_window_dtime // med_dtime)
                large_actual_samples = large_window_max_idx - large_window_min_idx
                large_window_packets_missed = large_expected_samples - large_actual_samples + 1
                if large_expected_samples > large_actual_samples:
                    missed_packets = np.vstack([missed_packets, [i, large_window_packets_missed]])
                    continue
        i += 1

    _logger.debug(f'{np.sum(missed_packets[:, 1])} missed packets')

    return missed_packets


def interpolate_timestamp_streaming(
    raw_timestamp: h5py.Dataset,
    new_timestamp: h5py.Dataset,
    packet_indices: h5py.Dataset,
    ds_factor: int = 1,
    chunk_size: int = 4096,
    time_offset: float = 0.0
):
    """
    Compute a linear fit of raw_timestamp vs packet_indices and generate
    an equally spaced new timestamp dataset in chunks.

    Parameters
    ----------
    raw_timestamp : h5py.Dataset
        Original timestamps (float64), shape (N,)
    new_timestamp : h5py.Dataset
        Output equally spaced timestamps (float64), shape (M,)
    packet_indices : h5py.Dataset
        Packet indices (uint32), shape (N,)
    ds_factor : int
        Downsampling factor for output
    chunk_size : int
        Number of elements to read at a time from HDF5
    time_offset : float
        Optional offset to add to output timestamps
    """

    N = raw_timestamp.shape[0]

    # Accumulators for linear regression
    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_xy = 0.0
    n_total = 0

    # --- Step 1: Streaming linear regression ---
    for start in range(0, N, chunk_size):
        stop = min(start + chunk_size, N)

        # Read chunks as plain numpy arrays
        x_chunk = np.uint64(packet_indices[start:stop])
        y_chunk = raw_timestamp[start:stop]

        # Shift indices so regression is well-conditioned
        if start == 0:
            x0 = x_chunk[0]
        x_chunk_shifted = x_chunk - x0

        # Accumulate sums using dot products (memory-efficient)
        sum_x  += x_chunk_shifted.sum()
        sum_y  += y_chunk.sum()
        sum_x2 += np.dot(x_chunk_shifted, x_chunk_shifted)
        sum_xy += np.dot(x_chunk_shifted, y_chunk)
        n_total += x_chunk_shifted.size

    # Compute slope (a) and intercept (b)
    denom = n_total * sum_x2 - sum_x ** 2
    if denom == 0:
        raise ValueError("Degenerate packet_indices, cannot compute regression.")
    a = (n_total * sum_xy - sum_x * sum_y) / denom
    b = (sum_y - a * sum_x) / n_total

    # --- Step 2: Generate new timestamps in chunks ---
    M = new_timestamp.shape[0]
    for start in range(0, M, chunk_size):
        stop = min(start + chunk_size, M)

        # Generate the equally spaced packet index positions
        indices = np.arange(start * ds_factor, stop * ds_factor, dtype=np.float64)

        # Linear fit + offset
        new_chunk = a * indices + b + time_offset

        # Write directly to HDF5
        new_timestamp[start:stop] = new_chunk

    
def interpolate_missing_data(
    input_data_I: h5py.Dataset,
    input_data_Q: h5py.Dataset,
    timestamp: h5py.Dataset,
    output_dset: h5py.Dataset,
    output_indices_dset: h5py.Dataset,
    packet_indices: h5py.Dataset,
    missed_packets: npt.NDArray,
    valid_tone_index: npt.NDArray,
):
    total_missed_packets = np.sum(missed_packets[:, 1])
    n_tones = np.size(valid_tone_index)
    n_samples = input_data_I.shape[-1]

    # count = 0
    for i, this_missed_packets in missed_packets:
        window_size = 5 * this_missed_packets
        index = packet_indices[i] - packet_indices[0]
        prev_index = packet_indices[i - 1] - packet_indices[0]

        # Fit a spline using data from nearest (window_size * 2) packets
        min_t = max(0, i - window_size)
        max_t = min(n_samples, i + window_size)
        window = range(min_t, max_t + 1)
        window_packet_indices = packet_indices[window] - packet_indices[0]
        times = timestamp[window_packet_indices]
        i_data = input_data_I[:, window][valid_tone_index, :]
        q_data = input_data_Q[:, window][valid_tone_index, :]
        fit_I = poly.polyfit(times - times[0], i_data.T, 4)
        fit_Q = poly.polyfit(times - times[0], q_data.T, 4)

        # Interpolate data between sample i-1 and i
        dtime = (timestamp[index] - timestamp[prev_index]) / this_missed_packets
        missing_packet_start_t = timestamp[prev_index] + dtime
        current_t = timestamp[index]
        missed_packet_t = np.linspace(missing_packet_start_t, current_t, this_missed_packets, endpoint=False) 
        new_data_I = poly.polyval(missed_packet_t - times[0], fit_I)
        new_data_Q = poly.polyval(missed_packet_t - times[0], fit_Q)
        new_data = np.stack((new_data_I, new_data_Q))

        this_interpolated_indices = list(range(prev_index + 1, index))

        old_size = output_indices_dset.size
        output_indices_dset.resize(old_size + np.size(this_interpolated_indices))
        output_indices_dset[old_size:] = this_interpolated_indices
        output_dset[..., window_packet_indices] = new_data


def get_detector_positions(
    timestamp: h5py.Dataset,
    tel_timestamp: h5py.Dataset,
    az_tel: h5py.Dataset,
    za_tel: h5py.Dataset,
    output_detector_az: h5py.Dataset,
    output_detector_za: h5py.Dataset,
    dx: npt.NDArray,
    dy: npt.NDArray,
    elevation_angle: float
) -> npt.NDArray:
    x = timestamp[:]
    xp = tel_timestamp[:]

    idx, w = build_interp_map(x, xp)

    chunk_size = output_detector_az.chunks[-1]
    n_samples = timestamp.size

    for start in range(0, n_samples, chunk_size):

        stop = min(start + chunk_size, n_samples)

        idx_chunk = idx[start:stop]
        w_chunk = w[start:stop]

        # telescope interpolation
        az = (1 - w_chunk) * az_tel[idx_chunk] + w_chunk * az_tel[idx_chunk + 1]
        az[x[start:stop] < xp[0]] = az_tel[0]
        az[x[start:stop] > xp[-1]] = az_tel[-1]
        za = (1 - w_chunk) * za_tel[idx_chunk] + w_chunk * za_tel[idx_chunk + 1]
        za[x[start:stop] < xp[0]] = za_tel[0]
        za[x[start:stop] > xp[-1]] = za_tel[-1]

        # rotation angle
        ang = np.deg2rad(elevation_angle - za)

        cos_ang = np.cos(ang)
        sin_ang = np.sin(ang)

        output_detector_az[:, start:stop] = (
            np.outer(dx[:], cos_ang)
            - np.outer(dy[:], sin_ang)
            + az
        )
        output_detector_za[:, start:stop] = (
            np.outer(dy[:], cos_ang)
            + np.outer(dx[:], sin_ang)
            + za
        )


#
# Data Classes
#

class NewDataStorage:
    """This wrapper around HDF5 files for data storage.
    
    Attributes:
        file (h5py.File): The file that the file is stored in.
    """
    @ensure_path(1)
    def __init__(self, filename: Path, mode: str='a'):
        self.filename = filename
        self.file = None
        self.mode = None
        self.open(mode=mode)

    @overload
    @classmethod
    def load(cls, filename: str, mode: str='a') -> NewDataStorage:
        pass

    @overload
    @classmethod
    def load(cls, date: str, setnum: int, mode: str='a', data_dir: str=DEFAULT_DATA_DIRECTORY) -> NewDataStorage:
        pass
    
    @classmethod
    def load(cls, *args, mode: str='a', data_dir: str=DEFAULT_DATA_DIRECTORY) -> NewDataStorage:
        if len(args) == 1:
            return cls(args[0], mode=mode)
        elif len(args) == 2:
            date, setnum = args
            filename = cls.get_template(date, setnum, data_dir=data_dir)
            return cls(filename, mode=mode)
        else:
            raise ValueError("Invalid number of arguments")
    
    def open(self, mode: str='r'):
        self.file = h5py.File(self.filename, mode=mode)
        self.mode = mode
    
    def close(self):
        if self.file is None:
            raise IOError(f'Attempting to close {self.filename} before opening file.')
        self.file.close()
    
    def get(self, name: str) -> H5pyObject:
        return self.file[name]

    def __getitem__(self, key):
        return self.get(key)

    def __delitem__(self, key: str):
        del self.file[key]

    def has(self, name: str, exact_match: bool=False) -> bool:
        res = self.search(name, exact_match=exact_match)
        return res is not None
    
    def __contains__(self, key: str) -> bool:
        return key in self.file
    
    def search(self, name: str, full_name: bool=True, exact_match: bool=False) -> tuple[str, H5pyObject] | None:
        return search(self.file, name, full_name=full_name, exact_match=exact_match)

    def list_datasets(self, full_names: bool=False) -> list[tuple[str, h5py.Dataset]]:
        return list_datasets(self.file, full_names=full_names)
    
    def list_dataset_names(self, full_names: bool=False) -> list[str]:
        l = self.list_datasets(full_names=full_names)
        return [name for (name, _) in l]
    
    def create_group(
        self,
        name: str,
        track_order: bool | None=None,
        track_times: bool | None=None,
    ) -> h5py.Group:
        return self.file.create_group(name, track_order=track_order, track_times=track_times)
    
    def create_dataset(
        self,
        name: str,
        shape: tuple | None=None,
        dtype: npt.DTypeLike | None=None,
        data: npt.ArrayLike | None=None,
        chunks: tuple | bool | None=True,
        **kwargs,
    ) -> h5py.Dataset:
        """Create a new dataset in the file.
        
        Auto chunking enabled by default.
        """
        return self.file.create_dataset(
            name,
            shape=shape,
            dtype=dtype,
            data=data,
            chunks=chunks,
            **kwargs,
        )
    
    @property
    def attrs(self) -> h5py.AttributeManager:
        return self.file.attrs
    
    @property
    def date(self) -> str:
        return self.attrs['date']
    
    @date.setter
    def date(self, date: str):
        self.attrs['date'] = date

    @property
    def setnum(self) -> int:
        return self.attrs['setnum']
    
    @setnum.setter
    def setnum(self, setnum: int):
        self.attrs['setnum'] = setnum

    @staticmethod
    def get_template(date: str, setnum: int, data_dir: str=DEFAULT_DATA_DIRECTORY) -> str:
        raise NotImplementedError("Must be implemented by subclass")

    @property
    def tod_template(self) -> str:
        return get_tod_template(self.date, self.setnum)

    @property
    def azel_template(self) -> str:
        return get_azel_template(self.date, self.setnum)

    @property
    def optcam_template(self) -> str:
        return get_optcam_template(self.date, self.setnum)

    @property
    def consolidated_file_template(self) -> str:
        return get_consolidated_file_template(self.date, self.setnum)
    
    @property
    def processed_file_template(self) -> str:
        return get_processed_file_template(self.date, self.setnum)

    @property
    def file_stub(self) -> str:
        return get_file_stub(self.date, self.setnum)

    @property
    def folder(self) -> Path:
        return Path(self.filename).parent
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class ConsolidatedData(NewDataStorage):
    """Class representing the data from the various sources consolidated into one file.
    
    Combines the data from the TOD files, LO sweeps, and params files into one file.
    """

    @staticmethod
    def get_template(date: str, setnum: int, data_dir=DEFAULT_DATA_DIRECTORY):
        return get_consolidated_file_template(date, setnum, data_dir=data_dir)

    @classmethod
    def from_tod(
        cls,
        date: str,
        setnum: int,
        data_dir: PathLike=DEFAULT_DATA_DIRECTORY,
        downsampling_factor: int=1,
    ) -> ConsolidatedData:
        
        todtemplate = get_tod_template(date, setnum)
        tele_template = Path(get_azel_template(date, setnum))
        optcam_template = Path(get_optcam_template(date , setnum))

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()
        if not optcam_exists:
            # Try old file naming format
            optcam_template = Path(get_optcam_template(date, setnum, old=True))
            optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = h5py.File(tele_template, 'r')
        
        if optcam_exists:
            optcam_file = h5py.File(optcam_template, 'r')
        
        # Find TOD files
        todlist = glob.glob(todtemplate)
        nchan = len(todlist)
        if nchan == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

        # Get the n_tones and n_samples from all TOD files to determine array sizes
        sample_counts = []
        missed_sample_counts = []
        missed_packets_list = []
        tile_names = []
        tone_counts = []
        for file in todlist:
            raw_data = RawDataFile(file, 'r')
            tone_counts.append(raw_data.n_tones[0])

            # TODO: Make kidpy store the tile name in the file
            # Temporary way to determine tile name from file names
            this_file_stem = Path(file).stem
            this_tile_name = this_file_stem[:this_file_stem.index('TOD')].split('_')[1]
            tile_names.append(this_tile_name)

            # Find the total number of samples accounting for missed packets
            # NOTE: Temporary fix until n_sample is fixed in the raw files
            # n_samples = f.n_sample[0]
            n_samples = raw_data.adc_i.shape[-1]

            if hasattr(raw_data, 'pkt_idx'):
                _logger.debug('Using pkt_idx to find missed packets')
                missed_packets = find_missed_packets_with_indices(raw_data.pkt_idx)
            else:
                missed_packets = find_missed_packets(
                    raw_data.timestamp,
                    n_samples
                )

            n_missed = int(np.sum(missed_packets[:, 1]))
            missed_sample_counts.append(n_missed)
            sample_counts.append(n_samples)
            missed_packets_list.append(missed_packets)

            raw_data.fh.close()

        # Normalize samle counts to the minimum across all channels
        total_samples = min(np.add(sample_counts, missed_sample_counts))
        n_samples_ds = int(np.ceil(total_samples / downsampling_factor))

        # NOTE: I forsee a potnetial bug where we try to interpolate the data for channel
        # say 2, which missed packet X, but channel 0 only had X - 1 total packets, so
        # trying to operate on packet X would be out of bounds. For now, we will just
        # limit the total samples to the minimum across all channels, and hope that this
        # doesn't happen.

        if azel_exists:
            # pdb.set_trace()
            az_tel = azel_file['az_tel']
            try:
                za_tel = azel_file['za_tel']
            except:
                za_tel = azel_file['el_tel']
            timestamp_tel = azel_file['timestamp_tel']
            # vis = azel_tfile.root.optical_visibility[0]
            vis = np.nan
            if isinstance(vis, bytes):
                vis = np.nan
        else:
            vis=0.

        # Initialize coalesced data file
        cfile_path = Path(get_consolidated_file_template(date, setnum, data_dir=data_dir))
        if not cfile_path.exists():
            cfile_path.touch(PERMISSIONS_ALL_FULL)
        cdata = cls(cfile_path, mode='w')
        cdata.date = date
        cdata.setnum = setnum

        # Create processing history
        processing_history = cdata.create_group('processing_history')
        step_0 = processing_history.create_group(get_step_group_name(0, 'consolidated'))
        step_0.attrs['name'] = 'ConsolidatedData'
        step_0.attrs['params'] = json.dumps({'downsampling_factor': downsampling_factor})
        step_0.attrs['rfsocinterface_version'] = VERSION
        step_0.attrs['code_version'] = get_git_hash()

        try:
            kidpy_version = version('kidpy3')
        except Exception as e:
            _logger.warning(f'kidpy3 version could not be accessed: {e}')
            kidpy_version = 'N/A'
        step_0.attrs['kidpy_version'] = kidpy_version

        # Initialize global data group
        global_data_group = cdata.create_group('global_data')
        global_data_group.attrs['n_samples'] = n_samples_ds

        # Optical image
        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            if 'optical_image' in optcam_file:
                global_data_group.create_dataset('optical_image', data=optcam_file['optical_image'][:])
            elif 'optical_video' in optcam_file:
                global_data_group.create_dataset('optical_image', data=optcam_file['optical_video'][..., 0])
                global_data_group.create_dataset('optical_video', data=optcam_file['optical_video'])
                global_data_group.create_dataset('optical_video_timestamp', data=optcam_file['timestamp'])
            optcam_file.close()
        else:
            global_data_group.create_dataset('optical_image', data=np.array([]))
        global_data_group.create_dataset('optical_visibility', data=vis)

        chunk_shape_1d = compute_chunk_shape(tuple(), 8, max_chunk_size=total_samples)
        chunk_shape_1d_ds = compute_chunk_shape(tuple(), 8, max_chunk_size=n_samples_ds)
        timestamp = global_data_group.create_dataset(
            'timestamp',
            shape=(n_samples_ds,),
            chunks=chunk_shape_1d_ds,
            dtype=np.float64,
        ) 
        temp_timestamp = global_data_group.create_dataset(
            'temp_timestamp',
            shape=(total_samples,),
            chunks=chunk_shape_1d,
            dtype=np.float64,
        )
        least_samples_channel = np.argmin(np.add(sample_counts, missed_sample_counts))

        # Interpolate timestamp using the channel with the limiting number of samples
        raw_data = RawDataFile(todlist[least_samples_channel], 'r')
        # NOTE: Temporary fix until n_sample is fixed in the raw files
        # n_samples = f.n_sample[0]
        n_samples = raw_data.adc_i.shape[-1]
        this_missed_packets = missed_packets_list[least_samples_channel]
        if hasattr(raw_data, 'pkt_idx'):
            pkt_idx = raw_data.pkt_idx
        else:
            pkt_idx = np.arange(n_samples)
            pkt_idx[this_missed_packets[:, 0]] += this_missed_packets[:, 1]
        _logger.debug('ConsolidatedData: Interpolating timestamp...')
        interpolate_timestamp_streaming(
            raw_data.timestamp,
            temp_timestamp,
            pkt_idx,
        )
        _logger.debug('ConsolidatedData: Downsampling timestamp...')
        chunked_downsample(
            temp_timestamp,
            timestamp,
            downsampling_factor,
            temp_timestamp.chunks[-1],
            use_filter=False,
        )
        raw_data.close()
        fs = 1 / (timestamp[1] - timestamp[0])
        global_data_group.attrs['fs'] = fs

        # Intiialize group for storing data per-channel
        all_channels_group = cdata.create_group('channels')
        all_channels_group.attrs['n_channels'] = nchan

        # Get the data from each channel
        for i_chan, file in enumerate(todlist):
            raw_data = RawDataFile(file, 'r')

            this_missed_packets = missed_packets_list[i_chan]
            this_n_missed = missed_sample_counts[i_chan]

            # Create the HDF5 group for this channel
            this_channel_group = all_channels_group.create_group(get_channel_group_name(i_chan))
            this_channel_group.attrs['tile_name'] = tile_names[i_chan]
            this_channel_group.attrs['lo_freq'] = raw_data.lo_freq[0]
            this_channel_group.attrs['detector_dx_dy_elevation_angle'] = raw_data.detector_dx_dy_elevation_angle[:]
            this_channel_group.attrs['attenuator_settings'] = raw_data.attenuator_settings[:]
            n_tones = raw_data.n_tones[0]
            this_channel_group.attrs['n_tones'] = n_tones

            # Store the tone parameters
            tones_table = this_channel_group.create_dataset('tones', shape=(n_tones,), dtype=TONES_TABLE_DTYPE)

            tones_table['baseband_freq'] = raw_data.baseband_freqs[:]
            tones_table['power'] = raw_data.tone_powers[:]
            tones_table['delta_x'] = raw_data.detector_delta_x[:]
            tones_table['delta_y'] = raw_data.detector_delta_y[:]
            tones_table['beam_amplitude'] = raw_data.detector_beam_ampl[:]
            tones_table['polarization']  = raw_data.detector_pol[:]
            tones_table['dfoverf_per_mK'] = raw_data.dfoverf_per_mK[:] * -1
            chanmask = raw_data.chanmask[:]
            off_res = np.argwhere(chanmask == 0).flatten()
            no_pol = np.argwhere(tones_table['polarization'] < 1).flatten()
            chanmask[no_pol] = -1
            chanmask[off_res] = 0  # Preserve off-resonance indices
            tones_table['chanmask'] = chanmask

            # Copy LO sweep
            this_channel_group.create_dataset('lo_sweep', data=raw_data.lo_sweep[:])

            # Compute the chunk sizes to use
            azel_shape = (n_tones, total_samples) if azel_exists else (n_tones, 1)
            azel_shape_ds = (n_tones, n_samples_ds) if azel_exists else (n_tones, 1)
            chunk_shape_3d = compute_chunk_shape((2, n_tones), 8, max_chunk_size=total_samples)
            chunk_shape_3d_ds = compute_chunk_shape((2, n_tones), 8, max_chunk_size=n_samples_ds)
            chunk_shape_azel = compute_chunk_shape((1,), 8, max_chunk_size=azel_shape[-1])
            chunk_shape_azel_ds = compute_chunk_shape((1,), 8, max_chunk_size=azel_shape_ds[-1])

            # Time ordered data
            time_ordered_data_group = this_channel_group.create_group('time_ordered_data')
            interpolated_samples = time_ordered_data_group.create_dataset(
                'interpolated_samples',
                shape=(0,),
                maxshape=(None,),
                dtype=np.uint32,
            )
            data_IQ = time_ordered_data_group.create_dataset(
                'data_IQ',
                shape=(2, n_tones, n_samples_ds),
                dtype=np.float64,
                chunks=chunk_shape_3d_ds,
                compression='lzf',
                shuffle=True,
            )
            # Create temporary datasets for the pre-downsampled data 
            temp_interpolated_samples = time_ordered_data_group.create_dataset(
                'temp_interpolated_samples',
                shape=(0,),
                maxshape=(None,),
                dtype=np.uint32,
            )
            temp_data_IQ = time_ordered_data_group.create_dataset(
                'temp_data_IQ',
                shape=(2, n_tones, total_samples),
                dtype=np.float64,
                chunks=chunk_shape_3d,
                compression='lzf',
                shuffle=True,
            )
            # Detector Positions
            temp_detector_az = time_ordered_data_group.create_dataset(
                'temp_detector_az',
                shape=azel_shape,
                chunks=chunk_shape_azel,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            temp_detector_za = time_ordered_data_group.create_dataset(
                'temp_detector_za',
                shape=azel_shape,
                chunks=chunk_shape_azel,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            detector_az = time_ordered_data_group.create_dataset(
                'detector_az',
                shape=azel_shape_ds,
                chunks=chunk_shape_azel_ds,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            detector_za = time_ordered_data_group.create_dataset(
                'detector_za',
                shape=azel_shape_ds,
                chunks=chunk_shape_azel_ds,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            
            if hasattr(raw_data, 'pkt_idx'):
                pkt_idx = raw_data.pkt_idx
            else:
                pkt_idx = np.arange(n_samples)
                pkt_idx[this_missed_packets[:, 0]] += this_missed_packets[:, 1]
            valid_tone_index = np.arange(n_tones, dtype=int)

            # Interpolate missing IQ data
            if this_n_missed > 0:
                _logger.debug('ConsolidatedData: Interpolating missing IQ data...')
                interpolate_missing_data(
                    raw_data.adc_i,
                    raw_data.adc_q,
                    temp_timestamp,
                    temp_data_IQ,
                    temp_interpolated_samples,
                    pkt_idx,
                    this_missed_packets,
                    valid_tone_index
                )
            
            _logger.debug('ConsolidatedData: Copying Raw IQ data...')
            chunk_shape_read_adc = compute_chunk_shape((1024, ), 8, max_chunk_size=n_samples)
            for chunk_start, chunk_end, chunk in iterate_chunks(raw_data.adc_i, chunk_size=chunk_shape_read_adc[-1]):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[0, :, sample_indices] = chunk[valid_tone_index]

            for chunk_start, chunk_end, chunk in iterate_chunks(raw_data.adc_q, chunk_size=chunk_shape_read_adc[-1]):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[1, :, sample_indices] = chunk[valid_tone_index]
            
            # Detector Positions
            if azel_exists:
                _logger.debug('ConsolidatedDaata: Computing detector positions...')
                get_detector_positions(
                    temp_timestamp,
                    timestamp_tel[:],
                    az_tel[:],
                    za_tel[:],
                    temp_detector_az,
                    temp_detector_za,
                    tones_table['delta_x'][:],
                    tones_table['delta_y'][:],
                    this_channel_group.attrs['detector_dx_dy_elevation_angle'],
                )

            # Downsample timestamp and IQ data
            _logger.debug('ConsolidatedData: Downsampling IQ data...')
            new_decimate_in_chunks(
                temp_data_IQ,
                data_IQ,
                downsampling_factor,
                chunk_shape=temp_data_IQ.chunks,
            )
            downsampled_interpolated_samples = []
            for sample in temp_interpolated_samples:
                if sample % downsampling_factor == 0:
                    downsampled_interpolated_samples.append(sample // downsampling_factor)
            downsampled_interpolated_samples = np.array(downsampled_interpolated_samples)
            interpolated_samples.resize(downsampled_interpolated_samples.shape)
            interpolated_samples = downsampled_interpolated_samples[:]

            if azel_exists:
                _logger.debug('ConsolidatedData: Downsampling detector position arrays...')
                chunked_downsample(
                    temp_detector_az,
                    detector_az,
                    downsampling_factor,
                    detector_az.chunks[-1],
                    use_filter=False,
                )
                chunked_downsample(
                    temp_detector_za,
                    detector_za,
                    downsampling_factor,
                    detector_za.chunks[-1],
                    use_filter=False,
                )

            # Delete temporary datasets
            del time_ordered_data_group['temp_data_IQ']
            del time_ordered_data_group['temp_interpolated_samples']
            del time_ordered_data_group['temp_detector_az']
            del time_ordered_data_group['temp_detector_za']
            
        # Get rid of full timestamp now that data from all channels read
        del global_data_group['temp_timestamp']

        # Create virtual datasets
        vdsets = cdata.create_group('vdsets')
        total_tones = sum(tone_counts)
        vdsets.attrs['n_tones'] = total_tones
        vdsets.attrs['n_samples'] = n_samples_ds
        channel_groups = all_channels_group.items()
        data_IQ_layout = h5py.VirtualLayout((2, total_tones, n_samples_ds), 'f8')
        azel_shape = (total_tones, n_samples_ds) if azel_exists else (total_tones, 1)
        detector_az_layout = h5py.VirtualLayout(azel_shape, 'f8')
        detector_za_layout = h5py.VirtualLayout(azel_shape, 'f8')
        tones_table_layout = h5py.VirtualLayout((total_tones,), TONES_TABLE_DTYPE)

        i_tone = 0
        for _, channel_group in channel_groups:
            n_tones = channel_group.attrs['n_tones']
            this_data_group = channel_group['time_ordered_data']
            data_IQ_layout[:, i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['data_IQ'])
            detector_az_layout[i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['detector_az'])
            detector_za_layout[i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['detector_za'])
            tones_table_layout[i_tone:i_tone+n_tones] = h5py.VirtualSource(channel_group['tones'])
            i_tone += n_tones
        
        vdsets.create_virtual_dataset('data_IQ', data_IQ_layout)
        vdsets.create_virtual_dataset('detector_az', detector_az_layout)
        vdsets.create_virtual_dataset('detector_za', detector_za_layout)
        vdsets.create_virtual_dataset('tones', tones_table_layout)

        return cdata
    
    def create_processed_data(self, mode:str='a') -> ProcessedData:
        pfile_path = Path(self.processed_file_template)
        self.close()
        shutil.copy2(self.filename, pfile_path)
        if self.mode == 'w':
            self.mode = 'a'
        self.open(self.mode)

        pd = ProcessedData(pfile_path, mode=mode)
        pd.initialize_processed_data_fields()
        return pd


class ProcessedData(NewDataStorage):

    @staticmethod
    def get_template(date: str, setnum: int, data_dir=DEFAULT_DATA_DIRECTORY):
        return get_processed_file_template(date, setnum, data_dir=data_dir)

    def initialize_processed_data_fields(self):
        """Initialize the datasets unique to the ProcessedData File.
        
        Will create the following datasets for each channel:
            * data_gain_phase (2, n_tones, n_samples): Detector data rotated to 
                gain/phase basis.
            * data_freq_diss (2, n_tones, n_samples): Detector data rotated to 
                frequency/dissipation basis.
            * data_mK (n_tones, n_samples): Calibrated detector data in mK units.
            * carrier_amplitudes (2, n_tones): The median I/Q values for each tone.
            * calibration_info (n_tones,): Structered datset containing various 
                information for creating the calibrated data. Contains:
                * adc_units_to_hz: Conversion factor from ADC units (IQ data) to
                    Hz (frequency/dissipation).
                * IQ_to_gain_phase_angle: Angle in radians to rotate IQ basis to
                    gain/phase.
                * IQ_to_freq_diss_angle: Angle in radians to rotate IQ basis to
                    frequency/dissipation.
                * df_per_mK: Conversion factor to convert Hz to mK.
        Also creates virtual datasets for each dataset, combined across channels.
        """
        n_samples = self['global_data'].attrs['n_samples']
        for _, channel_group in self['channels'].items():
            time_ordered_data_group: h5py.Group = channel_group['time_ordered_data']
            n_tones = channel_group.attrs['n_tones']
            data_IQ = time_ordered_data_group['data_IQ']
            tones_table = channel_group['tones']

            # Initialize caliibration-related datasets
            data_gain_phase = time_ordered_data_group.create_dataset_like('data_gain_phase', data_IQ)
            data_freq_diss = time_ordered_data_group.create_dataset_like('data_freq_diss', data_IQ)
            mK_chunks = compute_chunk_shape((n_tones,), 8, max_chunk_size=n_samples)
            data_mK = time_ordered_data_group.create_dataset(
                'data_mK',
                (n_tones, n_samples),
                dtype=np.float64,
                chunks=mK_chunks,
            )
            carrier_amplitudes = time_ordered_data_group.create_dataset(
                'carrier_amplitudes',
                data=np.nanmedian(data_IQ[:], axis=-1)
            )
            calibration_info = channel_group.create_dataset(
                'calibration_info',
                shape=(n_tones,),
                dtype=CALIBRATION_TABLE_DTYPE,
            )

            # Collect calibration information
            sweep = LoSweepData(
                tones_table['baseband_freq'],
                channel_group.attrs['lo_freq'],
                channel_group['lo_sweep'][:],
                tones_table['chanmask'],
            )
            IQ_to_freq_diss_angle, adc_units_to_hz = sweep.freq_direction()
            calibration_info['IQ_to_freq_diss_angle'] = IQ_to_freq_diss_angle
            calibration_info['adc_units_to_hz'] = adc_units_to_hz 

            detector_f = tones_table['baseband_freq'] + channel_group.attrs['lo_freq']
            df_per_mK = compute_df_per_mK(
                tones_table['polarization'],
                tones_table['beam_amplitude'],
                detector_f,
                tones_table['dfoverf_per_mK'],
            )
            calibration_info['df_per_mK'] = df_per_mK

            # Rotate to Gain / Phase
            IQ_to_gain_phase_angle = np.atan2(carrier_amplitudes[0], carrier_amplitudes[1])
            calibration_info['IQ_to_gain_phase_angle'] = IQ_to_gain_phase_angle
            rotate_basis(
                data_IQ,
                data_gain_phase,
                IQ_to_gain_phase_angle,
            )

            # Generate calibrated data
            # First mean center IQ data
            data_IQ[:] = data_IQ[:] - np.mean(data_IQ, axis=-1, keepdims=True)
            generate_calibrated_data(
                data_IQ,
                data_freq_diss,
                data_mK,
                IQ_to_freq_diss_angle,
                adc_units_to_hz,
                df_per_mK,
            )

        # Make virtual datasets for the new stuff
        total_tones = self['vdsets'].attrs['n_tones']
        data_gain_phase_layout = h5py.VirtualLayout((2, total_tones, n_samples), 'f8')
        data_freq_diss_layout = h5py.VirtualLayout((2, total_tones, n_samples), 'f8')
        data_mK_layout = h5py.VirtualLayout((total_tones, n_samples), 'f8')
        carrier_amplitudes_layout = h5py.VirtualLayout((2, total_tones), 'f8')
        calibration_info_layout = h5py.VirtualLayout((total_tones,), CALIBRATION_TABLE_DTYPE)

        i_tone = 0
        for _, channel_group in self['channels'].items():
            n_tones = channel_group.attrs['n_tones']
            this_data_group = channel_group['time_ordered_data']
            data_gain_phase_layout[:, i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['data_gain_phase'])
            data_freq_diss_layout[:, i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['data_freq_diss'])
            data_mK_layout[i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['data_mK'])
            carrier_amplitudes_layout[:, i_tone:i_tone+n_tones] = h5py.VirtualSource(this_data_group['carrier_amplitudes'])
            calibration_info_layout[i_tone:i_tone+n_tones] = h5py.VirtualSource(channel_group['calibration_info'])
            i_tone += n_tones

        self['vdsets'].create_virtual_dataset('data_gain_phase', data_gain_phase_layout)
        self['vdsets'].create_virtual_dataset('data_freq_diss', data_freq_diss_layout)
        self['vdsets'].create_virtual_dataset('data_mK', data_mK_layout)
        self['vdsets'].create_virtual_dataset('carrier_amplitudes', carrier_amplitudes_layout)
        self['vdsets'].create_virtual_dataset('calibration_info', calibration_info_layout)
    
    #
    # Useful getter methods
    #
    def list_history(self) -> list[dict]:
        if not self.has('processing_history'):
            return []
        hist = self['processing_history']
        return list(hist.keys())
    
    def print_history(self, verbose: bool=False):
        if not self.has('processing_history'):
            print('No history')
            return

        hist = self.file['processing_history']

        for k in sorted(hist.keys()):
            step = hist[k]
            name = step.attrs.get('name', '?')
            if verbose:
                print(f'[{k}]:\n{json.dumps(dict(step.attrs), indent=4)}')
            else:
                params = json.loads(step.attrs.get('params', '{}'))

                param_str = ', '.join(f'{k}={v}' for k, v in params.items())
                print(f'[{k}] {name}({param_str})')

    def get_channel_group(self, i_chan: int) -> h5py.Group:
        return self[f'channels/channel_{i_chan:03d}']

    def get_channel_group_from_tile_name(self, tile_name: str) -> h5py.Group:
        tile_names = []
        for _, channel_group in self['channels'].items():
            this_tile_name = channel_group.attrs['tile_name']
            tile_names.append(this_tile_name)
            if this_tile_name == tile_name:
                return channel_group
        raise KeyError(f'Unable to find channel with name "{tile_name}". Tile names found: {tile_names}')
    
    def get_from_channel(self, i_chan: int, obj_name: str) -> H5pyObject:
        return self.get_channel_group(i_chan)[obj_name]
    
    def get_from_all_channels(self, obj_name: str) -> list[H5pyObject]:
        l = []
        for channel_group in self['channels'].values():
            l.append(channel_group[obj_name])
        return l
    
    def search_in_channel(self, i_chan: int, name: str, full_name: bool=True, exact_match: bool=False) -> tuple[str, H5pyObject] | None:
        return search(self.get_channel_group(i_chan), name, full_name=full_name, exact_match=exact_match)

    def search_in_all_channels(self, name: str, full_name: bool=True, exact_match: bool=False) -> list[tuple[str, H5pyObject]] | None:
        l = []
        for channel_group in self['channels'].values():
            l.append(search(channel_group, name, full_name=full_name, exact_match=exact_match))
        return l
    
    def get_n_tones(self, i_chan: int) -> int:
        return self.get_channel_group(i_chan).attrs['n_tones']
    
    def get_chanmask(self, i_chan: int) -> npt.NDArray:
        return  self.get_from_channel(i_chan, 'tones')['chanmask']
    
    def get_onres_ind(self, i_chan: int) -> npt.NDArray:
        return np.argwhere(self.get_chanmask(i_chan) == 1).flatten()

    def get_offres_ind(self, i_chan: int) -> npt.NDArray:
        return np.argwhere(self.get_chanmask(i_chan) == 0).flatten()
    
    #
    # Useful properties 
    #
    @property
    def n_chan(self) -> int:
        return self['channels'].attrs['n_channels']
    
    @property
    def n_samples(self) -> int:
        return self['vdsets'].attrs['n_samples']

    @property
    def n_tones(self) -> int:
        return self['vdsets'].attrs['n_tones']

    @property
    def fs(self) -> float:
        """Return the averaged sampling rate across channels."""
        return self['global_data'].attrs['fs']

    @property
    def virtual_datasets(self) -> h5py.Group:
        return self['vdsets']

    # Time-ordered data
    @property
    def timestamp(self) -> h5py.Dataset:
        return self['global_data/timestamp']

    @property
    def optical_image(self) -> h5py.Dataset:
        return self['global_data/optical_image']
    
    @property
    def optical_visibility(self) -> h5py.Dataset:
        return self['global_data/optical_visibility']

    @property
    def data_IQ(self) -> h5py.Dataset:
        return self['vdsets/data_IQ']

    @property
    def data_gain_phase(self) -> h5py.Dataset:
        return self['vdsets/data_gain_phase']

    @property
    def data_freq_diss(self) -> h5py.Dataset:
        return self['vdsets/data_freq_diss']

    @property
    def data_mK(self) -> h5py.Dataset:
        return self['vdsets/data_mK']

    @property
    def detector_az(self) -> h5py.Dataset:
        return self['vdsets/detector_az']

    @property
    def detector_za(self) -> h5py.Dataset:
        return self['vdsets/detector_za']
    
    #
    # Tone/detector properties
    #
    @property
    def tones_table(self) -> h5py.Dataset:
        return self['vdsets/tones']

    def _set_table_field(self, table_name: str, field_name: str, new_values: npt.NDArray):
        """Utility function for setting table fields.
        
        Setting values through virtual datasets doesn't work for tables, so this is the
        work around.
        """
        i_tone = 0
        for i_chan in range(self.n_chan):
            channel_group = self.get_channel_group(i_chan)
            n_tones = channel_group.attrs['n_tones']
            channel_group[table_name][field_name] = new_values[i_tone:i_tone + n_tones]
            i_tone += n_tones
    
    @property
    def tone_counts(self) -> npt.NDArray:
        counts = []
        for i_chan in range(self.n_chan):
            counts.append(self.get_n_tones(i_chan))
        return np.array(counts)
    
    def get_channel_index_from_tone_index(self, tone_index: int) -> int:
        cumulative_counts = np.cumsum(self.tone_counts)
        channel_index = np.searchsorted(cumulative_counts, tone_index, side='right')
        return channel_index

    @property
    def baseband_freqs(self) -> npt.NDArray:
        return self.tones_table['baseband_freq']
    
    def set_baseband_freqs(self, new_freqs: npt.NDArray):
        self._set_table_field('tones', 'baseband_freq', new_freqs)

    @property
    def tone_powers(self) -> npt.NDArray:
        return self.tones_table['power']
    
    def set_tone_powers(self, new_powers: npt.NDArray):
        self._set_table_field('tones', 'power', new_powers)

    @property
    def chanmask(self) -> npt.NDArray:
        return self.tones_table['chanmask']
    
    def set_chanmask(self, new_chanmask: npt.NDArray):
        self._set_table_field('tones','chanmask', new_chanmask)

    def onres_ind(self) -> npt.NDArray:
        return np.argwhere(self.chanmask == 1)

    def offres_ind(self) -> npt.NDArray:
        return np.argwhere(self.chanmask == 0)

    @property
    def detector_pol(self) -> npt.NDArray:
        return self.tones_table['polarization']
    
    def set_detector_pol(self, new_pols: npt.NDArray):
        self._set_table_field('tones', 'polarization', new_pols)

    @property
    def detector_beam_ampl(self) -> npt.NDArray:
        return self.tones_table['beam_amplitude']
    
    def set_detector_beam_ampl(self, new_ampls: npt.NDArray):
        self._set_table_field('tones','beam_amplitude', new_ampls)

    @property
    def detector_delta_x(self) -> npt.NDArray:
        return self.tones_table['delta_x']
    
    def set_detector_delta_x(self, new_delta_x: npt.NDArray):
        self._set_table_field('tones','delta_x', new_delta_x)

    @property
    def detector_delta_y(self) -> npt.NDArray:
        return self.tones_table['delta_y']

    def set_detector_delta_y(self, new_delta_y: npt.NDArray):
        self._set_table_field('tones', 'delta_y', new_delta_y)

    @property
    def dfoverf_per_mK(self) -> npt.NDArray:
        return self.tones_table['dfoverf_per_mK']
    
    def set_dfoverf_per_mK(self, new_dfoverf_per_mK: npt.NDArray):
        self._set_table_field('tones', 'dfoverf_per_mK', new_dfoverf_per_mK)

    @property
    def carrier_amplitudes(self) -> h5py.Dataset:
        return self['vdsets/carrier_amplitudes']
    
    #
    # Calibration information 
    #
    @property
    def calibration_info(self) -> h5py.Dataset:
        return self['vdsets/calibration_info']

    @property
    def adc_units_to_hz(self) -> npt.NDArray:
        return self.calibration_info['adc_units_to_hz']
    
    def set_adc_units_to_hz(self, new_adc_units_to_hz: npt.NDArray):
        self._set_table_field('calibration_info', 'adc_units_to_hz', new_adc_units_to_hz)

    @property
    def IQ_to_gain_phase_angle(self) -> npt.NDArray:
        return self.calibration_info['IQ_to_gain_phase_angle']
    
    def set_IQ_to_gain_phase_angle(self, new_angle: npt.NDArray):
        self._set_table_field('calibration_info', 'IQ_to_gain_phase_angle', new_angle)

    @property
    def IQ_to_freq_diss_angle(self) -> npt.NDArray:
        return self.calibration_info['IQ_to_freq_diss_angle']
    
    def set_IQ_to_freq_diss_angle(self, new_angle: npt.NDArray):
        self._set_table_field('calibration_info', 'IQ_to_freq_diss_angle', new_angle)

    @property
    def df_per_mK(self) -> npt.NDArray:
        return self.calibration_info['df_per_mK']
    
    def set_df_per_mK(self, new_df_per_mK: npt.NDArray):
        self._set_table_field('calibration_info', 'df_per_mK', new_df_per_mK)


def plot_map(
        map: npt.NDArray,
        map_x: npt.NDArray,
        map_y: npt.NDArray,
        extent: tuple[float, float, float, float],
        max_abs: float=None,
        flagged_map: npt.NDArray=None,
        contour_levels: npt.NDArray=None,
        cb_shrink: float=0.95,
        cb_label: str='Signal (mK)',
        cmap: str='Greys_r',
        title: str='',
        add_x_label: bool=True,
) -> Figure:
    xlim = min(map_x),max(map_x)
    ylim = max(map_y),min(map_y)

    if max_abs is None:
        max_abs = np.nanmax(np.abs(map))

    fig = plt.figure()
    plt.imshow(
        np.flip(np.transpose(map[::-1]),1),
        aspect='equal',
        extent=extent,
        vmin=-max_abs,
        vmax=max_abs,
        cmap=cmap,
    )
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label(cb_label, rotation=270, labelpad=15)
    if flagged_map:
        plt.contour(
            np.flip(np.flip(np.transpose(flagged_map[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )
    plt.title(title)
    if add_x_label:
        plt.xlabel('Azimuth (degrees)')
    plt.ylabel('ZA (degrees)')
    plt.xlim(xlim), plt.ylim(ylim)

    return fig


def find_peaks(data: ProcessedData, primary_direction: str='az'):
    import numpy as np
    from numpy.polynomial import Polynomial
    # find peak going forward / back
    # fit gaussian
    # take position of both peask
    # right is 10-15
    # left is 20-25
    i_res = 241
    right_indices = np.argwhere(np.logical_and(10 <= data.time, data.time <= 15)).flatten()
    left_indices = np.argwhere(np.logical_and(20 <= data.time, data.time <= 25)).flatten()
    telescope_pos = data.detector_az[i_res] if primary_direction.lower() == 'az' else data.detector_za[i_res]

    right_peak_idx = right_indices[np.argmax(data.data_mK[i_res, right_indices])]
    left_peak_idx = left_indices[np.argmax(data.data_mK[i_res, left_indices])]

    right_slice = slice(right_peak_idx - 2, right_peak_idx + 3)
    left_slice = slice(left_peak_idx - 2, left_peak_idx + 3)

    right_fit = Polynomial.fit(telescope_pos[right_slice], data.data_mK[i_res, right_slice], 2).convert()
    left_fit = Polynomial.fit(telescope_pos[left_slice], data.data_mK[i_res, left_slice], 2).convert()

    right_az_0 = (-1 * right_fit.coef[1]) / (2 * right_fit.coef[2])
    left_az_0 = (-1 * left_fit.coef[1]) / (2 * left_fit.coef[2])
    plt.plot(telescope_pos[:], data.data_mK[i_res, :], label=f'Full Trace')
    plt.plot(telescope_pos[right_slice], data.data_mK[i_res, right_slice], label=f'Right {primary_direction.upper()}_0 = {right_az_0}')
    plt.plot(telescope_pos[left_slice], data.data_mK[i_res, left_slice], label=f'Left {primary_direction.upper()}_0 = {left_az_0}')
    scan_rate = (telescope_pos[right_peak_idx + 10] - telescope_pos[right_peak_idx - 10]) \
        / (data.time[right_peak_idx + 10] - data.time[right_peak_idx - 10])
    time_delay = (left_az_0 - right_az_0) / scan_rate / 2  # Amount RFSoC is behind the telescope
    plt.annotate(f'Time Delay (seconds RFSoC lags behind telescope)= {time_delay:.3f}s', (.1, .1), xycoords='axes fraction')
    plt.legend()
    plt.show()



if __name__ == '__main__':
    # Telescope Testing
    date = '20260320'
    setnum = 1010
    # Lab Testing
    # date = '20260212'
    # setnum = 1003

    cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=8)
    pd = cd.create_processed_data()

    pdb.set_trace()
