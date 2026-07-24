import logging
import logging.config

from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD, PsdBasis
from rfsocinterface.core.data import *
from rfsocinterface.analysis import *
import pdb
import matplotlib.pyplot as plt
import numpy as np


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 15
    hp_filter_freq = 0.03
    noise_removal_lp_filt_freq_offres = 244  # Filter disabled if set to 0
    noise_removal_lp_filt_freq_onres = 5  # Filter disabled if set to 0
    ds_factor = 16

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']

    find_fwhm = CheckFocus(
        'az',
        [20],
    )

    noise_removal_offres = RemoveElectronicsNoise(
        template_selection_indices='offres',
        lp_filt_freq=noise_removal_lp_filt_freq_offres,
    )
    noise_removal_onres = RemoveElectronicsNoise(
        template_selection_indices='onres',
        lp_filt_freq=noise_removal_lp_filt_freq_onres,
    )
    noise_removal = RemoveElectronicsNoise()
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, cut_time=2, selection_indices='all')
    psd_plotter = PlotPSD(
        PsdBasis.GAIN_PHASE,
        PsdBasis.FREQ_DISS,
        show=True,
    )
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=True,
        dataset=dataset,
        # az_trim=0,
        # za_trim=0,
        dpix=0.03,
    )
    plotter = PlotMap(show=True, max_abs_threshold=0.4, keep_figure_open=False)
    make_video = MakeVideo(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        block_size_s=0.1,
        dpix=0.08,
        az_trim=0,
        za_trim=0,
        # show=True,
        # savefile='test.gif',
    )

    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap()

    pipeline = Pipeline([
        # noise_removal_offres,
        # noise_removal_onres,
        # noise_removal,
        # compute_psd,
        # psd_plotter,
        # hp_filter,
        # lp_filter,
        # clean_tod,
        # bin_tod_to_map,
        # plotter,
        # make_video,
        # find_fwhm,
        # analyze_beammap,
        plot_beammap,
    ])

    # date = '20260319'
    # setnum = 1023
    # date = '20260309'
    # setnum = 1010
    date = '20260617'
    setnum = 1005
    # date = '20260325'
    # setnum = 1002
    # date = '20260223'
    # setnum = 1010  # 1009 - 1015


    # ConsolidatedData.from_tod(date, setnum, downsampling_factor=ds_factor)
    # pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)
    pdata = ProcessedData.load(date, setnum)
    pipeline.run(pdata)
