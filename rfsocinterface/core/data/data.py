"""Core functionality relating to data loading and processing."""

from __future__ import annotations
from pathlib import Path
import glob
import pdb
import time

import tables
import numpy as np
import numpy.typing as npt
from scipy import signal
import matplotlib.pyplot as plt

from rfsocinterface.core.utils import gaussian_filter, GAUSSIAN_SIGMA, BAD_RFSOC_TONE_START_INDEX, decimate_in_chunks
from rfsocinterface.core.losweep import LoSweepData

DATA_DIRECTORY = '/data'
DEFAULT_PARAMS_DIRECTORY = DATA_DIRECTORY + '/params/'

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
# File Templates
#

def get_tod_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_*_TOD_set{setnum}.h5'


def get_azel_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_AZEL_set{setnum}.h5'


def get_optcam_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_optcam_set{setnum}.h5'


def get_processed_file_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY, level: int=1) -> str:
    return f'{data_dir}/{date}/{date}_processed_data_level{level}_set{setnum}.h5'


def get_cleaned_file_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_cleaned_data_set{setnum}.h5'


def get_file_stub(date: str, setnum: int) -> str:
    return f'{date}_set{setnum}'


def get_map_file_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_mapped_data_set{setnum}.h5'


def get_beammap_file_template(date: str, setnum: int, data_dir: str=DATA_DIRECTORY) -> str:
    return f'{data_dir}/{date}/{date}_beammap_set{setnum}.h5'


def get_params_file_template(tile_name: str, params_dir: str=DEFAULT_PARAMS_DIRECTORY) -> str:
    return f'{params_dir}/params_tile_{tile_name}.h5'

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
    out_data[0, :] = np.cos(rotation_angle)[:, np.newaxis] * in_data[0, :] + np.sin(rotation_angle)[:, np.newaxis] * in_data[1, :]
    out_data[1, :] = -np.sin(rotation_angle)[:, np.newaxis] * in_data[0, :] + np.cos(rotation_angle)[:, np.newaxis] * in_data[1, :]


def generate_calibrated_data(data: tables.Group, global_data: tables.Group):
    rotate_basis(
        data.data_gain_phase,
        data.data_IQ,
        -data.IQ_to_gain_phase_angle[:],
    )
    data.data_IQ[:] = data.data_IQ - np.mean(data.data_IQ, axis=2, keepdims=True)
    # data.data_IQ[0, :] = data.data_IQ[0, :] - np.mean(data.data_IQ[0, :], axis=1, keepdims=True)
    # data.data_IQ[1, :] = data.data_IQ[1, :] - np.mean(data.data_IQ[1, :], axis=1, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f

    rotate_basis(data.data_IQ / data.adc_units_to_hz[:][:, np.newaxis], data.data_freq_diss, data.IQ_to_freq_diss_angle[:])

    # Finally, we need to get data_mK
    data.data_mK[:] = np.divide(data.data_freq_diss[0, :], global_data.df_per_mK[:][:, np.newaxis])
    # data.data_mK[:] = np.where(np.isinf(data.data_mK), np.nan, data.data_mK)

#
# Electronics Noise Removal
#

def compute_templates(data: npt.NDArray) -> npt.NDArray:
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

    # select only the middle few detectors
    # deproj = data_meansub[:, 8:1008, :]

    # create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(deproj, np.conj(np.transpose(deproj, axes=(0, 2, 1))))
    # calculate the eigenmodes of the correlation matrices
    _, v = np.linalg.eig(correlation_matrices)

    # create templates based on the 2 largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', v[:,:,0:2], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates


def remove_electronics_noise(data: npt.NDArray) -> npt.NDArray:
    """Remove correlated electronics noise templates from the data.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples). Data should
            be in the gain/phase basis.

    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    templates = compute_templates(data)  # N_chan x 2 x N_samples

    denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2
    numerator0 = np.einsum('ijk,ik->ij', data, templates[:, 0])  # N_chan x N_detector
    corr0 = numerator0 / denominator[:, 0:1]  # N_chan x N_detector
    deproj = data - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    numerator1 = np.einsum('ijk,ik->ij', deproj, templates[:, 1])  # N_chan x N_detector
    corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    clean_data = deproj - np.einsum('ij,ikl->ijl', corr1, templates[:, 1:])
    return clean_data


def remove_electronics_noise_tables(
    data_gain_phase: tables.Array,
):
    """Remove correlated electronics noise templates from data stored with PyTables.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples). Data should
            be in the gain/phase basis.

    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    for i_chan in range(data_gain_phase.shape[0]):
        clean_data = remove_electronics_noise(data_gain_phase[i_chan][np.newaxis])
        # templates = compute_templates(data_gain_phase[i_chan][np.newaxis]) # 1 x 2 x N_samples

        # denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 1 x 2
        # pdb.set_trace()
        # numerator0 = np.einsum('jk,k->j', data_gain_phase[i_chan], templates[0])  # N_detector
        # pdb.set_trace()
        # corr0 = numerator0 / denominator[:, 0:1]  # N_detector
        # deproj = data_gain_phase[i_chan] - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

        # numerator1 = np.einsum('ijk,ik->ij', deproj, templates[:, 1])  # N_chan x N_detector
        # pdb.set_trace()
        # corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
        data_gain_phase[i_chan, :] = clean_data.squeeze()

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
        ds_factor: int=1,
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
        

        pfile = tables.open_file(get_processed_file_template(date, setnum), 'w')
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
                n_samples = raw_dimension.n_sample[0]
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
                lo_freq = 4e8
                sweep = LoSweepData(raw_global_data.baseband_freqs, lo_freq, sweep_data, raw_global_data.chanmask[:])
                IQ_to_freq_diss_angle, adc_units_to_hz = sweep.freq_direction()
                detector_data.IQ_to_freq_diss_angle[:] = IQ_to_freq_diss_angle
                detector_data.adc_units_to_hz[:] = adc_units_to_hz
                # if np.size(dIQ_df) > 0:
                #     dIQ_df = np.concatenate((dIQ_df, this_dIQ_df), axis=0)
                # else:
                #     dIQ_df = np.copy(this_dIQ_df)
            
                #compute the calibration factor from dfoverf to mK
                detector_global_data.detector_pol[:] = raw_global_data.detector_pol[:]
                if np.count_nonzero(detector_global_data.detector_pol) == 0:
                    detector_global_data.detector_pol[:] = np.ones_like(detector_global_data.detector_pol)

                detector_beam_ampl = raw_global_data.detector_beam_ampl[:]
                if np.count_nonzero(detector_beam_ampl) == 0:
                    detector_beam_ampl = np.ones_like(detector_beam_ampl)

                dfoverf_per_mK = raw_global_data.dfoverf_per_mK[:]
                if np.count_nonzero(dfoverf_per_mK) == 0:
                    dfoverf_per_mK = np.ones_like(dfoverf_per_mK)

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
                time_ordered_data = f.root.time_ordered_data
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

                # TODO: Make this optional I guess
                if do_electronics_noise_removal:
                    # data_gain_phase = np.stack((detector_data.data_gain, detector_data.data_phase), axis=0)
                    # detector_data.data_gain[:], detector_data.data_phase[:] = remove_electronics_noise2(data_gain_phase)
                    remove_electronics_noise_tables(detector_data.data_gain_phase)
                

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
                time = time_ordered_data.timestamp
                time_0 = time - time[0]
                total_time = np.max(time_0)
                if i == 0:  # Only should make this once, since it's never changed
                    detector_data.timestamp[:] = np.linspace(
                        0, total_time, n_samples_ds
                    ) + time[0]

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
                no_pol = np.ndarray.flatten(np.argwhere(raw_global_data.detector_pol[:] < 1))
                # TODO: This is a temporary fix, should be removed when the polarization
                # is properly set up on the lab computer.
                if np.size(no_pol > 0):
                    chanmask[no_pol] = -1
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


class ProcessedDataL2(ProcessedData):
    """Class for storing level 2 processed data."""

    def __init__(self, l1file: tables.File, l2file: tables.File):
        super().__init__(l1file)
        self._l2file = l2file
    
    @classmethod
    def from_processed_data(cls, pl1: ProcessedData | tables.File, mode='w') -> ProcessedDataL2:
        if isinstance(pl1, tables.File):
            l1file = pl1
            l2file = tables.File(ProcessedData(pl1).processed_file_level2_template, mode)
        else:
            l1file = pl1._l1file
            l2file = tables.File(pl1.processed_file_level2_template, mode)

        # Set global attributes from L1 file
        pl2 = cls(l1file, l2file)
        pl2.date = pl1.date
        pl2.setnum = pl1.setnum
        return pl2
    
    def setup_l2file(self):
        """Setup the level 2 file with necessary attributes and arrays."""
        self.date = super().date
        self.setnum = super().setnum

        psd_group = self._l2file.create_group('/', 'psd')
        # self._l2file.create_array(psd_group, 'freq', shape=(self
        # self._l2file.create_array(psd_group, 'psd_gain_phase', shape=(self


    @property
    def chanmask(self) -> tables.Array:
        return self._l2file.root.chanmask

    @property
    def date(self) -> str:
        return self._l2file.root._v_attrs.date

    @date.setter
    def date(self, date: str):
        self._l2file.root._v_attrs.date = date

    @property
    def setnum(self) -> int:
        return self._l2file.root._v_attrs.setnum

    @setnum.setter
    def setnum(self, setnum: int):
        self._l2file.root._v_attrs.setnum = setnum



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
            mfile = tables.File(ProcessedData(pfile).map_file_template, mode)
        else:
            pfile = pdata._l1file
            mfile = tables.File(pdata.map_file_template, mode)

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
        if save:
            this_fig.savefig(self.folder / (self.file_stub + '_Source_Finder_Image.png'), bbox_inches='tight')
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


def update_params_file(
    tile_name: str,
    params_dir: Path=DEFAULT_PARAMS_DIRECTORY,
    baseband_freqs: npt.NDArray=None,
    lo_freq: float=None,
    detector_delta_dx: npt.NDArray=None,
    detector_delta_dy: npt.NDArray=None,
    detector_beam_ampl: npt.NDArray=None,
    detector_pol: npt.NDArray=None,
    dfoverf_per_mK: npt.NDArray=None,
    chanmask: npt.NDArray=None,
    tone_powers: npt.NDArray=None,
):
    params_tile_file = Path(get_params_file_template(tile_name, params_dir=params_dir))
    if not params_tile_file.exists():
        raise FileExistsError(f'Params file {params_tile_file} does not exist')

    with tables.open_file(params_tile_file, 'a') as fh:
        for k in update_params_file.__kwdefaults__:  # Check all of the keyword arguments
            if k == 'params_path':
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


if __name__ == '__main__':
    date = '20250611'
    setnum = 1003
    # date = '20250529'
    # setnum = 1011

    pd = ProcessedData.from_tod(date, setnum)
    pdb.set_trace()
    pd.close()
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
