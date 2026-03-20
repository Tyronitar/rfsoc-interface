"""Data proccessing routines."""

from __future__ import annotations
import abc
import pdb

import numpy as np
from scipy import signal
import tables
import time
import datetime
import json

from rfsocinterface.core.data.data import ConsolidatedData, ProcessedData, generate_calibrated_data, remove_electronics_noise_tables, get_channel_group_name, get_step_group_name
from rfsocinterface.core.data.data import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, GAUSSIAN_SIGMA, gaussian_filter, axis_index, get_git_hash

class ProcessingStage:
    """Enum for the different stages of data processing."""
    PRE_PROCESSING = 'pre_processing'
    PROCESSING_L1 = 'processing_l1'
    PROCESSING_L2 = 'processing_l2'
    POST_PROCESSING = 'post_processing'


class DataRoutine:
    name = "base"
    version = "0.0.0"
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

        meta = {
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

#
# Begin Data Routine Catlog
#

class GaussianFilter(DataRoutine):
    stage = ProcessingStage.PROCESSING_L1
    def __init__(self, gaussian_sigma: tuple[float, float]=GAUSSIAN_SIGMA):
        super().__init__()
        self.gaussian_sigma = gaussian_sigma

    def forward(self, pd: ProcessedData, field: str='data_mK'):
        array = getattr(pd, field)
        smoothed_data = gaussian_filter(array, self.gaussian_sigma)
        array[:] = smoothed_data
    
    def get_receipt_entry(self) -> str:
        return f'GaussianFilter: {{\n\tsigma = {self.gaussian_sigma}\n}}'

class CutoffFilter(DataRoutine):
    name = "CutoffFilter"
    version = "1.0"

    def __init__(self,
        filter_freq: float,
        btype: str,
        datasets: list[str]=['time_ordered_data/data_mK'],
    ):
        super().__init__(
            filter_freq=filter_freq,
            btype=btype,
            datasets=datasets,
        )
    
    def inputs(self, pdata: ProcessedData):
        l = []
        datasets = self.params['datasets']
        for i_chan in range(pdata.n_chan):
            for dset in datasets:
                l.append(f'/channels/{get_channel_group_name(i_chan)}/{dset}')
        return l

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        filter_freq = self.params['filter_freq']
        btype = self.params['btype']
        for input_name in inputs:
            # NOTE: If the group naming convention changes this will need to be updated
            i_chan = int(input_name.split('/')[2][-3:])  
            filt_sos = signal.butter(
                BUTTER_ORDER,
                filter_freq,
                btype=btype,
                fs=pdata.get_fs(i_chan),
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
        datasets: list[str]=['time_ordered_data/data_mK'],
    ):
        super().__init__(filter_freq, btype='lowpass', datasets=datasets)


class HighPassFilter(CutoffFilter):

    name = 'HighPassFilter'

    def __init__(
        self,
        filter_freq: float,
        datasets: list[str]=['time_ordered_data/data_mK'],
    ):
        super().__init__(filter_freq, btype='highpass', datasets=datasets)

class RemoveElectronicsNoise(DataRoutine):
    stage = ProcessingStage.PROCESSING_L1

    def __init__(self):
        super().__init__()

    def forward(self, pd: ProcessedData):
        remove_electronics_noise_tables(pd.data_gain_phase)
        generate_calibrated_data(pd.data_group, pd.global_data_group)

    def get_receipt_entry(self) -> str:
        return f'RemoveElectronicsNoise: {{\n}}'


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

    cutoff = CutoffFilter(10, 'low')
    cutoff.apply(pd)
    pdb.set_trace()