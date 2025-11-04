"""Core functionality relating to data loading and processing."""


from __future__ import annotations
from pathlib import Path
import glob
import pdb
import time
import inspect
import logging
from itertools import chain, batched
import typing

import tables
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

from rfsocinterface.core.utils import gaussian_filter, GAUSSIAN_SIGMA, BAD_RFSOC_TONE_START_INDEX, decimate_in_chunks, PERMISSIONS_ALL_FULL
from rfsocinterface.core.losweep import LoSweepData
from rfsocinterface.core.utils import (
    get_tod_template,
    get_azel_template,
    get_optcam_template,
    get_processed_file_template,
    get_processed_level_file_template,
    get_cleaned_file_template,
    get_file_stub,
    get_map_file_template,
    get_beammap_file_template,
    get_params_file_template,
    DATA_DIRECTORY,
    DEFAULT_PARAMS_DIRECTORY,
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

RFSOC_TIME_OFFSET = -0.05  # -50 ms, empirically determined

PARAM_FILE_N_TONE_ATTRIBUTES = [
    'baseband_freqs',
    'tone_powers',
    'detector_delta_x',
    'detector_delta_y',
    'detector_pol',
    'detector_beam_ampl',
    'dfoverf_per_mK',
    'chanmask',
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
        ):
    """Compute change of basis, rotating with the specified angle."""

    # new_data = np.zeros(shape=(2, np.size(tone_index), data_1.shape[-1]))
    # pdb.set_trace()
    out_data[0, :] = np.cos(rotation_angle)[:, np.newaxis] * in_data[0, :] - np.sin(rotation_angle)[:, np.newaxis] * in_data[1, :]
    out_data[1, :] = np.sin(rotation_angle)[:, np.newaxis] * in_data[0, :] + np.cos(rotation_angle)[:, np.newaxis] * in_data[1, :]


def generate_calibrated_data(data_group: tables.Group, global_data_group: tables.Group):
    rotate_basis(
        data_group.data_gain_phase,
        data_group.data_IQ,
        -data_group.IQ_to_gain_phase_angle[:],
    )
    data_group.data_IQ[:] = data_group.data_IQ[:] - np.mean(data_group.data_IQ[:], axis=2, keepdims=True)
    # data.data_IQ[0, :] = data.data_IQ[0, :] - np.mean(data.data_IQ[0, :], axis=1, keepdims=True)
    # data.data_IQ[1, :] = data.data_IQ[1, :] - np.mean(data.data_IQ[1, :], axis=1, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f

    rotate_basis(data_group.data_IQ[:] / data_group.adc_units_to_hz[:][:, np.newaxis], data_group.data_freq_diss, data_group.IQ_to_freq_diss_angle[:])
    # rotate_basis(data.data_IQ, data.data_freq_diss, data.IQ_to_freq_diss_angle[:])

    # Finally, we need to get data_mK
    data_group.data_mK[:] = np.divide(data_group.data_freq_diss[0, :], global_data_group.df_per_mK[:][:, np.newaxis])
    # data.data_mK[:] = np.where(np.isinf(data.data_mK), np.nan, data.data_mK)

def new_generate_calibrated_data(pd: ProcessedDataL1):
    if isinstance(pd.get_node('data_IQ'), ExternalLink):
        data_IQ = np.zeros(pd.data_IQ.shape, pd.data_IQ.dtype)
    else:
        data_IQ = pd.data_IQ
        

    rotate_basis(
        pd.data_gain_phase,
        data_IQ,
        -pd.IQ_to_gain_phase_angle[:],
    )
    data_IQ[:] = data_IQ[:] - np.mean(data_IQ[:], axis=2, keepdims=True)
    # data.data_IQ[0, :] = data.data_IQ[0, :] - np.mean(data.data_IQ[0, :], axis=1, keepdims=True)
    # data.data_IQ[1, :] = data.data_IQ[1, :] - np.mean(data.data_IQ[1, :], axis=1, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f

    rotate_basis(data_IQ[:] / pd.adc_units_to_hz[:][:, np.newaxis], pd.data_freq_diss, pd.IQ_to_freq_diss_angle[:])
    # rotate_basis(data.data_IQ, data.data_freq_diss, data.IQ_to_freq_diss_angle[:])

    # Finally, we need to get data_mK
    pd.data_mK[:] = np.divide(pd.data_freq_diss[0, :], pd.df_per_mK[:][:, np.newaxis])
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


def remove_electronics_noise(data: npt.NDArray, fs: float, lp_filt_freq: float=10, max_modes: int=30) -> npt.NDArray:
    """Remove correlated electronics noise templates from the data.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples). Data should
            be in the gain/phase basis.
        fs (float): Sampling frequency of the data.
        lp_filt_freq (float, optional): Low-pass filter frequency for the templates. Defaults to 10 Hz.

    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    filt_sos = signal.butter(BUTTER_ORDER, lp_filt_freq, btype='low', fs=fs, output='sos', analog=False)
    # data_lp = signal.sosfiltfilt(filt_sos, data)
    data_lp = data

    templates = compute_templates(data_lp, max_modes=max_modes)  # N_chan x 2 x N_samples
    n_modes = templates.shape[1]
    denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2

    for i in range(n_modes):
        numerator = np.einsum('ijk,ik->ij', data_lp, templates[:, i])  # N_chan x N_detector
        corr = numerator / denominator[:, i:i+1]  # N_chan x N_detector
        data = data - np.einsum('ij,ikl->ijl', corr, templates[:, i:i+1])  # N_chan x N_detector x N_samples
        # data_lp = signal.sosfiltfilt(filt_sos, data)
        data_lp = data

    # denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2
    # numerator0 = np.einsum('ijk,ik->ij', data_lp, templates[:, 0])  # N_chan x N_detector
    # corr0 = numerator0 / denominator[:, 0:1]  # N_chan x N_detector
    # deproj = data - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    # deproj_lp = signal.sosfiltfilt(filt_sos, deproj)

    # numerator1 = np.einsum('ijk,ik->ij', deproj_lp, templates[:, 1])  # N_chan x N_detector
    # corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    # clean_data = deproj - np.einsum('ij,ikl->ijl', corr1, templates[:, 1:])
    return data 


def remove_electronics_noise_tables(
    data_gain_phase: tables.Array,
    fs: float,
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
# Data Classes
#

class ProcessedData:
    """Class contianing data from processed TOD files."""

    def __init__(self, pfile: tables.File):
        self._l1file = pfile
    
    def test_node(self, name: str) -> bool:
        try:
            self._l1file.get_node('/', name)
            return True
        except tables.exceptions.NosuchNodeError:
            return False

    
    def close(self):
        self._l1file.close()

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
    def processed_file_level1_template(self) -> str:
        return get_processed_file_template(self.date, self.setnum)

    @property
    def processed_file_level2_template(self) -> str:
        return get_processed_file_template(self.date, self.setnum, level=2)

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
        return Path(f'{DATA_DIRECTORY}/{self.date}')
    
    @property
    def date(self) -> str:
        return self._l1file.root._v_attrs.date
    
    @date.setter
    def date(self, date: str):
        self._l1file.root._v_attrs.date = date

    @property
    def setnum(self) -> int:
        return self._l1file.root._v_attrs.setnum
    
    @setnum.setter
    def setnum(self, setnum: int):
        self._l1file.root._v_attrs.setnum = setnum

    def carrier_amplitude_norm(self) -> npt.NDArray:
        Z = self.carrier_amp_I + 1j*self.carrier_amp_Q
        return np.mean(np.abs(Z), axis=0)

    @property
    def n_tones(self) -> int:
        return self._l1file.root.detector_0.data._v_attrs.n_tones 

    @property
    def n_samples(self) -> int:
        return self._l1file.root.detector_0.data._v_attrs.n_samples
    
    @property
    def optical_image(self) -> tables.Array:
        return self._l1file.root.optical_image
    
    @property
    def carrier_amp_I(self) -> tables.Array:
        return self._l1file.root.detector_0.data.carrier_amplitudes[0]
    
    @property
    def carrier_amp_Q(self) -> tables.Array:
        return self._l1file.root.detector_0.data.carrier_amplitudes[1]

    @property
    def df_per_mK(self) -> tables.Array:
        return self._l1file.root.detector_0.global_data.df_per_mK

    @property
    def data_IQ(self) -> tables.Array:
        return self._l1file.root.detector_0.data.data_IQ
    
    @property
    def data_I(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_IQ[0]

    @property
    def data_Q(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_IQ[1]
    
    @property
    def IQ_to_gain_phase_angle(self) -> tables.Array:
        return self._l1file.root.detector_0.data.IQ_to_gain_phase_angle

    @property
    def IQ_to_freq_diss_angle(self) -> tables.Array:
        return self._l1file.root.detector_0.data.IQ_to_freq_diss_angle
    
    @property
    def adc_units_to_hz(self) -> float:
        return self._l1file.root.detector_0.data.adc_units_to_hz

    @property
    def data_freq_diss(self) -> tables.Array:
        return self._l1file.root.detector_0.data.data_freq_diss

    @property
    def data_freq(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_freq_diss[0]
    
    @property
    def data_diss(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_freq_diss[0]
    
    @property
    def data_mK(self) -> tables.Array:
        return self._l1file.root.detector_0.data.data_mK
    
    @property
    def data_gain_phase(self) -> tables.Array:
        return self._l1file.root.detector_0.data.data_gain_phase
    
    @property
    def data_gain(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_gain_phase[0]
    
    @property
    def data_phase(self) -> npt.NDArray:
        return self._l1file.root.detector_0.data.data_gain_phase[1]
    
    @property
    def timestamp(self) -> tables.Array:
        return self._l1file.root.detector_0.data.timestamp

    @property
    def time(self) -> npt.NDArray:
        return self.timestamp - self.timestamp[0]
    
    @property
    def delta_t(self) -> float:
        return np.median(self.time - np.roll(self.time, 1))

    @property
    def fs(self) -> float:
        return 1 / self.delta_t
    
    @property
    def detector_az(self) -> tables.Array:
        return self._l1file.root.detector_0.data.detector_az

    @property
    def detector_za(self) -> tables.Array:
        return self._l1file.root.detector_0.data.detector_za

    @property
    def vis(self) -> tables.Array:
        return self._l1file.root.detector_0.global_data.vis

    @property
    def detector_pol(self) -> tables.Array:
        return self._l1file.root.detector_0.global_data.detector_pol
    
    @property
    def chanmask(self) -> tables.Array:
        return self._l1file.root.detector_0.global_data.chanmask
    
    @property
    def receipt(self) -> str:
        return self._l1file.root._v_attrs.receipt 

    def add_receipt(self, receipt: str):
        """Add a receipt entry to the processed data file."""
        self._l1file.root._v_attrs.receipt = receipt
        self._l1file.flush()

    @classmethod
    def from_tod(
        cls,
        date: str,
        setnum: int,
        losweep: str | None=None,
        beam_map_mode: bool=False,
        do_electronics_noise_removal: bool=True,
        electronics_noise_lp_filt_freq: float=10,
        ds_factor: int=1,
        max_modes: int=30,
    ) -> ProcessedData:

        #20230803_rfsoc1_TOD_set1012
        date = date
        setnum = setnum
    

        folder = Path(f'{DATA_DIRECTORY}/{date}')
        todtemplate = get_tod_template(date, setnum)
        tele_template = Path(get_azel_template(date, setnum))
        optcam_template = Path(get_optcam_template(date ,setnum))

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = tables.open_file(tele_template, 'r')
        
        if optcam_exists:
            optcam_file = tables.open_file(optcam_template, 'r')
        

        # Create processed data file
        todlist = glob.glob(todtemplate)

        if len(todlist) == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

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
        

        pfile_path = Path(get_processed_file_template(date, setnum))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.open_file(pfile_path, 'w')
        pfile.root._v_attrs.date = date
        pfile.root._v_attrs.setnum = setnum
        pfile.root._v_attrs.receipt = ''

        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            pfile.create_array(pfile.root, 'optical_image', obj=optcam_file.root.optical_image[:])
            optcam_file.close()
        else:
            pfile.create_array(pfile.root, 'optical_image', obj=np.array([]))
            optical_image = None

        # dIQ_df = np.array([])
        # carrier_amp_I = np.array([])
        # carrier_amp_Q = np.array([])
        # df_per_mK = np.array([])
        # data_freq_diss = np.array([])
        # data_gain_phase = np.array([])
        # gain_phase_angle = np.array([])
        # data_mK = 0
        # chanmask = np.array([], dtype=np.int32)
        # detector_pol = np.array([])
        # detector_az = np.array([[]])
        # detector_za = np.array([[]])
        # Iterate over the TOD Files
        for i, file in enumerate(todlist):
                #compute the derivatives to obtain frequency direction
            with tables.open_file(file, 'r') as f:
                raw_global_data = f.root.global_data
                raw_dimension = f.root.dimension
                time_ordered_data = f.root.time_ordered_data

                # NOTE: Temporary fix until n_sample is fixed in the raw files
                # n_samples = raw_dimension.n_sample[0]
                n_samples = time_ordered_data.adc_i.shape[-1]
                n_samples_ds = int(np.ceil(n_samples / ds_factor))
                n_tones = raw_dimension.n_tones[0]

                # TODO: Change this for when there are multiple TOD files
                detector = pfile.create_group('/', f'detector_{i}')
                detector_global_data = pfile.create_group(detector, 'global_data')
                pfile.create_array(detector_global_data, 'vis', vis)
                pfile.create_array(detector_global_data, 'df_per_mK', shape=(n_tones,), atom=tables.Float64Atom())
                chanmask = pfile.create_array(detector_global_data, 'chanmask', shape=(n_tones,), atom=tables.Int8Atom(dflt=1))
                chanmask[:] = 1
                pfile.create_array(detector_global_data, 'detector_pol', shape=(n_tones,), atom=tables.Int8Atom())
                pfile.create_array(detector_global_data, 'optical_visibility', shape=(1,), atom=tables.Float64Atom())

                detector_data = pfile.create_group(detector, 'data')
                detector_data._v_attrs.n_tones = n_tones
                detector_data._v_attrs.n_samples = n_samples_ds
                pfile.create_array(detector_data, 'timestamp', shape=(n_samples_ds,), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'IQ_to_freq_diss_angle', shape=(n_tones,), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'adc_units_to_hz', shape=(n_tones,), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'carrier_amplitudes', shape=(2, n_tones), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'data_IQ', shape=(2, n_tones, n_samples_ds), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'data_gain_phase', shape=(2, n_tones, n_samples_ds), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'IQ_to_gain_phase_angle', shape=(n_tones,), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'data_freq_diss', shape=(2, n_tones, n_samples_ds), atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'data_mK', shape=(n_tones, n_samples_ds), atom=tables.Float64Atom())
                azel_shape = (n_tones, n_samples_ds) if azel_exists else (1, 0)
                pfile.create_array(detector_data, 'detector_az', shape=azel_shape, atom=tables.Float64Atom())
                pfile.create_array(detector_data, 'detector_za', shape=azel_shape, atom=tables.Float64Atom())

                # # Temporary fix for testing code:
                # f.baseband_freqs = np.load('/data/20250422/20250422_tone_list.npy')
                # f.lo_freq = np.array([4e8])

                if losweep:
                    losweep = Path(losweep)
                    # f.append_lo_sweep(losweep)
                    if losweep.suffix == '.npy':
                        sweep_data = np.load(folder / losweep)
                    else:
                        with tables.open_file(folder / losweep, 'r') as sweep_file:
                            sweep_data = sweep_file.root.global_data.lo_sweep
                    sweep_data = raw_global_data.lo_sweep
                elif raw_global_data.lo_sweep is not None:
                    sweep_data = raw_global_data.lo_sweep
                else:
                    raise RuntimeError('No LO sweep provided. Canceliing processing of file.')

                # f.lo_freq[:] = 4e8
                lo_freq = raw_global_data.lo_freq[:]
                # lo_freq = 4e8
                sweep = LoSweepData(raw_global_data.baseband_freqs, lo_freq, sweep_data, raw_global_data.chanmask[:])
                IQ_to_freq_diss_angle, adc_units_to_hz = sweep.freq_direction()
                detector_data.IQ_to_freq_diss_angle[:] = IQ_to_freq_diss_angle

                detector_data.adc_units_to_hz[:] = adc_units_to_hz
                # if np.size(dIQ_df) > 0:
                #     dIQ_df = np.concatenate((dIQ_df, this_dIQ_df), axis=0)
                # else:
                #     dIQ_df = np.copy(this_dIQ_df)
                time_ordered_data = f.root.time_ordered_data

                # Create timestamp
                if i == 0:  # Only should make this once, since it's never changed
                    time = time_ordered_data.timestamp

                    # Drop first few seconds of time samples
                    cut_time = 5  # Time in seconds to cut from the front
                    cut_samples = int(cut_time // np.median(np.diff(time)))
                    
                    # Exclude samples that dropped packets
                    # NOTE: The packet counter is all zeros currently??
                    packet_idx = time_ordered_data.pkt_idx[:]
                    dpkt_idx = np.diff(packet_idx)
                    good_idx = np.argwhere(dpkt_idx == 1).flatten()[cut_samples:]

                    # Fit a line to the samples without dropped packets and 
                    # generate a new timestamp.
                    good_times = time[cut_samples:][good_idx]
                    reg = linregress(good_idx, good_times)
                    time_0 = time[0]
                    total_time = reg.slope * n_samples
                    timestamp = np.linspace(0, total_time, n_samples_ds) + time_0
                    # pdb.set_trace()
                    detector_data.timestamp[:] = timestamp



                    # dtime = np.diff(good_times)
                    # total_time = np.ptp(good_times)
                    # timestamp = np.linspace(0, total_time + cut_time, n_samples_ds) + np.min(good_times)
                    # dtime = timestamp - time[::ds_factor]
                    # std = np.std(dtime)
                    # median = np.median(dtime)
                    # good_idx = np.argwhere(np.abs(dtime - median) < 0.5*std).flatten()
                    # median_diff = np.median(dtime[good_idx])
                    # detector_data.timestamp[:] = timestamp - median_diff - 0.04

                    # # Fit a line to the good times and generate new timestamps
                    # dtime = np.diff(good_times)
                    # std = np.std(dtime)
                    # median = np.median(dtime)
                    # skip_idx = np.where(dtime > 0.1)
                    # # good_idx = np.argwhere(np.abs(dtime - median) < 0.2 * median).flatten() + 1
                    # good_idx = np.argwhere(np.abs(dtime - median) < 1.5*std).flatten()
                    # reg = linregress(good_idx, good_times[good_idx])
                    # time_0 = reg.intercept
                    # total_time = reg.slope * n_samples
                    # detector_data.timestamp[:] = np.linspace(0, total_time, n_samples_ds) + time_0
                    
            
                #compute the calibration factor from dfoverf to mK
                detector_global_data.detector_pol[:] = raw_global_data.detector_pol[:]
                if np.count_nonzero(detector_global_data.detector_pol) == 0:
                    detector_global_data.detector_pol[:] = np.ones_like(detector_global_data.detector_pol)

                detector_beam_ampl = raw_global_data.detector_beam_ampl[:]
                if np.count_nonzero(detector_beam_ampl) == 0:
                    detector_beam_ampl = np.ones_like(detector_beam_ampl)

                dfoverf_per_mK = raw_global_data.dfoverf_per_mK[:] * -1
                if np.count_nonzero(dfoverf_per_mK) == 0:
                    dfoverf_per_mK = np.ones_like(dfoverf_per_mK)
                # plt.plot(dfoverf_per_mK, label='Old')

                detector_f = sweep.tone_list
                # detector_f = f.baseband_freqs[:] + f.lo_freq[:]

                # NOTE: Temporary fix: create dummy frequencies if they don't exist
                if np.count_nonzero(detector_f) == 0:  
                    detector_f[:] = np.linspace(0, 250e6, detector_f.size)

                detector_global_data.df_per_mK[:] = compute_df_per_mK(
                    detector_global_data.detector_pol,
                    detector_beam_ampl,
                    detector_f,
                    dfoverf_per_mK,
                ) 
                # df_per_mK = np.concatenate((df_per_mK,this_df_per_mK), axis=0)

                #create the calibrated datastreams-----------------------------------------------------------
                #first get the I and Q data
                # data_I = np.ndarray.astype(time_ordered_data.adc_i, np.float64)
                # data_Q = np.ndarray.astype(time_ordered_data.adc_q, np.float64)

                if int(date[:4]) < 2025:
                    expr = tables.Expr('time_ordered_data.adc_i[:, 0] != 0')
                    expr.eval()
                    valid_tone_index = np.ndarray.flatten(np.argwhere(expr))
                    valid_tone_index = valid_tone_index[:n_tones]
                else:
                    valid_tone_index = np.arange(n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX

                if ds_factor > 1:
                    # decimate_in_chunks(time_ordered_data.adc_i[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[0, :])
                    # decimate_in_chunks(time_ordered_data.adc_q[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[1, :])
                    detector_data.data_IQ[0, :] = signal.decimate(time_ordered_data.adc_i[valid_tone_index, :], ds_factor)
                    detector_data.data_IQ[1, :] = signal.decimate(time_ordered_data.adc_q[valid_tone_index, :], ds_factor)
                else:
                    detector_data.data_IQ[0, :] = time_ordered_data.adc_i[valid_tone_index, :]
                    detector_data.data_IQ[1, :] = time_ordered_data.adc_q[valid_tone_index, :]
                detector_data.carrier_amplitudes[:] = np.nanmedian(detector_data.data_IQ, axis=2)
                # detector_data.carrier_amplitudes[0] = np.nanmedian(time_ordered_data.adc_i[valid_tone_index, :], axis=1)
                # detector_data.carrier_amplitudes[1] = np.nanmedian(time_ordered_data.adc_q[valid_tone_index, :], axis=1)

                
                # Rotate to Gain / Phase

                detector_data.IQ_to_gain_phase_angle[:] = np.atan2(detector_data.carrier_amplitudes[0], detector_data.carrier_amplitudes[1])  # N_chan

                rotate_basis(
                    detector_data.data_IQ,
                    detector_data.data_gain_phase,
                    detector_data.IQ_to_gain_phase_angle,
                )

                fs = 1 / np.median(np.diff(detector_data.timestamp[:]))

                # TODO: Make this optional I guess
                if do_electronics_noise_removal:
                    # data_gain_phase = np.stack((detector_data.data_gain, detector_data.data_phase), axis=0)
                    # detector_data.data_gain[:], detector_data.data_phase[:] = remove_electronics_noise2(data_gain_phase)
                    remove_electronics_noise_tables(detector_data.data_gain_phase, fs, lp_filt_freq=electronics_noise_lp_filt_freq, max_modes=max_modes)
                

                # Create calibrated data
                generate_calibrated_data(detector_data, detector_global_data)

                # if np.size(data_freq_diss) > 0:
                #     data_freq_diss = np.concatenate((data_freq_diss, detector_data.data_freq), axis=0)
                # else:
                #     data_freq_diss = np.copy(detector_data.data_freq)

                # if np.size(data_mK) != 1:
                #     data_mK = np.concatenate((data_mK, detector_data.data_mK), axis=0)
                # else:
                #     data_mK = np.copy(detector_data.data_mK)
                #now the telescope data to get coordinates
                if azel_exists:
                    detector_dx_dy_elevation_angle = raw_global_data.detector_dx_dy_elevation_angle[0]
                    this_az_tel = np.interp(detector_data.timestamp, timestamp_tel, az_tel)
                    this_za_tel = np.interp(detector_data.timestamp, timestamp_tel, za_tel)
                    this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_za_tel)
                    this_detector_delta_x = raw_global_data.detector_delta_x[:]
                    this_detector_delta_y = raw_global_data.detector_delta_y[:]
                    if beam_map_mode:
                        this_detector_delta_x *= 0
                        this_detector_delta_y *= 0
                    #save the az/el information to the file
                    detector_data.detector_az[:] = np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                                np.outer(this_detector_delta_y,np.sin(this_ang)) + \
                                np.outer(np.ones(n_tones), this_az_tel)
                    detector_data.detector_za[:] = np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                                np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                                np.outer(np.ones(n_tones), this_za_tel)
                
                    # Close telescope file
                    azel_file.close()

                #also save the chanmask and detector polarization information
                chanmask = raw_global_data.chanmask[:]
                off_res = np.argwhere(chanmask == 0).flatten()
                no_pol = np.ndarray.flatten(np.argwhere(raw_global_data.detector_pol[:] < 1))
                # TODO: This is a temporary fix, should be removed when the polarization
                # is properly set up on the lab computer.
                if np.size(no_pol > 0):
                    chanmask[no_pol] = -1
                # Preserve off-resonance indices
                chanmask[off_res] = 0
                detector_global_data.chanmask[:] = chanmask
    #        detector_pol = np.concatenate((detector_pol, f.detector_pol[:]))
        # pfile.close()
        return cls(pfile)

    def with_values(self, **kwargs) -> ProcessedData:
        new_params = {
            key: np.copy(self.__getattribute__(key)) if key not in kwargs else kwargs[key]
            for key in vars(self).keys()
        }
        for key, val in kwargs.items():
            self._l1file.root.detector_0.data.__getattribute__(key)[:] = val
        return ProcessedData(self.file)

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r') -> ProcessedData:
        filename = Path(get_processed_file_template(date, setnum))

        if not filename.exists():
            raise FileNotFoundError(f'Could not find a processed data file on {date} with setnum {setnum}.')
        
        file = tables.File(filename, mode)
        return ProcessedData(file)
    
    def close(self):
        self._l1file.close()


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
    
    def __getitem__(self, key):
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

STATIC_PROCESSED_DATA_FIELDS = [
    'df_per_mK',
    'detector_az',
    'detector_za',
    'detector_pol',
    'optical_visibility',
    'optical_image',
    'interpolated_indices',
]

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
    'optical_visibility': '/global_data',
}

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
    
    
    def create_group(self, where: tables.Group | str, name: str) -> tables.Group:
        return self._file.create_group(where, name)
    
    def create_external_link(self, where: tables.Group | str, name: str, target: str) -> ExternalLink:
        return self._file.create_external_link(where, name, target)

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
        return get_processed_level_file_template(self.date, self.setnum, level=self.level)

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
        return Path(f'{DATA_DIRECTORY}/{self.date}')
    
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

def find_missed_packets(
    raw_timestamp: tables.Array,
    n_samples: int,
    window_size: int=5,
    sigma: float=3.0,
) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
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
    corrected_packet_idx = np.zeros(n_samples, dtype=int)
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
                    corrected_packet_idx[i] = corrected_packet_idx[i - 1] + large_window_packets_missed + 1

                    # Don't need to re-evaluate the next few samples, since their offset
                    # was already accounted for.
                    for j in range(i + 1, i + large_window_packets_missed + 1):
                        corrected_packet_idx[j] = corrected_packet_idx[j - 1] + 1
                    i = j
                    continue
                else:
                    corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
            else:
                corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1

            # plt.scatter(range(window_min_idx, window_max_idx + 1), timestamp_window)
            # plt.show()
            # pdb.set_trace()
        else:
            corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
        i += 1

    # new_timestamp.append(fit.slope * corrected_packet_idx + fit.intercept)
    print(f'{np.sum(missed_packets[:, 1])} missed packets')

    # Plotting Code for Debugging
    # fit = linregress(corrected_packet_idx, raw_timestamp[:])
    # x = np.arange(n_samples)
    # y = fit.slope * x + fit.intercept
    # plt.scatter(corrected_packet_idx, timestamp[:])
    # plt.scatter(corrected_packet_idx, new_timestamp)
    # plt.plot(x, y, color='red', linestyle='--')
    # plt.show()
    # pdb.set_trace()
    return missed_packets, corrected_packet_idx


def interpolate_timestamp(
    raw_timestamp: npt.NDArray,
    new_timestamp: tables.Array,
    packet_indices: npt.NDArray,
) -> npt.NDArray:
    normalized_packet_indices = packet_indices - packet_indices[0]
    n_samples = len(new_timestamp)
    fit = linregress(normalized_packet_indices, raw_timestamp[:])
    new_timestamp[:] = fit.slope * np.arange(n_samples) + fit.intercept + RFSOC_TIME_OFFSET
    return fit.slope * normalized_packet_indices + fit.intercept

    
def interpolate_missing_data(
    data_I: tables.Array,
    data_Q: tables.Array,
    timestamp: tables.Array,
    missed_packets: npt.NDArray,
    packet_indices: npt.NDArray,
    valid_tone_index: npt.NDArray,
) -> tuple[npt.NDArray. npt.NDArray, npt.NDArray]:
    total_missed_packets = np.sum(missed_packets[:, 1])
    n_tones = np.size(valid_tone_index)
    n_samples = data_I.shape[-1]
    # total_samples = raw_data_I.shape[-1] + total_missed_packets

    interpolated_indices = []
    interpolated_data = np.zeros((2, n_tones, total_missed_packets), dtype=data_I.dtype)
    normalized_packet_indices = packet_indices - packet_indices[0]

    # Iterate over the spots where data was missed
    count = 0
    for i, this_missed_packets in missed_packets:
        window_size = 5 * this_missed_packets
        index = normalized_packet_indices[i]
        prev_index = normalized_packet_indices[i - 1]
        # Fit a spline using data from nearest (window_size * 2) packets
        min_t = max(0, i - window_size)
        max_t = min(n_samples, i + window_size)
        window = range(min_t, max_t + 1)
        times = timestamp[packet_indices[window]]
        i_data = data_I[:, window][valid_tone_index, :]
        q_data = data_Q[:, window][valid_tone_index, :]
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
        interpolated_indices.extend(this_interpolated_indices)
        # data_IQ[:, :, this_interpolated_indices] = new_data
        interpolated_data[:, :, count:count + this_missed_packets] = new_data
        count += this_missed_packets

        # Plotting Code for Debugging
        # ax = plt.axes(projection='3d')
        # x = np.linspace(times[0], times[-1], 150)
        # ax.plot3D(x, poly.polyval(x - times[0], fit_I)[0], poly.polyval(x - times[0], fit_Q)[0], label='Polynomial Fit')
        # ax.scatter3D(times, i_data[0, :], q_data[0, :], label='Actual Values')
        # ax.scatter3D(missed_packet_t, *new_data[:, 0], label='Interpolated Points')
        # ax.set_xlabel('Timestamp (s)')
        # ax.set_ylabel('ADC I')
        # ax.set_zlabel('ADC Q')
        # ax.legend()
        # plt.show()
        # pdb.set_trace()
    return interpolated_indices, interpolated_data


class BaseProcessedData(DataStorage):

    def __init__(self, file: tables.File, level: int=1):
        super().__init__(file)
        self.level = level

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r', level: int=1):
        fname = get_processed_level_file_template(date, setnum, level=level)
        return cls(tables.File(fname, mode=mode), level=level)

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
    
    def get_lo_sweep_data(self) -> npt.NDArray:
        lo_sweep = None
        for node in self.lo_sweep_group._f_walknodes('ExternalLink'):
            this_lo_sweep = node(mode='r')[:]
            if lo_sweep is None:
                lo_sweep = this_lo_sweep
            else:
                lo_sweep = np.append(lo_sweep, this_lo_sweep, axis=1)
        return lo_sweep
    
    @property
    def lo_freq(self) -> float:
        return self.lo_sweep_group._v_attrs.lo_freq

    @lo_freq.setter
    def lo_freq(self, lo_freq: float):
        self.lo_sweep_group._v_attrs.lo_freq = lo_freq
    
    @property
    def baseband_freqs(self) -> tables.Array:
        return self.get_node_value('baseband_freqs')

    @property
    def tones(self) -> npt.NDArray:
        return self.baseband_freqs[:] + self.lo_freq

    @property
    def n_tones(self) -> int:
        return self._file.root.data._v_attrs.n_tones 
    
    @n_tones.setter
    def n_tones(self, n_tones: int):
        self._file.root.data._v_attrs.n_tones = n_tones

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
    
    def get_data_I(self) -> npt.NDArray:
        return self.data_IQ[0]

    def get_data_Q(self) -> npt.NDArray:
        return self.data_IQ[1]

    @property
    def interpolated_indices(self) -> tables.Array:
        return self.get_node_value('interpolated_indices')
  
    @property
    def timestamp(self) -> tables.Array:
        return self.get_node_value('timestamp')

    @property
    def time(self) -> npt.NDArray:
        return self.timestamp[:] - self.timestamp[0]
    
    @property
    def delta_t(self) -> float:
        return np.median(self.time - np.roll(self.time, 1))

    @property
    def fs(self) -> float:
        return 1 / self.delta_t
    
    @property
    def detector_az(self) -> tables.Array:
        return self.get_node_value('detector_az')

    @property
    def detector_za(self) -> tables.Array:
        return self.get_node_value('detector_za')

    @property
    def optical_visibility(self) -> tables.Array:
        return self.get_node_value('optical_visibility')

    @property
    def dfoverf_per_mK(self) -> tables.Array:
        return self.get_node_value('dfoverf_per_mK')
        
    @property
    def detector_beam_ampl(self) -> tables.Array:
        return self.get_node_value('detector_beam_ampl')

    @property
    def detector_pol(self) -> tables.Array:
        return self.get_node_value('detector_pol')
    
    @property
    def chanmask(self) -> tables.Array:
        return self.get_node_value('chanmask')


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

        folder = Path(f'{DATA_DIRECTORY}/{date}')
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
        ntod = len(todlist)
        if ntod == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

        # Get the n_tones and n_samples from all TOD files to determine array sizes
        sample_counts = []
        tone_counts = []
        for file in todlist:
            with tables.open_file(file, 'r') as f:
                raw_time_ordered_data = f.root.time_ordered_data
                # NOTE: Temporary fix until n_sample is fixed in the raw files
                # n_samples = raw_dimension.n_sample[0]
                n_samples = raw_time_ordered_data.adc_i.shape[-1]
                sample_counts.append(n_samples)
                raw_dimension = f.root.dimension
                tone_counts.append(raw_dimension.n_tones[0])
        n_samples = min(sample_counts)
        total_samples = n_samples
        n_tones = sum(tone_counts)


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
        pfile_path = Path(get_processed_level_file_template(date, setnum, level=0))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.open_file(pfile_path, 'w')
        pfile.root._v_attrs.date = date
        pfile.root._v_attrs.setnum = setnum
        pfile.root._v_attrs.receipt = ''



        time_ordered_data_group = pfile.create_group('/', 'data')
        global_data_group = pfile.create_group('/', 'global_data')
        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            pfile.create_array(global_data_group, 'optical_image', obj=optcam_file.root.optical_image[:])
            optcam_file.close()
        else:
            pfile.create_array(global_data_group, 'optical_image', obj=np.array([]))
            optical_image = None
        dfoverf_per_mK = pfile.create_earray(global_data_group, 'dfoverf_per_mK', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        detector_beam_amplitude = pfile.create_earray(global_data_group, 'detector_beam_ampl', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        chanmask = pfile.create_earray(global_data_group, 'chanmask', shape=(0,), expectedrows=n_tones, atom=tables.Int8Atom(dflt=1))
        baseband_freqs = pfile.create_earray(global_data_group, 'baseband_freqs', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        # chanmask[:] = 1
        detector_pol = pfile.create_earray(global_data_group, 'detector_pol', shape=(0,), expectedrows=n_tones, atom=tables.Int8Atom())
        optical_visibility = pfile.create_array(global_data_group, 'optical_visibility', obj=vis)

        time_ordered_data_group._v_attrs.n_tones = n_tones
        time_ordered_data_group._v_attrs.n_samples = n_samples
        corrected_packet_index = pfile.create_earray(time_ordered_data_group, 'packet_index', shape=(0,), expectedrows=n_samples, atom=tables.UInt32Atom())
        interpolated_indices = pfile.create_earray(time_ordered_data_group, 'interpolated_indices', shape=(0,), atom=tables.UInt32Atom())
        lo_group = pfile.create_group('/', 'lo_sweep')

        # TODO: Interpolation Code


        

        # Iterate over the TOD Files, extracting IQ data and calibration info
        for i, file in enumerate(todlist):
            with tables.open_file(file, 'r') as f:
                raw_global_data = f.root.global_data
                raw_time_ordered_data = f.root.time_ordered_data
                this_n_tones = tone_counts[i]

                # Get the correct tone indices in the TOD file
                if int(date[:4]) < 2025:
                    expr = tables.Expr('time_ordered_data.adc_i[:, 0] != 0')
                    expr.eval()
                    valid_tone_index = np.ndarray.flatten(np.argwhere(expr))
                    valid_tone_index = valid_tone_index[:this_n_tones]
                else:
                    valid_tone_index = np.arange(this_n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX

                tone_indices = np.arange(sum(tone_counts[:i]), sum(tone_counts[:i+1]), dtype=int)

                if raw_global_data.lo_sweep is None:
                    raise RuntimeError('No LO sweep provided. Canceliing processing of file.')

               # Initialize timestamp
               # TODO: find number of missed packets, resize accordingly, and
               # interpolate missing data
                if i == 0:  # Only should make this once, since it's never changed
                    raw_timestamp = raw_time_ordered_data.timestamp[:n_samples]
                    print('finding missed packets...')
                    missed_packets, this_corrected_packet_index = find_missed_packets(
                        raw_timestamp,
                        n_samples
                    )
                    n_missed = np.sum(missed_packets[:, 1])
                    total_samples = n_samples + n_missed
                    time_ordered_data_group._v_attrs.n_samples = total_samples
                    # Can now initialize time-ordered data arrays
                    # chunksize = int(1e5)
                    timestamp = pfile.create_array(time_ordered_data_group, 'timestamp', shape=(total_samples,), atom=tables.Float64Atom())
                    chunkshape = (1, 1, int(5e5))
                    clevel = 4
                    cname = 'lz4'
                    tables_filters = tables.Filters(
                        complevel=clevel,
                        complib="blosc2:%s" % cname,
                        shuffle=True,
                    )
                    # data_IQ = pfile.create_array(time_ordered_data_group, 'data_IQ', shape=(2, n_tones, total_samples), atom=tables.Float64Atom())
                    data_IQ = pfile.create_earray(time_ordered_data_group, 'data_IQ', shape=(2, 0, total_samples), atom=tables.Float64Atom(), filters=tables_filters)
                    azel_shape = (0, total_samples) if azel_exists else (1, 0)
                    detector_az = pfile.create_earray(time_ordered_data_group, 'detector_az', shape=azel_shape, expectedrows=n_tones, atom=tables.Float64Atom())
                    detector_za = pfile.create_earray(time_ordered_data_group, 'detector_za', shape=azel_shape, expectedrows=n_tones, atom=tables.Float64Atom())
                    normalized_packet_indices = this_corrected_packet_index - this_corrected_packet_index[0]
                    corrected_packet_index.append(this_corrected_packet_index)
                    # n_chunks = int(np.ceil(total_samples / chunksize))
                    # print('copying data')
                    # data_IQ[0, :, normalized_packet_indices] = raw_time_ordered_data.adc_i[valid_tone_index, :]
                    # data_IQ[1, :, normalized_packet_indices] = raw_time_ordered_data.adc_q[valid_tone_index, :]
                    # for i, tone in enumerate(valid_tone_index):
                    #     print(i)
                    #     data_IQ[0, i, normalized_packet_indices] = raw_time_ordered_data.adc_i[tone][:]
                    #     data_IQ[1, i, normalized_packet_indices] = raw_time_ordered_data.adc_q[tone][:]
                    #     # data_IQ[1, i, normalized_packet_indices[j * chunksize:(j + 1) * chunksize]] = raw_time_ordered_data.adc_q[tone, j * chunksize:(j + 1) * chunksize]
                    # print('done copying data')
                    print('interpolating timestamp...')
                    correct_timestamp = interpolate_timestamp(
                        raw_timestamp,
                        timestamp,
                        corrected_packet_index[:],
                    )
                    # interpolate_data(
                    #     raw_time_ordered_data.adc_i,
                    #     raw_time_ordered_data.adc_q,
                    #     correct_timestamp,
                    #     missed_packets,
                    #     corrected_packet_index,
                    #     valid_tone_index,
                    #     data_IQ,
                    # )

                this_data_IQ = np.zeros((2, 1024, total_samples))
                # Interpolate Data
                print('interpolating data...')
                this_interpolated_indices, interpolated_data = interpolate_missing_data(
                    raw_time_ordered_data.adc_i,
                    raw_time_ordered_data.adc_q,
                    timestamp,
                    missed_packets,
                    corrected_packet_index[:],
                    valid_tone_index
                )
                interpolated_indices.append(this_interpolated_indices)

                # Read IQ data
                print('copying data')
                this_data_IQ[0, :][:, normalized_packet_indices] = raw_time_ordered_data.adc_i[:]
                this_data_IQ[1, :][:, normalized_packet_indices] = raw_time_ordered_data.adc_q[:]
                this_data_IQ = this_data_IQ[:, valid_tone_index]
                this_data_IQ[:, :, this_interpolated_indices] = interpolated_data
                data_IQ.append(this_data_IQ)
                print('done copying data')
                # for j, tone in enumerate(tone_indices):
                #     data_IQ[:, tone, this_interpolated_indices] = interpolated_data[:, j, :]
                #     data_IQ[0, tone, normalized_packet_indices] = raw_time_ordered_data.adc_i[valid_tone_index[j], :]
                #     data_IQ[1, tone, normalized_packet_indices] = raw_time_ordered_data.adc_q[valid_tone_index[j], :]
                # for i, tone in enumerate(valid_tone_index):
                #     print(i)
                #     data_IQ[0, i, normalized_packet_indices] = raw_time_ordered_data.adc_i[tone, :]
                #     data_IQ[1, i, normalized_packet_indices] = raw_time_ordered_data.adc_q[tone, :]


                # Link to LO sweep
                pfile.create_external_link(lo_group, f'lo_sweep_{i}', f'{file}:/global_data/lo_sweep')
                lo_freq = raw_global_data.lo_freq[:]
                baseband_freqs.append(raw_global_data.baseband_freqs[:])
                lo_group._v_attrs.lo_freq = lo_freq
            
                # Copy calibration factors
                this_detector_pol = raw_global_data.detector_pol[:]
                if np.count_nonzero(this_detector_pol) == 0:
                    this_detector_pol = np.ones_like(this_detector_pol)
                detector_pol.append(this_detector_pol)

                this_detector_beam_ampl = raw_global_data.detector_beam_ampl[:]
                if np.count_nonzero(this_detector_beam_ampl) == 0:
                    this_detector_beam_ampl = np.ones_like(this_detector_beam_ampl)
                detector_beam_amplitude.append(this_detector_beam_ampl)

                this_dfoverf_per_mK = raw_global_data.dfoverf_per_mK[:] * -1
                if np.count_nonzero(this_dfoverf_per_mK) == 0:
                    this_dfoverf_per_mK = np.ones_like(this_dfoverf_per_mK)
                dfoverf_per_mK.append(this_dfoverf_per_mK)




                # # Read IQ data
                # data_IQ[0, tone_indices, corrected_packet_index] = raw_time_ordered_data.adc_i[valid_tone_index, :]
                # data_IQ[1, tone_indices, corrected_packet_index] = raw_time_ordered_data.adc_q[valid_tone_index, :]
                
                if azel_exists:
                    detector_dx_dy_elevation_angle = raw_global_data.detector_dx_dy_elevation_angle[0]
                    this_az_tel = np.interp(timestamp, timestamp_tel, az_tel)
                    this_za_tel = np.interp(timestamp, timestamp_tel, za_tel)
                    this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_za_tel)
                    this_detector_delta_x = raw_global_data.detector_delta_x[:]
                    this_detector_delta_y = raw_global_data.detector_delta_y[:]
                    if beam_map_mode:
                        this_detector_delta_x *= 0
                        this_detector_delta_y *= 0
                    #save the az/el information to the file
                    detector_az.append(
                        np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                        np.outer(this_detector_delta_y, np.sin(this_ang)) + \
                        np.outer(np.ones(n_tones), this_az_tel)
                    )
                    detector_za.append(
                        np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                        np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                        np.outer(np.ones(n_tones), this_za_tel)
                    )
                
                # Store chanmask from TOD
                chanmask.append(raw_global_data.chanmask[:])

        # # Populate the arrays, interpolating where necessary
        # interpolate_missing_data(
        #     data_IQ,
        #     timestamp,
        #     missed_packets,
        #     corrected_packet_index
        # )

        # Close telescope file as it's no longer needed
        if azel_exists:
            azel_file.close()

        return cls(pfile)

class NewProcessedData(BaseProcessedData):
    """Class contianing data from processed TOD files."""
   
    def carrier_amplitude_norm(self) -> npt.NDArray:
        Z = self.carrier_amp_I + 1j*self.carrier_amp_Q
        return np.mean(np.abs(Z), axis=0)

    @property
    def carrier_amplitudes(self) -> tables.Array:
        return self.get_node_value('carrier_amplitudes')

    @property
    def carrier_amp_I(self) -> tables.Array:
        return self.carrier_amplitudes[0]
    
    @property
    def carrier_amp_Q(self) -> tables.Array:
        return self.carrier_amplitudes[1]

    @property
    def df_per_mK(self) -> tables.Array:
        return self.get_node_value('df_per_mK')

    @property
    def IQ_to_gain_phase_angle(self) -> tables.Array:
        return self.get_node_value('IQ_to_gain_phase_angle')

    @property
    def IQ_to_freq_diss_angle(self) -> tables.Array:
        return self.get_node_value('IQ_to_freq_diss_angle')
    
    @property
    def adc_units_to_hz(self) -> tables.Array:
        return self.get_node_value('adc_units_to_hz')

    @property
    def data_freq_diss(self) -> tables.Array:
        return self.get_node_value('data_freq_diss')

    def get_data_freq(self) -> npt.NDArray:
        return self.data_freq_diss[0]
    
    def get_data_diss(self) -> npt.NDArray:
        return self.data_freq_diss[0]
    
    @property
    def data_mK(self) -> tables.Array:
        return self.get_node_value('data_mK')
    
    @property
    def data_gain_phase(self) -> tables.Array:
        return self.get_node_value('data_gain_phase')
    
    def get_data_gain(self) -> npt.NDArray:
        return self.data_gain_phase[0]
    
    def get_data_phase(self) -> npt.NDArray:
        return self.data_gain_phase[1]
  
    


class ProcessedDataL1(NewProcessedData):
    @classmethod
    def from_tod(
        cls,
        date: str,
        setnum: int,
        beam_map_mode: bool=False,
        do_electronics_noise_removal: bool=True,
        electronics_noise_lp_filt_freq: float=10,
        ds_factor: int=1,
        max_modes: int=30,
    ) -> ProcessedDataL1:
        
        date = date
        setnum = setnum
    

        folder = Path(f'{DATA_DIRECTORY}/{date}')
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
        ntod = len(todlist)
        if ntod == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

        # Get the n_tones and n_samples from all TOD files to determine array sizes
        sample_counts = []
        tone_counts = []
        for file in todlist:
            with tables.open_file(file, 'r') as f:
                time_ordered_data = f.root.time_ordered_data
                # NOTE: Temporary fix until n_sample is fixed in the raw files
                # n_samples = raw_dimension.n_sample[0]
                n_samples = time_ordered_data.adc_i.shape[-1]
                sample_counts.append(n_samples)
                raw_dimension = f.root.dimension
                tone_counts.append(raw_dimension.n_tones[0])
        n_samples = min(sample_counts)
        n_samples_ds = int(np.ceil(n_samples / ds_factor))
        n_tones = sum(tone_counts)


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
        pfile_path = Path(get_processed_level_file_template(date, setnum, level=1))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.open_file(pfile_path, 'w')
        pfile.root._v_attrs.date = date
        pfile.root._v_attrs.setnum = setnum
        pfile.root._v_attrs.receipt = ''



        global_data_group = pfile.create_group('/', 'global_data')
        if optcam_exists:
            # optical_image = optcam_file.root.optical_image
            pfile.create_array(global_data_group, 'optical_image', obj=optcam_file.root.optical_image[:])
            optcam_file.close()
        else:
            pfile.create_array(global_data_group, 'optical_image', obj=np.array([]))
            optical_image = None
        vis = pfile.create_array(global_data_group, 'vis', vis)
        df_per_mK = pfile.create_earray(global_data_group, 'df_per_mK', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        chanmask = pfile.create_earray(global_data_group, 'chanmask', shape=(0,), expectedrows=n_tones, atom=tables.Int8Atom(dflt=1))
        baseband_freqs = pfile.create_earray(global_data_group, 'baseband_freqs', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        # chanmask[:] = 1
        detector_pol = pfile.create_earray(global_data_group, 'detector_pol', shape=(0,), expectedrows=n_tones, atom=tables.Int8Atom())
        optical_visibility = pfile.create_array(global_data_group, 'optical_visibility', shape=(1,), atom=tables.Float64Atom())

        data_group = pfile.create_group('/', 'data')
        data_group._v_attrs.n_tones = n_tones
        data_group._v_attrs.n_samples = n_samples_ds
        timestamp =pfile.create_array(data_group, 'timestamp', shape=(n_samples_ds,), atom=tables.Float64Atom())
        IQ_to_freq_diss_angle = pfile.create_earray(data_group, 'IQ_to_freq_diss_angle', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        adc_units_to_hz = pfile.create_earray(data_group, 'adc_units_to_hz', shape=(0,), expectedrows=n_tones, atom=tables.Float64Atom())
        carrier_amplitudes = pfile.create_earray(data_group, 'carrier_amplitudes', shape=(2, 0), expectedrows=n_tones, atom=tables.Float64Atom())
        data_IQ = pfile.create_earray(data_group, 'data_IQ', shape=(2, 0, n_samples_ds), expectedrows=n_tones, atom=tables.Float64Atom())
        data_gain_phase = pfile.create_array(data_group, 'data_gain_phase', shape=(2, n_tones, n_samples_ds), atom=tables.Float64Atom())
        IQ_to_gain_phase_angle = pfile.create_array(data_group, 'IQ_to_gain_phase_angle', shape=(n_tones,), atom=tables.Float64Atom())
        data_freq_diss = pfile.create_array(data_group, 'data_freq_diss', shape=(2, n_tones, n_samples_ds), atom=tables.Float64Atom())
        data_mK = pfile.create_array(data_group, 'data_mK', shape=(n_tones, n_samples_ds), atom=tables.Float64Atom())
        azel_shape = (0, n_samples_ds) if azel_exists else (1, 0)
        detector_az = pfile.create_earray(data_group, 'detector_az', shape=azel_shape, expectedrows=n_tones, atom=tables.Float64Atom())
        detector_za = pfile.create_earray(data_group, 'detector_za', shape=azel_shape, expectedrows=n_tones, atom=tables.Float64Atom())

        lo_group = pfile.create_group('/', 'lo_sweep')

        # Iterate over the TOD Files, extracting IQ data and calibration info
        for i, file in enumerate(todlist):
                #compute the derivatives to obtain frequency direction
            with tables.open_file(file, 'r') as f:
                raw_global_data = f.root.global_data
                time_ordered_data = f.root.time_ordered_data
                this_n_tones = tone_counts[i]

                tone_indices = np.arange(sum(tone_counts[:i]), sum(tone_counts[:i+1]), dtype=int)

                if raw_global_data.lo_sweep is None:
                    raise RuntimeError('No LO sweep provided. Canceliing processing of file.')

                # Load LO sweep
                sweep_data = raw_global_data.lo_sweep
                pfile.create_external_link(lo_group, f'lo_sweep_{i}', f'{file}:/global_data/lo_sweep')
                lo_freq = raw_global_data.lo_freq[:]
                # lo_freq = 4e8
                baseband_freqs.append(raw_global_data.baseband_freqs[:])
                lo_group._v_attrs.lo_freq = lo_freq
                sweep = LoSweepData(raw_global_data.baseband_freqs, lo_freq, sweep_data, raw_global_data.chanmask[:])

                # Get frequency direction
                this_IQ_to_freq_diss_angle, this_adc_units_to_hz = sweep.freq_direction()
                IQ_to_freq_diss_angle.append(this_IQ_to_freq_diss_angle)
                adc_units_to_hz.append(this_adc_units_to_hz)
            
                #compute the calibration factor from dfoverf to mK
                this_detector_pol = raw_global_data.detector_pol[:]
                if np.count_nonzero(this_detector_pol) == 0:
                    this_detector_pol = np.ones_like(this_detector_pol)
                detector_pol.append(this_detector_pol)

                detector_beam_ampl = raw_global_data.detector_beam_ampl[:]
                if np.count_nonzero(detector_beam_ampl) == 0:
                    detector_beam_ampl = np.ones_like(detector_beam_ampl)

                dfoverf_per_mK = raw_global_data.dfoverf_per_mK[:] * -1
                if np.count_nonzero(dfoverf_per_mK) == 0:
                    dfoverf_per_mK = np.ones_like(dfoverf_per_mK)
                # plt.plot(dfoverf_per_mK, label='New')

                detector_f = sweep.tone_list
                # detector_f = f.baseband_freqs[:] + f.lo_freq[:]

                # NOTE: Temporary fix: create dummy frequencies if they don't exist
                if np.count_nonzero(detector_f) == 0:  
                    detector_f[:] = np.linspace(0, 250e6, detector_f.size)

                this_df_per_mK = compute_df_per_mK(
                    detector_pol[tone_indices],
                    detector_beam_ampl,
                    detector_f,
                    dfoverf_per_mK,
                ) 
                df_per_mK.append(this_df_per_mK)

                # Get the corrent tone indices in the TOD file
                if int(date[:4]) < 2025:
                    expr = tables.Expr('time_ordered_data.adc_i[:, 0] != 0')
                    expr.eval()
                    valid_tone_index = np.ndarray.flatten(np.argwhere(expr))
                    valid_tone_index = valid_tone_index[:this_n_tones]
                else:
                    valid_tone_index = np.arange(this_n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX

                # Append dummy data and then set in place to avoids loading in both 
                # I and Q into memory at the same time
                data_IQ.append(np.zeros((2, this_n_tones, n_samples_ds)))

                # Read IQ data
                if ds_factor > 1:
                    # decimate_in_chunks(time_ordered_data.adc_i[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[0, :])
                    # decimate_in_chunks(time_ordered_data.adc_q[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[1, :])
                    data_IQ[0, tone_indices] = signal.decimate(time_ordered_data.adc_i[valid_tone_index, :], ds_factor)
                    data_IQ[1, tone_indices] = signal.decimate(time_ordered_data.adc_q[valid_tone_index, :], ds_factor)
                else:
                    data_IQ[0, tone_indices] = time_ordered_data.adc_i[valid_tone_index, :]
                    data_IQ[1, tone_indices] = time_ordered_data.adc_q[valid_tone_index, :]
                carrier_amplitudes.append(np.nanmedian(data_IQ[:, tone_indices], axis=2))
                
                # Initialize timestamp
                if i == 0:  # Only should make this once, since it's never changed
                    time = time_ordered_data.timestamp[:n_samples]  # Ensure same length for all files
                    time_0 = time - time[0]
                    total_time = np.max(time_0)
                    timestamp[:] = np.linspace(
                        0, total_time, n_samples_ds
                    ) + time[0]

                # Get detector coordinates
                if azel_exists:
                    detector_dx_dy_elevation_angle = raw_global_data.detector_dx_dy_elevation_angle[0]
                    this_az_tel = np.interp(timestamp, timestamp_tel, az_tel)
                    this_za_tel = np.interp(timestamp, timestamp_tel, za_tel)
                    this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_za_tel)
                    this_detector_delta_x = raw_global_data.detector_delta_x[:]
                    this_detector_delta_y = raw_global_data.detector_delta_y[:]
                    if beam_map_mode:
                        this_detector_delta_x *= 0
                        this_detector_delta_y *= 0
                    #save the az/el information to the file
                    detector_az.append(
                        np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                        np.outer(this_detector_delta_y, np.sin(this_ang)) + \
                        np.outer(np.ones(n_tones), this_az_tel)
                    )
                    detector_za.append(
                        np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                        np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                        np.outer(np.ones(n_tones), this_za_tel)
                    )
                
                # Store chanmask from TOD
                chanmask.append(raw_global_data.chanmask[:])

        # Close telescope file as it's no longer needed
        if azel_exists:
            azel_file.close()

        # Rotate to Gain / Phase
        IQ_to_gain_phase_angle[:] = np.atan2(carrier_amplitudes[0], carrier_amplitudes[1])

        rotate_basis(
            data_IQ,
            data_gain_phase,
            IQ_to_gain_phase_angle,
        )
        
        # Remove electronics noise
        fs = 1 / np.median(np.diff(timestamp[:]))
        if do_electronics_noise_removal:
            remove_electronics_noise_tables(data_gain_phase, fs, lp_filt_freq=electronics_noise_lp_filt_freq, max_modes=max_modes)

        # Create calibrated data
        generate_calibrated_data(data_group, global_data_group)

        # Update chanmask to reflect no polarization detectors
        no_pol = np.ndarray.flatten(np.argwhere(detector_pol[:] < 1))
        # TODO: This is a temporary fix, should be removed when the polarization
        # is properly set up on the lab computer.
        if np.size(no_pol > 0):
            chanmask[no_pol] = -1
        return cls(pfile)
    
    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r') -> ProcessedDataL0:
        return super(ProcessedDataL1, cls).from_file(date, setnum, mode=mode, level=1)

    def link_to_l0(self, target: ProcessedDataL0):
        global_data_group = self._file.create_group('/', 'global_data')
        data_group = self._file.create_group('/', 'data')
        lo_group = self._file.create_group('/', 'lo_sweep')

        # Copy attributes
        self._file.root._v_attrs.date = target.date
        self._file.root._v_attrs.setnum = target.setnum
        self._file.root._v_attrs.receipt = target.receipt
        data_group._v_attrs.n_tones = target.n_tones
        # data_group._v_attrs.n_samples = target.n_samples

        # Copy LO sweep external links
        for node in target.lo_sweep_group._f_walknodes('ExternalLink'):
            self._file.create_external_link(lo_group, node._v_name, node.target)
        lo_group._v_attrs.lo_freq = target.lo_freq
        self._file.create_external_link(global_data_group, 'baseband_freqs', f'{target.filename}:/{target.baseband_freqs._v_pathname}')
        
        # Copy global data
        self.create_external_link(global_data_group, 'dfoverf_per_mK', f'{target.filename}:/{target.dfoverf_per_mK._v_pathname}')
        self.create_external_link(global_data_group, 'chanmask', f'{target.filename}:/{target.chanmask._v_pathname}')
        self.create_external_link(global_data_group, 'detector_pol', f'{target.filename}:/{target.detector_pol._v_pathname}')
        self.create_external_link(global_data_group, 'detector_beam_ampl', f'{target.filename}:/{target.detector_beam_ampl._v_pathname}')
        self.create_external_link(global_data_group, 'optical_visibility', f'{target.filename}:/{target.optical_visibility._v_pathname}')
        self.create_external_link(global_data_group, 'optical_image', f'{target.filename}:/{target.optical_image._v_pathname}')
        
    
    @classmethod
    def from_level0(
        cls,
        l0: ProcessedDataL0,
        do_electronics_noise_removal: bool=True,
        electronics_noise_lp_filt_freq: float=10,
        ds_factor: int=1,
        max_modes: int=30,
    ) -> ProcessedDataL1:
        pfile_path = Path(get_processed_level_file_template(l0.date, l0.setnum, level=1))
        if not pfile_path.exists():
            pfile_path.touch(PERMISSIONS_ALL_FULL)
        pfile = tables.File(pfile_path, mode='w')

        total_samples = l0.n_samples
        n_samples_ds = int(np.ceil(total_samples / ds_factor))
        n_tones = l0.n_tones

        new_data = cls(pfile, level=1)
        l0.close()
        l0.open('r')
        new_data.link_to_l0(l0)

        new_data.n_samples = n_samples_ds


        data_gain_phase = new_data.create_array(
            new_data.data_group,
            'data_gain_phase',
            shape=(2, n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        data_freq_diss = new_data.create_array(
            new_data.data_group,
            'data_freq_diss',
            shape=(2, n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        data_mK = new_data.create_array(
            new_data.data_group,
            'data_mK',
            shape=(n_tones, n_samples_ds),
            atom=tables.Float64Atom(),
        )
        azel_shape = (1, 0) if l0.detector_az.shape[-1] == 0 else (n_tones, n_samples_ds) 


        carrier_amplitudes = new_data.create_array(
            new_data.data_group,
            'carrier_amplitudes',
            shape=(2, n_tones),
            atom=tables.Float64Atom(),
        )
        adc_units_to_hz = new_data.create_array(
            new_data.data_group,
            'adc_units_to_hz',
            shape=(n_tones,),
            atom=tables.Float64Atom(),
        )
        IQ_to_gain_phase_angle = new_data.create_array(
            new_data.data_group,
            'IQ_to_gain_phase_angle',
            shape=(n_tones,),
            atom=tables.Float64Atom(),
        )
        IQ_to_freq_diss_angle = new_data.create_array(
            new_data.data_group,
            'IQ_to_freq_diss_angle',
            shape=(n_tones,),
            atom=tables.Float64Atom(),
        )
        df_per_mK = new_data.create_array(
            new_data.global_data_group,
            'df_per_mK',
            shape=(n_tones,),
            atom=tables.Float64Atom(),
        )

        # Load LO sweep
        lo_sweep_data = new_data.get_lo_sweep_data()
        sweep = LoSweepData(
            new_data.baseband_freqs[:],
            new_data.lo_freq,
            lo_sweep_data,
            new_data.chanmask[:],
        )
        # Get frequency direction
        this_IQ_to_freq_diss_angle, this_adc_units_to_hz = sweep.freq_direction()
        IQ_to_freq_diss_angle[:] = this_IQ_to_freq_diss_angle
        adc_units_to_hz[:] = this_adc_units_to_hz

        detector_f = sweep.tone_list
        df_per_mK[:] = compute_df_per_mK(
            new_data.detector_pol[:],
            new_data.detector_beam_ampl,
            detector_f,
            new_data.dfoverf_per_mK,
        ) 

        # Downsample IQ data
        if ds_factor > 1:
            data_IQ = new_data.create_array(
                new_data.data_group,
                'data_IQ',
                shape=(2, n_tones, n_samples_ds),
                atom=tables.Float64Atom(),
            )
            timestamp = new_data.create_array(
                new_data.data_group,
                'timestamp',
                shape=(n_samples_ds,),
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
            interpolated_indices = new_data.create_earray(
                new_data.data_group,
                'interpolated_indices',
                shape=(0,),
                expectedrows=len(l0.interpolated_indices),
                atom=tables.Float64Atom(),
            )
            # decimate_in_chunks(time_ordered_data.adc_i[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[0, :])
            # decimate_in_chunks(time_ordered_data.adc_q[valid_tone_index, :], ds_factor, out=detector_data.data_IQ[1, :])
            data_IQ[:] = signal.decimate(l0.data_IQ[:], ds_factor)
            timestamp[:] = l0.timestamp[::ds_factor]
            if azel_shape[1] == 0:
                detector_az[:] = l0.detector_az[:]
                detector_za[:] = l0.detector_za[:]
            else:
                detector_az[:] = l0.detector_az[:, ::ds_factor]
                detector_za[:] = l0.detector_za[:, ::ds_factor]
            interpolated_indices.append(l0.interpolated_indices[l0.interpolated_indices[:] % ds_factor == 0] // ds_factor)
        else:
            data_IQ = new_data.create_external_link(new_data.data_group, 'data_IQ', f'{l0.filename}:{l0.data_IQ._v_pathname}')
            timestamp = new_data.create_external_link(new_data.data_group, 'timestamp', f'{l0.filename}:{l0.timestamp._v_pathname}')
            detector_az = new_data.create_external_link(new_data.data_group, 'detector_az', f'{l0.filename}:{l0.detector_az._v_pathname}')
            detector_za = new_data.create_external_link(new_data.data_group, 'detector_za', f'{l0.filename}:{l0.detector_za._v_pathname}')
            interpolated_indices = new_data.create_external_link(new_data.data_group, 'interpolated_indices', f'{l0.filename}:{l0.interpolated_indices._v_pathname}')
        carrier_amplitudes[:] = np.nanmedian(new_data.data_IQ[:])


        # Rotate to Gain / Phase
        IQ_to_gain_phase_angle[:] = np.atan2(carrier_amplitudes[0], carrier_amplitudes[1])  # N_chan
        rotate_basis(
            new_data.data_IQ[:],
            data_gain_phase,
            IQ_to_gain_phase_angle,
        )
        fs = 1 / np.median(np.diff(new_data.timestamp[:]))

        # Remove electronics noise if specified
        if do_electronics_noise_removal:
            remove_electronics_noise_tables(data_gain_phase, fs, lp_filt_freq=electronics_noise_lp_filt_freq, max_modes=max_modes)

        # Create calibrated data
        new_generate_calibrated_data(new_data)
        
        return new_data


class ExternalLinkProcessedData(NewProcessedData):
    """Class for storing processed data with external links to another file."""
    def __init__(self, file: tables.File):
        super().__init__(file)

    def open(self, mode: str='r'):
        super().open(mode=mode)
        self._load_dynamic_fields()

    def _load_dynamic_fields(self):
        for field_name in DYNAMIC_PROCESSED_DATA_FIELDS:
            setattr(self, field_name, self.get_node(field_name))

    # @property
    # def baseband_freqs(self) -> tables.Array:
    #     return self.global_data_group.baseband_freqs(mode='r') 

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
    

    def link_to_file(self, target: NewProcessedData):
        global_data_group = self._file.create_group('/', 'global_data')
        data_group = self._file.create_group('/', 'data')
        lo_group = self._file.create_group('/', 'lo_sweep')

        # Copy attributes
        self._file.root._v_attrs.date = target.date
        self._file.root._v_attrs.setnum = target.setnum
        self._file.root._v_attrs.receipt = target.receipt
        data_group._v_attrs.n_tones = target.n_tones
        data_group._v_attrs.n_samples = target.n_samples

        # Copy LO sweep external links
        for node in target.lo_sweep_group._f_walknodes('ExternalLink'):
            self._file.create_external_link(lo_group, node._v_name, node.target)
        lo_group._v_attrs.lo_freq = target.lo_freq
        if isinstance(target, ProcessedDataLN):
            self._file.create_external_link(global_data_group, 'baseband_freqs', target.global_data_group.baseband_freqs.target)
        else:
            self._file.create_external_link(global_data_group, 'baseband_freqs', f'{target.filename}:/{target.baseband_freqs._v_pathname}')

        # Create external links for all datasets
        for node_name in DYNAMIC_PROCESSED_DATA_FIELDS + STATIC_PROCESSED_DATA_FIELDS:
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
    def from_previous_level(cls, previous: NewProcessedData) -> ProcessedDataLN:
        """Create a level N processed file with external links to level N-1."""
        level = previous.level + 1
        pfile_path = Path(get_processed_level_file_template(previous.date, previous.setnum, level=level))
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
        fname = get_processed_level_file_template(date, setnum, level=level)
        pd = cls(tables.File(fname, mode=mode), level=level)
        pd._load_dynamic_fields()
        return pd


class NewMapData(ProcessedDataLN):
    def __init__(self, file, level=3):
        super().__init__(file, level)

    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r'):
        # TODO: Appending "new" to compare with old data
        file_path = Path(get_map_file_template(date, setnum))
        file_path = file_path.with_stem(file_path.stem + '_new')
        md = cls(tables.File(file_path, mode=mode), level=3)
        md._load_dynamic_fields()
        return md

    @classmethod
    def from_processed_data(cls, pdata: NewProcessedData) -> NewMapData:
        return cls.from_previous_level(pdata)
    
    @classmethod
    def from_previous_level(cls, previous: NewProcessedData) -> NewMapData:
        """Create a map file with external links to level N-1."""
        file_path = Path(get_map_file_template(previous.date, previous.setnum))
        file_path = file_path.with_stem(file_path.stem + '_new')
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
        self.create_array('/map', 'netd', shape=(self.n_tones,), atom=tables.Float64Atom())
        initial_good_samples = np.arange(self.n_samples)
        good_samples = np.setdiff1d(initial_good_samples, self.interpolated_indices)
        self.create_earray('/map', 'good_samples', expectedrows=self.n_samples, obj=good_samples)

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
):
    xlim = min(map_x),max(map_x)
    ylim = max(map_y),min(map_y)

    if max_abs is None:
        max_abs = np.nanmax(np.abs(map))

    plt.figure()
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


class MapData(ProcessedData):
    """Class for storing values for generating maps."""

    def __init__(self, mfile: tables.File, pfile: tables.File):
        super().__init__(pfile)
        self._mfile = mfile
    
    def setup_mfile(self, n_pix_x: int, n_pix_y: int, beammap_mode: bool=False):
        self.date = super().date
        self.setnum = super().setnum

        # Create empty arrays
        n_maps = N_POLARIZATION if not beammap_mode else self.n_tones
        self._mfile.create_array(self._mfile.root, 'map_az', shape=(n_pix_x,), atom=tables.Float64Atom())
        self._mfile.create_array(self._mfile.root, 'map_za', shape=(n_pix_y,), atom=tables.Float64Atom())
        self._mfile.create_array(self._mfile.root, 'sum_map', shape=(n_maps, n_pix_x, n_pix_y), atom=tables.Float64Atom())
        self._mfile.create_array(self._mfile.root, 'hits_map', shape=(n_maps, n_pix_x, n_pix_y), atom=tables.Float64Atom())
        self._mfile.create_array(self._mfile.root, 'netd', shape=(self.n_tones,), atom=tables.Float64Atom())
        good_samples = self._mfile.create_earray(self._mfile.root, 'good_samples', shape=(0,), expectedrows=self.n_samples, atom=tables.UInt32Atom())
        good_samples.append(np.arange(self.n_samples))


    @classmethod
    def from_processed_data(cls, pdata: ProcessedData | tables.File, mode='w') -> MapData:
        if isinstance(pdata, tables.File):
            pfile = pdata
            fname = Path(ProcessedData(pfile).map_file_template)
        else:
            pfile = pdata._l1file
            fname = Path(pdata.map_file_template )
        mfile = tables.File(fname, mode)
        if mode == 'w' and not fname.exists():
            fname.touch(PERMISSIONS_ALL_FULL)

        map_data = MapData(mfile, pfile)
        chanmask = pfile.root.detector_0.global_data.chanmask
        # chanmask_node = map_data._mfile.create_array('/', 'chanmask', shape=chanmask.shape, atom=tables.Int8Atom(dflt=1))
        if not test_node(mfile, 'chanmask'):
            chanmask.copy(map_data._mfile.root, 'chanmask')
        return map_data
    
    @classmethod
    def from_file(cls, date: str, setnum: int, mode: str='r') -> MapData:
        pd = super().from_file(date, setnum, mode=mode)
        return cls.from_processed_data(pd, mode=mode)

    def close(self):
        super().close()
        self._mfile.close()
    
    @property
    def chanmask(self) -> tables.Array:
        return self._mfile.root.chanmask

    @property
    def date(self) -> str:
        return self._mfile.root._v_attrs.date

    @date.setter
    def date(self, date: str):
        self._mfile.root._v_attrs.date = date

    @property
    def setnum(self) -> int:
        return self._mfile.root._v_attrs.setnum

    @setnum.setter
    def setnum(self, setnum: int):
        self._mfile.root._v_attrs.setnum = setnum
    
    @property
    def netd(self) -> tables.Array:
        return self._mfile.root.netd

    @property
    def good_samples(self) -> tables.EArray:
        return self._mfile.root.good_samples

    @property
    def sum_map(self) -> tables.Array:
        return self._mfile.root.sum_map

    @property
    def hits_map(self) -> tables.Array:
        return self._mfile.root.hits_map
    
    @property
    def map(self) -> npt.NDArray:
        div = tables.Expr('sum_map / hits_map', {'sum_map': self.sum_map, 'hits_map': self.hits_map})
        d = div.eval()
        return d

    @property
    def map_az(self) -> tables.Array:
        return self._mfile.root.map_az

    @property
    def map_za(self) -> tables.Array:
        return self._mfile.root.map_za

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
        ', Optical Visibility = ' + str(self.vis[()]) + ' meters \n' + 'NETD V-Pol (30Hz) = ' + "{:.1f}".format(med_netd_1) + \
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

#
# Parameter Files
#

def initialize_params_file(
    tile_name: str,
    baseband_freqs: npt.NDArray,
    lo_freq: float,
    params_dir: Path=DEFAULT_PARAMS_DIRECTORY,
):
    params_tile_file = Path(get_params_file_template(tile_name, params_dir=params_dir))
    if not params_tile_file.exists():
        params_tile_file.touch(PERMISSIONS_ALL_FULL)
    n_tones = np.size(baseband_freqs)
    with tables.open_file(params_tile_file, 'w') as params_fh:
        params_fh.root._v_attrs.n_tones = n_tones
        params_fh.root._v_attrs.tile_name = tile_name
        params_fh.root._v_attrs.tile_number = 0
        params_fh.root._v_attrs.chan_number = 0
        params_fh.root._v_attrs.ifslice_number = 0
        chanmask = params_fh.create_array(
            '/',
            'chanmask',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        chanmask[:] = 1
        params_fh.create_array(
            '/',
            'baseband_freqs',
            obj=baseband_freqs,
        )
        params_fh.create_array(
            '/',
            'tone_powers',
            obj=np.ones(n_tones, dtype=np.float32),
        )
        params_fh.create_array(
            '/',
            'lo_freq',
            obj=lo_freq,
        )
        params_fh.create_array(
            '/',
            'detector_delta_x',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        params_fh.create_array(
            '/',
            'detector_delta_y',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        det_beam_ampl = params_fh.create_array(
            '/',
            'detector_beam_ampl',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        det_beam_ampl[:] = 1
        det_pol = params_fh.create_array(
            '/',
            'detector_pol',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        det_pol[:] = 1
        dfoveref_per_mK = params_fh.create_array(
            '/',
            'dfoverf_per_mK',
            atom=tables.Float64Atom(),
            shape=(n_tones,),
        )
        dfoveref_per_mK[:] = 1
    _logger.info(f'Initialized params file {params_tile_file}')


def update_params_file(
    tile_name: str,
    params_dir: Path=DEFAULT_PARAMS_DIRECTORY,
    baseband_freqs: npt.NDArray=None,
    lo_freq: float=None,
    detector_delta_x: npt.NDArray=None,
    detector_delta_y: npt.NDArray=None,
    detector_beam_ampl: npt.NDArray=None,
    detector_pol: npt.NDArray=None,
    dfoverf_per_mK: npt.NDArray=None,
    chanmask: npt.NDArray=None,
    tone_powers: npt.NDArray=None,
):
    params_tile_file = Path(get_params_file_template(tile_name, params_dir=params_dir))
    if not params_tile_file.exists():
        raise FileExistsError(f'Params file {params_tile_file} does not exist')
    
    signature = inspect.signature(update_params_file)
    keyword_args = {
        param.name: param.default
        for param in signature.parameters.values()
        if param.default is not inspect.Parameter.empty
    }

    with tables.open_file(params_tile_file, 'a') as fh:
        for k in keyword_args:  # Check all of the keyword arguments
            if k == 'params_dir':
                continue  # We only care about the parameters
            v = locals()[k]
            if v is None:
                continue  # The value is not being updated, so skip it
            # Check the array is the correct size if needed
            if k in PARAM_FILE_N_TONE_ATTRIBUTES:
                if np.size(v) != fh.root._v_attrs.n_tones:
                    raise ValueError(
                        f'{k} size {np.size(v)} does not match n_tones {fh.root._v_attrs.n_tones}'
                    )
            fh.get_node('/', k)[:] = v


def compute_timestamp(raw_data: tables.File, window_size: int=5, sigma: float=3.0) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
    pkt_idx = raw_data.root.time_ordered_data.pkt_idx
    timestamp = raw_data.root.time_ordered_data.timestamp
    n_samples = raw_data.root.time_ordered_data.adc_i.shape[-1]
    dtime = np.diff(timestamp)
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
    corrected_packet_idx = np.zeros(n_samples, dtype=int)
    missed_packets = np.empty((0, 2), dtype=int)
    i = 1
    while i < n_samples:
        dtime_idx = i - 1
        if dtime_idx in bad_samples:
            window_min_idx = max(0, i - window_size)
            window_max_idx = min(n_samples, i + window_size)
            window = timestamp[window_min_idx:window_max_idx + 1]
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
                large_window = timestamp[large_window_min_idx:large_window_max_idx + 1]
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
                    corrected_packet_idx[i] = corrected_packet_idx[i - 1] + large_window_packets_missed + 1

                    # Don't need to re-evaluate the next few samples, since their offset
                    # was already accounted for.
                    for j in range(i + 1, i + large_window_packets_missed + 1):
                        corrected_packet_idx[j] = corrected_packet_idx[j - 1] + 1
                    i = j
                    continue
                else:
                    corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
            else:
                corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1

            # plt.scatter(range(window_min_idx, window_max_idx + 1), timestamp_window)
            # plt.show()
            # pdb.set_trace()
        else:
            corrected_packet_idx[i] = corrected_packet_idx[i - 1] + 1
        i += 1

    fit = linregress(corrected_packet_idx, timestamp[:])
    new_timestamp = fit.slope * corrected_packet_idx + fit.intercept 
    print(f'{np.sum(missed_packets[:, 1])} missed packets')

    # Plotting Code for Debugging
    # x = np.arange(n_samples)
    # y = fit.slope * x + fit.intercept
    # plt.scatter(corrected_packet_idx, timestamp[:])
    # plt.scatter(corrected_packet_idx, new_timestamp)
    # plt.plot(x, y, color='red', linestyle='--')
    # plt.show()
    # pdb.set_trace()
    return new_timestamp, missed_packets, corrected_packet_idx


def interpolate_data(
        data_I: tables.Array,
        data_Q: tables.Array,
        timestamp: npt.NDArray,
        missed_packets: npt.NDArray,
        packet_indices: npt.NDArray,
        valid_tone_index: npt.NDArray,
        interpolated_data: tables.Array,
) -> tuple[npt.NDArray. npt.NDArray, npt.NDArray]:
    total_missed_packets = np.sum(missed_packets[:, 1])
    n_tones = len(valid_tone_index)
    total_samples = data_I.shape[-1] + total_missed_packets

    # Initialize Arrays
    # interpolated_data = np.zeros((2, n_tones, total_samples))
    new_timestamp = np.zeros(total_samples)
    interpolated_indices = []
    normalized_packet_indices = packet_indices - packet_indices[0]
    # print('copying data over')
    # interpolated_data[0, :][:, normalized_packet_indices] = data_I[valid_tone_index, :]
    # interpolated_data[1, :][:, normalized_packet_indices] = data_Q[valid_tone_index, :]
    # print('done')
    new_timestamp[normalized_packet_indices] = timestamp[:]

    # Iterate over the spot where data was missed
    # window_size = 50
    for i, this_missed_packets in missed_packets:
        print(f'interpolating data for i={i} with {this_missed_packets} missed packets')
        window_size = 5 * this_missed_packets
        # Fit a spline using data from nearest (window_size * 2) packets
        min_t = max(0, i - window_size)
        max_t = min(data_I.shape[-1], i + window_size)
        window = range(min_t, max_t + 1)
        times = timestamp[window]
        print('accessing iq data...')
        i_data = data_I[:, window][valid_tone_index, :]
        q_data = data_Q[:, window][valid_tone_index, :]
        print('done')
        iq_data = np.stack((i_data, q_data))
        fit_I = np.polyfit(times - times[0], i_data[0], 4)
        fit_Q = np.polyfit(times - times[0], q_data[0], 4)
        # spline = make_interp_spline(times, iq_data, axis=-1)

        # Use the spline to interpolate data between sample i-1 and i
        dtime = (timestamp[i] - timestamp[i - 1]) / this_missed_packets
        missing_packet_start_t = timestamp[i - 1] + dtime
        current_t = timestamp[i]
        missed_packet_t = np.linspace(missing_packet_start_t, current_t, this_missed_packets, endpoint=False) 
        new_data_I = np.polyval(fit_I, missed_packet_t - times[0])
        new_data_Q = np.polyval(fit_Q, missed_packet_t - times[0])
        new_data = np.stack((new_data_I, new_data_Q))
        # new_data = spline(missed_packet_t)
        this_interpolated_indices = list(range(normalized_packet_indices[i - 1] + 1, normalized_packet_indices[i]))
        interpolated_indices.extend(this_interpolated_indices)
        interpolated_data[:, 0, this_interpolated_indices] = new_data

        
        # Plotting Code for Debugging
        ax = plt.axes(projection='3d')
        x = np.linspace(times[0], times[-1], 150)
        # ax.plot3D(x, *spline(x)[:, 0], label='Spline Fit')
        ax.plot3D(x, np.polyval(fit_I, x - times[0]), np.polyval(fit_Q, x - times[0]), label='Polynomial Fit')
        ax.scatter3D(times, *iq_data[:, 0], label='Actual Values')
        ax.scatter3D(missed_packet_t, *new_data, label='Interpolated Points')
        ax.set_xlabel('Timestamp (s)')
        ax.set_ylabel('ADC I')
        ax.set_zlabel('ADC Q')
        ax.legend()
        plt.show()
        pdb.set_trace()
    return interpolated_data, new_timestamp, interpolated_indices



if __name__ == '__main__':
    # Telescope Testing
    date = '20251006'
    setnum = 1009
    # Lab Testing
    # date = '20250916'
    # setnum = 1017

    pd = ProcessedDataL0.from_tod(date, setnum, beam_map_mode=True)
    # pd = ProcessedDataL0.from_file(date, setnum)
    pd1 = ProcessedDataL1.from_level0(pd, ds_factor=12, do_electronics_noise_removal=False)
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
