"""Data proccessing routines."""

from __future__ import annotations
import abc
import pdb
import logging

import numpy as np
import numpy.typing as npt
from scipy import signal
import tables
import time
import datetime
import json


from rfsocinterface.core.data.data import ConsolidatedData, ProcessedData, generate_calibrated_data, get_channel_group_name, get_step_group_name, rotate_basis
from rfsocinterface.core.data.data import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, GAUSSIAN_SIGMA, gaussian_filter, axis_index, get_git_hash

_logger = logging.getLogger(__name__)

class ProcessingStage:
    """Enum for the different stages of data processing."""
    PRE_PROCESSING = 'pre_processing'
    PROCESSING_L1 = 'processing_l1'
    PROCESSING_L2 = 'processing_l2'
    POST_PROCESSING = 'post_processing'


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


class LowPassFilter(CutoffFilter):

    name = 'LowPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: list[str]=['/vdsets/data_mK'],
    ):
        super().__init__(filter_freq, btype='lowpass', datasets=datasets)


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
        for i_chan in range(pdata.n_chan):
            selection_indices = decode_tone_indices(pdata, i_chan, template_selection_indices)

            fs = pdata.get_fs(i_chan)
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


class CleanTOD(DataRoutine):
    stage = ProcessingStage.PROCESSING_L2

    def __init__(self, dataset: str='data_mK'):
        super().__init__()
        self.dataset = dataset

    def forward(self, pd: ProcessedData):

        # TODO: Does this need to still support the "good_sample" stuff?
        #average template subtraction
        for i_chan in range(pd.n_channels):
            good_tones = np.argwhere(pd.chanmask[i_chan] == 1).flatten()
            if self.dataset == 'data_freq':
                data = pd.data_freq_diss
                array_slice = (i_chan, 0, good_tones, slice(None))
            else:
                # BUG: This breaks if data has shape (2, n_tones, n_samples)
                data = getattr(pd, self.dataset)
                if data.ndim == 4:
                    array_slice = (i_chan, slice(None), good_tones, slice(None))
                else:
                    array_slice = (i_chan, good_tones, slice(None))
            template = np.nansum(data[array_slice], axis=0)
            template = template - np.mean(template)
            template_corr = np.sum(np.multiply(data[array_slice],template), axis=1) / \
                            np.sum(np.multiply(template,template))
            data[array_slice] = data[array_slice] - np.outer(template_corr, template)

        # with tables.File(pd.cleaned_file_template, 'w') as cfile:
        #     cfile.create_array('/', 'chanmask', pd.chanmask[:])
        #     cfile.create_array('/', 'detector_pol', pd.detector_pol[:])
        #     cfile.create_array('/', 'timestamp', pd.timestamp[:])
        #     cfile.create_array('/', 'detector_az', pd.detector_az[:])
        #     cfile.create_array('/', 'detector_za', pd.detector_za[:])
        #     cfile.create_array('/', 'clean_data', data[:])

    def get_receipt_entry(self) -> str:
        return f'CleanTOD: {{\n\tdataset = {self.dataset},\n}}'

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
    # Lab Testing
    date = '20260212'
    setnum = 1003

    cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=8)
    pd = cd.create_processed_data()

    noise_removal = RemoveElectronicsNoise()
    noise_removal.apply(pd)
    # cutoff = CutoffFilter(10, 'low')
    # cutoff.apply(pd)
    pdb.set_trace()

