import pdb

import matplotlib.pyplot as plt
import numpy as np
import tables
from kidpy3 import RawDataFile
from scipy.signal import decimate
import matplotlib.patches as mpatches


from PySide6.QtWidgets import QApplication
from kidpy3 import RawDataFile

from rfsocinterface.core.data import ProcessedData
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.gui.sweep_diagnostics import DiagnosticsDialog
from rfsocinterface.core.utils import mHz_axis_formatter, BAD_RESONANCE_COLOR

import logging
import logging.config

from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD, PsdBasis
from rfsocinterface.core.data import *
from rfsocinterface.core.params import RFSoCParameters
from rfsocinterface.analysis import *
import pdb
import matplotlib.pyplot as plt
import numpy as np


def process_20260917_set1005():

    date = '20260917'
    setnum = 1005

    lp_filter_freq = 15
    hp_filter_freq = 0.03
    ds_factor = 16

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']

    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=True,
        dataset=dataset,
        az_trim=0,
        za_trim=0,
        dpix=0.03,
        r0=0.15,
    )
    plot_map = PlotMap(show=True, max_abs_threshold=0.4, keep_figure_open=False, channel=None)

    pipeline = Pipeline([
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_map,
        plot_map,
    ])

    pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)
    # pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)

    # pdb.set_trace()

def process_20260917_set1007():
    date = '20260917'
    setnum = 1005

    lp_filter_freq = 15
    hp_filter_freq = 0.03
    ds_factor = 16

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']

    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    bin_tod_to_video = BinTODIntoVideo(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        dataset=dataset,
        block_size_s=0.1,
        dpix=0.04,
        az_trim=0,
        za_trim=0,
        # overwrite=False,
        # show=True,
        # savefile='test.gif',
    )
    animate_video = AnimateVideo()

  
    pipeline = Pipeline([
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_video,
        animate_video,
    ])

    date = '20260917'
    setnum = 1007


    pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)
    # pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)

    # pdb.set_trace()

def fix_df_per_mK():
    new_params_paths = (
        '/data/params/params_tile_Device_aSi1_Channel2_telescope_275mK_20260804.h5'
        '/data/params/params_tile_Device_aSi2_Channel3_telescope_275mK_20260804.h5'
    )
    old_params_path = 'params_tile_Device_aSi1_Channel2_telescope_275mK_20260325_with_offres.h5 '


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    process_20260917_set1005()
    process_20260917_set1007()

