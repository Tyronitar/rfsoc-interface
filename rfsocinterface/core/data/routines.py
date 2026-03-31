"""Data proccessing routines."""

from __future__ import annotations
import abc
import pdb
import logging
from typing import Literal
import warnings

import numpy as np
import numpy.typing as npt
from scipy import signal
import tables
import time
import datetime
import json
import h5py
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


from rfsocinterface.core.data.data import ConsolidatedData, ProcessedData, generate_calibrated_data, get_channel_group_name, get_step_group_name, rotate_basis, DEFAULT_MAP_DPIX, N_POLARIZATION, OPTCAM_PIX_SIZE_DEGREES, OPTCAM_OFFSET_AZ_PIX, OPTCAM_OFFSET_ZA_PIX
from rfsocinterface.core.data.data import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, GAUSSIAN_SIGMA, gaussian_filter, axis_index, get_git_hash, PERMISSIONS_ALL_FULL

__all__ = (
    'ROUTINE_REGISTRY',
    'register_routine',
    'DataRoutine',
    'CutoffFilter',
    'LowPassFilter',
    'HighPassFilter',
    'RemoveElectronicsNoise',
    # 'ComputeNoisePSD',
    'CleanTOD',
    'BinTODIntoMap',
    'PlotMap',
)

_logger = logging.getLogger(__name__)

class ProcessingStage:
    """Enum for the different stages of data processing."""
    PRE_PROCESSING = 'pre_processing'
    PROCESSING_L1 = 'processing_l1'
    PROCESSING_L2 = 'processing_l2'
    POST_PROCESSING = 'post_processing'


ROUTINE_REGISTRY = {}

def register_routine(cls: type[DataRoutine]):
    if not issubclass(cls, DataRoutine):
        _logger.warning(f'Failed to register class {cls.__name__} as a DataRoutine; it does not inherit from DataRoutine.')
        return
    ROUTINE_REGISTRY[cls.name] = cls
    _logger.debug(f'Registered data routine: {cls.__name__}')
    return cls


class DataRoutine:
    name = 'base'
    version = '0.0.0'
    record_checkpoint = False  # override per routine if desired

    requires = set()
    produces = set()

    def __init__(self, **params):
        self.params = params
    
    def validate_inputs(self, pdata: ProcessedData, inputs: list):
        missing = set(inputs) - set(pdata.list_dataset_names(full_names=True))
        if missing:
            raise RuntimeError(f'Missing required datsets: {missing}')

    # ---- main entry point ----
    def apply(self, pdata: ProcessedData):
        t0 = time.time()

        inputs = self.inputs(pdata)
        self.validate_inputs(pdata, inputs)
        shapes_before = self._get_shapes(pdata, inputs)

        # ---- run actual computation ----
        outputs = self.run(pdata, inputs=inputs)

        runtime = time.time() - t0
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()

        shapes_after = self._get_shapes(pdata, outputs)

        meta = self._get_metadata(
            timestamp,
            inputs,
            outputs,
            shapes_before,
            shapes_after,
            runtime,
        )

        self._log_step(pdata, meta)

        if self.record_checkpoint:
            self._checkpoint(pdata)

        return outputs

    # ---- to be implemented by subclasses ----
    def run(self, pdata: ProcessedData, inputs: list=None):
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a run method'
        )

    def inputs(self, pdata: ProcessedData):
        if self.requires:
            return list(self.requires)
        raise NotImplementedError

    # ---- helpers ----
    def _get_shapes(self, pdata, dataset_names):
        shapes = {}
        for name in dataset_names:
            if name in pdata.file:
                shapes[name] = pdata[name].shape
        return shapes

    def _log_step(self, pdata: ProcessedData, meta: str):
        hist = pdata.file.require_group("processing_history")

        step_idx = len(hist)
        step_name = get_step_group_name(step_idx, self.name)

        step_group = hist.create_group(step_name)

        for k, v in meta.items():
            if isinstance(v, (dict, list)):
                step_group.attrs[k] = json.dumps(v)
            else:
                step_group.attrs[k] = v

    def _checkpoint(self, pdata: ProcessedData):
        chk_group = pdata.file.require_group("checkpoints")
        name = get_step_group_name(len(chk_group), self.name)

        g = chk_group.create_group(name)

        # naive: copy all datasets (you can refine later)
        for key, item in pdata.file.items():
            if isinstance(item, type(pdata.file["/"])):  # dataset
                pdata.file.copy(item, g, name=key)
    
    def _get_metadata(
        self,
        timestamp: float,
        inputs: list[str],
        outputs: list[str],
        shapes_before: list[tuple],
        shapes_after: list[tuple],
        runtime: float,
    ) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "timestamp": timestamp,
            "params": self.params,
            "inputs": inputs,
            "outputs": outputs,
            "shape_before": shapes_before,
            "shape_after": shapes_after,
            "code_version": get_git_hash(),
            "runtime_sec": runtime,
        }

#
# Begin Data Routine Catlog
#

@register_routine
class CutoffFilter(DataRoutine):
    name = "CutoffFilter"
    version = "1.0"

    def __init__(self,
        filter_freq: float,
        btype: str,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        super().__init__(
            filter_freq=filter_freq,
            btype=btype,
            datasets=datasets,
        )
    
    def inputs(self, pdata: ProcessedData):
        return self.params['datasets']

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        filter_freq = self.params['filter_freq']
        btype = self.params['btype']
        for input_name in inputs:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', r'^Invalid value encountered in')
                filt_sos = signal.butter(
                    BUTTER_ORDER,
                    filter_freq,
                    btype=btype,
                    fs=pdata.fs,
                    output='sos',
                    analog=False,
                )
                dset = pdata[input_name]
                dset[:] = signal.sosfiltfilt(filt_sos, dset)
        return inputs


@register_routine
class LowPassFilter(CutoffFilter):

    name = 'LowPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        super().__init__(filter_freq, btype='lowpass', datasets=datasets)


@register_routine
class HighPassFilter(CutoffFilter):

    name = 'HighPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        super().__init__(filter_freq, btype='highpass', datasets=datasets)

#
# Electronics Noise Removal
#

def compute_templates(data: npt.NDArray, max_modes: int=30) -> npt.NDArray:
    """Compute templates for correlated noise removal.

    Args:
        data (npt.NDArray): Input data (2 x N_tone x N_samples).

    Returns:
        (npt.NDarray): Templates for noise removal (2 x M x N_samples).
            Computed using the first M eigenmodes of the correlation matrix.
    """
    # subtract the mean from each detector
    deproj = data - np.mean(data, axis=-1, keepdims=True)
    n_tones = data.shape[1]


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
    _logger.debug(f'Using {n_modes} eigen modes')

        # create templates based on the N_mode largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', sorted_v[:,:,0:n_modes], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates

def decode_tone_indices(pdata: ProcessedData, i_chan: int, input_indices: npt.NDArray | str):
    """Helper method for decoding the selected indices for noise removal."""
    if isinstance(input_indices, str):
        match input_indices.lower():
            case 'onres' | 'on_res' | 'on_resonance':
                return pdata.get_onres_ind(i_chan)
            case 'offres' | 'off_res' | 'off_resonance':
                return pdata.get_offres_ind(i_chan)
            case 'all':
                return np.arange(pdata.get_n_tones(i_chan), dtype=int)
            case _:
                _logger.warning(f'Unkown index selection string: {input_indices}; defaulting to all tones')
                return np.arange(pdata.get_n_tones(i_chan), dtype=int)
    else:
        return input_indices

@register_routine
class RemoveElectronicsNoise(DataRoutine):
    name = 'RemoveElectronicsNoise'

    def __init__(
        self,
        max_modes: int=30,
        lp_filt_freq: float=10,
        template_selection_indices: npt.NDArray | str='all',
        template_subtraction_indices: npt.NDArray | str='all',
    ):
        super().__init__(
            max_modes=max_modes,
            lp_filt_freq=lp_filt_freq,
            template_selection_indices=template_selection_indices,
            template_subtraction_indices=template_subtraction_indices,
        )
    
    def inputs(self, pdata: ProcessedData):
        # Requires data_IQ, data_gain_phase, data_freq_diss, and data_mK
        # but there's no case where those wouldn't exist, so I'm not sure this matters
        dsets = []
        for i_chan in range(pdata.n_chan):
            group_name = get_channel_group_name(i_chan)
            group_name = f'/channels/{get_channel_group_name(i_chan)}/'
            dsets.extend([
            group_name + 'time_ordered_data/data_IQ',
            group_name + 'time_ordered_data/data_gain_phase',
            group_name + 'time_ordered_data/data_freq_diss',
            group_name + 'time_ordered_data/data_mK',
            group_name + 'calibration_info',
        ])
        return dsets


    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        eigenmodes = []  # The actual number of modes we use for each channel
        lp_filt_freq = self.params['lp_filt_freq']
        template_selection_indices = self.params['template_selection_indices']
        template_subtraction_indices = self.params['template_subtraction_indices']
        max_modes = self.params['max_modes']
        fs = pdata.fs
        for i_chan in range(pdata.n_chan):
            selection_indices = decode_tone_indices(pdata, i_chan, template_selection_indices)

            data_gain_phase = pdata.get_from_channel(i_chan, 'time_ordered_data/data_gain_phase')
            clean_gain_phase = np.copy(data_gain_phase)
            clean_gain_phase -= np.mean(clean_gain_phase, axis=-1, keepdims=True)
            if lp_filt_freq < fs / 2:
                filt_sos = signal.butter(
                    BUTTER_ORDER,
                    lp_filt_freq,
                    btype='low',
                    fs=fs,output='sos',
                    analog=False,
                )
                clean_gain_phase = signal.sosfiltfilt(filt_sos, clean_gain_phase)
            templates = compute_templates(clean_gain_phase[:, selection_indices], max_modes=max_modes)  # 2 x N_modes x N_samples

            n_modes = templates.shape[1]
            eigenmodes.append(n_modes)
            denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 2 x N_modes

            subtraction_indices = decode_tone_indices(pdata, i_chan, template_subtraction_indices)

            for i_mode in range(n_modes):
                numerator = np.einsum('ijk,ik->ij', clean_gain_phase[:, subtraction_indices], templates[:, i_mode])  # 2 x N_tones
                corr = numerator / denominator[:, i_mode:i_mode+1]  # 2 x N_tones
                clean_gain_phase[:, subtraction_indices] = clean_gain_phase[:, subtraction_indices] - np.einsum('ij,ikl->ijl', corr, templates[:, i_mode:i_mode+1])  # 2 x N_tones x N_samples
            
            # Apply clean data
            data_gain_phase[:] = clean_gain_phase

            # Regenerate other data arrays
            data_IQ = pdata.get_from_channel(i_chan, 'time_ordered_data/data_IQ')
            calibration_info = pdata.get_from_channel(i_chan, 'calibration_info')
            rotate_basis(
                data_gain_phase,
                data_IQ,
                -calibration_info['IQ_to_gain_phase_angle'],
            )
            data_IQ[:] = data_IQ[:] - np.mean(data_IQ[:], axis=-1, keepdims=True)  # Mean center
            generate_calibrated_data(
                data_IQ,
                pdata.get_from_channel(i_chan, 'time_ordered_data/data_freq_diss'),
                pdata.get_from_channel(i_chan, 'time_ordered_data/data_mK'),
                calibration_info['IQ_to_freq_diss_angle'],
                calibration_info['adc_units_to_hz'],
                calibration_info['df_per_mK'],
            )

        self.params['eigenmodes'] = eigenmodes
        return inputs


@register_routine
class CleanTOD(DataRoutine):
    name = 'CleanTOD'
    version = 1.0

    def __init__(self, dataset: Literal['data_mK', 'data_freq']='data_mK'):
        super().__init__(dataset=dataset)
    
    def inputs(self, pdata: ProcessedData):
        dsets = []
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        for i_chan in range(pdata.n_chan):
            dsets.append(f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}')
        return dsets

    def run(self, pdata: ProcessedData, inputs: list[str]=None):

        for i_chan, dset in enumerate(inputs):
            data = pdata[dset]
            good_tones = pdata.get_onres_ind(i_chan)
            if data.ndim == 2:
                array_slice = (good_tones, slice(None))
                template = np.nansum(data[array_slice], axis=0)
            elif data.ndim == 3:
                array_slice = (0, good_tones, slice(None))
                template = np.nansum(data[array_slice], axis=1)
            else:
                msg = f'Unexpected data shape: {data.shape}; Expected 2D or 3D dataset.'
                _logger.exception(msg)
                raise ValueError(msg)
            template = template - np.mean(template)
            template_corr = np.sum(np.multiply(data[array_slice],template), axis=-1) / \
                            np.sum(np.multiply(template,template))
            data[array_slice] = data[array_slice] - np.outer(template_corr, template)

            return inputs


class PsdBasis:
    """Enum for the different bases to use for computing the PSD."""
    IQ = 'iq'
    GAIN_PHASE = 'gain_phase'
    FREQ_DISS = 'freq_diss'

class ComputeNoisePSD(DataRoutine):
    stage = ProcessingStage.PROCESSING_L2

    def __init__(
            self,
            *bases: PsdBasis,
            nominal_block_length: float=10,
            cut_time: float=0.0,
    ):
        super().__init__()
        self.bases = bases
        self.nominal_block_length = nominal_block_length
        self.cut_time = cut_time
    
    def forward(self, pd: ProcessedData):
        # Initialize PSD group in the file if needed
        if not pd.test_node('psd'):
            psd_group = pd.create_group('/', 'psd')
        else:
            psd_group = pd.get_node('psd')

        for basis in self.bases:
            time = pd.time
            match basis:
                case PsdBasis.IQ:
                    data = pd.data_IQ[:]
                case PsdBasis.GAIN_PHASE:
                    data = pd.data_gain_phase[:] / pd.carrier_amplitude_norm()
                case PsdBasis.FREQ_DISS:
                    f = pd.baseband_freqs[:] + pd.lo_freq[:]
                    data = pd.data_freq_diss[:] / f[:, np.newaxis, :, np.newaxis]
                case _:
                    raise ValueError(f'Cannot compute noise PSD for unknown basis "{basis}"')
            if self.cut_time > 0:
                n_samples_to_cut = np.round(self.cut_time * pd.fs).astype(int)
                data = data[:, :, n_samples_to_cut:-n_samples_to_cut]
                time = time[n_samples_to_cut:-n_samples_to_cut]

            # Determine the number of blocks for computing the PSD
            n_samples = np.size(time)
            n_samples_per_block = int(2**np.ceil(np.log2(self.nominal_block_length * pd.fs)))
            n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
            if n_blocks == 0:
                n_blocks = 1
                n_samples_per_block = n_samples
            
            # Compute the PSD
            for i_chan in range(pd.n_channels):
                good_tones = np.argwhere(pd.chanmask[i_chan, :] == 1).flatten()
                freq, psd = signal.welch(
                    axis_index(data[i_chan], good_tones, axis=-2),
                    pd.fs[i_chan],
                    nperseg=n_samples_per_block,
                )

                # Save to the file
                if not pd.test_node('freq'):
                    pd.create_array(psd_group, 'freq', obj=freq)
                if not pd.test_node(f'psd_{basis}'):
                    psd_shape = (pd.n_channels, *psd.shape)
                    psd_dtype = psd.dtype
                    psd_array = pd.create_array(psd_group, f'psd_{basis}', shape=psd_shape, atom=tables.Atom.from_dtype(psd_dtype))
                psd_array[i_chan, :] = psd
                

    def get_receipt_entry(self) -> str:
        return f'ComputeNoisePSD: {{\n' \
               f'\tbases: {self.bases},\n' \
               f'\tcut_time: {self.cut_time},\n' \
               f'\tnominal_block_length: {self.nominal_block_length},\n' \
               f'}}'

# 
# Mapping
#

# def get_map_size(map: MapData, az_trim: float, za_trim: float, map_dpix: float, beam_map_mode: bool=False) -> npt.NDArray:

#     max_az = np.max(map.detector_az) - az_trim
#     min_az = np.min(map.detector_az) + az_trim
#     max_za = np.max(map.detector_za) - za_trim
#     min_za = np.min(map.detector_za) + za_trim
#     n_pix_x = int(np.ceil((max_az - min_az) / map_dpix))
#     n_pix_y = int(np.ceil((max_za - min_za) / map_dpix))
#     map_x = np.arange(n_pix_x) * map_dpix + min_az + map_dpix / 2.
#     map_y = np.arange(n_pix_y) * map_dpix + min_za + map_dpix / 2.
#     if not beam_map_mode:
#         map_y += 0.1  # 0.1 accounts for assymmetry in array

#     # if map.setnum in [1007, 1009]:
#     #     np.savez('map_size.npz', n_pix_x, n_pix_y, map_x, map_y)
#     # elif map.setnum in [1008, 1010]:
#     #     data = np.load('map_size.npz')
#     #     n_pix_x = data['arr_0']
#     #     n_pix_y = data['arr_1']
#     #     map_x = data['arr_2']
#     #     map_y = data['arr_3']
#     return n_pix_x, n_pix_y, map_x, map_y

@register_routine
class BinTODIntoMap(DataRoutine):
    name = 'BinTODIntoMap'
    version = "1.0"

    produces = {
        '/map/netd',
        '/map/hits_map',
        '/map/sum_map',
        '/map/map_az',
        '/map/map_za',
        '/map/good_samples',
    }

    def __init__(
            self,
            dataset: Literal['data_mK', 'data_freq']='data_mK',
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            med_netd_cut_threshold: float=3.,
            beam_map_mode: bool=False,
            dpix: int=DEFAULT_MAP_DPIX,
    ):
        if dataset not in ('data_mK', 'data_freq'):
            raise ValueError(f'Unable to use dataset {dataset} for CleanTOD; choose "data_mK" or "data_freq".')
        if beam_map_mode:
            az_trim = 0.
            za_trim = 0.

        super().__init__(
            dataset=dataset,
            hp_filter_freq=hp_filter_freq,
            lp_filter_freq=lp_filter_freq,
            az_trim=az_trim,
            za_trim=za_trim,
            med_netd_cut_threshold=med_netd_cut_threshold,
            beam_map_mode=beam_map_mode,
            dpix=dpix,
        )

    def inputs(self, pdata: ProcessedData):
        dsets = []
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        for i_chan in range(pdata.n_chan):
            dsets.append(f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}')
        return dsets
    
    def _get_map_size(
        self,
        detector_az: h5py.Dataset,
        detector_za: h5py.Dataset,
        az_trim: float,
        za_trim: float,
        dpix: float=DEFAULT_MAP_DPIX,
        beam_map_mode: bool=False,
    ) -> tuple[int, int, npt.NDArray, npt.NDArray]:

        max_az = np.max(detector_az) - az_trim
        min_az = np.min(detector_az) + az_trim
        max_za = np.max(detector_za) - za_trim
        min_za = np.min(detector_za) + za_trim
        n_pix_x = int(np.ceil((max_az - min_az) / dpix))
        n_pix_y = int(np.ceil((max_za - min_za) / dpix))
        map_x = np.arange(n_pix_x) * dpix + min_az + dpix / 2.
        map_y = np.arange(n_pix_y) * dpix + min_za + dpix / 2.
        if not beam_map_mode:
            map_y += 0.1  # 0.1 accounts for assymmetry in array

        return n_pix_x, n_pix_y, map_x, map_y
    
    def _initialize_map_arrays(
        self,
        pdata: ProcessedData,
        n_maps: int,
        n_pix_x: int,
        n_pix_y: int,
        dpix: float,
    ):
        if pdata.has('map', exact_match=True):
            _logger.warning('Map group already exists in the file; overwriting datasets.')
            del pdata['map']
        map_group = pdata.create_group('map')
        map_group.create_dataset('map_az', shape=(n_pix_x,), dtype=np.float64)
        map_group.create_dataset('map_za', shape=(n_pix_y,), dtype=np.float64)
        map_group.create_dataset('sum_map', shape=(n_maps, n_pix_x, n_pix_y), chunks=(1, n_pix_x, n_pix_y), dtype=np.float64)
        map_group.create_dataset('hits_map', shape=(n_maps, n_pix_x, n_pix_y), chunks=(1, n_pix_x, n_pix_y), dtype=np.float64)
        map_group.create_dataset('netd', shape=(pdata.n_tones,), dtype=np.float64)
        map_group.attrs['dpix'] = dpix
        # TODO: fix this last part
        good_samples = map_group.create_dataset('good_samples', (pdata.n_chan,), dtype=h5py.vlen_dtype(np.uint32))
        for i_chan in range(pdata.n_chan):
            interpolated_samples = pdata.get_from_channel(i_chan, 'time_ordered_data/interpolated_samples')
            good_samples[i_chan] = np.setdiff1d(np.arange(pdata.n_samples), interpolated_samples)

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        dpix = self.params['dpix']
        beam_map_mode = self.params['beam_map_mode']
        n_pix_x, n_pix_y, map_az, map_za = self._get_map_size(
            pdata.detector_az,
            pdata.detector_za,
            self.params['az_trim'],
            self.params['za_trim'],
            dpix,
            beam_map_mode=beam_map_mode,
        )
        n_maps = N_POLARIZATION if not beam_map_mode else self.n_tones
        self._initialize_map_arrays(pdata, n_maps, n_pix_x, n_pix_y, dpix)
        pdata['map/map_az'][:] = map_az
        pdata['map/map_za'][:] = map_za
        detector_az = pdata.detector_az
        detector_za = pdata.detector_za

        match self.params['dataset']:
            case 'data_mK':
                data = pdata.data_mK[:]
            case 'data_freq':
                data = pdata.data_freq_diss[0]

        sum_map = pdata['map/sum_map'][:]
        hits_map = pdata['map/hits_map'][:]
        netd = pdata['map/netd'][:]

        chanmask = pdata.chanmask[:]
        bad_tones = [
            1, 3, 223, 278, 299,
            303, 10, 69, 192, 820,
            263, 483, 172, 574, 426,
            569, 297, 167, 15, 717,
            487, 842, 453, 13, 719,
            92, 571, 630, 84, 220,
            364, 516, 74, 726, 292,
            519, 812, 302, 683, 537,
            294, 534, 256, 661, 529,
            737, 54, 782, 567, 103,
            330, 133, 809, 460, 589,
            387, 538, 213, 120, 79,
            783, 612, 121, 117, 749
        ]
        chanmask[bad_tones] = -1

        # Compute NETD values
        _logger.info('BinTODIntoMap: Computing netd...')
        wind = signal.get_window('hamming', pdata.n_samples)
        hp_filter_freq = self.params['hp_filter_freq']
        lp_filter_freq = self.params['lp_filter_freq']
        for i_tone in np.where(chanmask == 1)[0]:
            this_freq, this_psd = signal.periodogram(data[i_tone, :], pdata.fs, window=wind)
            valid_freq = np.where((this_freq > hp_filter_freq) & (this_freq < lp_filter_freq))
            netd[i_tone] = np.sqrt(np.median(this_psd[valid_freq]))
        _logger.info('BinTODIntoMap: Done computing netd')

        # Get rid of tones with bad weights
        med_netd_cut_threshold = self.params['med_netd_cut_threshold']
        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        chanmask[good_idx] = np.where(good_netd > med_netd_cut_threshold * np.nanmedian(good_netd), -1, chanmask[good_idx])

        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, chanmask[good_idx])
        chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, chanmask[good_idx])

        netd[chanmask != 1] = 0

        if beam_map_mode:
            tones_to_map = np.argwhere(pdata.chanmask != 0).flatten()
        else:
            tones_to_map = np.argwhere(chanmask == 1).flatten()

        # Create map
        _logger.info('BinTODIntoMap: Creating map...')
        for n_loop, i_tone in enumerate(tones_to_map):
            if n_loop == np.size(tones_to_map) // 2:
                _logger.info('BinTODIntoMap: Halfway done creating map...')
            if beam_map_mode:
                map_idx = i_tone
                weight = 1.
            else:
                map_idx = pdata.detector_pol[i_tone] - 1  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1./ netd[i_tone] ** 2.

            this_detector_az = detector_az[i_tone]
            this_detector_za = detector_za[i_tone]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_tone])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/dpix))
            y_ind = y_ind.astype('int64')

            #eliminate samples outside the map
            i_chan = pdata.get_channel_index_from_tone_index(i_tone)
            good_samples = pdata['map/good_samples'][i_chan][:]
            # good_samples = np.arange(pdata.n_samples)  # TODO: Update this after fixing good_samples
            valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
                np.logical_and(x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x), \
                np.logical_and(y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y))))
            good_samples = good_samples[valid_index]

            #loop over samples to create sum and hits maps
            for time_sample in good_samples:
                sum_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += this_clean_data[time_sample] * weight
                hits_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += 1. * weight
        pdata.set_chanmask(chanmask)
        pdata['map/hits_map'][:] = hits_map
        pdata['map/sum_map'][:] = sum_map
        pdata['map/netd'][:] = netd
        _logger.info('BinTODIntoMap: Done creating map.')

        return list(self.produces) + ['/vdsets/chanmask']


@register_routine
class PlotMap(DataRoutine):
    name = 'PlotMap'
    version = '1.0'

    requires = {
        '/map/map_az',
        '/map/map_za',
        '/map/netd',
        '/map/sum_map',
        '/map/hits_map',
    }

    produces = {
        '/map/plotting/map',
        '/map/plotting/total_map',
        '/map/plotting/flagged_map_1',
        '/map/plotting/flagged_map_2',
        '/map/plotting/flagged_total_map',
        '/map/plotting/contour_levels',
    }

    def __init__(
            self,
            gaussian_sigma: float=GAUSSIAN_SIGMA,
            valid_covariance_threshold: float=0.5,
            cb_shrink: float=0.95,
            max_abs_threshold: float=0.75,
            save: bool=True,
            show: bool=False,
            overwrite: bool=True,
    ):
        super().__init__(
            gaussian_sigma=gaussian_sigma,
            valid_covariance_threshold=valid_covariance_threshold,
            cb_shrink=cb_shrink,
            max_abs_threshold=max_abs_threshold,
            save=save,
            show=show,
            overwrite=overwrite,
        )
    
    def inputs(self, pdata: ProcessedData):
        return list(self.requires)
    
    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        reset_arrays = self._intialize_arrays(pdata)
        if reset_arrays:
            self._get_combined_map(pdata)
        self.plot(pdata)

        if reset_arrays:
            return list(self.produces)
        return []

    def _intialize_arrays(self, pdata: ProcessedData) -> bool:
        if pdata.has('map/plotting', exact_match=True):
            if not self.params['overwrite']:
                # Specified not to overwrite existing plotting datasets, so just
                # plot the data without recomputing the maps.
                return False
            _logger.info('Plotting group already exists in the file; overwriting datasets.')
            del pdata['map/plotting']
        sum_map = pdata['map/sum_map']
        hits_map = pdata['map/hits_map']
        mapp = pdata.create_dataset(
            '/map/plotting/map',
            shape=sum_map.shape,
            dtype=np.float64,
        )
        total_map = pdata.create_dataset(
            '/map/plotting/total_map',
            shape=sum_map.shape[1:],
            dtype=np.float64,
        )
        with np.errstate(divide='ignore', invalid='ignore'):
            mapp[:] = sum_map[:] / hits_map[:]
            total_map[:] = np.sum(sum_map, axis=0) / np.sum(hits_map, axis=0)
        return True

    def _get_combined_map(self, pdata: ProcessedData) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
        sigma = self.params['gaussian_sigma']
        map = pdata['map/plotting/map']
        total_map = pdata['map/plotting/total_map']
        flagged_map_1 = gaussian_filter(map[0], sigma)
        flagged_map_2 = gaussian_filter(map[1], sigma)
        flagged_map_3 = gaussian_filter(total_map, sigma)

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

        flagged_map_1[combined_nan_map] = np.nan
        flagged_map_2[combined_nan_map] = np.nan
        flagged_map_3[combined_nan_map] = np.nan

        contour_levels = [1]

        # flagged_map_1= flagged_map_1.flatten()
        # flagged_map_2= flagged_map_2.flatten()
        # flagged_map_3= flagged_map_3.flatten()

        # flagged_map_1 = [x for x in flagged_map_1 if not np.isnan(x)]
        # flagged_map_2 = [x for x in flagged_map_2 if not np.isnan(x)]
        # flagged_map_3 = [x for x in flagged_map_3 if not np.isnan(x)]

        pdata.create_dataset('/map/plotting/flagged_map_1', data=flagged_map_1)
        pdata.create_dataset('/map/plotting/flagged_map_2', data=flagged_map_2)
        pdata.create_dataset('/map/plotting/flagged_total_map', data=flagged_map_3)
        pdata.create_dataset('/map/plotting/contour_levels', data=contour_levels)
    
    def _get_extent(self, pdata: ProcessedData) -> tuple[float, float, float, float]:
        map_az = pdata['map/map_az'][:]
        map_za = pdata['map/map_za'][:]
        dpix = pdata['map'].attrs['dpix']
        return (
            min(map_az)-dpix /2.,
            max(map_az)+dpix /2,
            max(map_za)+dpix /2.,
            min(map_za)-dpix /2.
        )

    def _get_scaled_optical_image(self, pdata: ProcessedData) -> npt.NDArray:
        dpix = pdata['map'].attrs['dpix']
        map_az = pdata['map/map_az']
        map_za = pdata['map/map_za']
        opt_npix_per_tel_npix = dpix / OPTCAM_PIX_SIZE_DEGREES
        opt_npix_az = int(map_az.size * opt_npix_per_tel_npix / 2) * 2
        opt_npix_za = int(map_za.size * opt_npix_per_tel_npix / 2) * 2
        # TODO: Replace these with references to optical camera dimensions
        opt_center_az = int(2592/2)+OPTCAM_OFFSET_AZ_PIX
        opt_center_za = int(1944/2)+OPTCAM_OFFSET_ZA_PIX
        az_range = slice(
            opt_center_az - int(opt_npix_az / 2),
            opt_center_az + int(opt_npix_az / 2),
        )
        za_range = slice(
            opt_center_za - int(opt_npix_za / 2),
            opt_center_za + int(opt_npix_za / 2),
        )
        return pdata.optical_image[za_range, az_range]

    def plot(self, pdata: ProcessedData):
        hits_map = pdata['map/hits_map']
        mapp = pdata['map/plotting/map'][:]
        total_map = pdata['map/plotting/total_map'][:]
        flagged_map_1_filt = pdata['map/plotting/flagged_map_1'][:]
        flagged_map_2_filt = pdata['map/plotting/flagged_map_2'][:]
        flagged_map_tot_filt = pdata['map/plotting/flagged_total_map'][:]
        contour_levels = pdata['map/plotting/contour_levels']

        map_az = pdata['map/map_az']
        map_za = pdata['map/map_za']
        extent = self._get_extent(pdata)

        valid_cov_1 = np.argwhere(hits_map[0] > 0.5 * np.median(hits_map[0]))
        map_goodcov_1 = np.zeros(np.size(valid_cov_1[:,0]))
        for i_cov in np.arange(np.size(valid_cov_1[:,0])):
            map_goodcov_1[i_cov] = mapp[0, valid_cov_1[i_cov,0],valid_cov_1[i_cov,1]]
        valid_cov_2 = np.argwhere(hits_map[1] > 0.5 * np.median(hits_map[1]))
        map_goodcov_2 = np.zeros(np.size(valid_cov_2[:,0]))
        for i_cov in np.arange(np.size(valid_cov_2[:,0])):
            map_goodcov_2[i_cov] = mapp[1, valid_cov_2[i_cov,0],valid_cov_2[i_cov,1]]

        netd = pdata['map/netd']
        netd_1 = netd[pdata.detector_pol == 1]
        netd_2 = netd[pdata.detector_pol == 2]
        valid_netd_1 = np.argwhere(netd_1 > 0)
        valid_netd_2 = np.argwhere(netd_2 > 0)

        cb_shrink = self.params['cb_shrink']
        max_abs_threshold = self.params['max_abs_threshold']
        this_xlim = min(map_az), max(map_az)
        this_ylim = max(map_za), min(map_za)
        max_abs = np.max(np.abs(np.append(map_goodcov_1, map_goodcov_2))) * max_abs_threshold
        med_netd_1 = 1./np.sqrt(np.sum(1./netd_1[valid_netd_1]**2)/np.size(valid_netd_1))
        med_netd_2 = 1./np.sqrt(np.sum(1./netd_2[valid_netd_2]**2)/np.size(valid_netd_2))

        t0 = time.asctime(time.localtime(pdata.timestamp[0]-7500))
        vis = pdata.optical_visibility[()]

        # TODO: Make figure size change based on the size of the map
        # aspect_ratio = (this_ylim[0] - this_ylim[1]) / (this_xlim[1] - this_xlim[0])
        # fig_height = 7.5
        # fig_width = fig_height / aspect_ratio
        fig, axes = plt.subplots(4, 1, figsize=(15, 7.5), sharex=True)
        fig.suptitle(
            f'{pdata.file_stub}\nLocal Time = {t0}, Optical Visibility = {vis} meters\n'
            f'NETD V-Pol (30Hz) = {med_netd_1:.1f} mK, NETD H-Pol (30Hz) = {med_netd_2:.1f} mK'
        )
        for ax in axes:
            ax.set_ylabel('ZA (degrees)')
            ax.set_xlim(this_xlim)
            ax.set_ylim(this_ylim)

        # Vertical polarization
        im = axes[0].imshow(
            np.flip(np.transpose(mapp[0][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Blues_r',
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[0])
        cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)
        axes[0].contour(
            np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Horizontal polarization
        im = axes[1].imshow(
            np.flip(np.transpose(mapp[1][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Reds_r'
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[1])
        cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)
        axes[1].contour(
            np.flip(np.flip(np.transpose(flagged_map_2_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='black',
        )

        # Total signal
        im = axes[2].imshow(
            np.flip(np.transpose(total_map[::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Greys_r'
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[2])
        cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
        axes[2].contour(
            np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Optical Image
        optical_image = self._get_scaled_optical_image(pdata)
        valid_opt_pix = np.where(optical_image < 240)
        opt_vmax = 255. 
        opt_vmin = -255  # NOTE: Shouldn't this be 0?
        im = axes[3].imshow(
            optical_image,
            extent=extent,
            aspect='equal',
            vmin=opt_vmin,
            vmax=opt_vmax,
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[3])
        cb.set_label('Optical Signal (rgb)', rotation=270, labelpad=15)
        axes[3].set_xlabel('Azimuth (degrees)')

        fig.subplots_adjust(wspace=0, hspace=0)
    #    pw.addPlot("Raw Image", this_fig)
        path = pdata.folder / f'{pdata.file_stub}_Source_Finder_Image.png'
        if not path.exists():
            path.touch(PERMISSIONS_ALL_FULL)
        if self.params['save']:
            fig.savefig(path, bbox_inches='tight')
        if self.params['show']:
            plt.show()

            

# class RemovePointLomaPickup(DataRoutine):
#     def __init__(self, ds_factor: int=6, pickup_filter_freq: float=1):
#         super().__init__()
#         self.ds_factor = ds_factor
#         self.pickup_filter_freq = pickup_filter_freq
    
#     def forward(self, pd: ProcessedData) -> MapData:
#         #need to high pass filter the data to remove basline drift
#         data_raw = pd.data_mK
#         chanmask = pd.chanmask

#         pickup_hpfilt_sos = signal.butter(6, self.pickup_filter_freq, 'hp', fs=pd.fs, output='sos', analog=False)

#         #sum all the data at each time sample, then look for outliers in this sum
#         data_sum_raw = np.zeros(np.size(data_raw[0,:]))
#         for i_chan in range(np.size(chanmask)):
#             if chanmask[i_chan] == 1:      
#                 data_sum_raw += np.abs(data_raw[i_chan,:])
#         data_sum = signal.sosfiltfilt(pickup_hpfilt_sos, data_sum_raw)

#         pickup_data = np.ndarray.flatten(np.argwhere(np.abs(data_sum) > 5.*np.median(np.abs(data_sum))))
#         pickup_good_index = []
#         valid_time = np.arange(np.size(data_sum))
#         if np.size(pickup_data > 0):
#             pickup_start = pickup_data[np.argwhere(pickup_data - np.roll(pickup_data,1) != 1)]
#             pickup_end = pickup_data[np.argwhere(np.roll(pickup_data,-1) - pickup_data != 1)]
#             for i_start in pickup_start:
#                 pickup_data = np.append(pickup_data, i_start - 1 - np.arange(10))
#             for i_end in pickup_end:
#                 pickup_data = np.append(pickup_data, i_end + 1 + np.arange(10))
#             pickup_data.sort()
#             valid_pickup = np.ndarray.flatten(np.argwhere(np.bitwise_and(pickup_data >= 0,pickup_data < np.size(valid_time))))
#             pickup_data = pickup_data[valid_pickup]
#             pickup_good_index = [element for element in np.arange(np.size(valid_time)) if element not in pickup_data]
#             pickup_good_index = np.divide(pickup_good_index[0::self.ds_factor], self.ds_factor)
#             pickup_good_index = pickup_good_index.astype(int)

#         m = MapData.from_processed_data(pd)
#         m.good_samples = np.array(pickup_good_index)
#         # pdb.set_trace()
#         return m


if __name__ == '__main__':
    date = '20260320'
    setnum = 1010

    lp_filter_freq = 30
    hp_filter_freq= 0.25

    cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=8)
    pd = cd.create_processed_data()

    # pd = ProcessedData.from_file(date, setnum, mode='a')

    noise_removal = RemoveElectronicsNoise()
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq)
    clean_tod = CleanTOD()
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        az_trim=0,
        za_trim=0,
        dpix=0.1,
    )
    plotter = PlotMap(show=True)

    noise_removal.apply(pd)
    hp_filter.apply(pd)
    lp_filter.apply(pd)
    clean_tod.apply(pd)
    bin_tod_to_map.apply(pd)
    plotter.apply(pd)

