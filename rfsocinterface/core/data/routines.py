"""Data proccessing routines."""

from typing import Any, Callable
import abc

import numpy as np
from scipy import signal
import h5py
import tables

from rfsocinterface.core.data import MapData, ProcessedData, generate_calibrated_data, remove_electronics_noise
from rfsocinterface.core.data.map import BUTTER_ORDER, DECIMATE_ORDER
from rfsocinterface.core.utils import GAUSSIAN_SIGMA, gaussian_filter


class DataPipeline:
    """A Pipeline of data routines from the raw data file to finished products.

    The general flow of the pipeline is as follows:
        1. Open the raw data file
        2. Run pre-processing routines
        3. Downsample data
        4. Run processing routines
        5. Run post-processing routines

    Attributes:
        _receipt (list[str]): "Receipt" for tracking which functions were run and
            what version of the code the data is being processed with.
        pre_processor (RoutineApplier): Wrapper for routines to apply before downsampling 
            the data e.g. RemovePointLomaPickup.
        processor (RoutineApplier): Wrapper for routines that are applied in processing
            e.g. RemoveElectronicsNoise, CleanTOD, etc.
        post_processor (RoutineApplier): Wrapper for routines to apply after processing
            the data, like mapping, or computing the PSD.
    """
    _receipt: list[str]

    def __init__(self):
        self._receipt = []
        self.pre_processor = RoutineApplier(self)
        self.processor = RoutineApplier(self)
        self.post_processor = RoutineApplier(self)
    
    def add_to_receipt(self, entry: str):
        self._receipt.append(entry)
    
    def run_pipeline(self, input: ProcessedData):
        self.pre_processor.apply_routines(input)
        self.pre_processor.apply_routines(input)
        self.post_processor.apply_routines(input)
    
    def generate_receipt(self) -> str:
        return '\n'.join(self._receipt)


class DataRoutine:
    __metaclass__ = abc.ABCMeta

    def __call__(self, *input, **kwargs):
        output = self.forward(*input, **kwargs)

        return output
    
    def forward(self, *input, **kwargs) -> Any:
        raise NotImplementedError(
            f'DataRoutine [{type(self).__name__}] is missing a forward method'
        )
    
    def get_receipt_entry(self) -> str:
        raise NotImplementedError


class RoutineApplier:
    def __init__(self, pipeline: DataPipeline, routines: list[DataRoutine]=[]):
        self.pipeline= pipeline
        self._routines = routines

    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected DataRoutine, got {type(routine)}')
        self._routines.append(routine)

    def apply_routines(self, input: ProcessedData, save: bool=True):

        output = input
        for routine in self._routines:
            output = routine(output)
            # do something to the pipeline's receipt...
            self.pipeline.add_to_receipt(routine.get_receipt_entry())
        if save:
            output.save()
        return output


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
    def __init__(self, gaussian_sigma: tuple[float, float]=GAUSSIAN_SIGMA):
        super().__init__()
        self.gaussian_sigma = gaussian_sigma

    def forward(self, pd: ProcessedData, field: str='data_mK') -> ProcessedData:
        smoothed_data = gaussian_filter(pd.__getattribute__(field), self.gaussian_sigma)
        return pd.with_values(**{field: smoothed_data})


class CutoffFilter(DataRoutine):
    def __init__(self, filter_freq: float, btype: str):
        super().__init__()
        self.filter_freq = filter_freq
        self.btype = btype

    def forward(self, pd: ProcessedData) -> ProcessedData:
        filt_sos = signal.butter(BUTTER_ORDER, self.filter_freq, btype=self.btype, fs=pd.fs, output='sos', analog=False)

        # Apply cutoff filter
        data_gain_phase_filt = signal.sosfiltfilt(filt_sos, pd.data_gain_phase)
        data_freq_diss_filt = signal.sosfiltfilt(filt_sos, pd.data_freq_diss)
        data_mK_filt = signal.sosfiltfilt(filt_sos, pd.data_mK)
        return pd.with_values(
            data_gain_phase=data_gain_phase_filt,
            data_freq_diss=data_freq_diss_filt,
            data_mK=data_mK_filt,
        )


class LowPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='lowpass')


class HighPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='highpass')


class Downsample(DataRoutine):
    def __init__(self, ds_factor: float=6, order: int=DECIMATE_ORDER):
        super().__init__()
        self.ds_factor = ds_factor
        self.order=order

    def forward(self, pd: ProcessedData) -> ProcessedData:
        data_freq_diss_ds = signal.decimate(pd.data_freq_diss, self.ds_factor)
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


class RemoveElectronicsNoise(DataRoutine):
    def __init__(self):
        super().__init__()

    def forward(self, pd: ProcessedData) -> ProcessedData:
        gain_phase_data = pd.data_gain_phase
        clean_gain_phase_data = remove_electronics_noise(gain_phase_data)

        new_data_freq_diss, new_data_mK = generate_calibrated_data(
            clean_gain_phase_data,
            pd.IQ_to_gain_phase_angle,
            pd.dIQ_df,
            pd.df_per_mK
        )
        return pd.with_values(
            data_gain_phase=clean_gain_phase_data,
            data_freq_diss=new_data_freq_diss,
            data_mK=new_data_mK,
        )


class CleanTOD(DataRoutine):

    def __init__(
            self,
            save_file: bool=True,
    ):
        super().__init__()
        self.save_file = save_file

    def forward(self, md: MapData) -> MapData:

        if not isinstance(md, MapData):
            md = MapData.from_processed_data(md)
        data = md.data_mK
        chanmask = md.chanmask
        data_clean = np.copy(data)
        good_samples = md.get_good_samples()

        #average template subtraction
        goodchan = np.ndarray.flatten(np.argwhere(chanmask == 1))
        # pdb.set_trace()
        data_good = data[goodchan][:, good_samples]
        template = np.sum(data_good, axis=0)
        template = template - np.mean(template)
        template_corr = np.sum(np.multiply(data_good,template), axis=1) / \
                        np.sum(np.multiply(template,template))
        data_clean_good = data_good - np.outer(template_corr, template)
        data_clean[goodchan][:, good_samples] = data_clean_good

        if self.save_file:
            with h5py.File(md.cleaned_file_template, 'w') as cfile:
                cfile.create_dataset("chanmask", data=chanmask)
                cfile.create_dataset("detector_pol", data=md.detector_pol)
                cfile.create_dataset("clean_data", data=data_clean)
                cfile.create_dataset("time", data=md.timestamp)
                cfile.create_dataset("detector_az", data=md.detector_az)
                cfile.create_dataset("detector_za", data=md.detector_za)


        return md.with_values(
            data_mK=data_clean,
        )