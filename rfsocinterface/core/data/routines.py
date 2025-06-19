"""Data proccessing routines."""

from typing import Any, Callable
import abc
import pdb

import numpy as np
from scipy import signal
import h5py
import tables

from rfsocinterface.core.data.data import PyTablesProcessedData, PyTablesMapData, ProcessedData, generate_calibrated_data2, remove_electronics_noise2
from rfsocinterface.core.data.data import DECIMATE_ORDER
from rfsocinterface.core.utils import BUTTER_ORDER, GAUSSIAN_SIGMA, gaussian_filter


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
    
    def run_pipeline(self, input: PyTablesProcessedData):
        self.pre_processor.apply_routines(input)
        self.processor.apply_routines(input)
        self.post_processor.apply_routines(input)
    
    def generate_receipt(self) -> str:
        return '\n'.join(self._receipt)


class DataRoutine:
    __metaclass__ = abc.ABCMeta

    def __call__(self, input: PyTablesProcessedData):
        self.forward(input)

    def forward(self, input: PyTablesProcessedData):
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

    def apply_routines(self, input: PyTablesProcessedData, save: bool=True):

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

    def forward(self, pd: PyTablesProcessedData, field: str='data_mK'):
        array = pd._pfile.get_node('/', field)
        smoothed_data = gaussian_filter(array, self.gaussian_sigma)
        array[:] = smoothed_data

class CutoffFilter(DataRoutine):
    def __init__(self, filter_freq: float, btype: str):
        super().__init__()
        self.filter_freq = filter_freq
        self.btype = btype

    def forward(self, pd: PyTablesProcessedData):
        filt_sos = signal.butter(BUTTER_ORDER, self.filter_freq, btype=self.btype, fs=pd.fs, output='sos', analog=False)

        # Apply cutoff filter
        # pd.data_gain_phase[:] = signal.sosfiltfilt(filt_sos, pd.data_gain_phase)
        # pd.data_freq_diss[:] = signal.sosfiltfilt(filt_sos, pd.data_freq_diss)
        pd.data_mK[:] = signal.sosfiltfilt(filt_sos, pd.data_mK)


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

    def forward(self, pd: PyTablesProcessedData):
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


class RemoveElectronicsNoise(DataRoutine):
    def __init__(self):
        super().__init__()

    def forward(self, pd: PyTablesProcessedData):
        remove_electronics_noise2(pd.data_gain_phase)
        generate_calibrated_data2(pd.root.detector_0.data, pd._pfile.root.detector_0.global_data)


class CleanTOD(DataRoutine):

    def __init__(
            self,
            save_file: bool=True,
    ):
        super().__init__()
        self.save_file = save_file

    def forward(self, pd: PyTablesProcessedData):

        # TODO: Does this need to still support the "good_sample" stuff?
        #average template subtraction
        pdb.set_trace()
        goodchan = np.ndarray.flatten(np.argwhere(pd.chanmask[:] == 1))
        template = np.sum(pd.data_mK[goodchan, :], axis=0)
        template = template - np.mean(template)
        template_corr = np.sum(np.multiply(pd.data_mK[goodchan, :],template), axis=1) / \
                        np.sum(np.multiply(template,template))
        pd.data_mK[goodchan, :] = pd.data_mK[goodchan, :] - np.outer(template_corr, template)

        if self.save_file:
            with tables.File(pd.cleaned_file_template, 'w') as cfile:
                cfile.create_array('/', 'chanmask', pd.chanmask[:])
                cfile.create_array('/', 'detector_pol', pd.detector_pol[:])
                cfile.create_array('/', 'timestamp', pd.timestamp[:])
                cfile.create_array('/', 'detector_az', pd.detector_az[:])
                cfile.create_array('/', 'detector_za', pd.detector_za[:])
                cfile.create_array('/', 'clean_data', pd.data_mK[:])


if __name__ == '__main__':
    date = '20250527'
    setnum = 1010
    # date = '20250529'
    # setnum = 1011

    pd = PyTablesProcessedData.from_tod(date, setnum)
    md = PyTablesMapData.from_processed_data(pd)
    md.setup_mfile(50, 50)

    cleaner = CleanTOD()
    cleaner(pd)
    pdb.set_trace()