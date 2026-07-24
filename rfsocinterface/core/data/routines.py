"""Data proccessing routines."""

from __future__ import annotations
import logging
from typing import Literal, TypeVar
import warnings
import functools

import pdb

import h5py
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial
from numpy.polynomial import polynomial as poly
from scipy import signal
import time
import datetime
import json
import matplotlib as mpl

from rfsocinterface.core.data.storage import ConsolidatedData, ProcessedData
from rfsocinterface.core.utils import PathJSONEncoder
#mpl.use('QtAgg')
import matplotlib.pyplot as plt


from rfsocinterface.core.data.utils import _logger, generate_calibrated_data, get_channel_group_name, get_step_group_name, rotate_basis, OPTCAM_PIX_SIZE_DEGREES, OPTCAM_OFFSET_AZ_PIX, OPTCAM_OFFSET_ZA_PIX, get_fft_csd_psd
from rfsocinterface.core.data.utils import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, axis_index, get_git_hash, axis_slice

__all__ = (
    'ROUTINE_REGISTRY',
    'register_routine',
    'DataRoutine',
    'CutoffFilter',
    'LowPassFilter',
    'HighPassFilter',
    'RemoveElectronicsNoise',
    'CleanTOD',
)


_logger = logging.getLogger(__name__)

ROUTINE_REGISTRY = {}
T = TypeVar('DataRoutine', bound='DataRoutine')


class ProcessingStage:
    """Enum for the different stages of data processing."""
    PRE_PROCESSING = 'pre_processing'
    PROCESSING_L1 = 'processing_l1'
    PROCESSING_L2 = 'processing_l2'
    POST_PROCESSING = 'post_processing'


def register_routine(cls: type[T]) -> type[T]:
    """Class decorator for registering a DataRoutine subclass in the ROUTINE_REGISTRY."""
    if not issubclass(cls, DataRoutine):
        _logger.warning(f'Failed to register class {cls.__name__} as a DataRoutine; it does not inherit from DataRoutine.')
        return
    ROUTINE_REGISTRY[cls.name] = cls
    _logger.debug(f'Registered data routine: {cls.__name__}')
    return cls


class DataRoutine:
    """Base class for data processing routines.
    
    
    Attributes:
        name (str): Name of the routine.
        version (str): Version of the routine.
        record_checkpoint (bool): Whether to record a checkpoint after applying this routine.
        requires (set): Set of dataset names required by this routine.
        produces (set): Set of dataset names produced by this routine.
    
    """
    name = 'base'
    version = '0.0.0'
    record_checkpoint = False  # override per routine if desired

    requires = set()
    produces = set()

    def __init__(self, **params):
        self.params = params
    
    def validate_inputs(self, pdata: ProcessedData, inputs: list):
        """Validate that the required datasets are present in the ProcessedData.
        
        Raises:
            RuntimeError: If any required datasets are missing from the ProcessedData.
        """
        missing = set(inputs) - set(pdata.list_dataset_names(full_names=True))
        if missing:
            raise RuntimeError(f'Missing required datsets: {missing}')

    # ---- main entry point ----
    def apply(self, pdata: ProcessedData):
        """Apply the routine to the given ProcessedData.
        
        This method handles the common workflow of validating inputs, running the computation,
        logging metadata, and recording checkpoints. The actual computation should be implemented
        in the run() method of the subclass.

        """
        _logger.info(f'{self.name}: Applying routine...')
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
        _logger.info(f'{self.name}: Finished applying routine.')

        return outputs

    # ---- to be implemented by subclasses ----
    def run(self, pdata: ProcessedData, inputs: list=None):
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a run method'
        )

    def inputs(self, pdata: ProcessedData):
        """Return a list of dataset names required by this routine."""
        if self.requires:
            return list(self.requires)
        raise NotImplementedError

    # ---- helpers ----
    def _get_shapes(self, pdata, dataset_names):
        """Helper method to get the shapes of the input and output datasets."""
        shapes = {}
        for name in dataset_names:
            if name in pdata.file:
                shapes[name] = pdata[name].shape
        return shapes

    def _log_step(self, pdata: ProcessedData, meta: str):
        """Log the processing step in the 'processing_history' group of the ProcessedData."""
        hist = pdata.file.require_group('processing_history')

        step_idx = len(hist)
        step_name = get_step_group_name(step_idx, self.name)

        step_group = hist.create_group(step_name)

        for k, v in meta.items():
            if isinstance(v, (dict, list)):
                step_group.attrs[k] = json.dumps(v, cls=PathJSONEncoder)
            else:
                step_group.attrs[k] = v

    def _checkpoint(self, pdata: ProcessedData):
        """Save a checkpoint of the current state of the ProcessedData."""
        chk_group = pdata.file.require_group('checkpoints')
        name = get_step_group_name(len(chk_group), self.name)

        g = chk_group.create_group(name)

        # naive: copy all datasets (you can refine later)
        for key, item in pdata.file.items():
            if isinstance(item, type(pdata.file['/'])):  # dataset
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
        """Helper method to construct the metadata dictionary for logging the processing step."""
        return {
            'name': self.name,
            'version': self.version,
            'timestamp': timestamp,
            'params': self.params,
            'inputs': inputs,
            'outputs': outputs,
            'shape_before': shapes_before,
            'shape_after': shapes_after,
            'code_version': get_git_hash(),
            'runtime_sec': runtime,
        }

#
# Begin Data Routine Catlog
#

@register_routine
class CutoffFilter(DataRoutine):
    """Base class for cutoff filters (low-pass, high-pass, band-pass).
    
    Not meant to be used directly, but provides common functionality for the different 
    types of cutoff filters.
    """
    name = 'CutoffFilter'
    version = '1.0.0'

    def __init__(self,
        filter_freq: float,
        btype: str,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        """Initialize the cutoff filter routine.
        
        Arguments:
            filter_freq (float): The cutoff frequency for the filter in Hz.
            btype (str): The type of filter to apply. Must be one of 'low', 'high',
                'bandpass', or 'bandstop'.
            datasets (list[str], optional): List of dataset names to apply the filter 
                to. Defaults to ['/vdsets/data_mK'].
        """
        super().__init__(
            filter_freq=filter_freq,
            btype=btype,
            datasets=datasets,
        )
    
    def inputs(self, pdata: ProcessedData):
        return self.params['datasets']

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        """Apply the cutoff filter to the specified datasets.
        
        Applies a Butterworth filter with the specified cutoff frequency and type to 
        each of the input datasets.
        """
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
    """Low-pass filter routine."""

    name = 'LowPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        super().__init__(filter_freq, btype='lowpass', datasets=datasets)


@register_routine
class HighPassFilter(CutoffFilter):
    """High-pass filter routine."""

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
        max_modes (int, optional): Maximum number of eigenmodes to use for template 
            construction.

    Returns:
        (npt.NDarray): Templates for noise removal (2 x M x N_samples).
            Computed using the first M eigenmodes of the correlation matrix.
    """
    # Subtract the mean from each detector
    deproj = data - np.mean(data, axis=-1, keepdims=True)
    deproj_flat = deproj / np.std(deproj, axis=-1, keepdims=True)
    n_tones = data.shape[1]

    # Create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(deproj_flat, np.conj(np.transpose(deproj, axes=(0, 2, 1))))

    # Calculate the eigenmodes of the correlation matrices
    eigen_values, v = np.linalg.eig(correlation_matrices)
    sorted_indices = np.argsort(eigen_values, axis=1)[:, ::-1]
    sorted_eigen_values = np.take_along_axis(eigen_values, sorted_indices, axis=1)
    sorted_v = np.take_along_axis(v, sorted_indices[:, np.newaxis, :], axis=2)

    # Use a different sigma multiplier based on the number of tones
    if n_tones < 25:
        sigma_mult = 1.5
    elif n_tones < 50:
        sigma_mult = 2.5
    else:
        sigma_mult = 3

    n_modes = 2
    new_modes = -1
    while new_modes != 0 and n_modes <= max_modes:
        with np.errstate(divide='ignore', invalid='ignore'):
            log_eigen_values = np.log10(sorted_eigen_values[:, n_modes:])
        mu = np.mean(log_eigen_values, axis=1)
        sigma = np.std(log_eigen_values, axis=1)
        large_eigen_values = np.where(log_eigen_values > (mu + sigma_mult * sigma)[:, np.newaxis])
        i_count = large_eigen_values[0].size - np.sum(large_eigen_values[0])
        q_count = large_eigen_values[0].size - i_count
        new_modes = max(i_count, q_count)
        n_modes += new_modes
    n_modes = min(n_modes, max_modes)
    _logger.debug(f'RemoveElectronincsNoise: Using {n_modes} eigen modes')

    # create templates based on the N_mode largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', sorted_v[:,:,0:n_modes], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates



def compute_templates_fspace(
        data: npt.NDArray,
        fs:float,
        lp_filt_freq:int = 1,
        max_modes: int=30,
        plot_eigenvalues: bool=False,
) -> npt.NDArray:

    deproj = data - np.mean(data, axis=-1, keepdims=True)
    n_tones = data.shape[1]
    n_dir = data.shape[0]
    n_modes = 2
    good_pixels = np.arange(n_tones)

    sigma = np.std(deproj, axis = -1, keepdims=True)
    whitened_noise = deproj/sigma
    _, _, csd, freqs = get_fft_csd_psd(whitened_noise, fs)

    lp_bound_idx = np.searchsorted(freqs, lp_filt_freq)
    correlation_matrices = np.mean(csd[:, :, :, 0:lp_bound_idx], axis = -1)
    
    eigen_values, v = np.linalg.eigh(correlation_matrices)
    sorted_indices = np.argsort(eigen_values, axis=1)[:, ::-1]
    sorted_eigen_values = np.take_along_axis(eigen_values, sorted_indices, axis=1)

    sorted_v = np.take_along_axis(v, sorted_indices[:, np.newaxis, :], axis=-1)

    if plot_eigenvalues:
        plt.figure()
        plt.loglog(sorted_eigen_values[0],'-o')
        plt.xlabel('Eigenvalue Index')
        plt.ylabel('Eigenvalue')
        plt.title('Eigenvalues of Correlation Matrix')
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.show()
        
    if n_tones < 25:
        sigma_mult = 1.5
    elif n_tones < 50:
        sigma_mult = 2.0
    else:
        sigma_mult = 2.5

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
    _logger.debug(f'RemoveElectronincsNoise: Using {n_modes} eigen modes')

    # create templates based on the N_mode largest eigenmodes of each
    filt_sos = signal.butter(BUTTER_ORDER, lp_filt_freq, btype='low', fs=fs, output='sos', analog=False)
    data_lp = signal.sosfiltfilt(filt_sos, whitened_noise)
    templates = np.einsum('ijk,ijl->ikl', sorted_v[:,:,0:n_modes], whitened_noise)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates


def decode_tone_indices(pdata: ProcessedData, selection_indices: npt.NDArray | str, i_chan: int=None) -> npt.NDArray:
    """Helper method for decoding the selected indices for routines.

    Arguments:
        pdata (ProcessedData): ProcessedData object containing the data.
        selection_indices (npt.NDArray | str, optional): Either a string specifying the 
            type of tones to select or an array of indices to select. Possible string 
            values are:
                - 'onres' or 'on_res' or 'on_resonance': Select on-resonance tones
                - 'offres' or 'off_res' or 'off_resonance': Select off-resonance tones
                - 'all': Select all tones
        i_chan (int, optional): The channel index to select the tones for. If None, 
            will use the tone indices for all channels.

    Returns:
        (npt.NDArray): The indices of the tones to select.
    """
    if isinstance(selection_indices, str):
        match selection_indices.lower():
            case 'onres' | 'on_res' | 'on_resonance':
                return pdata.get_onres_ind(i_chan) if i_chan is not None else pdata.onres_ind
            case 'offres' | 'off_res' | 'off_resonance':
                return pdata.get_offres_ind(i_chan) if i_chan is not None else pdata.offres_ind
            case 'all':
                return np.arange(pdata.get_n_tones(i_chan), dtype=int) if i_chan is not None else np.arange(pdata.n_tones, dtype=int)
            case _:
                _logger.warning(f'Unkown index selection string: {selection_indices}; defaulting to all tones')
                return np.arange(pdata.get_n_tones(i_chan), dtype=int) if i_chan is not None else np.arange(pdata.n_tones, dtype=int)
    else:
        return selection_indices

@register_routine
class RemoveElectronicsNoise(DataRoutine):
    """Routine to remove correlated electronics noise.
    
    Removes correlated electronics noise using eigenmode decomposition of the 
    gain/phase data. Then rotates the cleaned gain/phase data back to IQ and regenerates
    the calibrated data arrays (data_freq_diss, data_mK).
    """
    name = 'RemoveElectronicsNoise'
    version = '1.0.0'

    def __init__(
        self,
        max_modes: int=30,
        lp_filt_freq: float=0,
        template_selection_indices: npt.NDArray | str='all',
        fspace: bool=False,
        eigenmodes: list[int]=None,
    ):
        """Initialize the RemoveElectronicsNoise routine.
        
        Arguments:
            max_modes (int, optional): Maximum number of eigenmodes to use for template 
                construction.
            lp_filt_freq (float, optional): The cutoff frequency for the low-pass filter
                applied to the gain/phase data before computing templates. Set to 0 or 
                a value >= Nyquist to disable filtering. Defaults to 0 (no filtering).
            template_selection_indices (npt.NDArray | str, optional): Indices of tones 
                to use for computing the templates. Can be any value supported by 
                `decode_tone_indices`. Defaults to `all`.
            fspace (bool, optional): Whether to operate in frequency space.
            eigenmodes (list[int], optional): The actual number of modes used for each
                channel. If None, will be computed and stored in the params after running.
                This is mostly for logging purposes since the number of modes used can
                vary based on the data and the max_modes parameter. Defaults to None.
        """
        super().__init__(
            max_modes=max_modes,
            lp_filt_freq=lp_filt_freq,
            template_selection_indices=template_selection_indices,
            fspace=fspace,
            eigenmodes=eigenmodes,
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
        max_modes = self.params['max_modes']
        fs = pdata.fs

        for i_chan in range(pdata.n_chan):
            selection_indices = decode_tone_indices(pdata, template_selection_indices, i_chan)

            data_gain_phase = pdata.get_from_channel(i_chan, 'time_ordered_data/data_gain_phase')
            clean_gain_phase = np.copy(data_gain_phase)
            clean_gain_phase -= np.mean(clean_gain_phase, axis=-1, keepdims=True)
            if 0 < lp_filt_freq < fs / 2:
                filt_sos = signal.butter(
                    BUTTER_ORDER,
                    lp_filt_freq,
                    btype='low',
                    fs=fs,
                    output='sos',
                    analog=False,
                )
                data_lp = signal.sosfiltfilt(filt_sos, clean_gain_phase)
            else:
                data_lp = clean_gain_phase[:]

            if self.params['fspace']:
                # compute in fspace
                templates = compute_templates_fspace(data_lp[:, selection_indices], pdata.fs, lp_filt_freq=lp_filt_freq, max_modes=max_modes)
            else:   
                templates = compute_templates(data_lp[:, selection_indices], max_modes=max_modes)  # 2 x N_modes x N_samples

            n_modes = templates.shape[1]
            eigenmodes.append(n_modes)
            denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 2 x N_modes


            for i_mode in range(n_modes):
                clean_gain_phase -= np.mean(clean_gain_phase, axis=-1, keepdims=True)
                numerator = np.einsum('ijk,ik->ij', clean_gain_phase/np.std(clean_gain_phase, axis=-1, keepdims=True), templates[:, i_mode])  # 2 x N_tones
                corr = numerator / denominator[:, i_mode:i_mode+1]  # 2 x N_tones
                clean_gain_phase[:] = clean_gain_phase - np.einsum('ij,ikl->ijl', corr, templates[:, i_mode:i_mode+1])  # 2 x N_tones x N_samples
            
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
            data_freq_diss = pdata.get_from_channel(i_chan, 'time_ordered_data/data_freq_diss')
            data_mK = pdata.get_from_channel(i_chan, 'time_ordered_data/data_mK')
            generate_calibrated_data(
                data_IQ,
                data_freq_diss,
                data_mK,
                calibration_info['IQ_to_freq_diss_angle'],
                calibration_info['adc_units_to_hz'],
                calibration_info['df_per_mK'],
            )

        self.params['eigenmodes'] = eigenmodes
        return inputs

#
# Cosmic Ray Removal
#

def get_z_arrays(
        data: npt.NDArray,
        num_processing_blocks: int,
) -> npt.NDArray:
    time_stream_size = data.shape[-1]


    block_indices = np.linspace(
        0, time_stream_size, num_processing_blocks + 1, dtype=int
    )
    
    z_I = np.zeros_like(data[0, :, :])
    z_Q = np.zeros_like(data[0, :, :])
    

    for i in range(num_processing_blocks):
        start, end = block_indices[i], block_indices[i + 1]
        I = data[0, :, start:end]
        Q = data[1, :, start:end]

        mean_I = np.mean(I, axis=1)
        mean_Q = np.mean(Q, axis=1)
        std_I  = np.std(I, axis=1)
        std_Q  = np.std(Q, axis=1)

        std_I[std_I == 0] = np.nan
        std_Q[std_Q == 0] = np.nan
        z_I[:, start:end]= np.abs(I - mean_I[:, None]) / std_I[:, None]
        z_Q[:, start:end] = np.abs(Q[:] - mean_Q[:, None]) / std_Q[:, None]

    return z_I, z_Q


def interpolate_CR_packets(data_IQ: h5py.Dataset, glitch_mask_I: npt.NDArray, glitch_mask_Q: npt.NDArray, window: int = 10):
    timestream_packets = data_IQ.shape[2]
    tone_list = np.arange(data_IQ.shape[1])
    timestream = np.arange(timestream_packets)
    for t in range(timestream_packets):
        start = int(max(0, t-window))
        end = int(min(timestream_packets, t + window))
        

        glitchy_tones_I = tone_list[glitch_mask_I[:,t].T]
        glitchy_tones_Q = tone_list[glitch_mask_Q[:,t].T]
        glitchy_tones = list(set(glitchy_tones_I)|set(glitchy_tones_Q))
        if len(glitchy_tones) != 0:

            times = np.concatenate((
                timestream[start:t],
                timestream[t+1:end]
            ))

            data = np.concatenate((
                data_IQ[:, glitchy_tones, start:t],
                data_IQ[:, glitchy_tones, t+1:end]
            ), axis=2)

            # Center time axis
            x = times - timestream[t]

            # Fit along time axis
            fit_I = poly.polyfit(x, data[0].T, deg=4)
            fit_Q = poly.polyfit(x, data[1].T, deg=4)

            # Evaluate polynomial at x = 0
            interpolated_I_val = poly.polyval(0, fit_I)
            interpolated_Q_val = poly.polyval(0, fit_Q)

            #print(interpolated_I_val-data_IQ[0,glitchy_tones, t])
            #print(interpolated_Q_val-data_IQ[1,glitchy_tones, t])
            data_IQ[0,glitchy_tones,t] = interpolated_I_val
            data_IQ[1,glitchy_tones,t] = interpolated_Q_val



# TODO: Expand docstrings
@register_routine
class RemoveCosmicRays(DataRoutine):
    """Routine for removing cosmic rays."""
    name = 'RemoveCosmicRays'
    version = '1.0.0'


    def __init__(
        self,
        std_threshold: float=5,
        num_processing_blocks: int=1,
    ):
        super().__init__(
            std_threshold=std_threshold,
            num_processing_blocks=num_processing_blocks,
        )
    
    def inputs(self, pdata: ProcessedData):
        return ['/vdsets/data_IQ']
    
    def run(self, pdata: ProcessedData, inputs: list=None):

        threshold = self.params['std_threshold']
        n_blocks = self.params['num_processing_blocks']
        data_IQ = pdata.data_IQ

        z_I, z_Q = get_z_arrays(data_IQ[:], n_blocks)
        glitch_mask_I = np.array(z_I) > threshold
        glitch_mask_Q = np.array(z_Q) > threshold
        interpolate_CR_packets(data_IQ, glitch_mask_I, glitch_mask_Q)

        return inputs


@register_routine
class CleanTOD(DataRoutine):
    """Routine to remove common-mode signals from the time-ordered data."""
    name = 'CleanTOD'
    version = '1.0.0'

    def __init__(self, dataset: Literal['data_mK', 'data_freq']='data_mK'):
        """Initialize the CleanTOD routine.
        
        Arguments:
            dataset (str, optional): The name of the dataset to clean. Must be either 
                'data_mK' or 'data_freq'. Defaults to 'data_mK'.
        """
        if dataset not in ('data_mK', 'data_freq'):
            raise ValueError(f'{self.name}: Unable to use dataset {dataset}; choose "data_mK" or "data_freq".')
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
                template = np.nansum(data[array_slice], axis=0)
            else:
                msg = f'{self.name}: Unexpected data shape: {data.shape}; Expected 2D or 3D dataset.'
                _logger.exception(msg)
                raise ValueError(msg)
            template = template - np.mean(template)
            template_corr = np.sum(np.multiply(data[array_slice],template), axis=-1) / \
                            np.sum(np.multiply(template,template))
            data[array_slice] = data[array_slice] - np.outer(template_corr, template)

            return inputs


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

