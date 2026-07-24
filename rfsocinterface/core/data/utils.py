"""Core functionality relating to data loading and processing."""

from __future__ import annotations

import logging
import re
from typing import Literal

# import tables
import h5py

# from tables.link import ExternalLink
import numpy as np
import numpy.typing as npt
from numpy.polynomial import polynomial as poly

from rfsocinterface.core.utils import (
    argclosest,
    build_interp_map,
)

_logger = logging.getLogger(__name__)

OPTCAM_PIX_SIZE_DEGREES = 0.0104
OPTCAM_OFFSET_AZ_PIX = 74
OPTCAM_OFFSET_ZA_PIX = 49
DEFAULT_MAP_DPIX = 0.03
OPTCAM_HEIGHT_PIXELS = 1944
OPTCAM_WIDTH_PIXELS = 2592
# DATA_DIRECTORY = 'reference_data'  # For testing with local data files

N_POLARIZATION = 2

DECIMATE_ORDER = 5
AZ_TRIM = 2.3
ZA_TRIM = 0.2

# RFSOC_TIME_OFFSET_AZ = -12e-3 # -12 ms, empirically determined
RFSOC_TIME_OFFSET_AZ = 0  # -12 ms, empirically determined
RFSOC_TIME_OFFSET_ZA = -3e-3  # -3 ms, empirically determined


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
    ('carrier_amplitudes', 'f8', (2,)),
    ('IQ_to_gain_phase_angle', 'f8'),
    ('IQ_to_freq_diss_angle', 'f8'),
    ('df_per_mK', 'f8'),
]


def get_channel_group_name(idx: int) -> str:
    """Return the properly formatted group name for the channel with index `idx`."""
    return f'channel_{idx:03d}'


def get_step_group_name(idx: int, name: str) -> str:
    """Return the properly formatted group name for a step in the processing history."""
    return f'{idx:04d}_{name}'


def get_channel_index_from_dset_name(name: str) -> int | None:
    """Return the index of the channel that contains the dataset, if any.

    Returns:
        (int | None): If the dataset is contained inside a channel group, the index of
            that group. Otherwise, returns None.
    """
    res = re.search(r'(?<=channel_)\d', name)
    if res:
        return int(res[0])
    return None


#
# Data Processing
#


def compute_df_per_mK(
    beam_pol: npt.NDArray, detector_beam_amp: npt.NDArray, detector_f, dfoverf_per_mK
):
    """Compute df / mK for the detectors."""
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
    out_data[0] = (
        np.cos(rotation_angle)[:, np.newaxis] * in_data[0]
        - np.sin(rotation_angle)[:, np.newaxis] * in_data[1]
    )

    out_data[1] = (
        np.sin(rotation_angle)[:, np.newaxis] * in_data[0]
        + np.cos(rotation_angle)[:, np.newaxis] * in_data[1]
    )


# TODO: Optimize this for chunked data
def generate_calibrated_data(
    data_IQ: h5py.Dataset,
    data_freq_diss: h5py.Dataset,
    data_mK: h5py.Dataset,
    IQ_to_freq_diss_angle: npt.NDArray,
    adc_units_to_hz: npt.NDArray,
    df_per_mK: npt.NDArray,
):
    """Create data_freq_diss and data_mK from data_IQ."""
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
    """Determine which packets were missed using `pkt_idx` in the TOD file.

    Arguments:
        packet_idx (h5py.Dataset): The index for each data packet.

    Returns:
        (npt.NDArray): A 2D array consisting of indices where packets were missed and
            how many packets were missed. E.g. A list [0, 11, ...] would yield
            [[1, 10]].
    """
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
    window_size: int = 5,
    sigma: float = 3.0,
) -> npt.NDArray:
    """Determine which packets were missed using based on the timestamp."""
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
            window = raw_timestamp[window_min_idx : window_max_idx + 1]
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
                large_window = raw_timestamp[
                    large_window_min_idx : large_window_max_idx + 1
                ]
                large_window_dtime = np.ptp(large_window)
                large_expected_samples = int(large_window_dtime // med_dtime)
                large_actual_samples = large_window_max_idx - large_window_min_idx
                large_window_packets_missed = (
                    large_expected_samples - large_actual_samples + 1
                )
                if large_expected_samples > large_actual_samples:
                    missed_packets = np.vstack(
                        [missed_packets, [i, large_window_packets_missed]]
                    )
        i += 1

    _logger.debug(f'{np.sum(missed_packets[:, 1])} missed packets')

    return missed_packets


def interpolate_timestamp_streaming(
    raw_timestamp: h5py.Dataset,
    new_timestamp: h5py.Dataset,
    packet_indices: h5py.Dataset,
    ds_factor: int = 1,
    chunk_size: int = 4096,
    time_offset: float = 0.0,
):
    """Generate an equally spaced timestamp.

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
    n = raw_timestamp.shape[0]

    # Accumulators for linear regression
    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_xy = 0.0
    n_total = 0

    # --- Step 1: Streaming linear regression ---
    for start in range(0, n, chunk_size):
        stop = min(start + chunk_size, n)

        # Read chunks as plain numpy arrays
        x_chunk = np.uint64(packet_indices[start:stop])
        y_chunk = raw_timestamp[start:stop]

        # Shift indices so regression is well-conditioned
        if start == 0:
            x0 = x_chunk[0]
        x_chunk_shifted = x_chunk - x0

        # Accumulate sums using dot products (memory-efficient)
        sum_x += x_chunk_shifted.sum()
        sum_y += y_chunk.sum()
        sum_x2 += np.dot(x_chunk_shifted, x_chunk_shifted)
        sum_xy += np.dot(x_chunk_shifted, y_chunk)
        n_total += x_chunk_shifted.size

    # Compute slope (a) and intercept (b)
    denom = n_total * sum_x2 - sum_x**2
    if denom == 0:
        raise ValueError('Degenerate packet_indices, cannot compute regression.')
    a = (n_total * sum_xy - sum_x * sum_y) / denom
    b = (sum_y - a * sum_x) / n_total

    # --- Step 2: Generate new timestamps in chunks ---
    m = new_timestamp.shape[0]
    for start in range(0, m, chunk_size):
        stop = min(start + chunk_size, m)

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
    """Interpolate data for missing packets in IQ data."""
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
        fit_i = poly.polyfit(times - times[0], i_data.T, 4)
        fit_q = poly.polyfit(times - times[0], q_data.T, 4)

        # Interpolate data between sample i-1 and i
        dtime = (timestamp[index] - timestamp[prev_index]) / this_missed_packets
        missing_packet_start_t = timestamp[prev_index] + dtime
        current_t = timestamp[index]
        missed_packet_t = np.linspace(
            missing_packet_start_t, current_t, this_missed_packets, endpoint=False
        )
        new_data_I = poly.polyval(missed_packet_t - times[0], fit_i)
        new_data_Q = poly.polyval(missed_packet_t - times[0], fit_q)
        new_data = np.stack((new_data_I, new_data_Q))

        this_interpolated_indices = list(range(prev_index + 1, index))

        old_size = output_indices_dset.size
        output_indices_dset.resize(
            old_size + np.size(this_interpolated_indices), axis=0
        )
        output_indices_dset[old_size:] = this_interpolated_indices
        output_dset[..., this_interpolated_indices] = new_data


def get_detector_positions_no_interp(
    az_tel: npt.NDArray,
    za_tel: npt.NDArray,
    output_detector_az: h5py.Dataset,
    output_detector_za: h5py.Dataset,
    dx: npt.NDArray,
    dy: npt.NDArray,
    elevation_angle: float,
) -> npt.NDArray:
    """Compute the detector positions without interpolation."""
    chunk_size = output_detector_az.chunks[-1]
    n_samples = az_tel.size

    for start in range(0, n_samples, chunk_size):
        stop = min(start + chunk_size, n_samples)

        # telescope interpolation
        az = az_tel[start:stop]
        za = za_tel[start:stop]

        # rotation angle
        ang = np.deg2rad(elevation_angle - za)

        cos_ang = np.cos(ang)
        sin_ang = np.sin(ang)

        output_detector_az[:, start:stop] = (
            np.outer(dx[:], cos_ang) - np.outer(dy[:], sin_ang) + az
        )
        output_detector_za[:, start:stop] = (
            np.outer(dy[:], cos_ang) + np.outer(dx[:], sin_ang) + za
        )


# TODO: Update this to the new data processing scheme
def get_detector_positions(
    timestamp: h5py.Dataset,
    tel_timestamp: h5py.Dataset,
    az_tel: h5py.Dataset,
    za_tel: h5py.Dataset,
    output_detector_az: h5py.Dataset,
    output_detector_za: h5py.Dataset,
    dx: npt.NDArray,
    dy: npt.NDArray,
    elevation_angle: float,
) -> npt.NDArray:
    """Compute the detector positions using interpolation."""
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
            np.outer(dx[:], cos_ang) - np.outer(dy[:], sin_ang) + az
        )
        output_detector_za[:, start:stop] = (
            np.outer(dy[:], cos_ang) + np.outer(dx[:], sin_ang) + za
        )


def interpolate_telescope_position(
    data_timestamp: npt.NDArray,
    telescope_timestamp: npt.NDArray,
    tel_position: npt.NDArray,
    pps_position: npt.NDArray,
    data_pps: npt.NDArray,
    search_radius: int = 100,
    direction: Literal['az', 'za'] = 'az',
) -> npt.NDArray:
    """Interpolate and align the telescope positions."""
    # Find the telescope positions and timestamps corresponding to the PPS pulses
    pps_tel_idx = (
        np.where(np.diff(pps_position) != 0)[0] + 1
    )  # Indices where the pps changes
    pps_tel_pos = pps_position[pps_tel_idx]
    pps_times_tel = telescope_timestamp[pps_tel_idx]

    if pps_tel_idx.size == 0:
        # The telescoep never mvoed in this direction, so aligning the times doesn't
        # matter. Just upsample the positions.
        _logger.info(
            f'Doing simple interpolation for detector positions in {direction.upper()} '
            'direction.'
        )
        return np.interp(data_timestamp, telescope_timestamp, tel_position)
    _logger.info(f'Using PPS for detector positions in {direction.upper()} direction.')

    # Upsample the telescope positions ignoring the positions when the pulse is receivd,
    # since the extra commands slow the loop
    interpolated_tel_pos = np.interp(
        data_timestamp,
        np.delete(telescope_timestamp, pps_tel_idx),
        np.delete(tel_position, pps_tel_idx),
    )

    # Now shift the upsampled positions so that the PPS is synced between the
    # raw data and the telescope data.

    pps_samples_tel = np.zeros(pps_tel_idx.shape, dtype=int)

    # Find timestamps in the raw data corresponding to the PPS pulses
    pps_samples_data = np.where(data_pps == 1)[0]
    pps_times_data = data_timestamp[pps_samples_data]

    # Correlate the two timestamps to find which samples in the interpolated telescope
    # positions correspond to each pulse
    for i in range(len(pps_tel_idx)):
        closest_index = argclosest(pps_times_data, pps_times_tel[i])
        sample = pps_samples_data[closest_index]
        pps_samples_tel[i] = (
            argclosest(
                interpolated_tel_pos[
                    sample - search_radius : sample + search_radius + 1
                ],
                pps_tel_pos[i],
            )
            + sample
            - search_radius
        )

    # Find the median offset between the two sets of PPS samples, and shift the
    # interpolated telescope positions by this amount to sync them up.
    pps_offset = np.zeros(pps_samples_tel.shape, dtype=int)
    for i, pps_tel_sample in enumerate(pps_samples_tel):
        closest_data_sample = argclosest(pps_samples_data, pps_tel_sample)
        pps_offset[i] = pps_tel_sample - pps_samples_data[closest_data_sample]

    # Shift by empirically determined offset
    sample_rate = 1 / (data_timestamp[1] - data_timestamp[0])
    if direction == 'az':
        additional_offset = RFSOC_TIME_OFFSET_AZ * sample_rate
    else:
        additional_offset = RFSOC_TIME_OFFSET_ZA * sample_rate
    median_offset = np.round(
        np.median(pps_offset.astype(float) + additional_offset)
    ).astype(int)

    # If the median offset is positive, that means the telescope data is lagging behind
    # the RFSoC, so we shift to the left. If it's negative, the telescope data is ahead
    # of the RFSoC, so we shift to the right. Hence the negative sign.
    fixed_positions = np.roll(interpolated_tel_pos, -median_offset)

    # Fill the array with nans where we shifted away from
    if median_offset < 0:
        fixed_positions[:-median_offset] = np.nan
    else:
        fixed_positions[-median_offset:] = np.nan

    _logger.info(f'Shifting telescope positions by {-median_offset} samples')

    return fixed_positions
