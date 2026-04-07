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


if __name__ == '__main__':
    import matplotlib as mpl
    mpl.use('TkAgg')
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
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_map,
        plotter,
    ])
    pdata = pipeline.from_tod(date, setnum, ds_factor)
    # pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)
    pdb.set_trace()
