"""Data proccessing routines."""

from typing import Any, Callable
import abc

from rfsocinterface.core.data import ProcessedData


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