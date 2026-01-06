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

def find_peaks(data: ProcessedData, i_res: int, samples: slice, primary_direction: str='az'):
    import numpy as np
    from numpy.polynomial import Polynomial
    # find peak going forward / back
    # fit gaussian
    # take position of both peask
    # right is 10-15
    # left is 20-25
    # right_indices = np.argwhere(np.logical_and(10 <= data.time, data.time <= 15)).flatten()
    # left_indices = np.argwhere(np.logical_and(20 <= data.time, data.time <= 25)).flatten()
    telescope_pos = data.detector_az[i_res] if primary_direction.lower() == 'az' else data.detector_za[i_res]
    telescope_pos = telescope_pos[samples]

    diff = telescope_pos - np.roll(telescope_pos, 1)
    turn_point = np.argmax(np.where(diff > 0)[0])
    left_indices = np.arange(0, turn_point)
    left_slice = slice(0, turn_point)
    right_indices = np.arange(turn_point, len(telescope_pos))
    right_slice = slice(turn_point, len(telescope_pos))
    # plt.axvline(turn_point, color='r')
    # plt.show()
    # pdb.set_trace()

    data_segment = data.data_mK[i_res, samples]
    right_peak_idx = right_indices[np.argmax(data_segment[right_indices])]
    left_peak_idx = left_indices[np.argmax(data_segment[left_indices])]
    # plt.plot(telescope_pos)

    right_slice = slice(right_peak_idx - 5, right_peak_idx + 6)
    left_slice = slice(left_peak_idx - 5, left_peak_idx + 6)

    right_fit = Polynomial.fit(telescope_pos[right_slice], data_segment[right_slice], 2).convert()
    left_fit = Polynomial.fit(telescope_pos[left_slice], data_segment[left_slice], 2).convert()

    right_az_0 = (-1 * right_fit.coef[1]) / (2 * right_fit.coef[2])
    left_az_0 = (-1 * left_fit.coef[1]) / (2 * left_fit.coef[2])
    fig = plt.figure()
    plt.title(f'Detector {i_res} Peak Finding')
    plt.plot(telescope_pos[:], data_segment, label=f'Full Trace')
    plt.plot(telescope_pos[right_slice], data_segment[right_slice], label=f'Right {primary_direction.upper()}_0 = {right_az_0:.3f}')
    plt.plot(telescope_pos[left_slice], data_segment[left_slice], label=f'Left {primary_direction.upper()}_0 = {left_az_0:.3f}')
    scan_rate = (telescope_pos[right_peak_idx + 10] - telescope_pos[right_peak_idx - 10]) \
        / (data.time[right_peak_idx + 10] - data.time[right_peak_idx - 10])
    time_delay = (left_az_0 - right_az_0) / scan_rate / 2  # Amount RFSoC is behind the telescope
    plt.plot([], [], label=f'Time Delay (seconds RFSoC lags behind telescope)= {time_delay:.3f}s')
    plt.legend(loc="lower center", bbox_transform=fig.transFigure, bbox_to_anchor=(0.5, 0.0), ncol=2)
    plt.xlim(telescope_pos[right_peak_idx - 50], telescope_pos[right_peak_idx + 50])
    plt.tight_layout(rect=[0, 0.15, 1, 1])
    plt.xlabel(f'{"Azimuth" if primary_direction.lower() == "az" else "Zenith Angle"} (degrees)')
    plt.ylabel('Detector Response (mK)')
    return fig, time_delay


if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    from kidpy3 import RawDataFile
    import numpy as np


    date = '20251212'
    setnum = 1003

    raw = RawDataFile('/data/20251212/20251212_Device_aSi1_Channel2_telescope_275mK_TOD_set1003.h5', 'r')
    i_res = 263
    dy = raw.detector_delta_y[i_res]
    same_dy = np.where(np.isclose(raw.detector_delta_y[:], dy, atol=0.05))[0]

    l0 = ProcessedDataL0.from_file(date, setnum)
    packet_indices = l0.get_node_value('packet_index')[:]
    packet_indices = np.arange(np.min(packet_indices), np.max(packet_indices)+1)

    # plt.plot(raw.fh['time_ordered_data/pkt_idx'][:], raw.timestamp[:])
    # plt.plot(packet_indices, l0.timestamp[:])
    # plt.show()

    data = ProcessedDataLN.from_file(date, setnum, level=2)
    max_sample = np.argmax(data.data_mK[i_res])
    # plt.figure()
    # plt.plot(data.timestamp[:], data.data_mK[i_res])
    # plt.axvline(data.timestamp[max_sample], color='r')

    slice_around_max = slice(max_sample-400, max_sample+1500)
    # plt.figure()
    # plt.plot(data.timestamp[slice_around_max], data.detector_az[i_res, slice_around_max])
    # plt.axvline(data.timestamp[max_sample], color='r')
    # plt.show()
    # pdb.set_trace()

    same_dy = same_dy[data.chanmask[same_dy] == 1]
    # same_dy = np.setdiff1d(same_dy, [389, 390, 617, 618])
    delays = np.zeros(len(same_dy))
    with PdfPages('timing_offsets.pdf') as pdf:
        for i, i_res in enumerate(same_dy):
            print(i_res)
            fig, delay = find_peaks(data, i_res, slice_around_max)
            delays[i] = delay
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)
    pdb.set_trace()
    exit()



    # Lab Testing
    # date = '20250916'
    # setnum = 1017

    #Telescope Testing
    date = '20251212'
    setnums = [1009, 1010]
    # setnums = [1006]

    dataset = 'data_mK'
    beam_map_mode = False
    do_electronics_noise_removal = True
    primary_direction = 'az'

    ds_factor = 8
    hp_filt_freq = 0.25
    lp_filt_freq = 30

    hpfilt = HighPassFilter(hp_filt_freq)
    lpfilt = LowPassFilter(lp_filt_freq)
    cleaner = CleanTOD()
    binner = BinTODIntoMap()
    # psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS)

    pipeline = DataPipeline(
        ds_factor=ds_factor,
        hp_filter_freq=hp_filt_freq,
        lp_filter_freq=lp_filt_freq,
        dataset=dataset,
        beam_map_mode=beam_map_mode,
        do_electronics_noise_removal=do_electronics_noise_removal,
        max_modes=2,
    )
    pipeline.add_routine(hpfilt)
    pipeline.add_routine(lpfilt)
    # pipeline.add_routine(psd)
    pipeline.add_routine(cleaner)
    pipeline.add_routine(binner)

    for setnum in setnums:
        data = pipeline.run_pipeline(date, setnum)
        data.plot(show=False)
        data.close()
    plt.show()
#     from rfsocinterface.analysis.psd import plot_psd
#     freq = data.get_node_value('freq')[:]
#     psd = data.get_node_value('psd_gain_phase')[:]
#     plot_psd(freq, psd, 'test.pdf', basis='gp')
#     plt.show()
    # find_peaks(data, primary_direction=primary_direction)