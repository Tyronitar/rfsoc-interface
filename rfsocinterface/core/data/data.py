"""Core functionality relating to data loading and processing."""


from __future__ import annotations
from pathlib import Path
import glob
import pdb
import time
import logging
from itertools import chain, batched
import typing
from importlib.metadata import version

import tables
import h5py
from tables.link import ExternalLink
import numpy as np
import numpy.typing as npt
from numpy.polynomial import polynomial as poly
from scipy.interpolate import make_interp_spline
from numpy.polynomial import Polynomial
from scipy.stats import linregress
from scipy import signal
from scipy.stats import linregress
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import kidpy3
from kidpy3.data_handler import RawDataFile

from rfsocinterface import __version__ as VERSION
from rfsocinterface.core.losweep import LoSweepData
from rfsocinterface.core.utils import (
    gaussian_filter,
    GAUSSIAN_SIGMA,
    BAD_RFSOC_TONE_START_INDEX,
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
    linregress_in_chunks,
    iterate_chunks,
    compute_chunk_shape,
    chunked_downsample,
    apply_interp,
    build_interp_map,
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


DYNAMIC_PROCESSED_DATA_FIELDS = [
    'carrier_amplitudes',
    'data_IQ',
    'IQ_to_gain_phase_angle',
    'adc_units_to_hz',
    'data_gain_phase',
    'data_freq_diss',
    'data_mK',
    'timestamp',
    'chanmask',
]

STATIC_BASE_PROCESSED_DATA_FIELDS = [
    'dfoverf_per_mK',
    'detector_pol',
    'detector_beam_ampl',
    'optical_visibility',
    'optical_image',
    'baseband_freqs',
    'lo_freq',
    'tones_per_channel'
]


STATIC_PROCESSED_DATA_FIELDS = [
    'detector_az',
    'detector_za',
    'interpolated_indices',
    'df_per_mK',
]

ALL_PROCESSED_DATA_FIELDS = DYNAMIC_PROCESSED_DATA_FIELDS + STATIC_PROCESSED_DATA_FIELDS + STATIC_BASE_PROCESSED_DATA_FIELDS

MAP_DATA_FIELDS = [
    'hits_map',
    'sum_map',
    'map_az',
    'map_za',
    'net',
    'good_samples'
]

ALL_MAP_DATA_FIELDS = ALL_PROCESSED_DATA_FIELDS + MAP_DATA_FIELDS

PROCESSED_DATA_FIELD_LOCATIONS = {
    'carrier_amplitudes': '/data',
    'data_IQ': '/data',
    'IQ_to_gain_phase_angle': '/data',
    'adc_units_to_hz': '/data',
    'data_gain_phase': '/data',
    'data_freq_diss': '/data',
    'data_mK': '/data',
    'timestamp': '/data',
    'interpolated_indices': '/data',
    'detector_az': '/data',
    'detector_za': '/data',
    'optical_image': '/global_data',
    'chanmask': '/global_data',
    'vis': '/global_data',
    'df_per_mK': '/global_data',
    'detector_pol': '/global_data',
    'detector_beam_ampl': '/global_data',
    'optical_visibility': '/global_data',
    'baseband_freqs': '/global_data',
    'lo_freq': '/global_data',
    'tones_per_channel': '/global_data',
    'dfoverf_per_mK': '/global_data',
}


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


def test_node(f: tables.File, name: str) -> bool:
    try:
        f.get_node('/', name)
        return True
    except tables.exceptions.NoSuchNodeError:
        return False

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


def rotate_basis(
        in_data: tables.Array,
        out_data: tables.Array,
        rotation_angle: tables.Array,
        i_chan: int=0,
        valid_tone_indices: npt.NDArray | None=None,
        ):
    """Compute change of basis, rotating with the specified angle."""

    # new_data = np.zeros(shape=(2, np.size(tone_index), data_1.shape[-1]))
    out_data[i_chan, 0, valid_tone_indices] = \
        np.cos(rotation_angle)[i_chan, valid_tone_indices, np.newaxis] * \
        in_data[i_chan, 0, valid_tone_indices] - \
        np.sin(rotation_angle)[i_chan, valid_tone_indices, np.newaxis] * \
        in_data[i_chan, 1, valid_tone_indices]

    out_data[i_chan, 1, valid_tone_indices] = \
        np.sin(rotation_angle)[i_chan, valid_tone_indices, np.newaxis] * \
        in_data[i_chan, 0, valid_tone_indices] - \
        np.sin(rotation_angle)[i_chan, valid_tone_indices, np.newaxis] * \
        in_data[i_chan, 1, valid_tone_indices]


def generate_calibrated_data(data_group: tables.Group, global_data_group: tables.Group):
    nchan = global_data_group._v_attrs.n_channels
    for i_chan in range(nchan):
        rotate_basis(
            data_group.data_gain_phase[:],
            data_group.data_IQ,
            -data_group.IQ_to_gain_phase_angle[:],
            i_chan=i_chan,
            valid_tone_indices=np.arange(global_data_group.tones_per_channel[i_chan]),
        )
    data_group.data_IQ[:] = data_group.data_IQ[:] - np.mean(data_group.data_IQ[:], axis=2, keepdims=True)
    # data.data_IQ[0, :] = data.data_IQ[0, :] - np.mean(data.data_IQ[0, :], axis=1, keepdims=True)
    # data.data_IQ[1, :] = data.data_IQ[1, :] - np.mean(data.data_IQ[1, :], axis=1, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f

    for i_chan in range(nchan):
        rotate_basis(
            data_group.data_IQ[:] / data_group.adc_units_to_hz[:][:, np.newaxis],
            data_group.data_freq_diss,
            data_group.IQ_to_freq_diss_angle[:],
            i_chan=i_chan,
            valid_tone_indices=np.arange(global_data_group.tones_per_channel[i_chan]),
        )
    rotate_basis(data_group.data_IQ[:] / data_group.adc_units_to_hz[:][:, np.newaxis], data_group.data_freq_diss, data_group.IQ_to_freq_diss_angle[:])
    # rotate_basis(data.data_IQ, data.data_freq_diss, data.IQ_to_freq_diss_angle[:])

    # Finally, we need to get data_mK
    data_group.data_mK[:] = np.divide(data_group.data_freq_diss[0, :], global_data_group.df_per_mK[:][:, np.newaxis])
    # data.data_mK[:] = np.where(np.isinf(data.data_mK), np.nan, data.data_mK)

def new_generate_calibrated_data(pd: ProcessedDataL1):
    if isinstance(pd.get_node('data_IQ'), ExternalLink):
        data = pd.data_IQ[:]
        pd.remove_node('/data', 'data_IQ')
        pd.create_array('/data', 'data_IQ', obj=data)
    data_IQ = pd.data_IQ
        

    for i_chan in range(pd.n_channels):
        rotate_basis(
            pd.data_gain_phase[:],
            data_IQ,
            -pd.IQ_to_gain_phase_angle[:],
            i_chan=i_chan,
            valid_tone_indices=np.arange(pd.get_n_tones(i_chan))
        )
    data_IQ[:] = data_IQ[:] - np.mean(data_IQ[:], axis=2, keepdims=True)
    # data.data_IQ[0, :] = data.data_IQ[0, :] - np.mean(data.data_IQ[0, :], axis=1, keepdims=True)
    # data.data_IQ[1, :] = data.data_IQ[1, :] - np.mean(data.data_IQ[1, :], axis=1, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f

    for i_chan in range(pd.n_channels):
        rotate_basis(
            data_IQ[:] / pd.adc_units_to_hz[:][:, :, np.newaxis],
            pd.data_freq_diss,
            pd.IQ_to_freq_diss_angle[:],
            i_chan=i_chan,
            valid_tone_indices=np.arange(pd.get_n_tones(i_chan))
        )
    # rotate_basis(data.data_IQ, data.data_freq_diss, data.IQ_to_freq_diss_angle[:])

    # Finally, we need to get data_mK
    pd.data_mK[:] = np.divide(pd.data_freq_diss[:, 0], pd.df_per_mK[:][:, :, np.newaxis])
    # data.data_mK[:] = np.where(np.isinf(data.data_mK), np.nan, data.data_mK)

#
# Electronics Noise Removal
#

def compute_templates(data: npt.NDArray, max_modes: int=30) -> npt.NDArray:
    """Compute templates for correlated noise removal.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples).

    Returns:
        (npt.NDarray): Templates for noise removal (N_chan x 2 x N_samples).
            Computed using the first two eigenmodes of the correlation matrix.
    """
    # subtract the mean from each detector
    # data_meansub = data - np.mean(data, axis=2)[:, :, np.newaxis]
    deproj = data - np.mean(data, axis=2)[:, :, np.newaxis]
    n_tones = data.shape[1]

    # select only the middle few detectors
    # deproj = data_meansub[:, 8:1008, :]

    # create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(deproj, np.conj(np.transpose(deproj, axes=(0, 2, 1))))
    # calculate the eigenmodes of the correlation matrices
    eigen_values, v = np.linalg.eig(correlation_matrices)
    sorted_indices = np.argsort(eigen_values, axis=1)[:, ::-1]
    sorted_eigen_values = np.take_along_axis(eigen_values, sorted_indices, axis=1)
    sorted_v = np.take_along_axis(v, sorted_indices[:, np.newaxis, :], axis=2)
    
    if n_tones < 25:
        sigma_mult = 1.5
    elif n_tones < 50:
        sigma_mult = 2.5
    else:
        sigma_mult = 3

    n_modes = 2
    new_modes = -1
    while new_modes != 0 and n_modes <= max_modes:
        log_eigen_values = np.log10(sorted_eigen_values[:, n_modes:])
        mu = np.mean(log_eigen_values, axis=1)
        sigma = np.std(log_eigen_values, axis=1)
        large_eigen_values = np.where(log_eigen_values > (mu + sigma_mult * sigma)[:, np.newaxis])
        i_count = large_eigen_values[0].size - np.sum(large_eigen_values[0])
        q_count = large_eigen_values[0].size - i_count
        new_modes = max(i_count, q_count)
        n_modes += new_modes
    # pdb.set_trace()
    n_modes = min(n_modes, max_modes)
    print(f'Using {n_modes} eigen modes')

        # create templates based on the N_mode largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', sorted_v[:,:,0:n_modes], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates


def remove_electronics_noise(data: npt.NDArray, fs: npt.NDArray, lp_filt_freq: float=10, max_modes: int=30) -> npt.NDArray:
    """Remove correlated electronics noise templates from the data.

    Args:
        data (npt.NDArray): Input data (N_chan x 2 x N_tones x N_samples). Data should
            be in the gain/phase basis.
        fs (npt.NDArray): Sampling frequency of the data, per channel.
        lp_filt_freq (float, optional): Low-pass filter frequency for the templates. Defaults to 10 Hz.

    Returns:
        npt.NDarray: Cleaned data (N_chan x 2 x N_tones x N_samples).
    """
    # filt_sos = signal.butter(BUTTER_ORDER, lp_filt_freq, btype='low', fs=fs, output='sos', analog=False)
    # data_lp = signal.sosfiltfilt(filt_sos, data)
    out_data = np.zeros_like(data)

    for i_chan in range(data.shape[0]):
        data_lp = data[i_chan]
        templates = compute_templates(data_lp, max_modes=max_modes)  # 2 x N_modes x N_samples
        n_modes = templates.shape[1]
        denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 2 x N_modes

        for i in range(n_modes):
            numerator = np.einsum('ijk,ik->ij', data_lp, templates[:, i])  # 2 x N_tones
            corr = numerator / denominator[:, i:i+1]  # N_chan x N_tones
            data_lp = data_lp - np.einsum('ij,ikl->ijl', corr, templates[:, i:i+1])  # 2 x N_tones x N_samples
            # data_lp = signal.sosfiltfilt(filt_sos, data)
        
        out_data[i_chan] = data_lp

    # denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2
    # numerator0 = np.einsum('ijk,ik->ij', data_lp, templates[:, 0])  # N_chan x N_detector
    # corr0 = numerator0 / denominator[:, 0:1]  # N_chan x N_detector
    # deproj = data - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    # deproj_lp = signal.sosfiltfilt(filt_sos, deproj)

    # numerator1 = np.einsum('ijk,ik->ij', deproj_lp, templates[:, 1])  # N_chan x N_detector
    # corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    # clean_data = deproj - np.einsum('ij,ikl->ijl', corr1, templates[:, 1:])
    return out_data


def remove_electronics_noise_tables(
    data_gain_phase: tables.Array,
    fs: npt.NDArray,
    lp_filt_freq: float=10,
    max_modes: int=30,
):
    """Remove correlated electronics noise templates from data stored with PyTables.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples). Data should
            be in the gain/phase basis.
        fs (float): Sampling frequency of the data.
        lp_filt_freq (float, optional): Low-pass filter frequency for the templates. Defaults to 10 Hz.

    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    clean_data = remove_electronics_noise(data_gain_phase[:], fs, lp_filt_freq=lp_filt_freq, max_modes=max_modes)
    data_gain_phase[:] = clean_data
    # for i_chan in range(data_gain_phase.shape[0]):
    #     clean_data = remove_electronics_noise(data_gain_phase[i_chan][np.newaxis])
    #     # templates = compute_templates(data_gain_phase[i_chan][np.newaxis]) # 1 x 2 x N_samples

    #     # denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 1 x 2
    #     # pdb.set_trace()
    #     # numerator0 = np.einsum('jk,k->j', data_gain_phase[i_chan], templates[0])  # N_detector
    #     # pdb.set_trace()
    #     # corr0 = numerator0 / denominator[:, 0:1]  # N_detector
    #     # deproj = data_gain_phase[i_chan] - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    #     # numerator1 = np.einsum('ijk,ik->ij', deproj, templates[:, 1])  # N_chan x N_detector
    #     # pdb.set_trace()
    #     # corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    #     data_gain_phase[i_chan, :] = clean_data.squeeze()

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

    # Plotting specfically for 20251006set1009
    # plt.scatter(range(1, n_samples), dtime, label='Delta Time for each sample')
    # plt.scatter(bad_samples + 1, dtime[bad_samples], color='red', label='Flagged Samples')
    # plt.axhline(med_dtime, linestyle='--', color='blue', label=f'Median Delta T $\\mu = {med_dtime:.5f}$')
    # plt.xlim(235450, 235500)
    # plt.ylim(0.00001, 0.2)
    # plt.yscale('log')

    # plt.xlabel('Sample Index')
    # plt.ylabel('Delta Time (s)')
    # plt.legend()
    # plt.show()
    # pdb.set_trace()
    # corrected_packet_idx = np.zeros(n_samples, dtype=int)
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
                    # print(f'Missed {large_missed_packets} in large window, {missed_packets} in original')
                    # plt.scatter(range(large_window_min_idx, large_window_max_idx + 1), large_window)
                    # plt.scatter(range(window_min_idx, window_max_idx + 1), window)
                    # plt.scatter(i, timestamp[i], color='red')
                    # plt.show()
                    # pdb.set_trace()
                    missed_packets = np.vstack([missed_packets, [i, large_window_packets_missed]])
                    # corrected_packet_idx[i] = corrected_packet_idx[i - 1] + large_window_packets_missed + 1

                    # Don't need to re-evaluate the next few samples, since their offset
                    # was already accounted for.
                    # for j in range(i + 1, i + large_window_packets_missed + 1):
                    #     corrected_packet_idx[j] = corrected_packet_idx[j - 1] + 1
                    # i = j
                    continue
                else:
                    # corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
                    pass
            else:
                # corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
                pass

            # plt.scatter(range(window_min_idx, window_max_idx + 1), timestamp_window)
            # plt.show()
            # pdb.set_trace()
        else:
            # corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
            pass
        i += 1

    # new_timestamp.append(fit.slope * corrected_packet_idx + fit.intercept)
    _logger.debug(f'{np.sum(missed_packets[:, 1])} missed packets')

    # Plotting Code for Debugging
    # fit = linregress(corrected_packet_idx, raw_timestamp[:])
    # x = np.arange(n_samples)
    # y = fit.slope * x + fit.intercept
    # plt.scatter(corrected_packet_idx, timestamp[:])
    # plt.scatter(corrected_packet_idx, new_timestamp)
    # plt.plot(x, y, color='red', linestyle='--')
    # plt.show()
    # pdb.set_trace()
    return missed_packets



# Note, I may have to move the downsampling unitl after all of the interpolation
# I should look more into that though (i.e. ask ChatGPT)
def interpolate_timestamp(
    raw_timestamp: h5py.Dataset,
    new_timestamp: h5py.Dataset,
    packet_indices: h5py.Dataset,
    ds_factor: int=1,
):
    chunk_size = new_timestamp.chunks[-1]
    chunk_size_ds = int(np.ceil(chunk_size / ds_factor))

    # TODO: find a way to not have all of normalized_packet_indices in memory at once
    # May require some code duplication, or storing an intermediate array on disk
    normalized_packet_indices = packet_indices - packet_indices[0]
    n_samples = raw_timestamp.size
    n_samples_ds = new_timestamp.size
    a, b = linregress_in_chunks(normalized_packet_indices, raw_timestamp)
    
    # Compute the new timestamp in chunks while simultaneously downsampling
    for i_chunk, chunk_start in enumerate(range(0, n_samples, chunk_size)):
        this_new_timestamp = a * np.arange(chunk_start, chunk_start + chunk_size) + b + RFSOC_TIME_OFFSET
        chunk_start_ds = i_chunk * chunk_size_ds
        chunk_stop_ds = min(chunk_start_ds + chunk_size_ds, n_samples_ds)
        new_timestamp[chunk_start_ds:chunk_stop_ds] = this_new_timestamp[::ds_factor]

    
def interpolate_missing_data(
    input_data_I: h5py.Dataset,
    input_data_Q: h5py.Dataset,
    timestamp: h5py.Dataset,
    output_dset: h5py.Dataset,
    output_indices_dset: h5py.Dataset,
    packet_indices: h5py.Dataset,
    missed_packets: npt.NDArray,
    valid_tone_index: npt.NDArray,
) -> tuple[npt.NDArray. npt.NDArray, npt.NDArray]:
    total_missed_packets = np.sum(missed_packets[:, 1])
    n_tones = np.size(valid_tone_index)
    n_samples = input_data_I.shape[-1]

    # interpolated_indices = []
    # interpolated_data = np.zeros((2, n_tones, total_missed_packets), dtype=input_data_I.dtype)

    # Iterate over the spots where data was missed
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
        # interpolated_indices.extend(this_interpolated_indices)

        old_size = output_indices_dset.size
        output_indices_dset.resize(old_size + np.size(this_interpolated_indices))
        output_indices_dset[old_size:] = this_interpolated_indices
        # data_IQ[:, :, this_interpolated_indices] = new_data
        # interpolated_data[:, :, count:count + this_missed_packets] = new_data
        output_dset[..., window_packet_indices] = new_data
        # count += this_missed_packets

        # Plotting Code for Debugging
        ax = plt.axes(projection='3d')
        x = np.linspace(times[0], times[-1], 150)
        ax.plot3D(x, poly.polyval(x - times[0], fit_I)[0], poly.polyval(x - times[0], fit_Q)[0], label='Polynomial Fit')
        ax.scatter3D(times, i_data[0, :], q_data[0, :], label='Actual Values')
        ax.scatter3D(missed_packet_t, *new_data[:, 0], label='Interpolated Points')
        ax.set_xlabel('Timestamp (s)')
        ax.set_ylabel('ADC I')
        ax.set_zlabel('ADC Q')
        ax.legend()
        plt.show()
        pdb.set_trace()
    # return interpolated_indices, interpolated_data

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

    idx, w = build_interp_map(timestamp, tel_timestamp)

    chunk_size = 200_000
    chunk_size = timestamp.chunks[-1]
    n_samples = timestamp.size
    n_tones = output_detector_az.shape[0]

    for start in range(0, n_samples, chunk_size):

        stop = min(start + chunk_size, n_samples)

        idx_chunk = idx[start:stop]
        w_chunk = w[start:stop]

        # telescope interpolation
        az = (1 - w_chunk) * az_tel[idx_chunk] + w_chunk * az_tel[idx_chunk + 1]
        za = (1 - w_chunk) * za_tel[idx_chunk] + w_chunk * za_tel[idx_chunk + 1]

        # rotation angle
        ang = np.deg2rad(elevation_angle - za)

        cos_ang = np.cos(ang)
        sin_ang = np.sin(ang)

        for tone in range(n_tones):
            output_detector_az[tone, start:stop] = (
                dx[tone] * cos_ang
                - dy[tone] * sin_ang
                + az
            )
            output_detector_za[tone, start:stop] = (
                dy[tone] * cos_ang
                + dx[tone] * sin_ang
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
        self.file = h5py.File(filename, mode=mode)
    
    def has(self, name: str) -> bool:
        def search_fn(string: str):
            if name in string:
                return True
        if self.file.visit(search_fn):
            return True
        return False
    
    def get(self, name: str) -> npt.NDArray:
        return self.file[name]
    
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
    
    def list_datasets(self) -> list[str]:
        datasets = []
        def search_fn(name: str, obj: h5py.Group | h5py.Dataset):
            if isinstance(obj, h5py.Dataset):
                datasets.append(name)
        self.file.visititems(search_fn)
        return datasets

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

    @property
    def receipt(self) -> str:
        return self.attrs['receipt']

    @receipt.setter
    def receipt(self, receipt: str):
        """Add a receipt entry to the processed data file."""
        self.attrs['receipt'] = receipt

    @property
    def tod_template(self) -> str:
        return get_tod_template(self.date, self.setnum)

    @property
    def azel_template(self) -> str:
        return get_azel_template(self.date, self.setnum)

    @property
    def optcam_template(self) -> str:
        return get_optcam_template(self.date ,self.setnum)

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
    def filename(self) -> str:
        return self.file.filename

    @property
    def folder(self) -> Path:
        return Path(self.filename).parent

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()


class ConsolidatedData(NewDataStorage):
    """Class representing the data from the various sources consolidated into one file.
    
    Combines the data from the TOD files, LO sweeps, and params files into one file.
    """

    @classmethod
    def from_tod(
        cls,
        date: str,
        setnum: int,
        data_dir: PathLike=DEFAULT_DATA_DIRECTORY,
        downsampling_factor: int=1,
    ) -> ConsolidatedData:
        

        folder = Path(f'{data_dir}/{date}')
        todtemplate = get_tod_template(date, setnum)
        tele_template = Path(get_azel_template(date, setnum))
        optcam_template = Path(get_optcam_template(date , setnum))

        azel_exists = tele_template.exists()
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
        for file in todlist:
            raw_data = RawDataFile(file, 'r')

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
            # total_samples = n_samples + n_missed
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
            az_tel = azel_file.root.az_tel
            try:
                za_tel = azel_file.root.za_tel
            except:
                za_tel = azel_file.rooe.el_tel
            timestamp_tel = azel_file.root.timestamp_tel
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
        cdata.receipt = ''

        # Initialize global data group
        global_data_group = cdata.create_group('global_data')
        global_data_group.attrs['n_samples'] = n_samples_ds
        global_data_group.attrs['downsampling_factor'] = downsampling_factor
        global_data_group.attrs['rfsocinterface_version'] = VERSION
        try:
            kidpy_version = version(kidpy3)
        except Exception as e:
            _logger.warning(f'kidpy3 version could not be accessed: {e}')
            kidpy_version = 'N/A'
        global_data_group.attrs['kidpy_version'] = kidpy_version

        # Optical image
        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            global_data_group.create_dataset('optical_image', data=optcam_file['optical_image'][:])
            optcam_file.close()
        else:
            global_data_group.create_dataset('optical_image', data=np.array([]))
            optical_image = None
        optical_visibility = global_data_group.create_dataset('optical_visibility', data=vis)

        # Intiialize group for storing data per-channel
        all_channels_group = cdata.create_group('channels')
        all_channels_group.attrs['n_channels'] = nchan


        # Get the data from each channel
        for i_chan, file in enumerate(todlist):
            raw_data = RawDataFile(file, 'r')

            this_missed_packets = missed_packets_list[i_chan]
            this_n_missed = missed_sample_counts[i_chan]

            # Create the HDF5 group for this channel
            this_channel_group = all_channels_group.create_group(f'channel_{i_chan:03d}')
            this_channel_group.attrs['tile_name'] = tile_names[i_chan]
            this_channel_group.attrs['lo_freq'] = raw_data.lo_freq[0]
            this_channel_group.attrs['detector_dx_dy_elevation_angle'] = raw_data.detector_dx_dy_elevation_angle[:]
            this_channel_group.attrs['attenuator_settings'] = raw_data.attenuator_settings[:]

            n_tones = raw_data.n_tones[0]

            # Store the tone parameters
            tones_table = this_channel_group.create_dataset('tones', shape=(n_tones,), dtype=TONES_TABLE_DTYPE)
            # tones_table = np.zeros(n_tones, dtype=TONES_TABLE_DTYPE)

            tones_table['baseband_freq'] = raw_data.baseband_freqs[:]
            tones_table['power'] = raw_data.tone_powers[:]
            tones_table['delta_x'] = raw_data.detector_delta_x[:]
            tones_table['delta_y'] = raw_data.detector_delta_y[:]
            tones_table['beam_amplitude'] = raw_data.detector_beam_ampl[:]
            tones_table['polarization']  = raw_data.detector_pol[:]
            tones_table['dfoverf_per_mK'] = raw_data. dfoverf_per_mK[:]
            tones_table['chanmask'] = raw_data.chanmask[:]

            # Copy LO sweep
            this_channel_group.create_dataset('lo_sweep', data=raw_data.lo_sweep[:])

            # Compute the chunk sizes to use
            azel_shape = (n_tones, total_samples) if azel_exists else (n_tones, 1)
            azel_shape_ds = (n_tones, n_samples_ds) if azel_exists else (n_tones, 1)

            chunk_shape_1d = chunk_shape_1d_ds = compute_chunk_shape(tuple(), 8)
            chunk_shape_3d = chunk_shape_3d_ds = compute_chunk_shape((2, n_tones), 8)
            chunk_shape_azel = chunk_shape_azel_ds = compute_chunk_shape(azel_shape[:-1], 8)
            if chunk_shape_1d[-1] > total_samples:
                chunk_shape_1d = (*chunk_shape_1d[:-1], total_samples)
                chunk_shape_3d = (*chunk_shape_3d[:-1], total_samples)
            if chunk_shape_azel[-1] > azel_shape[-1]:
                chunk_shape_azel = (*chunk_shape_azel[:-1], azel_shape[-1])
            if chunk_shape_azel_ds[-1] > azel_shape_ds[-1]:
                chunk_shape_azel_ds = (*chunk_shape_azel_ds[:-1], azel_shape[-1])
            if chunk_shape_1d_ds[-1] > n_samples_ds:
                chunk_shape_1d_ds = (*chunk_shape_1d_ds[:-1], n_samples_ds)
                chunk_shape_3d_ds = (*chunk_shape_3d_ds[:-1], n_samples_ds)


            # Time ordered data
            time_ordered_data_group = this_channel_group.create_group('time_ordered_data')
            timestamp = time_ordered_data_group.create_dataset(
                'timestamp',
                shape=(n_samples_ds,),
                chunks=chunk_shape_1d_ds,
                dtype=np.float64,
            )
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
            temp_timestamp = time_ordered_data_group.create_dataset(
                'temp_timestamp',
                shape=(total_samples,),
                chunks=chunk_shape_1d,
                dtype=np.float64,
            )
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
                shape=azel_shape,
                chunks=chunk_shape_azel_ds,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            detector_za = time_ordered_data_group.create_dataset(
                'detector_za',
                shape=azel_shape,
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

            # Interpolate the timestamp
            interpolate_timestamp(
                raw_data.timestamp,
                temp_timestamp,
                pkt_idx,
            )

            # valid_tone_index = np.arange(n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX
            valid_tone_index = np.arange(n_tones, dtype=int) + 8  # TODO: How to make this backwards compatible?
            # Interpolate missing IQ data
            if this_n_missed > 0:
                print('interpolating data...')
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
            
            print('Copying Raw IQ data')
            for chunk_start, chunk_end, chunk in iterate_chunks(raw_data.adc_i, chunk_size=temp_data_IQ.chunks[-1]):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[0, :, sample_indices] = chunk[valid_tone_index]

            for chunk_start, chunk_end, chunk in iterate_chunks(raw_data.adc_q, chunk_size=temp_data_IQ.chunks[-1]):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[1, :, sample_indices] = chunk[valid_tone_index]
            


            # Detector Positions
            if azel_exists:
                get_detector_positions(
                    temp_timestamp,
                    timestamp_tel,
                    az_tel,
                    za_tel,
                    temp_detector_az,
                    temp_detector_za,
                    tones_table['delta_x'],
                    tones_table['delta_y'],
                    this_channel_group.attrs['detector_dx_dy_elevation_angle'],
                )

            # Downsample timestamp and IQ data
            print('Downsampling data...')
            chunked_downsample(
                temp_timestamp,
                timestamp,
                downsampling_factor,
                temp_timestamp.chunks[-1]
            )
            chunked_downsample(
                temp_data_IQ,
                data_IQ,
                downsampling_factor,
                data_IQ.chunks[-1],
            )
            downsampled_interpolated_samples = []
            for sample in temp_interpolated_samples:
                if sample % downsampling_factor == 0:
                    downsampled_interpolated_samples.append(sample // downsampling_factor)
            downsampled_interpolated_samples = np.array(downsampled_interpolated_samples)
            # downsampled_interpolated_samples = temp_interpolated_samples[temp_interpolated_samples % downsampling_factor == 0] // downsampling_factor
            interpolated_samples.resize(downsampled_interpolated_samples.shape)
            interpolated_samples = downsampled_interpolated_samples[:]

            if azel_exists:
                chunked_downsample(
                    temp_detector_az,
                    detector_az,
                    downsampling_factor,
                    detector_az.chunks[-1],
                )
                chunked_downsample(
                    temp_detector_za,
                    detector_za,
                    downsampling_factor,
                    detector_za.chunks[-1],
                )

            # Delete temporary datasets
            # del temp_timestamp, temp_data_IQ, temp_interpolated_samples
            # del temp_detector_az, temp_detector_za
            
            # Store chanmask from TOD
            # this_chanmask = raw_global_data.chanmask[:]
            # off_res = np.argwhere(this_chanmask == 0).flatten()
            # no_pol = np.argwhere(this_detector_pol[:] < 1).flatten()
            # this_chanmask[no_pol] = -1
            # # Preserve off-resonance indices
            # this_chanmask[off_res] = 0
            # chanmask[i, :] = pad_to_length(this_chanmask, max_n_tones, constant_values=-1)

            ...

        # iq = cd.get('/channels/channel_000/time_ordered_data/temp_data_IQ')
        plt.plot(np.arange(n_samples), temp_data_IQ[0, 0], label='Full data')
        plt.plot(np.arange(0, n_samples, downsampling_factor), data_IQ[0, 0], label='Downsampled data')
        plt.legend()
        plt.show()
        pdb.set_trace()
        return cdata



class PyTablesDataset:
    """Class for handling PyTables datasets and links.
    
    Will store an external link to a previous dataset until a write operation is
    attempted, at which point it will copy the data to the new file.
    """
    def __init__(self, data: tables.Array | ExternalLink, file: tables.File):
        self._data = data
        self._file = file
    
    def __str__(self):
        return str(self._data)
    
    def __repr__(self):
        return f'PyTablesDataset({self._data}, {self._file.filename})'
    
    def __setitem__(self, key, value):
        # Dereference link if necessary
        if isinstance(self._data, ExternalLink):
            parent_node = self._data._v_parent
            old_array: tables.Array = self._data(mode='r')
            # Copy over data from old array to the new file before setting anything
            temp_name = self._data._v_name + '_temp'
            self._file.rename_node(self._data, temp_name)
            new_array = self._file.copy_node(old_array, parent_node, overwrite=True)
            self._file.remove_node(parent_node, temp_name)
            self._data = new_array
        self._data[key] = value
    
    def __getitem__(self, key: slice):
        # Dereference link if necessary
        if isinstance(self._data, ExternalLink):
            return self._data(mode='r')[key]
        return self._data[key]
    
    @property
    def shape(self) -> tuple[int, ...]:
        if isinstance(self._data, ExternalLink):
            return self._data(mode='r').shape
        return self._data.shape
    
    @property
    def ndim(self) -> int:
        return len(self.shape)
    
class DataStorage:
    """Class contianing data from processed TOD files."""
    def __init__(self, file: tables.File):
        self._file = file
 
    def test_node(self, name: str) -> bool:
        try:
            self.find_node(name)
            return True
        except tables.exceptions.NoSuchNodeError:
            return False
    
    def find_node(self, name: str, where: tables.Group | str='/') -> tables.Node:
        for node in self._file.walk_nodes(where):
            if node._v_name == name:
                return node
        raise tables.exceptions.NoSuchNodeError(f'group `{where}` does not have a child named `{name}`')
    
    def close(self):
        self._file.close()
    
    def open(self, mode: str='r'):
        self._file = tables.open_file(self.filename, mode=mode)
    
    @property
    def root(self) -> tables.Group:
        return self._file.root

    def get_node(self, name: str, where: str='/') -> tables.Node:
        return self.find_node(name, where=where)
        # return self._file.get_node(where, name)

    def get_node_value(self, name: str, where: str='/') -> tables.Array:
        node = self.get_node(name, where=where)
        # Dereference link if necessary
        if isinstance(node, ExternalLink):
            return node(mode='r')
        return node

    def create_array(
            self,
            where: tables.Group | str,
            name: str,
            obj: npt.NDArray | None=None,
            atom: tables.Atom | None=None,
            shape: tuple[int, ...] | None=None,
    ) -> tables.Array:
        return self._file.create_array(where, name, shape=shape, obj=obj, atom=atom)

    def create_earray(
            self,
            where: tables.Group | str,
            name: str,
            obj: npt.NDArray | None=None,
            atom: tables.Atom | None=None,
            shape: tuple[int, ...] | None=None,
            expectedrows: int=1000,
    ) -> tables.Array:
        return self._file.create_earray(where, name, shape=shape, obj=obj, atom=atom, expectedrows=expectedrows)
    
    def create_vlarray(
            self,
            where: tables.Group | str,
            name: str,
            obj: npt.NDArray | None=None,
            atom: tables.Atom | None=None,
            expectedrows: int=1000,
    ) -> tables.Array:
        return self._file.create_vlarray(where, name, obj=obj, atom=atom, expectedrows=expectedrows)
    
    def create_group(self, where: tables.Group | str, name: str) -> tables.Group:
        return self._file.create_group(where, name)
    
    def create_external_link(self, where: tables.Group | str, name: str, target: str) -> ExternalLink:
        return self._file.create_external_link(where, name, target)
    
    def remove_node(self, where: tables.Group | str, name: str):
        self._file.remove_node(where, name)

    @property
    def tod_template(self) -> str:
        return get_tod_template(self.date, self.setnum)

    @property
    def azel_template(self) -> str:
        return get_azel_template(self.date, self.setnum)

    @property
    def optcam_template(self) -> str:
        return get_optcam_template(self.date ,self.setnum)
    
    @property
    def processed_file_template(self) -> str:
        return get_processed_file_template(self.date, self.setnum, level=self.level)

    @property
    def cleaned_file_template(self) -> str:
        return get_cleaned_file_template(self.date ,self.setnum)

    @property
    def map_file_template(self) -> str:
        return get_map_file_template(self.date, self.setnum)

    @property
    def beammap_file_template(self) -> str:
        return get_beammap_file_template(self.date, self.setnum)
    
    @property
    def file_stub(self) -> str:
        return get_file_stub(self.date, self.setnum)

    @property
    def folder(self) -> Path:
        return Path(f'{DEFAULT_DATA_DIRECTORY}/{self.date}')
    
    @property
    def filename(self) -> str:
        return self._file.filename
    
    @property
    def date(self) -> str:
        return self._file.root._v_attrs.date
    
    @date.setter
    def date(self, date: str):
        self._file.root._v_attrs.date = date

    @property
    def setnum(self) -> int:
        return self._file.root._v_attrs.setnum
    
    @setnum.setter
    def setnum(self, setnum: int):
        self._file.root._v_attrs.setnum = setnum

    @property
    def receipt(self) -> str:
        return self._file.root._v_attrs.receipt 

    def add_receipt(self, receipt: str):
        """Add a receipt entry to the processed data file."""
        self._file.root._v_attrs.receipt = receipt
        self._file.flush()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class BaseProcessedData(DataStorage):

    def __init__(self, file: tables.File, level: int=1):
        super().__init__(file)
        self.level = level

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r', level: int=1):
        fname = get_processed_file_template(date, setnum, level=level)
        return cls(tables.File(fname, mode=mode), level=level)
    
    @ensure_path(1)
    def compile_to_file(self, path: Path, datasets: list[str]=None, mode: str='w') -> tables.File:
        if not path.exists():
            path.touch(PERMISSIONS_ALL_FULL)
        new_file = tables.open_file(path, mode=mode)

        new_file.root._v_attrs.date = self.date
        new_file.root._v_attrs.setnum = self.setnum
        new_file.root._v_attrs.receipt = self.receipt

        if datasets is None:
            datasets = ALL_PROCESSED_DATA_FIELDS
        for dataset in datasets:
            new_file.create_array('/', dataset, obj=getattr(self, dataset)[:])
        
        return new_file

    def get_node(self, name: str, where: str='/') -> tables.Node:
        if where is None:
            where = PROCESSED_DATA_FIELD_LOCATIONS[name]
        return super().get_node(name, where=where)
    
    @property
    def global_data_group(self) -> tables.Group:
        return self._file.root.global_data

    @property
    def data_group(self) -> tables.Group:
        return self._file.root.data

    @property
    def lo_sweep_group(self) -> tables.Group:
        return self._file.root.lo_sweep
    
    def get_combined_lo_sweep_data_array(self) -> npt.NDArray:
        lo_sweep = None
        for node in self.lo_sweep_group._f_walknodes('ExternalLink'):
            this_lo_sweep = node(mode='r')[:]
            if lo_sweep is None:
                lo_sweep = this_lo_sweep
            else:
                lo_sweep = np.append(lo_sweep, this_lo_sweep, axis=1)
        return lo_sweep

    def get_lo_sweep_data_array(self, i_chan: int) -> npt.NDArray:
        total_array = self.get_combined_lo_sweep_data_array()
        return total_array[:, np.sum(self.tones_per_channel[:i_chan]):np.sum(self.tones_per_channel[:i_chan + 1])]
    
    def get_lo_sweep_data(self, i_chan: int) -> LoSweepData:
        return LoSweepData(
            self.get_baseband_freqs(i_chan),
            self.lo_freq[i_chan],
            self.get_lo_sweep_data_array(i_chan),
            self.get_chanmask(i_chan),
        )
    
    @property
    def lo_freq(self) -> tables.Array:
        return self.get_node_value('lo_freq')

    def get_lo_freq(self, i_chan: int) -> float:
        return self.lo_freq[i_chan]
    
    @property
    def tones_per_channel(self) -> tables.Array:
        return self.get_node_value('tones_per_channel')

    @property
    def baseband_freqs(self) -> tables.Array:
        return self.get_node_value('baseband_freqs')
    
    def get_baseband_freqs(self, i_chan: int) -> npt.NDArray:
        return self.baseband_freqs[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def tones(self) -> npt.NDArray:
        return self.baseband_freqs[:] + self.lo_freq
    
    def get_tones(self, i_chan: int) -> npt.NDArray:
        return self.get_baseband_freqs(i_chan) + self.lo_freq

    @property
    def tones_per_channel(self) -> tables.Array:
        return self.get_node_value('tones_per_channel')

    def get_n_tones(self, i_chan: int) -> int:
        return self.tones_per_channel[i_chan]
    
    @property
    def max_n_tones(self) -> int:
        return max(self.tones_per_channel[:])
    
    @property
    def n_tones_total(self) -> int:
        return np.sum(self.tones_per_channel[:])
    
    @property
    def n_channels(self) -> int:
        return self._file.root.global_data._v_attrs.n_channels
    
    @n_channels.setter
    def n_channels(self, n_channels: int):
        self._file.root.global_data._v_attrs.n_channels = n_channels

    @property
    def n_samples(self) -> int:
        return self._file.root.data._v_attrs.n_samples

    @n_samples.setter
    def n_samples(self, n_samples: int):
        self._file.root.data._v_attrs.n_samples = n_samples
    
    @property
    def optical_image(self) -> tables.Array:
        return self.get_node_value('optical_image')

    @property
    def data_IQ(self) -> tables.Array:
        return self.get_node_value('data_IQ')
    
    def get_data_IQ(self, i_chan: int) -> npt.NDArray:
        return self.data_IQ[i_chan, :, :self.tones_per_channel[i_chan]]
    
    def get_all_data_I(self) -> npt.NDArray:
        return self.data_IQ[:, 0, :]
    
    def get_data_I(self, i_chan: int) -> npt.NDArray:
        return self.data_IQ[i_chan, 0, :self.tones_per_channel[i_chan]]
    
    def get_all_data_Q(self) -> npt.NDArray:
        return self.data_IQ[:, 1, :]

    def get_data_Q(self, i_chan: int) -> npt.NDArray:
        return self.data_IQ[i_chan, 1, :self.tones_per_channel[i_chan]]

    @property
    def interpolated_indices(self) -> tables.VLArray:
        return self.get_node_value('interpolated_indices')
    
    def get_interpolated_indices(self, i_chan: int) -> npt.NDArray:
        return self.interpolated_indices[i_chan, :]
  
    @property
    def timestamp(self) -> tables.Array:
        return self.get_node_value('timestamp')
    
    def get_timestamp(self, i_chan: int) -> npt.NDArray:
        return self.timestamp[i_chan, :]

    @property
    def time(self) -> npt.NDArray:
        return self.timestamp[:] - self.timestamp[:, 0]
    
    def get_time(self, i_chan: int) -> npt.NDArray:
        timestamp = self.get_timestamp(i_chan)
        return timestamp - timestamp[0]
    
    @property
    def delta_t(self) -> npt.NDarray:
        return np.median(self.time - np.roll(self.time, 1), axis=1)
    
    def get_delta_t(self, i_chan: int) -> float:
        time = self.get_time(i_chan)
        return np.median(time - np.roll(time, 1))

    @property
    def fs(self) -> npt.NDArray:
        return 1 / self.delta_t
    
    def get_fs(self, i_chan: int) -> float:
        return 1 / self.get_delta_t(i_chan)
    
    @property
    def detector_az(self) -> tables.Array:
        return self.get_node_value('detector_az')
    
    def get_detector_az(self, i_chan: int) -> npt.NDArray:
        return self.detector_az[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def detector_za(self) -> tables.Array:
        return self.get_node_value('detector_za')
    
    def get_detector_za(self, i_chan: int) -> npt.NDArray:
        return self.detector_za[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def optical_visibility(self) -> tables.Array:
        return self.get_node_value('optical_visibility')

    @property
    def dfoverf_per_mK(self) -> tables.Array:
        return self.get_node_value('dfoverf_per_mK')
    
    def get_dfoverf_per_mK(self, i_chan: int) -> npt.NDArray:
        return self.dfoverf_per_mK[i_chan, :self.tones_per_channel[i_chan]]
        
    @property
    def detector_beam_ampl(self) -> tables.Array:
        return self.get_node_value('detector_beam_ampl')
    
    def get_detector_beam_ampl(self, i_chan: int) -> npt.NDArray:
        return self.detector_beam_ampl[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def detector_pol(self) -> tables.Array:
        return self.get_node_value('detector_pol')
    
    def get_detector_pol(self, i_chan: int) -> npt.NDArray:
        return self.detector_pol[i_chan, :self.tones_per_channel[i_chan]]
    
    @property
    def chanmask(self) -> tables.Array:
        return self.get_node_value('chanmask')
    
    def get_chanmask(self, i_chan: int) -> npt.NDArray:
        return self.chanmask[i_chan, :self.tones_per_channel[i_chan]]


class ProcessedDataL0(BaseProcessedData):
    """Class for interpolating data where needed from the raw TOD files."""

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r') -> ProcessedDataL0:
        return super(ProcessedDataL0, cls).from_file(date, setnum, mode=mode, level=0)

    @classmethod
    def from_tod(
        cls,
        date: str,
        setnum: int,
        beam_map_mode: bool=False,
    ) -> ProcessedDataL0:

        folder = Path(f'{DEFAULT_DATA_DIRECTORY}/{date}')
        todtemplate = get_tod_template(date, setnum)
        tele_template = Path(get_azel_template(date, setnum))
        optcam_template = Path(get_optcam_template(date ,setnum))

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = tables.open_file(tele_template, 'r')
        
        if optcam_exists:
            optcam_file = tables.open_file(optcam_template, 'r')
        

        # Find TOD files
        todlist = glob.glob(todtemplate)
        nchan = len(todlist)
        if nchan == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

        # Get the n_tones and n_samples from all TOD files to determine array sizes
        sample_counts = []
        tone_counts = []
        missed_sample_counts = []
        missed_packets_list = []
        corrected_packet_index_list = []
        for file in todlist:
            with tables.open_file(file, 'r') as f:
                # Find number of tones
                raw_dimension = f.root.dimension
                n_tones = raw_dimension.n_tones[0]
                tone_counts.append(n_tones)

                # Find the total number of samples accounting for missed packets
                raw_time_ordered_data = f.root.time_ordered_data
                # NOTE: Temporary fix until n_sample is fixed in the raw files
                # n_samples = raw_dimension.n_sample[0]
                n_samples = raw_time_ordered_data.adc_i.shape[-1]
                raw_timestamp = raw_time_ordered_data.timestamp[:n_samples]
                print('finding missed packets...')
                if hasattr(raw_time_ordered_data, 'pkt_idx'):
                    print('using pkt_idx to find missed packets')
                    missed_packets = find_missed_packets_with_indices(raw_time_ordered_data.pkt_idx)
                    this_corrected_packet_index = raw_time_ordered_data.pkt_idx[:]
                else:
                    missed_packets, this_corrected_packet_index = find_missed_packets(
                        raw_timestamp,
                        n_samples
                    )
                corrected_packet_index_list.append(this_corrected_packet_index)
                n_missed = int(np.sum(missed_packets[:, 1]))
                missed_sample_counts.append(n_missed)
                # total_samples = n_samples + n_missed
                sample_counts.append(n_samples)
                missed_packets_list.append(missed_packets)

        max_n_tones = int(sum(tone_counts))
        max_missed_samples = int(max(missed_sample_counts))
        tones_per_channel = np.array(tone_counts, dtype=np.uint32)

        # Normalize samle counts to the minimum across all channels
        total_samples = min(np.add(sample_counts, missed_sample_counts))

        # NOTE: I forsee a potnetial bug where we try to interpolate the data for channel
        # say 2, which missed packet X, but channel 0 only had X - 1 total packets, so
        # trying to operate on packet X would be out of bounds. For now, we will just
        # limit the total samples to the minimum across all channels, and hope that this
        # doesn't happen.

        if azel_exists:
            # pdb.set_trace()
            az_tel = azel_file.root.az_tel
            try:
                za_tel = azel_file.root.za_tel
            except:
                za_tel = azel_file.rooe.el_tel
            timestamp_tel = azel_file.root.timestamp_tel
            # vis = azel_tfile.root.optical_visibility[0]
            vis = np.nan
            if isinstance(vis, bytes):
                vis = np.nan
        else:
            vis=0.

        # Create processed data file
        pfile_path = Path(get_processed_file_template(date, setnum, level=0))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.open_file(pfile_path, 'w')
        pfile.root._v_attrs.date = date
        pfile.root._v_attrs.setnum = setnum
        pfile.root._v_attrs.receipt = ''

        time_ordered_data_group = pfile.create_group('/', 'data')
        global_data_group = pfile.create_group('/', 'global_data')
        global_data_group._v_attrs.n_channels = nchan
        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            pfile.create_array(global_data_group, 'optical_image', obj=optcam_file.root.optical_image[:])
            optcam_file.close()
        else:
            pfile.create_array(global_data_group, 'optical_image', obj=np.array([]))
            optical_image = None
        dfoverf_per_mK = pfile.create_array(global_data_group, 'dfoverf_per_mK', shape=(nchan, max_n_tones), atom=tables.Float64Atom())
        detector_beam_amplitude = pfile.create_array(global_data_group, 'detector_beam_ampl', shape=(nchan, max_n_tones), atom=tables.Float64Atom())
        chanmask = pfile.create_array(global_data_group, 'chanmask', shape=(nchan, max_n_tones), atom=tables.Int8Atom(dflt=1))
        baseband_freqs = pfile.create_array(global_data_group, 'baseband_freqs', shape=(nchan, max_n_tones), atom=tables.Float64Atom())
        # chanmask[:] = 1
        detector_pol = pfile.create_array(global_data_group, 'detector_pol', shape=(nchan, max_n_tones), atom=tables.Int8Atom())
        optical_visibility = pfile.create_array(global_data_group, 'optical_visibility', obj=vis)
        tones_per_channel_array = pfile.create_array(global_data_group, 'tones_per_channel', obj=tones_per_channel)
        lo_freq_array = pfile.create_array(global_data_group, 'lo_freq', shape=(nchan,), atom=tables.Float64Atom())

        lo_group = pfile.create_group('/', 'lo_sweep')

        # Can now initialize time-ordered data arrays
        time_ordered_data_group._v_attrs.n_samples = total_samples
        timestamp = pfile.create_array(time_ordered_data_group, 'timestamp', shape=(nchan, total_samples,), atom=tables.Float64Atom())
        interpolated_indices = pfile.create_vlarray(time_ordered_data_group, 'interpolated_indices', expectedrows=max_missed_samples, atom=tables.UInt32Atom())
        chunkshape = (1, 1, int(5e5))
        clevel = 4
        cname = 'lz4'
        tables_filters = tables.Filters(
            complevel=clevel,
            complib="blosc2:%s" % cname,
            shuffle=True,
        )
        # data_IQ = pfile.create_array(time_ordered_data_group, 'data_IQ', shape=(2, n_tones, total_samples), atom=tables.Float64Atom())
        data_IQ = pfile.create_array(time_ordered_data_group, 'data_IQ', shape=(nchan, 2, max_n_tones, total_samples), atom=tables.Float64Atom())
        azel_shape = (nchan, max_n_tones, n_samples) if azel_exists else (nchan, max_n_tones, 1)
        detector_az = pfile.create_array(time_ordered_data_group, 'detector_az', shape=azel_shape, atom=tables.Float64Atom())
        detector_za = pfile.create_array(time_ordered_data_group, 'detector_za', shape=azel_shape, atom=tables.Float64Atom())

        # Iterate over the TOD Files, extracting IQ data and calibration info
        for i, file in enumerate(todlist):
            with tables.open_file(file, 'r') as f:
                raw_global_data = f.root.global_data
                raw_time_ordered_data = f.root.time_ordered_data
                this_n_tones = tones_per_channel[i]
                this_missed_packets = missed_packets_list[i]
                this_n_missed = missed_sample_counts[i]

                raw_timestamp = raw_time_ordered_data.timestamp[:total_samples]

                # Get the correct tone indices in the TOD file
                if int(date[:4]) < 2025:
                    expr = tables.Expr('time_ordered_data.adc_i[:, 0] != 0')
                    expr.eval()
                    valid_tone_index = np.ndarray.flatten(np.argwhere(expr))
                    valid_tone_index = valid_tone_index[:this_n_tones]
                else:
                    valid_tone_index = np.arange(this_n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX

                this_corrected_packet_index = corrected_packet_index_list[i][:total_samples]
                normalized_packet_indices = this_corrected_packet_index - this_corrected_packet_index[0]

                print('interpolating timestamp...')
                interpolated_timestamp = interpolate_timestamp(
                    raw_timestamp,
                    timestamp,
                    i,
                    this_corrected_packet_index,
                )

                this_data_IQ = np.zeros((2, 1024, total_samples))
                # Interpolate Data
                if this_n_missed > 0:
                    print('interpolating data...')
                    this_interpolated_indices, interpolated_data = interpolate_missing_data(
                        raw_time_ordered_data.adc_i,
                        raw_time_ordered_data.adc_q,
                        interpolated_timestamp,
                        this_missed_packets,
                        this_corrected_packet_index,
                        valid_tone_index
                    )
                    interpolated_indices.append(this_interpolated_indices)
                else:
                    interpolated_indices.append([])

                # Read IQ data
                print('copying IQ data from raw file...')
                this_data_IQ[0, :][:, normalized_packet_indices] = raw_time_ordered_data.adc_i[:]
                this_data_IQ[1, :][:, normalized_packet_indices] = raw_time_ordered_data.adc_q[:]
                this_data_IQ = this_data_IQ[:, valid_tone_index]
                if this_n_missed > 0:
                    this_data_IQ[:, :, this_interpolated_indices] = interpolated_data
                data_IQ[i, :] = this_data_IQ[:, :max_n_tones]
                print('done copying data')

                # Link to LO sweep
                pfile.create_external_link(lo_group, f'lo_sweep_{i}', f'{file}:/global_data/lo_sweep')
                lo_freq = raw_global_data.lo_freq[:]
                lo_freq_array[i] = lo_freq
                baseband_freqs[i, :] = pad_to_length(raw_global_data.baseband_freqs[:], max_n_tones)
            
                # Copy calibration factors
                this_detector_pol = raw_global_data.detector_pol[:]
                if np.count_nonzero(this_detector_pol) == 0:
                    this_detector_pol = np.ones_like(this_detector_pol)
                detector_pol[i, :] = pad_to_length(this_detector_pol, max_n_tones)

                this_detector_beam_ampl = raw_global_data.detector_beam_ampl[:]
                if np.count_nonzero(this_detector_beam_ampl) == 0:
                    this_detector_beam_ampl = np.ones_like(this_detector_beam_ampl)
                detector_beam_amplitude[i, :] = pad_to_length(this_detector_beam_ampl, max_n_tones)

                this_dfoverf_per_mK = raw_global_data.dfoverf_per_mK[:] * -1
                if np.count_nonzero(this_dfoverf_per_mK) == 0:
                    this_dfoverf_per_mK = np.ones_like(this_dfoverf_per_mK)
                dfoverf_per_mK[i, :] = pad_to_length(this_dfoverf_per_mK, max_n_tones)

                if azel_exists:
                    detector_dx_dy_elevation_angle = raw_global_data.detector_dx_dy_elevation_angle[0]
                    this_az_tel = np.interp(interpolated_timestamp, timestamp_tel, az_tel)
                    this_za_tel = np.interp(interpolated_timestamp, timestamp_tel, za_tel)
                    this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_za_tel)
                    this_detector_delta_x = raw_global_data.detector_delta_x[:]
                    this_detector_delta_y = raw_global_data.detector_delta_y[:]
                    if beam_map_mode:
                        this_detector_delta_x *= 0
                        this_detector_delta_y *= 0
                    #save the az/el information to the file
                    detector_az[i, :] = \
                            np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                            np.outer(this_detector_delta_y, np.sin(this_ang)) + \
                            np.outer(np.ones(max_n_tones), this_az_tel)
                    
                    detector_za[i, :] = \
                        np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                        np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                        np.outer(np.ones(max_n_tones), this_za_tel)
                
                # Store chanmask from TOD
                this_chanmask = raw_global_data.chanmask[:]
                off_res = np.argwhere(this_chanmask == 0).flatten()
                no_pol = np.argwhere(this_detector_pol[:] < 1).flatten()
                this_chanmask[no_pol] = -1
                # Preserve off-resonance indices
                this_chanmask[off_res] = 0
                chanmask[i, :] = pad_to_length(this_chanmask, max_n_tones, constant_values=-1)

        # Close telescope file as it's no longer needed
        if azel_exists:
            azel_file.close()

        return cls(pfile)


class ProcessedData(BaseProcessedData):
    """Class contianing data from processed TOD files."""
   
    def carrier_amplitude_norm(self) -> npt.NDArray:
        Z = self.carrier_amp_I + 1j*self.carrier_amp_Q
        return np.mean(np.abs(Z), axis=1)

    @property
    def carrier_amplitudes(self) -> tables.Array:
        return self.get_node_value('carrier_amplitudes')
    
    def get_carrier_amplitudes(self, i_chan: int) -> npt.NDArray:
        return self.carrier_amplitudes[i_chan, :, :self.tones_per_channel[i_chan]]

    @property
    def carrier_amp_I(self) -> npt.NDArray:
        return self.carrier_amplitudes[:, 0]
    
    def get_carrier_amp_I(self, i_chan) -> npt.NDArray:
        return self.get_carrier_amplitudes(i_chan)[0]
    
    @property
    def carrier_amp_Q(self) -> npt.NDArray:
        return self.carrier_amplitudes[:, 1]

    def get_carrier_amp_Q(self, i_chan) -> npt.NDArray:
        return self.get_carrier_amplitudes(i_chan)[1]

    @property
    def df_per_mK(self) -> tables.Array:
        return self.get_node_value('df_per_mK')
    
    def get_df_per_mK(self, i_chan: int) -> npt.NDArray:
        return self.df_per_mK[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def IQ_to_gain_phase_angle(self) -> tables.Array:
        return self.get_node_value('IQ_to_gain_phase_angle')
    
    def get_IQ_to_gain_phase_angle(self, i_chan: int) -> npt.NDArray:
        return self.IQ_to_gain_phase_angle[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def IQ_to_freq_diss_angle(self) -> tables.Array:
        return self.get_node_value('IQ_to_freq_diss_angle')
    
    def get_IQ_to_freq_diss_angle(self, i_chan: int) -> npt.NDArray:
        return self.IQ_to_freq_diss_angle[i_chan, :self.tones_per_channel[i_chan]]
    
    @property
    def adc_units_to_hz(self) -> tables.Array:
        return self.get_node_value('adc_units_to_hz')
    
    def get_adc_units_to_hz(self, i_chan: int) -> npt.NDArray:
        return self.adc_units_to_hz[i_chan, :self.tones_per_channel[i_chan]]

    @property
    def data_freq_diss(self) -> tables.Array:
        return self.get_node_value('data_freq_diss')
    
    def get_data_freq_diss(self, i_chan: int) -> npt.NDArray:
        return self.data_freq_diss[i_chan, :, :self.tones_per_channel[i_chan]]

    def get_all_data_freq(self) -> npt.NDArray:
        return self.data_freq_diss[:, 0]
    
    def get_data_freq(self, i_chan: int) -> npt.NDArray:
        return self.get_data_freq_diss(i_chan)[0]
    
    def get_all_data_diss(self) -> npt.NDArray:
        return self.data_freq_diss[:, 0]
    
    def get_data_diss(self, i_chan: int) -> npt.NDArray:
        return self.get_data_freq_diss(i_chan)[1]
    
    @property
    def data_mK(self) -> tables.Array:
        return self.get_node_value('data_mK')
    
    def get_data_mK(self, i_chan: int) -> npt.NDArray:
        return self.data_mK[i_chan, :self.tones_per_channel[i_chan]]
    
    @property
    def data_gain_phase(self) -> tables.Array:
        return self.get_node_value('data_gain_phase')
    
    def get_data_gain_phase(self, i_chan: int) -> npt.NDArray:
        return self.data_gain_phase[i_chan, :, :self.tones_per_channel[i_chan]]
    
    def get_all_data_gain(self) -> npt.NDArray:
        return self.data_gain_phase[:, 0]
    
    def get_data_gain(self, i_chan: int) -> npt.NDArray:
        return self.get_data_gain_phase(i_chan)[0]
    
    def get_all_data_phase(self) -> npt.NDArray:
        return self.data_gain_phase[:, 1]
    
    def get_data_phase(self, i_chan: int) -> npt.NDArray:
        return self.get_data_gain_phase(i_chan)[1]
    
    
class ProcessedDataL1(ProcessedData):
    
    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r') -> ProcessedDataL0:
        return super(ProcessedDataL1, cls).from_file(date, setnum, mode=mode, level=1)

    def link_to_l0(self, target: ProcessedDataL0):
        global_data_group = self.create_group('/', 'global_data')
        data_group = self.create_group('/', 'data')
        lo_group = self.create_group('/', 'lo_sweep')

        # Copy attributes
        self.date = target.date
        self.setnum = target.setnum
        self.add_receipt(target.receipt)
        self.n_samples = target.n_samples
        self.n_channels = target.n_channels

        # Copy LO sweep external links
        for node in target.lo_sweep_group._f_walknodes('ExternalLink'):
            self.create_external_link(lo_group, node._v_name, node.target)

        # Copy global data
        for node_name in STATIC_BASE_PROCESSED_DATA_FIELDS + ['chanmask']:
            node = target.get_node(node_name)
            parent_path = node._v_parent._v_pathname
            if isinstance(node, ExternalLink):
                target_path = node.target
            else:
                target_path = f'{target.filename}:{node._v_pathname}'
            self.create_external_link(parent_path, node_name, target_path)
        
    
    @classmethod
    def from_level0(
        cls,
        l0: ProcessedDataL0,
        do_electronics_noise_removal: bool=True,
        electronics_noise_lp_filt_freq: float=10,
        ds_factor: int=1,
        max_modes: int=30,
    ) -> ProcessedDataL1:
        pfile_path = Path(get_processed_file_template(l0.date, l0.setnum, level=1))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.File(pfile_path, mode='w')

        total_samples = l0.n_samples
        n_samples_ds = int(np.ceil(total_samples / ds_factor))
        max_n_tones = l0.max_n_tones
        nchan = l0.n_channels

        new_data = cls(pfile, level=1)
        l0.close()
        l0.open('r')
        new_data.link_to_l0(l0)

        new_data.n_samples = n_samples_ds


        data_gain_phase = new_data.create_array(
            new_data.data_group,
            'data_gain_phase',
            shape=(nchan, 2, max_n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        data_freq_diss = new_data.create_array(
            new_data.data_group,
            'data_freq_diss',
            shape=(nchan, 2, max_n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        data_mK = new_data.create_array(
            new_data.data_group,
            'data_mK',
            shape=(nchan, max_n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        azel_shape = (nchan, max_n_tones, 1) if l0.detector_az.shape[-1] == 1 else (nchan, max_n_tones, n_samples_ds) 


        carrier_amplitudes = new_data.create_array(
            new_data.data_group,
            'carrier_amplitudes',
            shape=(nchan, 2, max_n_tones),
            atom=tables.Float64Atom(),
        )
        adc_units_to_hz = new_data.create_array(
            new_data.data_group,
            'adc_units_to_hz',
            shape=(nchan, max_n_tones),
            atom=tables.Float64Atom(),
        )
        IQ_to_gain_phase_angle = new_data.create_array(
            new_data.data_group,
            'IQ_to_gain_phase_angle',
            shape=(nchan, max_n_tones),
            atom=tables.Float64Atom(),
        )
        IQ_to_freq_diss_angle = new_data.create_array(
            new_data.data_group,
            'IQ_to_freq_diss_angle',
            shape=(nchan, max_n_tones),
            atom=tables.Float64Atom(),
        )
        df_per_mK = new_data.create_array(
            new_data.global_data_group,
            'df_per_mK',
            shape=(nchan, max_n_tones),
            atom=tables.Float64Atom(),
        )

        # Load LO sweeps
        for i_chan in range(nchan):
            sweep = new_data.get_lo_sweep_data(i_chan)

            # Get frequency direction
            this_IQ_to_freq_diss_angle, this_adc_units_to_hz = sweep.freq_direction()
            IQ_to_freq_diss_angle[i_chan, :] = pad_to_length(this_IQ_to_freq_diss_angle, max_n_tones)
            adc_units_to_hz[i_chan, :] = pad_to_length(this_adc_units_to_hz, max_n_tones)

            detector_f = sweep.tone_list
            df_per_mK[i_chan, :] = pad_to_length(
                compute_df_per_mK(
                    new_data.get_detector_pol(i_chan),
                    new_data.get_detector_beam_ampl(i_chan),
                    detector_f,
                    new_data.get_df_per_mK(i_chan),
                ),
                max_n_tones,
            )

        # Downsample IQ data
        if ds_factor > 1:
            data_IQ = new_data.create_array(
                new_data.data_group,
                'data_IQ',
                shape=(nchan, 2, max_n_tones, n_samples_ds),
                atom=tables.Float64Atom(),
            )
            timestamp = new_data.create_array(
                new_data.data_group,
                'timestamp',
                shape=(nchan, n_samples_ds),
                atom=tables.Float64Atom(),
            )
            detector_az = new_data.create_array(
                new_data.data_group,
                'detector_az',
                shape=azel_shape,
                atom=tables.Float64Atom(),
            )
            detector_za = new_data.create_array(
                new_data.data_group,
                'detector_za',
                shape=azel_shape,
                atom=tables.Float64Atom(),
            )
            interpolated_indices = new_data.create_vlarray(
                new_data.data_group,
                'interpolated_indices',
                atom=tables.UInt32Atom(),
            )
            # TODO: Decimate the data in a memory-efficient manner
            # decimate_in_chunks(time_ordered_data.adc_i[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[0, :])
            # decimate_in_chunks(time_ordered_data.adc_q[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[1, :])
            data_IQ[:] = signal.decimate(l0.data_IQ[:], ds_factor)
            timestamp[:] = l0.timestamp[:, ::ds_factor]
            if azel_shape[1] == 0:
                detector_az[:] = l0.detector_az[:]
                detector_za[:] = l0.detector_za[:]
            else:
                detector_az[:] = l0.detector_az[:, :, ::ds_factor]
                detector_za[:] = l0.detector_za[:, :, ::ds_factor]
            for i_chan in range(nchan):
                interpolated_indices.append(l0.interpolated_indices[i_chan][l0.interpolated_indices[i_chan] % ds_factor == 0] // ds_factor)
        else:
            data_IQ = new_data.create_external_link(new_data.data_group, 'data_IQ', f'{l0.filename}:{l0.data_IQ._v_pathname}')
            timestamp = new_data.create_external_link(new_data.data_group, 'timestamp', f'{l0.filename}:{l0.timestamp._v_pathname}')
            detector_az = new_data.create_external_link(new_data.data_group, 'detector_az', f'{l0.filename}:{l0.detector_az._v_pathname}')
            detector_za = new_data.create_external_link(new_data.data_group, 'detector_za', f'{l0.filename}:{l0.detector_za._v_pathname}')
            interpolated_indices = new_data.create_external_link(new_data.data_group, 'interpolated_indices', f'{l0.filename}:{l0.interpolated_indices._v_pathname}')
        carrier_amplitudes[:] = np.nanmedian(new_data.data_IQ[:], axis=-1)

        # Rotate to Gain / Phase
        IQ_to_gain_phase_angle[:] = np.atan2(carrier_amplitudes[:, 0], carrier_amplitudes[:, 1])  # N_chan
        for i_chan in range(nchan):
            rotate_basis(
                new_data.data_IQ[:],
                data_gain_phase,
                IQ_to_gain_phase_angle,
                i_chan=i_chan,
                valid_tone_indices=np.arange(l0.tones_per_channel[i_chan]),
            )
        fs = 1 / np.median(np.diff(new_data.timestamp[:], axis=-1), axis=-1)

        # Remove electronics noise if specified
        if do_electronics_noise_removal:
            remove_electronics_noise_tables(data_gain_phase, fs, lp_filt_freq=electronics_noise_lp_filt_freq, max_modes=max_modes)

        # Create calibrated data
        new_generate_calibrated_data(new_data)
        
        return new_data


class ExternalLinkProcessedData(ProcessedData):
    """Class for storing processed data with external links to another file."""
    def __init__(self, file: tables.File):
        super().__init__(file)

    def open(self, mode: str='r'):
        super().open(mode=mode)
        self._load_dynamic_fields()

    def _load_dynamic_fields(self):
        for field_name in DYNAMIC_PROCESSED_DATA_FIELDS:
            setattr(self, field_name, self.get_node(field_name))

    @property
    def carrier_amplitudes(self) -> PyTablesDataset:
        return self._carrier_amplitudes

    @carrier_amplitudes.setter
    def carrier_amplitudes(self, carrier_amplitudes: tables.Array | ExternalLink):
        self._carrier_amplitudes = PyTablesDataset(carrier_amplitudes, self._file)
    
    @property
    def data_IQ(self) -> PyTablesDataset:
        return self._data_IQ
    
    @data_IQ.setter
    def data_IQ(self, data_IQ: tables.Array | ExternalLink):
        self._data_IQ = PyTablesDataset(data_IQ, self._file)
    
    @property
    def IQ_to_gain_phase_angle(self) -> PyTablesDataset:
        return self._IQ_to_gain_phase_angle

    @IQ_to_gain_phase_angle.setter
    def IQ_to_gain_phase_angle(self, IQ_to_gain_phase_angle: tables.Array | ExternalLink):
        self._IQ_to_gain_phase_angle = PyTablesDataset(IQ_to_gain_phase_angle, self._file)
    
    @property
    def adc_units_to_hz(self) -> PyTablesDataset:
        return self._adc_units_to_hz
    
    @adc_units_to_hz.setter
    def adc_units_to_hz(self, adc_units_to_hz: tables.Array | ExternalLink):
        self._adc_units_to_hz = PyTablesDataset(adc_units_to_hz, self._file)

    @property
    def data_gain_phase(self) -> PyTablesDataset:
        return self._data_gain_phase
    
    @data_gain_phase.setter
    def data_gain_phase(self, data_gain_phase: tables.Array | ExternalLink):
        self._data_gain_phase = PyTablesDataset(data_gain_phase, self._file)
    
    @property
    def data_freq_diss(self) -> PyTablesDataset:
        return self._data_freq_diss
    
    @data_freq_diss.setter
    def data_freq_diss(self, data_freq_diss: tables.Array | ExternalLink):
        self._data_freq_diss = PyTablesDataset(data_freq_diss, self._file)
    
    @property
    def data_mK(self) -> PyTablesDataset:
        return self._data_mK
    
    @data_mK.setter
    def data_mK(self, data_mK: tables.Array | ExternalLink):
        self._data_mK = PyTablesDataset(data_mK, self._file)
    
    @property
    def timestamp(self) -> PyTablesDataset:
        return self._timestamp
    
    @timestamp.setter
    def timestamp(self, timestamp: tables.Array | ExternalLink):
        self._timestamp = PyTablesDataset(timestamp, self._file)

    @property
    def chanmask(self) -> tables.Array:
        return self._chanmask
    
    @chanmask.setter
    def chanmask(self, chanmask: tables.Array | ExternalLink):
        self._chanmask = PyTablesDataset(chanmask, self._file)

    def link_to_file(self, target: ProcessedData):
        global_data_group = self._file.create_group('/', 'global_data')
        data_group = self._file.create_group('/', 'data')
        lo_group = self._file.create_group('/', 'lo_sweep')

        # Copy attributes
        self.date = target.date
        self.setnum = target.setnum
        self.add_receipt(target.receipt)
        self.n_samples = target.n_samples
        self.n_channels = target.n_channels

        # Copy LO sweep external links
        for node in target.lo_sweep_group._f_walknodes('ExternalLink'):
            self._file.create_external_link(lo_group, node._v_name, node.target)

        # Create external links for all datasets
        for node_name in ALL_PROCESSED_DATA_FIELDS:
            node = target.get_node(node_name)
            parent_path = node._v_parent._v_pathname
            if isinstance(node, ExternalLink):
                target_path = node.target
            else:
                target_path = f'{target.filename}:{node._v_pathname}'
            self._file.create_external_link(parent_path, node_name, target_path)



class ProcessedDataLN(ExternalLinkProcessedData):
    """Class for storing level N processed data."""
    def __init__(self, file: tables.File, level: int=2):
        super().__init__(file)
        if level < 2:
            raise ValueError(f'Argument `level` must be >= 2 for class `ProcessedDataLN`, received {level}')
        self.level = level
    
    @classmethod
    def from_previous_level(cls, previous: ProcessedData) -> ProcessedDataLN:
        """Create a level N processed file with external links to level N-1."""
        level = previous.level + 1
        pfile_path = Path(get_processed_file_template(previous.date, previous.setnum, level=level))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        file = tables.File(pfile_path, mode='w')
        new_data = cls(file, level)
        new_data.link_to_file(previous)
        new_data._load_dynamic_fields()

        # Swap the previous file to read-only
        previous.close()
        previous.open('r')

        return new_data

    @classmethod
    def from_file(cls, date: str, setnum: int, level: int, mode: str='r'):
        fname = get_processed_file_template(date, setnum, level=level)
        pd = cls(tables.File(fname, mode=mode), level=level)
        pd._load_dynamic_fields()
        return pd


class MapData(ProcessedDataLN):
    def __init__(self, file, level=3):
        super().__init__(file, level)

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r'):
        file_path = Path(get_map_file_template(date, setnum))
        md = cls(tables.File(file_path, mode=mode), level=3)
        md._load_dynamic_fields()
        return md

    @classmethod
    def from_processed_data(cls, pdata: ProcessedData) -> MapData:
        return cls.from_previous_level(pdata)
    
    @classmethod
    def from_previous_level(cls, previous: ProcessedData) -> MapData:
        """Create a map file with external links to level N-1."""
        file_path = Path(get_map_file_template(previous.date, previous.setnum))
        if not file_path.exists():
            file_path.touch(PERMISSIONS_ALL_FULL)
        file = tables.File(file_path, mode='w')
        new_data = cls(file)
        new_data.link_to_file(previous)
        new_data._load_dynamic_fields()

        # Swap the previous file to read-only
        previous.close()
        previous.open('r')

        return new_data

    def setup_map_arrays(self, n_pix_x: int, n_pix_y: int, beammap_mode: bool=False):
        # Create empty arrays
        n_maps = N_POLARIZATION if not beammap_mode else self.n_tones
        self.create_group('/', 'map')
        self.create_array('/map', 'map_az', shape=(n_pix_x,), atom=tables.Float64Atom())
        self.create_array('/map', 'map_za', shape=(n_pix_y,), atom=tables.Float64Atom())
        self.create_array('/map', 'sum_map', shape=(n_maps, n_pix_x, n_pix_y), atom=tables.Float64Atom())
        self.create_array('/map', 'hits_map', shape=(n_maps, n_pix_x, n_pix_y), atom=tables.Float64Atom())
        self.create_array('/map', 'netd', shape=(self.n_channels, self.max_n_tones,), atom=tables.Float64Atom())
        good_samples = self.create_vlarray('/map', 'good_samples', expectedrows=self.n_channels, atom=tables.UInt32Atom())
        for i_chan in range(self.n_channels):
            good_samples.append(np.setdiff1d(np.arange(self.n_samples), self.interpolated_indices[i_chan]))
    
    @ensure_path(1)
    def compile_to_file(self, path: Path, datasets: list[str]=None, mode: str='w') -> tables.File:
        if datasets is None:
            datasets = ALL_MAP_DATA_FIELDS
        return super().compile_to_file(path, datasets=datasets, mode=mode)

    @property
    def map_az(self) -> tables.Array:
        return self.get_node_value('map_az', where='/map')

    @property
    def map_za(self) -> tables.Array:
        return self.get_node_value('map_za', where='/map')

    @property
    def sum_map(self) -> tables.Array:
        return self.get_node_value('sum_map', where='/map')

    @property
    def hits_map(self) -> tables.Array:
        return self.get_node_value('hits_map', where='/map')
    
    @property
    def netd(self) -> tables.Array:
        return self.get_node_value('netd', where='/map')

    @property
    def good_samples(self) -> tables.Array:
        return self.get_node_value('good_samples', where='/map')

    @property
    def map(self) -> npt.NDArray:
        div = tables.Expr('sum_map / hits_map', {'sum_map': self.sum_map, 'hits_map': self.hits_map})
        d = div.eval()
        return d

    @property
    def total_map(self) -> npt.NDArray:
        return np.sum(self.sum_map, axis=0) / np.sum(self.hits_map, axis=0)

    def get_netd_pol(self, polarization: int) -> npt.NDArray:
        return self.netd[self.detector_pol[:] == polarization]

    @property
    def integration_time(self) -> npt.NDArray:
        integration_times = [
            np.flip(
                np.transpose(self.hits_map[i,::-1]) * \
                    np.median(self.get_netd_pol(pol)) ** 2. / self.fs,
                1,
            )
            for i, pol in enumerate(range(1, N_POLARIZATION + 1))
        ]
        return integration_times

    def get_scaled_optical_image(self) -> npt.NDArray:
        opt_npix_per_tel_npix = DEFAULT_MAP_DPIX/OPTCAM_PIX_SIZE_DEGREES
        opt_npix_az = int(np.size(self.map_az)*opt_npix_per_tel_npix/2)*2
        opt_npix_za = int(np.size(self.map_za)*opt_npix_per_tel_npix/2)*2
        opt_center_az = int(2592/2)+OPTCAM_OFFSET_AZ_PIX
        opt_center_za = int(1944/2)+OPTCAM_OFFSET_ZA_PIX
        return self.optical_image[opt_center_za-int(opt_npix_za/2):opt_center_za+int(opt_npix_za/2),\
                                    opt_center_az-int(opt_npix_az/2):opt_center_az+int(opt_npix_az/2)]

    def get_combined_map(self, sigma: tuple[float,...]=GAUSSIAN_SIGMA) -> npt.NDArray:
        flagged_map_1 = gaussian_filter(self.map[0], sigma)
        flagged_map_2 = gaussian_filter(self.map[1], sigma)
        flagged_map_3 = gaussian_filter(self.total_map, sigma)
       # pdb.set_trace()
        # flagged_map_1 = np.copy(self.map[0])
        # flagged_map_2 = np.copy(self.map[1])
        # flagged_map_3 = np.copy(self.total_map)

        final_final_map1= np.copy(flagged_map_1)
        final_final_map2= np.copy(flagged_map_2)
        final_final_map3= np.copy(flagged_map_3)

        # Convert all nans to boolean True
        nan_map_1 = np.isnan(flagged_map_1)
        nan_map_2 = np.isnan(flagged_map_2)
        nan_map_3 = np.isnan(flagged_map_3)

        # Combine the boolean maps such that if any pixel is flagged in any map, it is flagged in the combined map
        combined_nan_map = np.logical_or(np.logical_or(nan_map_1, nan_map_2), nan_map_3)
        
        # Get the coordinates of True values in the combined_nan_map
        flagged_positions = np.where(combined_nan_map)
        final_flagged_coords = list(zip(flagged_positions[0], flagged_positions[1]))

        # Apply this combined map to each of the final maps
        flagged_map_1[combined_nan_map] = 1
        flagged_map_2[combined_nan_map] = 1
        flagged_map_3[combined_nan_map] = 1

        flagged_map_1[flagged_map_1 != 1] = 0
        flagged_map_2[flagged_map_2 != 1] = 0
        flagged_map_3[flagged_map_3 != 1] = 0

        final_final_map1[combined_nan_map] = np.nan
        final_final_map2[combined_nan_map] = np.nan
        final_final_map3[combined_nan_map] = np.nan

        contour_levels = [1]

        final_final_map1= final_final_map1.flatten()
        final_final_map2= final_final_map2.flatten()
        final_final_map3= final_final_map3.flatten()

        final_final_map1 = [x for x in final_final_map1 if not np.isnan(x)]
        final_final_map2 = [x for x in final_final_map2 if not np.isnan(x)]
        final_final_map3 = [x for x in final_final_map3 if not np.isnan(x)]
        return flagged_map_1, flagged_map_2, flagged_map_3, contour_levels
    
    def extent(self) -> tuple[float, float, float, float]:
        return (
            min(self.map_az)-DEFAULT_MAP_DPIX /2.,
            max(self.map_az)+DEFAULT_MAP_DPIX /2,
            max(self.map_za)+DEFAULT_MAP_DPIX /2.,
            min(self.map_za)-DEFAULT_MAP_DPIX /2.
        )

    def plot_individual(self, index: int):
        plot_map(self.map[index], self.map_az, self.map_za, self.extent(), title=f'Resonator {index}')

    def plot(self, show: bool=True, save: bool=True):

        hits_map = self.hits_map[:]
        mapp = self.map[:]
        total_map = self.total_map[:]

        valid_cov_1 = np.argwhere(hits_map[0] > 0.5 * np.median(hits_map[0]))
        map_goodcov_1 = np.zeros(np.size(valid_cov_1[:,0]))
        for i_cov in np.arange(np.size(valid_cov_1[:,0])):
            map_goodcov_1[i_cov] = mapp[0, valid_cov_1[i_cov,0],valid_cov_1[i_cov,1]]
        valid_cov_2 = np.argwhere(hits_map[1] > 0.5 * np.median(hits_map[1]))
        map_goodcov_2 = np.zeros(np.size(valid_cov_2[:,0]))
        for i_cov in np.arange(np.size(valid_cov_2[:,0])):
            map_goodcov_2[i_cov] = mapp[1, valid_cov_2[i_cov,0],valid_cov_2[i_cov,1]]

        netd_1 = self.get_netd_pol(1)
        netd_2 = self.get_netd_pol(2)
        cb_shrink = 0.95
        this_xlim = min(self.map_az),max(self.map_az)
        this_ylim = max(self.map_za),min(self.map_za)
        max_abs = np.max(np.abs(np.append(map_goodcov_1,map_goodcov_2)))*0.75
        valid_netd_1 = np.argwhere(netd_1 > 0)
        med_netd_1 = 1./np.sqrt(np.sum(1./netd_1[valid_netd_1]**2)/np.size(valid_netd_1))
        valid_netd_2 = np.argwhere(netd_2 > 0)
        med_netd_2 = 1./np.sqrt(np.sum(1./netd_2[valid_netd_2]**2)/np.size(valid_netd_2))

        #Sage's plotting code---------------------------------------------------------------------------------------------

        # contour_levels, final_map_1_filt, final_map_2_filt, final_map_tot_filt, flagged_map_1_filt, flagged_map_2_filt, \
        # flagged_map_tot_filt, final_flagged_coordinates = combined_map(map_1_filt_final_map, map_2_filt_final_map, map_tot_filt_final_map)
        flagged_map_1_filt, flagged_map_2_filt, flagged_map_tot_filt, contour_levels = self.get_combined_map()

    #    pw = plotWindow()
        # TODO: Make figure size change based on the size of the map
        this_fig = plt.figure(figsize=(15,7.5))
        plt.subplot(4,1,1)
        plt.imshow(np.flip(np.transpose(mapp[0][::-1]),1), \
        extent = self.extent(), \
        aspect='equal', vmin=-max_abs, vmax=max_abs, cmap='Blues_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=self.extent(), colors='red')
        plt.title(self.file_stub + '\n' + 'Local Time = ' + time.asctime(time.localtime(self.timestamp[0]-7500.)) + \
        ', Optical Visibility = ' + str(self.optical_visibility[()]) + ' meters \n' + 'NETD V-Pol (30Hz) = ' + "{:.1f}".format(med_netd_1) + \
        ' mK, ' + 'NETD H-Pol (30Hz) = ' + "{:.1f}".format(med_netd_2) + ' mK')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)

        plt.subplot(4,1,2)
        plt.imshow(np.flip(np.transpose(mapp[1][::-1]),1), \
        extent = self.extent(), \
        aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Reds_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_2_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=self.extent(), colors='black')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)

        plt.subplot(4,1,3)
        plt.imshow(np.flip(np.transpose(total_map[::-1]),1), \
        extent = self.extent(), \
        aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Greys_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=self.extent(), colors='red')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)
        
        plt.subplot(4,1,4)
        optical_image = self.get_scaled_optical_image()
        valid_opt_pix = np.where(optical_image < 240)
        opt_vmax = 255. #np.percentile(optical_image[valid_opt_pix], 90)
        opt_vmin = -255. #np.percentile(optical_image[valid_opt_pix], 10)
        plt.imshow(optical_image, \
                extent = self.extent(), \
                aspect='equal', vmax=255, vmin=-255)
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('Optical Signal (rgb)', rotation=270, labelpad=15)
        ##Need to match aspect ratio of plots (and get rid of colorbar).
        plt.xlabel('Azimuth (degrees)'), plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)
            
        this_fig.subplots_adjust(wspace=0, hspace=0)
    #    pw.addPlot("Raw Image", this_fig)
        path = self.folder / (self.file_stub + '_Source_Finder_Image.png')
        if not path.exists():
            path.touch(PERMISSIONS_ALL_FULL)
        if save:
            this_fig.savefig(path, bbox_inches='tight')
        if show:
            plt.show()
    

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


if __name__ == '__main__':
    # Telescope Testing
    # date = '20251006'
    # setnum = 1009
    # Lab Testing
    date = '20260212'
    setnum = 1003

    cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=2)
    print(cd.list_datasets())

    pdb.set_trace()

    pd = ProcessedDataL0.from_tod(date, setnum, beam_map_mode=False)
    # pd = ProcessedDataL0.from_file(date, setnum)
    pd1 = ProcessedDataL1.from_level0(pd, ds_factor=1, do_electronics_noise_removal=True)
    # f = tables.File(f'/data/{date}/{date}_Device_aSi1_Channel2_telescope_275mK_TOD_set{setnum}.h5', 'r')
    # corrected_timestamp, missed_packets, corrected_packet_index = compute_timestamp(f, sigma=2.0)
    # data_I = f.root.time_ordered_data.adc_i
    # data_Q = f.root.time_ordered_data.adc_q
    # interpolate_data(data_I, data_Q, corrected_timestamp, missed_packets, corrected_packet_index)
    # f.close()
    pdb.set_trace()
   
    # pd.close()
#     date = '20250916'
#     setnum = 1017
#     # date = '20250529'
#     # setnum = 1011
#     pd = ProcessedDataL1.from_tod(date, setnum)
#     pd2 = ProcessedDataLN.from_previous_level(pd)
#     pd2.data_IQ[:] = 0
#     pd3 = ProcessedDataLN.from_previous_level(pd2)
#     pdb.set_trace()
#     pd.close()
#     pd2.close()
#     pd3.close()

    # pd_old = ProcessedData.from_tod(date, setnum)
    # pd_new = ProcessedDataL1.from_tod(date, setnum)
    # plt.show()
    # plt.plot(pd_old.df_per_mK[:], label='Old')
    # plt.plot(pd_new.df_per_mK[:], label='New')
    # plt.legend()
    # plt.show()
    # pdb.set_trace()
    # pd_old.close()
    # pd_new.close()
    # data = ProcessedData.from_file(date, setnum)
    # pfile = PyTablesProcessedData.from_tod(date, setnum, save=False)
    # todtemplate = get_tod_template(date, setnum)
    # todlist = glob.glob(todtemplate)

    # # h5file = RawDataFile(todlist[0], 'r')
    # # data_I = h5file.adc_i[:]
    # # data_Q = h5file.adc_q[:]

    # h5file = tables.open_file(todlist[0], 'r')
    # data_I = h5file.root.time_ordered_data.adc_i[:]
    # data_Q = h5file.root.time_ordered_data.adc_q[:]

    # carrier_amp_I = np.nanmedian(data_I, axis=1)
    # carrier_amp_Q = np.nanmedian(data_Q, axis=1)
    
    # # Rotate to Gain / Phase
    # this_gain_phase_angle = np.atan2(carrier_amp_I, carrier_amp_Q)  # N_chan

    # data_IQ = np.stack((data_I, data_Q), axis=0)
    # this_data_gain_phase = rotate_basis(
    #     data_IQ,
    #     this_gain_phase_angle
    # )
    # clean_data = remove_electronics_noise(this_data_gain_phase)

    # # pdb.set_trace()
    # h5file.close()
    # # pdb.set_trace()
