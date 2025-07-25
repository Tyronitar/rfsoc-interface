"""Data proccessing routines."""

from __future__ import annotations
import abc
import pdb

import numpy as np
from scipy import signal
import tables

from rfsocinterface.core.data.data import ProcessedData, ProcessedData, generate_calibrated_data, remove_electronics_noise_tables
from rfsocinterface.core.data.data import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, GAUSSIAN_SIGMA, gaussian_filter

class ProcessingStage:
    """Enum for the different stages of data processing."""
    PRE_PROCESSING = 'pre_processing'
    PROCESSING = 'processing'
    POST_PROCESSING = 'post_processing'
    MAPPING = 'mapping'


class DataRoutine(abc.ABC):
    stage: ProcessingStage

    def __call__(self, input: ProcessedData):
        self.forward(input)

    def forward(self, input: ProcessedData):
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a forward method'
        )
    
    def get_receipt_entry(self) -> str:
        raise NotImplementedError


class Mapper:
    def __init__(self, routines: list[DataRoutine]=[]):
        self._routines = routines

    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected DataRoutine, got {type(routine)}')
        self._routines.append(routine)

    def __call__(self, input: ProcessedData, save: bool=True):

        output = input
        for routine in self._routines:
            # if isinstance(routine, BinTODIntoMap):
            #     pdb.set_trace()
            output = routine(output)
        if save:
            output.save()
        return output

#
# Begin Data Routine Catlog
#

class GaussianFilter(DataRoutine):
    stage = ProcessingStage.PROCESSING
    def __init__(self, gaussian_sigma: tuple[float, float]=GAUSSIAN_SIGMA):
        super().__init__()
        self.gaussian_sigma = gaussian_sigma

    def forward(self, pd: ProcessedData, field: str='data_mK'):
        array = pd._pfile.get_node('/', field)
        smoothed_data = gaussian_filter(array, self.gaussian_sigma)
        array[:] = smoothed_data
    
    def get_receipt_entry(self) -> str:
        return f'GaussianFilter: {{\n\tsigma = {self.gaussian_sigma}\n}}'


class CutoffFilter(DataRoutine):
    stage = ProcessingStage.POST_PROCESSING

    def __init__(self, filter_freq: float, btype: str):
        super().__init__()
        self.filter_freq = filter_freq
        self.btype = btype

    def forward(self, pd: ProcessedData):
        filt_sos = signal.butter(BUTTER_ORDER, self.filter_freq, btype=self.btype, fs=pd.fs, output='sos', analog=False)

        # Apply cutoff filter
        # pd.data_gain_phase[:] = signal.sosfiltfilt(filt_sos, pd.data_gain_phase)
        # pd.data_freq_diss[:] = signal.sosfiltfilt(filt_sos, pd.data_freq_diss)
        pd.data_mK[:] = signal.sosfiltfilt(filt_sos, pd.data_mK)


class LowPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='lowpass')

    def get_receipt_entry(self) -> str:
        return f'LowPassFilter: {{\n\tfreq= {self.filter_freq}\n}}'


class HighPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='highpass')

    def get_receipt_entry(self) -> str:
        return f'HighPassFilter: {{\n\tfreq= {self.filter_freq}\n}}'


class Downsample(DataRoutine):
    stage = ProcessingStage.PRE_PROCESSING

    def __init__(self, ds_factor: float=6, order: int=DECIMATE_ORDER):
        super().__init__()
        self.ds_factor = ds_factor
        self.order=order

    def forward(self, pd: ProcessedData):
        # TODO: Should this routine even still exist?
        # Downsampling after the fact is annoying with PyTables

        data_freq_diss_ds = signal.decimate(pd.data_freq_diss, self.ds_factor)
        pd._pfile.remove_node('/', 'data_freq_diss')
        pd._pfile.create_array('/detector_0/data/', 'data_freq_diss', data_freq_diss_ds)
        data_gain_phase_ds = signal.decimate(pd.data_gain_phase, self.ds_factor)
        data_mK_ds = signal.decimate(pd.data_mK, self.ds_factor)
        timestamp_ds = signal.decimate(pd.timestamp, self.ds_factor)
        if np.size(pd.detector_az) > 1:
            detector_az_ds = signal.decimate(pd.detector_az, self.ds_factor, n=self.order, axis=1)
            detector_za_ds = signal.decimate(pd.detector_za, self.ds_factor, n=self.order, axis=1)
        else:
            detector_az_ds = pd.detector_az
            detector_za_ds = pd.detector_za
        return pd.with_values(
            data_freq_diss=data_freq_diss_ds,
            data_gain_phase=data_gain_phase_ds,
            data_mK=data_mK_ds,
            timestamp=timestamp_ds,
            detector_az=detector_az_ds,
            detector_za=detector_za_ds,
        )

    def get_receipt_entry(self) -> str:
        return f'Downsample: {{\n\tds_factor = {self.ds_factor}\n\torder = {self.order}\n}}'


class RemoveElectronicsNoise(DataRoutine):
    stage = ProcessingStage.PROCESSING

    def __init__(self):
        super().__init__()

    def forward(self, pd: ProcessedData):
        remove_electronics_noise_tables(pd.data_gain_phase)
        generate_calibrated_data(pd.root.detector_0.data, pd._pfile.root.detector_0.global_data)

    def get_receipt_entry(self) -> str:
        return f'RemoveElectronicsNoise: {{\n}}'


class CleanTOD(DataRoutine):
    stage = ProcessingStage.POST_PROCESSING

    def __init__(self):
        super().__init__()

    def forward(self, pd: ProcessedData):

        # TODO: Does this need to still support the "good_sample" stuff?
        #average template subtraction
        goodchan = np.ndarray.flatten(np.argwhere(pd.chanmask[:] == 1))
        template = np.sum(pd.data_mK[goodchan, :], axis=0)
        template = template - np.mean(template)
        template_corr = np.sum(np.multiply(pd.data_mK[goodchan, :],template), axis=1) / \
                        np.sum(np.multiply(template,template))
        pd.data_mK[goodchan, :] = pd.data_mK[goodchan, :] - np.outer(template_corr, template)

        with tables.File(pd.cleaned_file_template, 'w') as cfile:
            cfile.create_array('/', 'chanmask', pd.chanmask[:])
            cfile.create_array('/', 'detector_pol', pd.detector_pol[:])
            cfile.create_array('/', 'timestamp', pd.timestamp[:])
            cfile.create_array('/', 'detector_az', pd.detector_az[:])
            cfile.create_array('/', 'detector_za', pd.detector_za[:])
            cfile.create_array('/', 'clean_data', pd.data_mK[:])

    def get_receipt_entry(self) -> str:
        return f'CleanTOD: {{\n}}'

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


