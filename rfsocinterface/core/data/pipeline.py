from __future__ import annotations

import logging
from datetime import datetime, timezone
from itertools import chain
import git
import json
import time

import rfsocinterface
from rfsocinterface.core.data.data import ProcessedData, ProcessedDataL1, ProcessedDataLN, MapData, ProcessedDataL0
from rfsocinterface.core.data.map import BinTODIntoMap
from rfsocinterface.core.data.routines import ProcessingStage, DataRoutine, Downsample, HighPassFilter, LowPassFilter, CleanTOD, ComputeNoisePSD, PsdBasis

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
        1. Coallesce raw data files into L0 file
        2. Run L0 data routines
        3. Downsample data and cretae L1 file
        4. Run L1 data routines
        5. Run L2 data routines
        6. Run mapping routines

    Attributes:
        _receipt (list[str]): "Receipt" for tracking which functions were run and
            what version of the code the data is being processed with.
        l0_applier (RoutineApplier): Wrapper for routines to apply before processing 
            the data e.g. RemovePointLomaPickup.
        l1_applier (RoutineApplier): Wrapper for routines that are applied in processing
            e.g. Downsample, RemoveElectronicsNoise, etc.
        l2_applier (RoutineApplier): Wrapper for routines to apply after creating
            the processed data file, e.g. HighPassFilter, LowPassFilter, CleanTOD, etc.
        mapping_applier (RoutineApplier): Wrapper for routines to apply during map creation
            e.g. BinTODIntoMap, etc. 
        shared_values (dict): Values that are shared across routines, such as
            `ds_factor`, `hp_filter_freq`, and `lp_filter_freq`.
    """
    _receipt: list[str]

    def __init__(self, ds_factor: float=1, beam_map_mode: bool=False, **kwargs):
        self._receipt = []
        self.l0_applier = RoutineApplier(self)
        self.l1_applier = RoutineApplier(self)
        self.l2_applier = RoutineApplier(self)
        self.mapping_applier = RoutineApplier(self)
        self.shared_values = kwargs
        self.shared_values['ds_factor'] = ds_factor
        self.shared_values['beam_map_mode'] = beam_map_mode

    def synchronize_values(self):
        """Update all routines to use shared values."""
        for routine in self.all_routines():
            match routine:
                case BinTODIntoMap():
                    routine.beam_map_mode = self.shared_values['beam_map_mode']
                    if routine.beam_map_mode:
                        routine.az_trim = 0
                        routine.za_trim = 0
                    if 'hp_filter_freq' in self.shared_values:
                        routine.hp_filter_freq = self.shared_values['hp_filter_freq']
                    if 'lp_filter_freq' in self.shared_values:
                        routine.lp_filter_freq = self.shared_values['lp_filter_freq']
                    if 'dataset' in self.shared_values:
                        routine.dataset = self.shared_values['dataset']
                case Downsample():
                    if 'ds_factor' in self.shared_values:
                        routine.ds_factor = self.shared_values['ds_factor']
                case HighPassFilter():
                    if 'hp_filter_freq' in self.shared_values:
                        routine.filter_freq = self.shared_values['hp_filter_freq']
                    if 'dataset' in self.shared_values:
                        routine.dataset = self.shared_values['dataset']
                case LowPassFilter():
                    if 'lp_filter_freq' in self.shared_values:
                        routine.filter_freq = self.shared_values['lp_filter_freq']
                    if 'dataset' in self.shared_values:
                        routine.dataset = self.shared_values['dataset']
                case CleanTOD():
                    if 'dataset' in self.shared_values:
                        routine.dataset = self.shared_values['dataset']
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
            self.l0_applier.routines,
            self.l1_applier.routines,
            self.l2_applier.routines,
            self.mapping_applier.routines
        ))

    def get_routines_by_type(self, *routine_type: type[DataRoutine]) -> list[DataRoutine]:
        """Get all routines of a specific type."""
        return [routine for routine in self.all_routines() if any(isinstance(routine, rt) for rt in routine_type)]

    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected an instance of `DataRoutine`, got `{type(routine)}`')
        match routine.stage:
            case ProcessingStage.PRE_PROCESSING:
                self.l0_applier.add_routine(routine)
            case ProcessingStage.PROCESSING_L1:
                self.l1_applier.add_routine(routine)
            case ProcessingStage.PROCESSING_L2:
                self.l2_applier.add_routine(routine)
            case ProcessingStage.POST_PROCESSING:
                self.mapping_applier.add_routine(routine)
            case _:
                pass

    def run_pipeline(self, date: str, setnum: int) -> ProcessedData:
        self.synchronize_values()
        _logger.info(f'Beginning data pipeline for {date}set{setnum}')
        start_time = time.time()
        # TODO: Propogate effects from pre-processing to the processed file
        _logger.info('Creating level 0 prcoessed data...')
        pd = ProcessedDataL0.from_tod(
            date,
            setnum,
            beam_map_mode=self.shared_values['beam_map_mode']
        )
        _logger.info('Creating level 1 processed data...')
        pd1 = ProcessedDataL1.from_level0(
            pd,
            ds_factor=self.shared_values['ds_factor'],
            do_electronics_noise_removal=self.shared_values.get('do_electronics_noise_removal', True),
            max_modes=self.shared_values.get('max_modes', 30),
        )
        self.l1_applier.apply_routines(pd1)
        pd1.add_receipt(self.generate_receipt())

        _logger.info('Creating level 2 processed data...')
        pd2 = ProcessedDataLN.from_previous_level(pd1)
        self.l2_applier.apply_routines(pd2)

        pd2.add_receipt(self.generate_receipt())
        output = pd2
        if len(self.mapping_applier) > 0:
            _logger.info('Running mapping routines...')
            md = MapData.from_processed_data(pd2)
            self.mapping_applier.apply_routines(md)
            md.add_receipt(self.generate_receipt())
            output = md
        stop_time = time.time()
        _logger.info(f'Data pipeline completed in {stop_time - start_time:.3f} seconds.')
        return output


if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    # Lab Testing
    # date = '20250916'
    # setnum = 1017

    #Telescope Testing
    date = '20251211'
    setnum = 1002

    dataset = 'data_freq'
    beam_map_mode = False 
    do_electronics_noise_removal = True

    ds_factor = 12
    hp_filt_freq = 0.05
    lp_filt_freq = 10

    hpfilt = HighPassFilter(hp_filt_freq)
    lpfilt = LowPassFilter(lp_filt_freq)
    cleaner = CleanTOD()
    binner = BinTODIntoMap()
    psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS)

    pipeline = DataPipeline(
        ds_factor=ds_factor,
        hp_filter_freq=hp_filt_freq,
        lp_filter_freq=lp_filt_freq,
        dataset=dataset,
        beam_map_mode=beam_map_mode,
        do_electronics_noise_removal=do_electronics_noise_removal,
        max_modes=2,
    )
    #pipeline.add_routine(hpfilt)
    #pipeline.add_routine(lpfilt)
    pipeline.add_routine(psd)
    #pipeline.add_routine(cleaner)
    #pipeline.add_routine(binner)

    data = pipeline.run_pipeline(date, setnum)
#     from rfsocinterface.analysis.psd import plot_psd
#     freq = data.get_node_value('freq')[:]
#     psd = data.get_node_value('psd_gain_phase')[:]
#     plot_psd(freq, psd, 'test.pdf', basis='gp')
#     plt.show()
    pdb.set_trace()
    data.close()