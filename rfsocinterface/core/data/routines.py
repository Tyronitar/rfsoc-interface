"""Data proccessing routines."""

from __future__ import annotations

import datetime
import json
import logging
import time
import typing
import warnings
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, TypeVar

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
    'CleanTOD',
    'CutoffFilter',
    'DataRoutine',
    'HighPassFilter',
    'LowPassFilter',
    'RemoveElectronicsNoise',
    'register_routine',
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


@dataclass
class RoutineResult:
    """Structure representing the output of a data routine.

    Each field represents a map of input names to object paths within the input file.

    Attributes:
        modified (dict[str, list[str]]): Pre-existing objects that have been altered.
        created (dict[str, list[str]]): Newly created objects.
        deleted (dict[str, list[str]]): Objects that have been removed from the file.
        values (dict[str, Any]): In-memory results returned from the routine.
    """

    # Meta data
    modified: dict[str, Collection[str]] = field(default_factory=dict)
    created: dict[str, Collection[str]] = field(default_factory=dict)
    deleted: dict[str, Collection[str]] = field(default_factory=dict)
    # Return values
    values: dict[str, Any] = field(default_factory=dict)

"""
Possible formats for the result of `routine.inputs`:
1. Mapping[str, Sequence[Collection[str]]: Map of input names to a
    collection of datasets needed for each input.
    e.g. {
        "reference": {"/path/to/dset", ...},
        "candidate": {"/path/to/dset", ...},
    }
2. Sequence[Collection[str]]: A collection of datasets needed for each input
    in positional order. Prefer format 1 if possible.
    e.g. (["/path/to/dset", ...], ["/path/to/dset", ...])
3. Collection[str]: A collection of datasets for the single input to the
    routine. Included for backwards compatibility.
    e.g. ('/path/to/dset1', '/path/to/dset2', ...)
"""
type RoutineInputs = (
Sequence[str] | Sequence[Collection[str]] | Mapping[str, Collection[str]]
)

"""
Format for normalized routine inputs:
(
    (input_role, processed_data, dataset_paths),
    ...,
)
"""
type NormalizedRoutineInputs = tuple[tuple[str, ProcessedData, tuple[str]], ...]


class DataRoutine:
    """Base class for data processing routines.

    Attributes:
        name (str): Name of the routine.
        version (str): Version of the routine.
        record_checkpoint (bool): Whether to record a checkpoint after applying this
            routine.
        requires (dict[str, set[str]]): Set of datasets required by this routine, for
            each input.
        produces (dict[str, set[str]]): Set of datasets produced by this routine, for
            each input.
        min_inputs (int): The minimum number of inputs the routine can take. Defaults to
            1.
        max_inputs (int | None): The maximum number of inputs the routine can take. If
            None, the routine can take an arbitray amount of inputs. Defaults to 1.
        map_over_inputs (bool): Whether to apply the routine to each input ProcessedData
            individually. Defaults to True.
    """

    name = 'base'
    version = '0.0.0'
    record_checkpoint = False  # override per routine if desired

    # Multi-input support
    min_inputs = 1
    max_inputs = 1
    map_over_inputs = True

    requires: ClassVar[dict[str, set[str]]] = {}
    produces: ClassVar[dict[str, set[str]]] = {}

    def __init__(self, **params):
        """Initialize a DataRoutine."""
        self.params = params

    @classmethod
    def validate_input_count(cls, count: int) -> None:
        """Validate the number of inputs."""
        if count < cls.min_inputs:
            raise ValueError(
                f'{cls.__name__} requires at least '
                f'{cls.min_inputs} input dataset(s); received {count}.'
            )

        if cls.max_inputs is not None and count > cls.max_inputs:
            raise ValueError(
                f'{cls.__name__} accepts at most '
                f'{cls.max_inputs} input dataset(s); received {count}.'
            )

    def _normalize_resolved_inputs(
        self,
        pdata: tuple[ProcessedData, ...],
        resolved: RoutineInputs,
    ) -> NormalizedRoutineInputs:
        """Convert supported inputs() return formats into a normalized form.

        The resulting format is:
            (
                (input_role, processed_data, dataset_paths),
                ...
            )
        """
        # Backward-compatible single-input format:
        # ["/data_IQ", "/timestamp"]
        if len(pdata) == 1 and self._is_dataset_path_list(resolved):
            return (('input', pdata[0], tuple(resolved)),)

        # Multi-input positional format:
        # (
        #     ["/data_IQ"],
        #     ["/data_IQ"],
        # )
        if (
            isinstance(resolved, Collection)
            and not isinstance(resolved, (str, bytes))
            and len(resolved) == len(pdata)
            and all(self._is_dataset_path_list(paths) for paths in resolved)
        ):
            return tuple(
                (f'input_{index}', data, tuple(paths))
                for index, (data, paths) in enumerate(zip(pdata, resolved, strict=True))
            )

        # Multi-input named format:
        # {
        #     "reference": ["/data_IQ"],
        #     "candidate": ["/data_IQ"],
        # }
        if isinstance(resolved, Mapping):
            if len(resolved) != len(pdata):
                raise ValueError(
                    f'{type(self).__name__}.resolve_inputs() returned '
                    f'{len(resolved)} input roles for {len(pdata)} data files.'
                )

            return tuple(
                (role, data, tuple(paths))
                for (role, paths), data in zip(resolved.items(), pdata, strict=True)
            )

        raise TypeError(
            f'Unsupported result from {type(self).__name__}.resolve_inputs(): '
            f'{resolved!r}'
        )

    @staticmethod
    def _is_dataset_path_list(value) -> bool:
        return (
            isinstance(value, Collection)
            and not isinstance(value, (str, bytes))
            and all(isinstance(path, str) for path in value)
        )

    def validate_inputs(
        self,
        normalized_inputs: NormalizedRoutineInputs,
    ) -> None:
        """Validate that the required datasets are present in the ProcessedData.

        Raises:
            ValueError: If any required datasets are missing.
        """
        missing = []

        for role, data, paths in normalized_inputs:
            missing.extend(f'{role}: {path}' for path in paths if path not in data)

        if missing:
            msg = f'{self.name} is missing required datasets: , '.join(missing)
            _logger.error(msg)
            raise ValueError(msg)

    # ---- main entry point ----
    def apply(self, *pdata: ProcessedData):
        """Apply this routine to the input(s).

        Serves as the main entry point to the routine's execution. Handles, how
        the routine should be applied depending on the number of inputs and the
        routine's mapping behavior.
        """
        if not pdata:
            raise ValueError(f'{self.name} requires at least one ProcessedData object.')

        if self.map_over_inputs:
            return tuple(self._apply_once(pd) for pd in pdata)

        return self._apply_once(*pdata)

    def _apply_once(self, *pdata: ProcessedData):
        """Apply the routine to the given ProcessedData objects.

        This method handles the common workflow of validating inputs, running the
        computation, logging metadata, and recording checkpoints. The actual computation
        should be implemented in the run() method of the subclass.

        """
        _logger.debug(f'{self.name}: Validating inputs...')
        self.validate_input_count(len(pdata))  # Validate number of input datasets

        # Check that all datasets have the fields they should
        inputs = self.inputs(*pdata)
        normalized_inputs = self._normalize_resolved_inputs(pdata, inputs)
        self.validate_inputs(normalized_inputs)
        _logger.debug(f'{self.name}: Finished validating inputs.')

        # shapes_before = self._get_shapes(pdata, inputs)

        # Run actual computation
        _logger.info(f'{self.name}: Applying routine...')
        t0 = time.time()

        outputs = self.run(*pdata, inputs=inputs)

        runtime = time.time() - t0
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        _logger.info(f'{self.name}: Finished applying routine.')

        # shapes_after = self._get_shapes(pdata, outputs)

        # Log metadata in the data file(s)
        _logger.debug(f'{self.name}: Logging metadata...')
        meta = self._get_metadata(
            timestamp,
            inputs,
            outputs,
            # shapes_before,
            # shapes_after,
            runtime,
        )
        self._log_step(meta, *pdata)
        _logger.debug(f'{self.name}: Finished logging metadata.')
        if self.record_checkpoint:
            self._checkpoint(*pdata)

        return outputs

    # ---- to be implemented by subclasses ----
    def run(
        self, pdata: ProcessedData, inputs: NormalizedRoutineInputs,
    ) -> RoutineResult:
        """Run this data routine."""
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a run method'
        )

    def inputs(
        self, *pdata: ProcessedData
    ) -> RoutineInputs:
        """Return the names of datasets required for this routine.

        Default behavior is to return the `requires` class variable. Overwrite in
        subclass if different behavior is desired.

        Output must conform to formats described in `RoutineInputs`.
        """
        return self.requires

    # ---- helpers ----
    def _get_shapes(self, pdata, dataset_names):
        """Helper method to get the shapes of the input and output datasets."""
        shapes = {}
        for name in dataset_names:
            if name in pdata.file:
                shapes[name] = pdata[name].shape
        return shapes

    def _log_step(self, meta: str, *pdata: ProcessedData):
        """Append to the 'processing_history' group of the ProcessedData."""
        for pd in pdata:
            hist = pd.file.require_group('processing_history')

            step_idx = len(hist)
            step_name = get_step_group_name(step_idx, self.name)

            step_group = hist.create_group(step_name)

            for k, v in meta.items():
                if isinstance(v, dict | list):
                    step_group.attrs[k] = json.dumps(v, cls=PathJSONEncoder)
                else:
                    step_group.attrs[k] = v

    def _checkpoint(self, *pdata: ProcessedData):
        """Save a checkpoint of the current state of the ProcessedData."""
        for pd in pdata:
            chk_group = pd.file.require_group('checkpoints')
            name = get_step_group_name(len(chk_group), self.name)

            g = chk_group.create_group(name)

            # naive: copy all datasets (you can refine later)
            for key, item in pd.file.items():
                if isinstance(item, type(pd.file['/'])):  # dataset
                    pd.file.copy(item, g, name=key)

    def _get_metadata(
        self,
        timestamp: float,
        inputs: Sequence[str],
        outputs: Sequence[str],
        # shapes_before: Sequence[tuple],
        # shapes_after: Sequence[tuple],
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
            # 'shape_before': shapes_before,
            # 'shape_after': shapes_after,
            'code_version': get_git_hash(),
            'runtime_sec': runtime,
        }


def register_routine[DataRoutineType: 'DataRoutine'](
    cls: type[DataRoutineType],
) -> type[DataRoutineType]:
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

    def run(self, pdata: ProcessedData, inputs: NormalizedRoutineInputs):
        """Apply the cutoff filter to the specified datasets.

        Applies a Butterworth filter with the specified cutoff frequency and type to
        each of the input datasets.
        """
        filter_freq = self.params['filter_freq']
        btype = self.params['btype']
        dsets = inputs[0][2]
        for dset_name in dsets:
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
                dset = pdata[dset_name]
                dset[:] = signal.sosfiltfilt(filt_sos, dset)

        return RoutineResult(
            modified={'input': dsets}
        )


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
