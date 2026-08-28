import logging
import logging.config

from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD, PsdBasis
from rfsocinterface.core.data import *
from rfsocinterface.core.params import RFSoCParameters
from rfsocinterface.analysis import *
import pdb
import matplotlib.pyplot as plt
import numpy as np


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 15
    hp_filter_freq = 0.2
    noise_removal_lp_filt_freq_offres = 244  # Filter disabled if set to 0
    noise_removal_lp_filt_freq_onres = 5  # Filter disabled if set to 0
    ds_factor = 5

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
    compute_psd = ComputeNoisePSD(
        # PsdBasis.GAIN_PHASE,
        PsdBasis.FREQ_DISS,
        cut_time=2,
        selection_indices='all',
    )
    psd_plotter = PlotPSD(
        # PsdBasis.GAIN_PHASE,
        PsdBasis.FREQ_DISS,
        show=True,
    )
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=False,
        dataset=dataset,
        az_trim=0,
        za_trim=0,
        dpix=0.04,
        r0=0,
    )
    plotter = PlotMap(show=True, max_abs_threshold=0.4, keep_figure_open=False, channel=None)
    bin_tod_to_video = BinTODIntoVideo(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        dataset=dataset,
        block_size_s=0.1,
        dpix=0.08,
        az_trim=0,
        za_trim=0,
        # overwrite=False,
        # show=True,
        # savefile='test.gif',
    )
    animate_video = AnimateVideo()

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
        # bin_tod_to_video,
        animate_video,
        # find_fwhm,
        # analyze_beammap,
        # plot_beammap,
    ])

    date = '20260828'
    setnum = 1002


    # pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)

    pdata = ProcessedData.load(date, setnum)
    pipeline.run(pdata)
    # pdb.set_trace()
    # params = RFSoCParameters.from_tile_name('Device_aSi2_Channel3_telescope_275mK_20260804')
    # det_dy = params.detector_delta_y[:]
    # i_res = 676
    # same_za = np.argwhere(np.abs(det_dy - det_dy[i_res]) < 0.05).flatten()
    # same_za = same_za[params.detector_pol[same_za] == params.detector_pol[i_res]]
    # same_za = same_za.tolist()
    # find_fwhm = CheckFocus(
    #     'az',
    #     resonators=same_za,
    #     dataset=dataset,
    # )
    # find_fwhm.apply(pdata)

