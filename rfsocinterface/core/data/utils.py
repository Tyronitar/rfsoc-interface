"""Core functionality relating to data loading and processing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
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


# OPTCAM_SENSOR_SIZE = (5.76, 4.29)  # mm, (width, height)
OPTCAM_DPIX = 0.0025  # Degrees / pixel
# Empirically determined optical camera offset relative to telescope position
# i.e. optical position in telescope coordinates = tel position - offset
# optical camera aligned to tel position -> tel position + offset
OPTCAM_OFFSET_ZA_DEG = -1.7138
OPTCAM_OFFSET_AZ_DEG = -1.1465
OPTCAM_OFFSET_AZ_PIX = int(OPTCAM_OFFSET_AZ_DEG / OPTCAM_DPIX)
OPTCAM_OFFSET_ZA_PIX = int(OPTCAM_OFFSET_ZA_DEG / OPTCAM_DPIX)
OPTCAM_HEIGHT_PIXELS = 1944
OPTCAM_WIDTH_PIXELS = 2592
DEFAULT_MAP_DPIX = 0.03  # Degrees / pixel
DEFAULT_VIDEO_DPIX = 0.045  # Degrees / pixel

SKIPR_PSF_SIGMA = 0.087 / 2.3  # Degrees
# DATA_DIRECTORY = 'reference_data'  # For testing with local data files

# def get_optical_camera_pixel_scale(
#     focal_length: float,
# ) -> tuple[float, float]:
#     """Return the pixel scale of the optical camera in degrees."""
#     """Determining Optical camera pixel scale.
#         Camera Attributes:
#             * Aspect ratio 4/3
#             * Sensor size 5.76mm by 4.29mm
#             * Horizontal crop factor is 6.25
#             * Vertical crop factor is 5.59
#             * total pixel count 2592 (H) x 1944 (V)

#         Formula for FOV (in radians) is 2 * arctan(0.5 * sensor_size / focal_length)

#         12 mm Lens Attributes:
#             * Focal length = 12mm
#             * Effective horizontal focal length = 75 mm
#             * Effective vertical focal length = 67 mm
#             * Horizontal FOV = 27.0 degrees
#             * Vertical FOV = 20.4 degrees
#             * Horizontal pixel size = 0.0104 degrees
#             * Vertical pixel size = 0.0104 degrees

#         50 mm Lens Attributes:
#             * Focal length = 50mm
#             * Horizontal FOV = 6.6 degrees
#             * Vertical FOV = 4.9 degrees
#             * Horizontal pixel size = 0.0025 degrees
#             * Vertical pixel size = 0.0025 degrees
# """

N_POLARIZATION = 2

DECIMATE_ORDER = 5
AZ_TRIM = 2.3
ZA_TRIM = 0.2

# RFSOC_TIME_OFFSET_AZ = -12e-3 # -12 ms, empirically determined
RFSOC_TIME_OFFSET_AZ = 0  # -12 ms, empirically determined
RFSOC_TIME_OFFSET_ZA = -3e-3  # -3 ms, empirically determined

# Half of the backlash between the azimuth motor encoder and the telescope, i.e. how far
# the telescope trails the encoder while moving. Measured from the separation of the
# beams in opposite scan directions, which is independent of the scan speed.
AZ_BACKLASH_DEG = 0.0125


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


def get_current_camera_extent(
    tel_az: float, tel_za: float
) -> tuple[float, float, float, float]:
    """Return the extent of the camera given the current telescope position."""
    # Get the optical image's actual coordinates (hence subtraction)
    opt_center_az = tel_az - OPTCAM_OFFSET_AZ_DEG
    opt_center_za = tel_za - OPTCAM_OFFSET_ZA_DEG
    opt_width_deg = OPTCAM_WIDTH_PIXELS * OPTCAM_DPIX
    opt_height_deg = OPTCAM_HEIGHT_PIXELS * OPTCAM_DPIX
    return (
        opt_center_az - opt_width_deg / 2,
        opt_center_az + opt_width_deg / 2,
        opt_center_za + opt_height_deg / 2,
        opt_center_za - opt_height_deg / 2,
    )


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

    _logger.debug(f'find_missed_packets: {np.sum(missed_packets[:, 1])} missed packets')
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
    output_pps_dset: h5py.Dataset,
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
        output_pps_dset[this_interpolated_indices] = 0


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
        ang = np.deg2rad(za - elevation_angle)

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
        ang = np.deg2rad(za - elevation_angle)

        cos_ang = np.cos(ang)
        sin_ang = np.sin(ang)

        output_detector_az[:, start:stop] = (
            np.outer(dx[:], cos_ang) - np.outer(dy[:], sin_ang) + az
        )
        output_detector_za[:, start:stop] = (
            np.outer(dy[:], cos_ang) + np.outer(dx[:], sin_ang) + za
        )


def interpolate_telescope_positions(
    data_timestamp: npt.NDArray,
    telescope_timestamp: npt.NDArray,
    tel_position: npt.NDArray,
    pps_position: npt.NDArray,
    data_pps: npt.NDArray,
    map_signal_mask: npt.NDArray,
    search_radius: int = 100,
    fit_radius: int = 200,
    direction: Literal['az', 'za'] = 'az',
) -> tuple[npt.NDArray, npt.NDArray]:
    """Interpolate and align the telescope positions."""
    n_samples = data_timestamp.size
    # Find the telescope positions and timestamps corresponding to the PPS pulses
    pps_tel_idx = (
        np.where(np.diff(pps_position) != 0)[0] + 1
    )  # Indices where the pps changes
    pps_tel_pos = pps_position[pps_tel_idx]
    pps_times_tel = telescope_timestamp[pps_tel_idx]

    # pdb.set_trace()
    if pps_tel_idx.size <= 1:
        # The telescope didn't move enough in this direction, so aligning the times
        # doesn't work. Just upsample the positions.
        _logger.info(
            f'Doing simple interpolation for detector positions in '
            f'{direction.upper()} direction.'
        )
        corrected_tel_pos = np.interp(
            data_timestamp, telescope_timestamp, tel_position, left=np.nan, right=np.nan
        )
        float_signal_mask = map_signal_mask[:].astype(float)
        interp_float_mask = np.interp(
            data_timestamp,
            telescope_timestamp,
            float_signal_mask[:],
            left=0,
            right=0,
        )
        corrected_signal_mask = (
            interp_float_mask >= 1 / 2
        )  # Convert float back to boolean
        corrected_signal_mask[np.isnan(corrected_tel_pos)] = False
        return corrected_tel_pos, corrected_signal_mask

    _logger.info(f'Using PPS for detector positions in {direction.upper()} direction.')

    # Upsample the telescope positions ignoring the positions when the pulse is receivd,
    # since the extra commands slow the loop
    interpolated_tel_pos = np.interp(
        data_timestamp,
        np.delete(telescope_timestamp, pps_tel_idx),
        np.delete(tel_position, pps_tel_idx),
    )
    float_mask = map_signal_mask.astype(float)
    interpolated_signal_mask = np.interp(
        data_timestamp,
        np.delete(telescope_timestamp, pps_tel_idx),
        np.delete(float_mask, pps_tel_idx),
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

    # Find the offset between the two sets of PPS samples, and shift the
    # interpolated telescope positions by this amount to sync them up.
    pps_offset = np.zeros(pps_samples_tel.shape, dtype=int)
    for i, pps_tel_sample in enumerate(pps_samples_tel):
        closest_data_sample = argclosest(pps_samples_data, pps_tel_sample)
        pps_offset[i] = pps_tel_sample - pps_samples_data[closest_data_sample]

    np.full(n_samples, np.nan)
    sample_boundaries = ((pps_samples_tel[1:] + pps_samples_tel[:-1]) / 2).astype(int)
    xp = []
    pos_fp = []
    mask_fp = []
    for i_tel_pps, this_pps_offset in enumerate(pps_offset):
        pps_sample = pps_samples_tel[i_tel_pps]
        max_shift = np.abs(this_pps_offset)
        if i_tel_pps == 0:
            i_tel_start = max(0, pps_sample - fit_radius)
            i_tel_stop = min(sample_boundaries[i_tel_pps], pps_sample + fit_radius + 1)
            i_fit_start = max(0, i_tel_start - max_shift)
            i_fit_stop = min(sample_boundaries[i_tel_pps], i_tel_stop + max_shift)
        elif i_tel_pps == pps_samples_tel.size - 1:
            i_tel_start = max(sample_boundaries[i_tel_pps - 1], pps_sample - fit_radius)
            i_tel_stop = min(n_samples, pps_sample + fit_radius + 1)
            i_fit_start = max(sample_boundaries[i_tel_pps - 1], i_tel_start - max_shift)
            i_fit_stop = min(n_samples, i_tel_stop + max_shift)
        else:
            i_tel_start = max(sample_boundaries[i_tel_pps - 1], pps_sample - fit_radius)
            i_tel_stop = min(sample_boundaries[i_tel_pps], pps_sample + fit_radius + 1)
            i_fit_start = max(sample_boundaries[i_tel_pps - 1], i_tel_start - max_shift)
            i_fit_stop = min(sample_boundaries[i_tel_pps], i_tel_stop + max_shift)
        # i_fit_start = max(0, i_tel_start - max_shift)
        # i_fit_stop = min(n_samples, i_tel_stop + max_shift)
        this_timestamp = data_timestamp[i_tel_start:i_tel_stop]
        possible_tel_pos = interpolated_tel_pos[i_fit_start:i_fit_stop]
        possible_singal_mask = interpolated_signal_mask[i_fit_start:i_fit_stop]
        n_times = this_timestamp.size
        if this_pps_offset < 0:
            this_tel_pos = possible_tel_pos[0:-max_shift]
            this_signal_mask = possible_singal_mask[0:-max_shift]
        else:
            this_tel_pos = possible_tel_pos[max_shift:]
            this_signal_mask = possible_singal_mask[max_shift:]
        min_length = min(n_times, this_tel_pos.size)
        this_tel_pos = this_tel_pos[:min_length]
        this_signal_mask = this_signal_mask[:min_length]
        this_timestamp = this_timestamp[:min_length]
        xp.extend(this_timestamp)
        pos_fp.extend(this_tel_pos)
        mask_fp.extend(this_signal_mask)

    corrected_tel_pos = np.interp(data_timestamp, xp, pos_fp, left=np.nan, right=np.nan)
    interp_float_mask = np.interp(data_timestamp, xp, mask_fp, left=0, right=0)
    corrected_signal_mask = interp_float_mask >= 1 / 2  # Convert float back to boolean
    corrected_signal_mask[np.isnan(corrected_tel_pos)] = False
    return corrected_tel_pos, corrected_signal_mask


#
# PPS-based telescope / RFSoC time alignment
#
PPS_PERIOD_S = 1.0


@dataclass
class PPSGrid:
    """Linear model of the RFSoC PPS pulse times: ``T(n) = t_ref + a + b * n``."""

    t_ref: float
    a: float
    b: float
    n_pulses: int
    rms_residual: float

    def time(self, n: npt.ArrayLike) -> npt.NDArray:
        """Return the (data clock) time of pulse number ``n``."""
        return self.t_ref + self.a + self.b * np.asarray(n, dtype=float)


@dataclass
class TelescopeAlignment:
    """Result of :func:`align_telescope_positions`.

    Attributes:
        az (npt.NDArray): Azimuth at every data sample (NaN outside telescope data).
        za (npt.NDArray): Zenith angle at every data sample (NaN outside telescope
            data).
        signal_mask (npt.NDArray): Map signal mask at every data sample.
        aligned (bool): Whether a PPS-based clock correction was applied. If False,
            the telescope timestamps were used as-is (plus ``default_offset``).
        info (dict): Diagnostics (pulse counts, fit coefficients, residuals, ...).
    """

    az: npt.NDArray
    za: npt.NDArray
    signal_mask: npt.NDArray
    aligned: bool
    info: dict = field(default_factory=dict)


def _wrap(x: npt.ArrayLike, period: float) -> npt.NDArray:
    """Wrap ``x`` into ``[-period / 2, period / 2)``."""
    return (np.asarray(x) + period / 2) % period - period / 2


def _circular_center(x: npt.NDArray, period: float) -> float:
    """Robust center of ``x`` modulo ``period`` (circular mean + median refinement)."""
    ang = 2 * np.pi * np.asarray(x) / period
    center = np.angle(np.mean(np.exp(1j * ang))) * period / (2 * np.pi)
    return center + float(np.median(_wrap(x - center, period)))


def fit_data_pps_grid(
    data_timestamp: npt.NDArray,
    data_pps: npt.NDArray,
    period: float = PPS_PERIOD_S,
    max_residual: float = 0.01,
) -> PPSGrid | None:
    """Fit the RFSoC PPS pulses to a regular grid of pulse times.

    Each pulse is assigned an integer pulse number using the known PPS period, so
    pulses missing from the data (e.g. dropped packets) and spurious pulses do not
    break the pulse numbering. Fitting a line to (pulse number, time) also averages
    away the +/- 1 sample quantization of the individual pulses.

    Arguments:
        data_timestamp (npt.NDArray): Equally spaced data timestamps.
        data_pps (npt.NDArray): 1 where a pulse was received, 0 elsewhere.
        period (float): Nominal PPS period in seconds.
        max_residual (float): Pulses further than this (s) from the grid are ignored.

    Returns:
        (PPSGrid | None): The fitted grid, or None if fewer than two consistent pulses
            were found.
    """
    pps = np.asarray(data_pps).astype(bool)
    # Rising edges only, so multi-sample pulses are counted once. A pulse already
    # high at sample 0 has an unknown start and is skipped.
    edges = np.flatnonzero(pps[1:] & ~pps[:-1]) + 1
    if edges.size < 2:  # noqa: PLR2004
        return None

    t_edges = np.asarray(data_timestamp)[edges]
    t_ref = float(t_edges[0])
    rel = t_edges - t_ref

    # Phase of the pulses on the 1 s grid; reject pulses off the dominant phase.
    phase = _circular_center(rel, period)
    inliers = np.abs(_wrap(rel - phase, period)) < max_residual
    if inliers.sum() < 2:  # noqa: PLR2004
        return None
    n = np.round((rel - phase) / period)

    a, b = phase, period
    for _ in range(5):
        if np.unique(n[inliers]).size < 2:  # noqa: PLR2004
            return None
        b, a = np.polyfit(n[inliers], rel[inliers], 1)
        resid = rel - (a + b * n)
        new_inliers = np.abs(resid) < max_residual
        if np.array_equal(new_inliers, inliers):
            break
        inliers = new_inliers

    rms = float(np.sqrt(np.mean(resid[inliers] ** 2)))
    if abs(b - period) > 1e-3 * period:
        _logger.warning(
            f'fit_data_pps_grid: Fitted PPS period {b:.6f} s differs from nominal '
            f'{period} s; check the data timestamp.'
        )
    _logger.debug(
        f'fit_data_pps_grid: {inliers.sum()}/{edges.size} pulses used, '
        f'period={b:.7f} s, rms residual={rms * 1e3:.3f} ms'
    )
    return PPSGrid(t_ref, float(a), float(b), int(inliers.sum()), rms)


def find_telescope_pps_times(
    telescope_timestamp: npt.NDArray,
    position: npt.NDArray,
    latched_position: npt.NDArray,
    drop_latch_rows: bool = True,
    max_segment_dt: float = 0.1,
    bracket_slack: float = 0.02,
    search_rows: int = 3,
    prior_motion_rows: int = 4,
) -> npt.NDArray:
    """Estimate the telescope-clock times of the PPS pulses seen by one motor axis.

    The motors latch their position when a pulse arrives. A new latch value means a
    pulse occurred between the previous latch read (row ``i - 1``) and this one (row
    ``i``). The time of the pulse is the time at which the recorded trajectory passed
    through the latched position, found by linear interpolation of the trajectory.

    A pulse is only used when this is well defined:
      * The latched value lies *strictly* between two consecutive positions, so the
        axis was actually moving. This rejects pulses while the axis was stationary
        and stale latch values (e.g. the first latch read after the axis was idle,
        which equals the current position).
      * The two positions are at most ``max_segment_dt`` apart in time, so the
        interpolated time is precise.
      * The crossing falls inside the bracket ``[t[i-1], t[i]]`` (+/- slack).
      * The axis was already moving in the ``prior_motion_rows`` rows before the
        change. A latch is only polled while its axis is being driven, so the first
        read at the start of a move can return a value latched long ago (the ZA
        latch holds the first pulse after it was last re-armed, ~1 s after the end
        of the previous ZA move). If the axis passes back through that position, the
        stale value would otherwise look like a valid crossing.

    Arguments:
        telescope_timestamp (npt.NDArray): Telescope timestamps.
        position (npt.NDArray): Positions of this axis.
        latched_position (npt.NDArray): Latched PPS positions of this axis.
        drop_latch_rows (bool): Exclude the rows where the latch changed from the
            trajectory, since the extra latch commands delay those rows.
        max_segment_dt (float): Maximum time between trajectory samples used to
            interpolate a crossing (s).
        bracket_slack (float): Tolerance on the bracket (s).
        search_rows (int): Number of rows on either side of the latch change to look
            for the crossing.
        prior_motion_rows (int): Number of rows before the latch change in which the
            axis must have moved.

    Returns:
        (npt.NDArray): Telescope-clock times of the identified pulses.
    """
    t = np.asarray(telescope_timestamp, dtype=float)
    pos = np.asarray(position, dtype=float)
    latch = np.asarray(latched_position, dtype=float)

    change_rows = np.flatnonzero(np.diff(latch) != 0) + 1
    keep = np.ones(t.size, dtype=bool)
    if drop_latch_rows:
        keep[change_rows] = False
    traj_rows = np.flatnonzero(keep)
    t_traj = t[traj_rows]
    pos_traj = pos[traj_rows]

    times = []
    for i in change_rows:
        p = latch[i]
        if np.ptp(pos[max(0, i - 1 - prior_motion_rows) : i]) == 0:
            continue  # Axis was not being driven before this latch read
        lo_t = t[i - 1] - bracket_slack
        hi_t = t[i] + bracket_slack
        # Segments of the (reduced) trajectory near row i
        k = np.searchsorted(traj_rows, i)
        j0 = max(0, k - 1 - search_rows)
        j1 = min(t_traj.size - 1, k + search_rows)
        if j1 <= j0:
            continue
        p0 = pos_traj[j0:j1]
        p1 = pos_traj[j0 + 1 : j1 + 1]
        t0 = t_traj[j0:j1]
        t1 = t_traj[j0 + 1 : j1 + 1]
        crosses = ((p0 - p) * (p1 - p) < 0) & ((t1 - t0) <= max_segment_dt)
        if not crosses.any():
            continue
        frac = (p - p0[crosses]) / (p1[crosses] - p0[crosses])
        t_cross = t0[crosses] + frac * (t1[crosses] - t0[crosses])
        t_cross = t_cross[(t_cross >= lo_t) & (t_cross <= hi_t)]
        if t_cross.size == 0:
            continue
        # If several crossings qualify, use the one closest to the bracket center
        times.append(t_cross[np.argmin(np.abs(t_cross - (t[i - 1] + t[i]) / 2))])

    return np.asarray(times, dtype=float)


@dataclass
class ClockOffsetModel:
    """Smooth model of the offset ``data_time - tel_time`` as a function of time.

    The offset is a piecewise-linear curve through ``(knots, values)`` (held constant
    beyond the ends) plus a constant per axis for the axis-specific read latency.
    """

    knots: npt.NDArray
    values: npt.NDArray
    axis_constants: dict[str, float]

    def offset(self, tel_time: npt.ArrayLike, axis: str | None = None) -> npt.NDArray:
        """Return ``data_time - tel_time`` at the given telescope-clock times."""
        const = self.axis_constants.get(axis, 0.0) if axis is not None else 0.0
        return np.interp(tel_time, self.knots, self.values) + const

    def to_data_clock(
        self, tel_time: npt.ArrayLike, axis: str | None = None
    ) -> npt.NDArray:
        """Convert telescope-clock times to data-clock times."""
        tel_time = np.asarray(tel_time, dtype=float)
        return tel_time + self.offset(tel_time, axis)


def _running_median(t: npt.NDArray, y: npt.NDArray, window: float) -> npt.NDArray:
    """Median of ``y`` within +/- ``window / 2`` of each (sorted) ``t``."""
    lo = np.searchsorted(t, t - window / 2)
    hi = np.searchsorted(t, t + window / 2, side='right')
    return np.array([np.median(y[a:b]) for a, b in zip(lo, hi, strict=True)])


def fit_clock_offset(
    pulse_times: dict[str, npt.NDArray],
    grid: PPSGrid,
    knot_spacing: float = 1.0,
    smoothing: float = 0.1,
    expected_offset: float = 0.0,
    max_residual: float = 0.1,
    n_sigma: float = 4.0,
    min_tolerance: float = 2e-3,
    min_pulses_per_axis: int = 5,
) -> tuple[ClockOffsetModel, dict] | None:
    """Fit the offset between the telescope clock and the data clock.

    The model is ``data_time = tel_time + c_axis + s(tel_time)``, where ``s`` is a
    smooth piecewise-linear curve shared by all axes and ``c_axis`` is a constant per
    axis that absorbs the axis-specific read latency. ``s`` is time-varying because
    the host clock used for the telescope timestamps wanders relative to the
    (linearized) RFSoC sample clock: slowly by tens of ms over minutes, and in
    some runs by transients of up to ~50 ms/s lasting ~10 s. Pulses arrive every
    second, so the default 1 s knot spacing follows those transients while the
    curvature penalty keeps the curve smooth and bridges gaps without pulses.

    ``s`` has knots every ``knot_spacing`` seconds and is regularized by a penalty on
    its curvature, so stretches without usable pulses (e.g. the telescope is not
    moving) are bridged smoothly. An axis with fewer than ``min_pulses_per_axis``
    pulses does not get its own constant. Mis-numbered or badly timed pulses are
    removed by iterative sigma clipping.

    Arguments:
        pulse_times (dict[str, npt.NDArray]): Telescope-clock pulse times per axis.
        grid (PPSGrid): The data PPS grid.
        knot_spacing (float): Spacing of the knots of ``s`` (s). Use ``np.inf`` for a
            single linear drift.
        smoothing (float): Weight of the curvature penalty relative to one pulse.
        expected_offset (float): Prior on the offset (s). The PPS only fixes the
            offset modulo the PPS period; the solution closest to this is chosen.
        max_residual (float): Absolute limit on a pulse's residual (s).
        n_sigma (float): Clipping threshold in robust standard deviations.
        min_tolerance (float): Lower limit on the clipping threshold (s).
        min_pulses_per_axis (int): Minimum pulses for an axis to get its own
            constant.

    Returns:
        (tuple[ClockOffsetModel, dict] | None): The model and diagnostics, or None
            if there are not enough usable pulses.
    """
    axes = [ax for ax, tp in pulse_times.items() if tp.size > 0]
    if not axes:
        return None
    t_all = np.concatenate([pulse_times[ax] for ax in axes])
    labels = np.concatenate([[ax] * pulse_times[ax].size for ax in axes])
    order = np.argsort(t_all)
    t_all, labels = t_all[order], labels[order]
    if t_all.size < 2:  # noqa: PLR2004
        return None

    # Initial offset (modulo the PPS period) from the pulse phases
    rel = t_all - grid.t_ref
    frac = (rel - grid.a) / grid.b
    offset0 = _circular_center((np.round(frac) - frac) * grid.b, grid.b)
    offset0 += grid.b * np.round((expected_offset - offset0) / grid.b)

    # Assign each telescope pulse to a data pulse number and measure the offsets
    n = np.round((rel + offset0 - grid.a) / grid.b)
    y = grid.time(n) - t_all  # data_time - tel_time

    # Axis constants are relative to the axis with the most pulses
    counts = {ax: int((labels == ax).sum()) for ax in axes}
    own = [ax for ax in axes if counts[ax] >= min_pulses_per_axis]
    ref_axis = max(own or axes, key=counts.get)
    rel_axes = [ax for ax in own if ax != ref_axis]
    valid = np.isin(labels, own) if own else np.ones(t_all.size, dtype=bool)

    # Piecewise-linear basis: each pulse touches two neighboring knots
    span = t_all[-1] - t_all[0]
    n_knots = (
        2
        if not np.isfinite(knot_spacing)
        else max(2, int(np.ceil(span / knot_spacing)) + 1)
    )
    knots = (
        np.linspace(t_all[0], t_all[-1], n_knots)
        if span > 0
        else t_all[[0, -1]] + [0, 1]
    )
    k = np.clip(np.searchsorted(knots, t_all, side='right') - 1, 0, n_knots - 2)
    w = (t_all - knots[k]) / (knots[k + 1] - knots[k])
    n_par = n_knots + len(rel_axes)
    axis_col = {ax: n_knots + i for i, ax in enumerate(rel_axes)}

    # Curvature penalty (second differences of the knot values)
    penalty = np.zeros((n_par, n_par))
    if n_knots > 2:  # noqa: PLR2004
        d2 = np.zeros((n_knots - 2, n_par))
        idx = np.arange(n_knots - 2)
        d2[idx, idx], d2[idx, idx + 1], d2[idx, idx + 2] = 1.0, -2.0, 1.0
        penalty = smoothing * d2.T @ d2

    def predict(params: npt.NDArray) -> npt.NDArray:
        pred = (1 - w) * params[k] + w * params[k + 1]
        for ax, col in axis_col.items():
            pred = pred + np.where(labels == ax, params[col], 0.0)
        return pred

    def solve(use: npt.NDArray) -> npt.NDArray:
        # Normal equations, accumulated sparsely (each row has <= 3 nonzeros)
        cols = [k[use], k[use] + 1]
        vals = [1 - w[use], w[use]]
        lab = labels[use]
        for ax, col in axis_col.items():
            cols.append(np.full(lab.size, col))
            vals.append((lab == ax).astype(float))
        ata = penalty.copy()
        aty = np.zeros(n_par)
        for ci, vi in zip(cols, vals, strict=True):
            np.add.at(aty, ci, vi * y[use])
            for cj, vj in zip(cols, vals, strict=True):
                np.add.at(ata, (ci, cj), vi * vj)
        # Tiny ridge keeps knots without any constraint well defined
        ata[np.diag_indices(n_par)] += 1e-9
        return np.linalg.solve(ata, aty)

    # Start from a running median so a few mis-numbered pulses can't skew the fit
    window = max(3 * knot_spacing, 6.0) if np.isfinite(knot_spacing) else np.inf
    start = _running_median(t_all, y, window) if np.isfinite(window) else np.median(y)
    inliers = valid & (np.abs(y - start) < max_residual)
    if inliers.sum() < 2:  # noqa: PLR2004
        return None
    for _ in range(20):
        params = solve(inliers)
        resid = y - predict(params)
        sigma = 1.4826 * np.median(np.abs(resid[inliers]))
        thresh = min(max(n_sigma * sigma, min_tolerance), max_residual)
        new_inliers = valid & (np.abs(resid) < thresh)
        if np.array_equal(new_inliers, inliers) or new_inliers.sum() < 2:  # noqa: PLR2004
            break
        inliers = new_inliers

    # Put the mean axis constant into the curve so each constant is a small latency
    consts = {ref_axis: 0.0} | {ax: float(params[col]) for ax, col in axis_col.items()}
    weights = {ax: (inliers & (labels == ax)).sum() for ax in consts}
    mean_const = sum(consts[ax] * weights[ax] for ax in consts) / max(
        1, sum(weights.values())
    )
    axis_constants = {ax: consts[ax] - mean_const for ax in consts}
    model = ClockOffsetModel(knots, params[:n_knots] + mean_const, axis_constants)

    info = {
        'axes_with_own_constant': [ref_axis, *rel_axes] if own else [],
        'axis_constants': axis_constants,
        'n_pulses': {ax: int((labels == ax).sum()) for ax in pulse_times},
        'n_inliers': {ax: int((inliers & (labels == ax)).sum()) for ax in pulse_times},
        'rms_residual': float(np.sqrt(np.mean(resid[inliers] ** 2))),
        'max_abs_residual': float(np.max(np.abs(resid[inliers]))),
        'offset_range': (float(np.min(model.values)), float(np.max(model.values))),
        'pulse_times': t_all,
        'pulse_axes': labels,
        'pulse_offsets': y,
        'pulse_residuals': resid,
        'pulse_inliers': inliers,
    }
    return model, info


def apply_backlash(position: npt.NDArray, backlash: float) -> npt.NDArray:
    """Convert motor encoder positions to the positions of the telescope.

    The telescope trails the encoder by ``backlash`` while moving, in whichever
    direction it is moving. After a reversal, the encoder travels ``2 * backlash``
    before the telescope follows; while the encoder is stationary, the telescope stays
    put. Without this correction, rows of a map scanned in opposite directions are
    offset from each other by ``2 * backlash``, whatever the scan speed.

    This must not be used on the positions compared to the PPS latch, since the latch
    and the positions it is compared to are both read from the encoder.

    Arguments:
        position (npt.NDArray): Encoder positions in time order. NaNs are left as they
            are.
        backlash (float): Half of the total backlash, in the units of ``position``.

    Returns:
        (npt.NDArray): The telescope positions. The mean of the two scan directions is
            unchanged.
    """
    if backlash < 0:
        raise ValueError(f'backlash must not be negative; got {backlash}')
    position = np.asarray(position, dtype=float)
    if backlash == 0:
        return position.copy()

    corrected = position.copy()
    finite = np.flatnonzero(np.isfinite(position))
    if finite.size == 0:
        return corrected

    # Assume that the backlash has been taken up in the direction of the first move
    first = position[finite[0]]
    moved = np.flatnonzero(np.abs(position[finite] - first) > 2 * backlash)
    direction = np.sign(position[finite[moved[0]]] - first) if moved.size else 0.0
    telescope = first - direction * backlash

    for i in finite.tolist():
        x = position[i]
        telescope = min(max(telescope, x - backlash), x + backlash)
        corrected[i] = telescope
    return corrected


def _strictly_increasing_rows(t: npt.NDArray) -> npt.NDArray:
    """Return indices that sort ``t`` and drop duplicate times."""
    order = np.argsort(t, kind='stable')
    keep = np.r_[True, np.diff(t[order]) > 0]
    return order[keep]


def align_telescope_positions(
    data_timestamp: npt.NDArray,
    data_pps: npt.NDArray,
    telescope_timestamp: npt.NDArray,
    az_tel: npt.NDArray,
    za_tel: npt.NDArray,
    az_pps: npt.NDArray,
    za_pps: npt.NDArray,
    map_signal_mask: npt.NDArray | None = None,
    primary_axis: Literal['az', 'za'] = 'az',
    knot_spacing: float = 1.0,
    smoothing: float = 0.1,
    expected_offset: float = 0.0,
    default_offset: float = 0.0,
    drop_latch_rows: bool = True,
    max_segment_dt: float = 0.1,
    max_residual: float = 0.1,
    min_pulses_per_axis: int = 5,
    az_backlash: float = 0.0,
    za_backlash: float = 0.0,
) -> TelescopeAlignment:
    """Align the telescope positions to the data timestamps using the shared PPS.

    Rather than locally shifting each axis to line up individual pulses, this finds
    a single smooth mapping from the telescope clock to the data clock and then
    resamples the raw telescope trajectory through it:

    1. Fit the data PPS pulses to a regular 1 s grid (:func:`fit_data_pps_grid`).
    2. For each axis, find the telescope-clock time of every pulse whose latched
       position can be located on the recorded trajectory, i.e. the axis was moving
       (:func:`find_telescope_pps_times`). Pulses while an axis is stationary are
       simply not used; they are not needed.
    3. Fit a smooth ``data_time = tel_time + offset_axis(tel_time)`` to all pulses
       from both axes together (:func:`fit_clock_offset`). The time-varying part is
       shared, so an axis with few or no usable pulses still gets a well constrained
       mapping.
    4. Map each raw telescope row onto the data clock and interpolate each axis onto
       ``data_timestamp``.

    Because every row is moved by a smooth, slowly varying amount, the shape of
    the trajectory is preserved: if only one axis moves in the raw telescope data,
    only that axis moves in the output, and simultaneous motion is kept as well.
    The axes can only differ by their (few ms) latency constants.

    Arguments:
        data_timestamp (npt.NDArray): Equally spaced data timestamps.
        data_pps (npt.NDArray): Data PPS (1 where a pulse was received).
        telescope_timestamp (npt.NDArray): Telescope timestamps.
        az_tel (npt.NDArray): Telescope azimuth.
        za_tel (npt.NDArray): Telescope zenith angle.
        az_pps (npt.NDArray): Latched azimuth at the most recent pulse.
        za_pps (npt.NDArray): Latched zenith angle at the most recent pulse.
        map_signal_mask (npt.NDArray | None): Per-row signal mask. All True if None.
        primary_axis ('az' | 'za'): The axis whose time mapping is used for the
            signal mask.
        knot_spacing (float): See :func:`fit_clock_offset`.
        smoothing (float): See :func:`fit_clock_offset`.
        expected_offset (float): Prior on the clock offset (s); the solution within
            half a PPS period of this is used.
        default_offset (float): Offset (s) to apply if the PPS cannot be used.
        drop_latch_rows (bool): See :func:`find_telescope_pps_times`.
        max_segment_dt (float): See :func:`find_telescope_pps_times`.
        max_residual (float): See :func:`fit_clock_offset`.
        min_pulses_per_axis (int): See :func:`fit_clock_offset`.
        az_backlash (float): Azimuth backlash to remove from the output (see
            :func:`apply_backlash`). Doesn't affect the time alignment.
        za_backlash (float): Zenith angle backlash to remove from the output.

    Returns:
        (TelescopeAlignment): The aligned positions, signal mask and diagnostics.
    """
    data_timestamp = np.asarray(data_timestamp, dtype=float)
    t_tel = np.asarray(telescope_timestamp, dtype=float)
    positions = {
        'az': np.asarray(az_tel, dtype=float),
        'za': np.asarray(za_tel, dtype=float),
    }
    latches = {
        'az': np.asarray(az_pps, dtype=float),
        'za': np.asarray(za_pps, dtype=float),
    }
    if map_signal_mask is None:
        map_signal_mask = np.ones(t_tel.size, dtype=bool)
    mask_float = np.asarray(map_signal_mask).astype(float)
    primary_axis = primary_axis.lower()

    info: dict = {}
    model: ClockOffsetModel | None = None

    grid = fit_data_pps_grid(data_timestamp, data_pps)
    info['data_pps_grid'] = grid
    if grid is None:
        _logger.warning('align_telescope_positions: Not enough PPS pulses in the data.')
    else:
        pulse_times = {
            ax: find_telescope_pps_times(
                t_tel,
                positions[ax],
                latches[ax],
                drop_latch_rows=drop_latch_rows,
                max_segment_dt=max_segment_dt,
            )
            for ax in ('az', 'za')
        }
        fit = fit_clock_offset(
            pulse_times,
            grid,
            knot_spacing=knot_spacing,
            smoothing=smoothing,
            expected_offset=expected_offset,
            max_residual=max_residual,
            min_pulses_per_axis=min_pulses_per_axis,
        )
        if fit is None:
            _logger.warning(
                'align_telescope_positions: No usable telescope PPS pulses '
                f'(az: {pulse_times["az"].size}, za: {pulse_times["za"].size}).'
            )
        else:
            model, fit_info = fit
            info.update(fit_info)
            lo, hi = fit_info['offset_range']
            consts = ', '.join(
                f'{ax.upper()} {c * 1e3:+.2f} ms'
                for ax, c in fit_info['axis_constants'].items()
            )
            _logger.info(
                f'align_telescope_positions: Clock offset {lo * 1e3:.2f} to '
                f'{hi * 1e3:.2f} ms (axis constants: {consts}); '
                f'inliers {fit_info["n_inliers"]} of {fit_info["n_pulses"]}; '
                f'rms residual {fit_info["rms_residual"] * 1e3:.2f} ms'
            )
    info['clock_model'] = model

    def to_data_clock(t: npt.NDArray, axis: str) -> npt.NDArray:
        if model is None:
            return t + default_offset
        return model.to_data_clock(t, axis)

    backlash = {'az': az_backlash, 'za': za_backlash}
    out = {}
    for ax in ('az', 'za'):
        telescope_position = apply_backlash(positions[ax], backlash[ax])
        rows = np.ones(t_tel.size, dtype=bool)
        if drop_latch_rows:
            rows[np.flatnonzero(np.diff(latches[ax]) != 0) + 1] = False
        rows = np.flatnonzero(rows)
        rows = rows[_strictly_increasing_rows(t_tel[rows])]
        out[ax] = np.interp(
            data_timestamp,
            to_data_clock(t_tel[rows], ax),
            telescope_position[rows],
            left=np.nan,
            right=np.nan,
        )

    rows = _strictly_increasing_rows(t_tel)
    interp_mask = np.interp(
        data_timestamp,
        to_data_clock(t_tel[rows], primary_axis),
        mask_float[rows],
        left=0,
        right=0,
    )
    signal_mask = (interp_mask >= 1 / 2) & ~np.isnan(out['az']) & ~np.isnan(out['za'])

    return TelescopeAlignment(
        az=out['az'],
        za=out['za'],
        signal_mask=signal_mask,
        aligned=model is not None,
        info=info,
    )
