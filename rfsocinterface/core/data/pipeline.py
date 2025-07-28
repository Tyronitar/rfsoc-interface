from __future__ import annotations

import logging
from datetime import datetime, timezone
from itertools import chain
import git
import json
import time

import rfsocinterface
from rfsocinterface.core.data.data import ProcessedData, MapData
from rfsocinterface.core.data.map import BinTODIntoMap
from rfsocinterface.core.data.routines import DataRoutine, Downsample, HighPassFilter, LowPassFilter, ProcessingStage, CleanTOD

_logger = logging.getLogger(__name__)


class RoutineApplier:
    def __init__(self, pipeline: DataPipeline):
        self.pipeline = pipeline
        self.routines = []

    @property
    def options(self):
        return self.pipeline.shared_values
    
    def __len__(self):
        return len(self.routines)

    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected an instance of `DataRoutine`, got `{type(routine)}`')
        self.routines.append(routine)

    def apply_routines(self, input: ProcessedData):
        for routine in self.routines:
            _logger.debug(f'Running routine: {routine.__class__.__name__}')
            routine(input)
            self.pipeline.add_to_receipt(routine.get_receipt_entry())


class DataPipeline:
    """A Pipeline of data routines from the raw data file to finished products.

    The general flow of the pipeline is as follows:
        1. Open the raw data file
        2. Run pre-processing routines
        3. Downsample data
        4. Run processing routines
        5. Run post-processing routines
        6. Run mapping routines

    Attributes:
        _receipt (list[str]): "Receipt" for tracking which functions were run and
            what version of the code the data is being processed with.
        pre_processor (RoutineApplier): Wrapper for routines to apply before processing 
            the data e.g. RemovePointLomaPickup.
        processor (RoutineApplier): Wrapper for routines that are applied in processing
            e.g. Downsample, RemoveElectronicsNoise, etc.
        post_processor (RoutineApplier): Wrapper for routines to apply after creating
            the processed data file, e.g. HighPassFilter, LowPassFilter, CleanTOD, etc.
        mapper (RoutineApplier): Wrapper for routines to apply curing map creation
            e.g. BinTODIntoMap, etc. 
        shared_values (dict): Values that are shared across routines, such as
            `ds_factor`, `hp_filter_freq`, and `lp_filter_freq`.
    """
    _receipt: list[str]

    def __init__(self, ds_factor: float=1, beam_map_mode: bool=False, **kwargs):
        self._receipt = []
        self.pre_processor = RoutineApplier(self)
        self.processor = RoutineApplier(self)
        self.post_processor = RoutineApplier(self)
        self.mapper = RoutineApplier(self)
        self.shared_values = kwargs
        self.shared_values['ds_factor'] = ds_factor
        self.shared_values['beam_map_mode'] = beam_map_mode

    def synchronize_values(self):
        """Update all routines to use shared values."""
        for routine in self.all_routines():
            match routine:
                case BinTODIntoMap():
                    if 'hp_filter_freq' in self.shared_values:
                        routine.hp_filter_freq = self.shared_values['hp_filter_freq']
                    if 'lp_filter_freq' in self.shared_values:
                        routine.lp_filter_freq = self.shared_values['lp_filter_freq']
                case Downsample():
                    if 'ds_factor' in self.shared_values:
                        routine.ds_factor = self.shared_values['ds_factor']
                case HighPassFilter():
                    if 'hp_filter_freq' in self.shared_values:
                        routine.filter_freq = self.shared_values['hp_filter_freq']
                case LowPassFilter():
                    if 'lp_filter_freq' in self.shared_values:
                        routine.filter_freq = self.shared_values['lp_filter_freq']
                case _:
                    pass

    def add_to_receipt(self, entry: str):
        self._receipt.append(entry)

    def generate_receipt(self) -> str:
        preamble = f'Rfsocinterface Version {rfsocinterface.__version__}\n' \
            f'Git Hash: {git.Repo(search_parent_directories=True).head.object.hexsha}\n' \
            f'Date and Time of Processing (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n' \
            f'Shared Values: {json.dumps(self.shared_values, indent=4)}\n' \
            f'Routines: ['
        entries = ',\n'.join(self._receipt)
        formatted_entries = '\t'.join(('\n' + entries.lstrip()).splitlines(True))
        return preamble + formatted_entries + '\n]'

    def all_routines(self) -> list[DataRoutine]:
        return list(chain(
            self.pre_processor.routines,
            self.processor.routines,
            self.post_processor.routines,
            self.mapper.routines
        ))

    def get_routines_by_type(self, *routine_type: type[DataRoutine]) -> list[DataRoutine]:
        """Get all routines of a specific type."""
        return [routine for routine in self.all_routines() if any(isinstance(routine, rt) for rt in routine_type)]

    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected an instance of `DataRoutine`, got `{type(routine)}`')
        match routine.stage:
            case ProcessingStage.PRE_PROCESSING:
                self.pre_processor.add_routine(routine)
            case ProcessingStage.PROCESSING:
                self.processor.add_routine(routine)
            case ProcessingStage.POST_PROCESSING:
                self.post_processor.add_routine(routine)
            case ProcessingStage.MAPPING:
                self.mapper.add_routine(routine)
            case _:
                pass

    def run_pipeline(self, date: str, setnum: int) -> ProcessedData | MapData:
        self.synchronize_values()
        _logger.info(f'Beginning data pipeline for {date}set{setnum}')
        start_time = time.time()
        # _logger.info('Runnig pre-processing routines...')
        # self.pre_processor.apply_routines(input)
        # TODO: Propogate effects from pre-processing to the processed file
        _logger.info('Running processing routines...')
        pd = ProcessedData.from_tod(
            date,
            setnum,
            beam_map_mode=self.shared_values['beam_map_mode'],
            ds_factor=self.shared_values['ds_factor'],
        )
        self.processor.apply_routines(pd)
        _logger.info('Running post-processing routines...')
        self.post_processor.apply_routines(pd)

        pd.add_receipt(self.generate_receipt())
        output = pd
        if len(self.mapper) > 0:
            _logger.info('Running mapping routines...')
            md = MapData.from_processed_data(pd)
            self.mapper.apply_routines(md)
            md.add_receipt(self.generate_receipt())
            output = md
        stop_time = time.time()
        _logger.info(f'Data pipeline completed in {stop_time - start_time:.3f} seconds.')
        return output


if __name__ == '__main__':
    import pdb
    date = '20250728'
    setnum = 1006
    dataset = 'data_mK'

    ds_factor = 10
    hp_filt_freq = 0.5
    lp_filt_freq = 10


    hpfilt = HighPassFilter(hp_filt_freq, dataset=dataset)
    lpfilt = LowPassFilter(lp_filt_freq, dataset=dataset)
    cleaner = CleanTOD(dataset=dataset)
    binner = BinTODIntoMap(dataset=dataset)

    pipeline = DataPipeline(ds_factor=ds_factor, hp_filter_freq=hp_filt_freq, lp_filter_freq=lp_filt_freq)
    pipeline.add_routine(hpfilt)
    pipeline.add_routine(lpfilt)
    pipeline.add_routine(cleaner)
    pipeline.add_routine(binner)

    data = pipeline.run_pipeline(date, setnum)
    data.plot()
    pdb.set_trace()
    data.close()