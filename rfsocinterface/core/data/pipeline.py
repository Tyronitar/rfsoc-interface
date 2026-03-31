from __future__ import annotations

import logging
from datetime import datetime, timezone
from itertools import chain
import git
import json
import time

import matplotlib.pyplot as plt

import rfsocinterface
from rfsocinterface.core.data.data import ProcessedData, ConsolidatedData
# from rfsocinterface.core.data.map import BinTODIntoMap
from rfsocinterface.core.data.routines import DataRoutine, ROUTINE_REGISTRY

_logger = logging.getLogger(__name__)

class Pipeline:

    def __init__(self, routines: list[DataRoutine]=[]):
        self.routines = routines
    
    def from_tod(self, date: str, setnum: int, downsampling_factor: int=1) -> ProcessedData:
        _logger.info(f'Running pipeline on TOD {date}_set{setnum}')
        cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=downsampling_factor)
        pd = cd.create_processed_data()
        self.run(pd)
        return pd
    
    def add_routine(self, name: str, **params):
        routine_cls = ROUTINE_REGISTRY[name]
        routine = routine_cls(**params)
        self.routines.append(routine)
        _logger.debug(f'Added routine {name} with params {params} to pipeline.')
    
    def load_config(self, config: dict):
        """Loads a pipeline configuration from a dictionary.
        
        The dictionary should have the following format:
        {
            "routine_name_1": {
                "param1": value1,
                "param2": value2,
                ...
            },
            "routine_name_2": {
                "param1": value1,
                "param2": value2,
                ...
            },
            ...
        }
        """
        for name, params in config.items():
            self.add_routine(name, **params)

    def run(self, pdata: ProcessedData):
        for routine in self.routines:
            routine.apply(pdata)


def find_peaks(data: ProcessedData, primary_direction: str='az'):
    import numpy as np
    from numpy.polynomial import Polynomial
    # find peak going forward / back
    # fit gaussian
    # take position of both peask
    # right is 10-15
    # left is 20-25
    i_res = 241
    right_indices = np.argwhere(np.logical_and(10 <= data.time, data.time <= 15)).flatten()
    left_indices = np.argwhere(np.logical_and(20 <= data.time, data.time <= 25)).flatten()
    telescope_pos = data.detector_az[i_res] if primary_direction.lower() == 'az' else data.detector_za[i_res]

    right_peak_idx = right_indices[np.argmax(data.data_mK[i_res, right_indices])]
    left_peak_idx = left_indices[np.argmax(data.data_mK[i_res, left_indices])]

    right_slice = slice(right_peak_idx - 2, right_peak_idx + 3)
    left_slice = slice(left_peak_idx - 2, left_peak_idx + 3)

    right_fit = Polynomial.fit(telescope_pos[right_slice], data.data_mK[i_res, right_slice], 2).convert()
    left_fit = Polynomial.fit(telescope_pos[left_slice], data.data_mK[i_res, left_slice], 2).convert()

    right_az_0 = (-1 * right_fit.coef[1]) / (2 * right_fit.coef[2])
    left_az_0 = (-1 * left_fit.coef[1]) / (2 * left_fit.coef[2])
    plt.plot(telescope_pos[:], data.data_mK[i_res, :], label=f'Full Trace')
    plt.plot(telescope_pos[right_slice], data.data_mK[i_res, right_slice], label=f'Right {primary_direction.upper()}_0 = {right_az_0}')
    plt.plot(telescope_pos[left_slice], data.data_mK[i_res, left_slice], label=f'Left {primary_direction.upper()}_0 = {left_az_0}')
    scan_rate = (telescope_pos[right_peak_idx + 10] - telescope_pos[right_peak_idx - 10]) \
        / (data.time[right_peak_idx + 10] - data.time[right_peak_idx - 10])
    time_delay = (left_az_0 - right_az_0) / scan_rate / 2  # Amount RFSoC is behind the telescope
    plt.annotate(f'Time Delay (seconds RFSoC lags behind telescope)= {time_delay:.3f}s', (.1, .1), xycoords='axes fraction')
    plt.legend()
    plt.show()


if __name__ == '__main__':
    from rfsocinterface.core.data.routines import *
    import pdb
    date = '20260309'
    setnum = 1010

    lp_filter_freq = 15
    hp_filter_freq= 0.25
    ds_factor = 8

    noise_removal = RemoveElectronicsNoise(max_modes=2)
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq)
    clean_tod = CleanTOD()
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        # az_trim=0,
        # za_trim=0,
        # dpix=0.03,
    )
    plotter = PlotMap(show=True)

    pipeline = Pipeline([
        noise_removal,
        lp_filter,
        hp_filter,
        clean_tod,
        bin_tod_to_map,
        plotter,
    ])
    # pdata = pipeline.from_tod(date, setnum, ds_factor)
    pdata = ProcessedData.load(date, setnum)
    pipeline.run(pdata)
    pdb.set_trace()
