"""Data proccessing routines."""

from __future__ import annotations

import datetime
import json
import logging
import time
import typing
import warnings
from typing import ClassVar, Literal, Sequence, TypeVar

import matplotlib as mpl
import numpy as np
import numpy.typing as npt
from scipy import signal

from rfsocinterface.core.data.storage import ProcessedData
from rfsocinterface.core.utils import PathJSONEncoder

mpl.use('QtAgg')

from rfsocinterface.core.data.utils import (
    generate_calibrated_data,
    get_channel_group_name,
    get_step_group_name,
    rotate_basis,
)
from rfsocinterface.core.utils import BUTTER_ORDER, get_git_hash

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
DataRoutineType = TypeVar('DataRoutineType', bound='DataRoutine')


class ProcessingStage:
    """Enum for the different stages of data processing."""

    PRE_PROCESSING = 'pre_processing'
    PROCESSING_L1 = 'processing_l1'
    PROCESSING_L2 = 'processing_l2'
    POST_PROCESSING = 'post_processing'


def register_routine(cls: type[DataRoutineType]) -> type[DataRoutineType]:
    """Class decorator for registering a DataRoutine class in the ROUTINE_REGISTRY."""
    if not issubclass(cls, DataRoutine):
        _logger.warning(
            f'Failed to register class {cls.__name__} as a DataRoutine; it does not'
            ' inherit from DataRoutine.'
        )
        return None
    ROUTINE_REGISTRY[cls.name] = cls
    _logger.debug(f'Registered data routine: {cls.__name__}')
    return cls


class DataRoutine:
    """Base class for data processing routines.

    Attributes:
        name (str): Name of the routine.
        version (str): Version of the routine.
        record_checkpoint (bool): Whether to record a checkpoint after applying this
            routine.
        requires (set): Set of dataset names required by this routine.
        produces (set): Set of dataset names produced by this routine.

    """

    name = 'base'
    version = '0.0.0'
    record_checkpoint = False  # override per routine if desired

    requires: ClassVar[set] = set()
    produces: ClassVar[set] = set()

    def __init__(self, **params):
        """Initialize a DataRoutine."""
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

        This method handles the common workflow of validating inputs, running the
        computation, logging metadata, and recording checkpoints. The actual computation
        should be implemented in the run() method of the subclass.

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
    def run(self, pdata: ProcessedData, inputs: Sequence):
        """Run this data routine."""
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a run method'
        )

    def inputs(self, pdata: ProcessedData):  # noqa: ARG002
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
        """Append to the 'processing_history' group of the ProcessedData."""
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
        inputs: Sequence[str],
        outputs: Sequence[str],
        shapes_before: Sequence[tuple],
        shapes_after: Sequence[tuple],
        runtime: float,
    ) -> dict:
        """Helper method to construct the metadata dictionary for history logging."""
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

    def __init__(
        self,
        filter_freq: float,
        btype: str,
        datasets: Sequence[str] = ['/vdsets/data_mK'],
    ):
        """Initialize the cutoff filter routine.

        Arguments:
            filter_freq (float): The cutoff frequency for the filter in Hz.
            btype (str): The type of filter to apply. Must be one of 'low', 'high',
                'bandpass', or 'bandstop'.
            datasets (Sequence[str], optional): List of dataset names to apply the
                filter to. Defaults to ['/vdsets/data_mK'].
        """
        super().__init__(
            filter_freq=filter_freq,
            btype=btype,
            datasets=datasets,
        )

    @typing.override
    def inputs(self, pdata: ProcessedData):
        return self.params['datasets']

    def run(self, pdata: ProcessedData, inputs: Sequence[str] = []):
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
        datasets: Sequence[str] = ['/vdsets/data_mK'],
    ):
        """Initialize the LowPassFilter routine.

        Arguments:
            filter_freq (float): The cutoff frequency for the filter in Hz.
            datasets (Sequence[str], optional): List of dataset names to apply the
                filter to. Defaults to ['/vdsets/data_mK'].
        """
        super().__init__(filter_freq, btype='lowpass', datasets=datasets)


@register_routine
class HighPassFilter(CutoffFilter):
    """High-pass filter routine."""

    name = 'HighPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: Sequence[str] = ['/vdsets/data_mK'],
    ):
        """Initialize the HighPassFilter routine.

        Arguments:
            filter_freq (float): The cutoff frequency for the filter in Hz.
            datasets (Sequence[str], optional): List of dataset names to apply the
                filter to. Defaults to ['/vdsets/data_mK'].
        """
        super().__init__(filter_freq, btype='highpass', datasets=datasets)


#
# Electronics Noise Removal
#


def compute_templates(
    data: npt.NDArray,
    max_modes: int = 30,
    low_sigma: float = 1.5,
    low_sigma_tone_threshold: float = 25,
    med_sigma: float = 2.5,
    med_sigma_tone_threshold: float = 50,
    high_sigma: float = 3,
) -> npt.NDArray:
    """Compute templates for correlated noise removal.

    Args:
        data (npt.NDArray): Input data (2 x N_tone x N_samples).
        max_modes (int, optional): Maximum number of eigenmodes to use for template
            construction.
        low_sigma (float, optional): Sigma multiplier for low number of tones.
        low_sigma_tone_threshold (float, optional): Tone threshold for low sigma.
        med_sigma (float, optional): Sigma multiplier for medium number of tones.
        med_sigma_tone_threshold (float, optional): Tone threshold for medium sigma.
        high_sigma (float, optional): Sigma multiplier for high number of tones.

    Returns:
        (npt.NDarray): Templates for noise removal (2 x M x N_samples).
            Computed using the first M eigenmodes of the correlation matrix.
    """
    # Subtract the mean from each detector
    deproj = data - np.mean(data, axis=-1, keepdims=True)
    deproj_flat = deproj / np.std(deproj, axis=-1, keepdims=True)
    n_tones = data.shape[1]

    # Create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(
        deproj_flat, np.conj(np.transpose(deproj, axes=(0, 2, 1)))
    )

    # Calculate the eigenmodes of the correlation matrices
    eigen_values, v = np.linalg.eig(correlation_matrices)
    sorted_indices = np.argsort(eigen_values, axis=1)[:, ::-1]
    sorted_eigen_values = np.take_along_axis(eigen_values, sorted_indices, axis=1)
    sorted_v = np.take_along_axis(v, sorted_indices[:, np.newaxis, :], axis=2)

    # Use a different sigma multiplier based on the number of tones
    if n_tones < low_sigma_tone_threshold:
        sigma_mult = low_sigma
    elif n_tones < med_sigma_tone_threshold:
        sigma_mult = med_sigma
    else:
        sigma_mult = high_sigma

    n_modes = 2
    new_modes = -1
    while new_modes != 0 and n_modes <= max_modes:
        with np.errstate(divide='ignore', invalid='ignore'):
            log_eigen_values = np.log10(sorted_eigen_values[:, n_modes:])
        mu = np.mean(log_eigen_values, axis=1)
        sigma = np.std(log_eigen_values, axis=1)
        large_eigen_values = np.where(
            log_eigen_values > (mu + sigma_mult * sigma)[:, np.newaxis]
        )
        i_count = large_eigen_values[0].size - np.sum(large_eigen_values[0])
        q_count = large_eigen_values[0].size - i_count
        new_modes = max(i_count, q_count)
        n_modes += new_modes
    n_modes = min(n_modes, max_modes)
    _logger.debug(f'RemoveElectronincsNoise: Using {n_modes} eigen modes')

    # create templates based on the N_mode largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', sorted_v[:, :, 0:n_modes], deproj)

    # subtract the mean again to be sure
    return np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]


def decode_tone_indices(
    pdata: ProcessedData,
    selection_indices: npt.NDArray | str,
    i_chan: int | None = None,
) -> npt.NDArray:
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
                return (
                    pdata.get_onres_ind(i_chan)
                    if i_chan is not None
                    else pdata.onres_ind
                )
            case 'offres' | 'off_res' | 'off_resonance':
                return (
                    pdata.get_offres_ind(i_chan)
                    if i_chan is not None
                    else pdata.offres_ind
                )
            case 'all':
                return (
                    np.arange(pdata.get_n_tones(i_chan), dtype=int)
                    if i_chan is not None
                    else np.arange(pdata.n_tones, dtype=int)
                )
            case _:
                _logger.warning(
                    f'Unkown index selection string: {selection_indices}; defaulting to'
                    ' all tones'
                )
                return (
                    np.arange(pdata.get_n_tones(i_chan), dtype=int)
                    if i_chan is not None
                    else np.arange(pdata.n_tones, dtype=int)
                )
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
        max_modes: int = 30,
        lp_filt_freq: float = 0,
        template_selection_indices: npt.NDArray | str = 'all',
        eigenmodes: list[int] | None = None,
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
            eigenmodes (list[int], optional): The actual number of modes used for each
                channel. If None, will be computed and stored in the params after
                running. This is mostly for logging purposes since the number of modes
                used can vary based on the data and the max_modes parameter. Defaults
                to None.
        """
        super().__init__(
            max_modes=max_modes,
            lp_filt_freq=lp_filt_freq,
            template_selection_indices=template_selection_indices,
            eigenmodes=eigenmodes,
        )

    @typing.override
    def inputs(self, pdata: ProcessedData):
        # Requires data_IQ, data_gain_phase, data_freq_diss, and data_mK
        # but there's no case where those wouldn't exist, so I'm not sure this matters
        dsets = []
        for i_chan in range(pdata.n_chan):
            group_name = get_channel_group_name(i_chan)
            group_name = f'/channels/{get_channel_group_name(i_chan)}/'
            dsets.extend(
                [
                    group_name + 'time_ordered_data/data_IQ',
                    group_name + 'time_ordered_data/data_gain_phase',
                    group_name + 'time_ordered_data/data_freq_diss',
                    group_name + 'time_ordered_data/data_mK',
                    group_name + 'calibration_info',
                ]
            )
        return dsets

    @typing.override
    def run(self, pdata: ProcessedData, inputs: Sequence[str] = []):
        eigenmodes = []  # The actual number of modes we use for each channel
        lp_filt_freq = self.params['lp_filt_freq']
        template_selection_indices = self.params['template_selection_indices']
        max_modes = self.params['max_modes']
        fs = pdata.fs

        for i_chan in range(pdata.n_chan):
            selection_indices = decode_tone_indices(
                pdata, template_selection_indices, i_chan
            )

            data_gain_phase = pdata.get_from_channel(
                i_chan, 'time_ordered_data/data_gain_phase'
            )
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
            templates = compute_templates(
                data_lp[:, selection_indices], max_modes=max_modes
            )  # 2 x N_modes x N_samples

            n_modes = templates.shape[1]
            eigenmodes.append(n_modes)
            denominator = np.einsum('ijk,ijk->ij', templates, templates)  # 2 x N_modes

            for i_mode in range(n_modes):
                clean_gain_phase -= np.mean(clean_gain_phase, axis=-1, keepdims=True)
                numerator = np.einsum(
                    'ijk,ik->ij', clean_gain_phase, templates[:, i_mode]
                )  # 2 x N_tones
                corr = numerator / denominator[:, i_mode : i_mode + 1]  # 2 x N_tones
                clean_gain_phase[:] = clean_gain_phase - np.einsum(
                    'ij,ikl->ijl', corr, templates[:, i_mode : i_mode + 1]
                )  # 2 x N_tones x N_samples

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
            data_IQ[:] = data_IQ[:] - np.mean(
                data_IQ[:], axis=-1, keepdims=True
            )  # Mean center
            data_freq_diss = pdata.get_from_channel(
                i_chan, 'time_ordered_data/data_freq_diss'
            )
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


@register_routine
class CleanTOD(DataRoutine):
    """Routine to remove common-mode signals from the time-ordered data."""

    name = 'CleanTOD'
    version = '1.0.0'

    def __init__(self, dataset: Literal['data_mK', 'data_freq'] = 'data_mK'):
        """Initialize the CleanTOD routine.

        Arguments:
            dataset (str, optional): The name of the dataset to clean. Must be either
                'data_mK' or 'data_freq'. Defaults to 'data_mK'.
        """
        if dataset not in ('data_mK', 'data_freq'):
            msg = (
                f'{self.name}: Unable to use dataset {dataset}; choose "data_mK" or'
                ' "data_freq".'
            )
            _logger.error(msg)
            raise ValueError(msg)
        super().__init__(dataset=dataset)

    @typing.override
    def inputs(self, pdata: ProcessedData):
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        return [
            f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}'
            for i_chan in range(pdata.n_chan)
        ]

    @typing.override
    def run(self, pdata: ProcessedData, inputs: Sequence[str] = []):
        for i_chan, dset in enumerate(inputs):
            data = pdata[dset]
            good_tones = pdata.get_onres_ind(i_chan)
            if data.ndim == 2:  # noqa: PLR2004
                array_slice = (good_tones, slice(None))
                template = np.nansum(data[array_slice], axis=0)
            elif data.ndim == 3:  # noqa: PLR2004
                array_slice = (0, good_tones, slice(None))
                template = np.nansum(data[array_slice], axis=0)
            else:
                msg = (
                    f'{self.name}: Unexpected data shape: {data.shape}; Expected 2D'
                    ' or 3D dataset.'
                )
                _logger.exception(msg)
                raise ValueError(msg)
            template = template - np.mean(template)
            template_corr = np.sum(
                np.multiply(data[array_slice], template), axis=-1
            ) / np.sum(np.multiply(template, template))
            data[array_slice] = data[array_slice] - np.outer(template_corr, template)

        return inputs
