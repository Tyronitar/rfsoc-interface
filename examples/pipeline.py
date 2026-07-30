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
    noise_removal_lp_filt_freq = 0  # Filter disabled if set to 0
    ds_factor = 16

    # dataset = 'data_mK'
    # datasets = ['/vdsets/data_mK']

    dataset = 'data_freq'
    datasets = ['/vdsets/data_freq_diss']

    #find_fwhm = FindFWHM(
    #    'az',
    #    [241],
    #)

    noise_removal_offres = RemoveElectronicsNoise(
        template_selection_indices='offres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    noise_removal_onres = RemoveElectronicsNoise(
        template_selection_indices='onres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    noise_removal = RemoveElectronicsNoise()
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, cut_time=2, selection_indices='onres')
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
        # dpix=0.04,
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
        analyze_beammap,
        # plot_beammap,
    ])

    date = '20260617'
    setnum = 1005

    # pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)

    pdata = ProcessedData.load(date, setnum, mode='a')
    pipeline.run(pdata)

    pdb.set_trace()
    # map_val = pdata['map/map_val'][:]
    # map_az = pdata['map/map_az'][:]
    # map_za = pdata['map/map_za'][:]
    # extent = get_extent(map_az, map_za, dpix=pdata['map'].attrs['dpix'])
    # for i, i_res in enumerate(pdata.onres_ind):
    #     # if i_res < 500:
    #     #     continue
    #     plot_map(map_val[i_res], map_az, map_za, extent, cb_label='Signal (Hz)', title=f'Resonator {i_res}')
    #     if i > 0 and i % 15 == 0:
    #         plt.show()
    #         pdb.set_trace()
    # pdb.set_trace()

    # pdata = ProcessedData.load(date, setnum, mode='a')
    # target_res = 241
    # # bad_resonators = [259, 748, 924]
    # mean_za = np.nanmean(pdata.detector_za[:], axis=1)
    # same_za = np.argwhere(np.isclose(mean_za, mean_za[target_res], atol=0.05)).flatten()
    # same_za = same_za[pdata.chanmask[same_za] == 1]
    # # same_za = same_za[pdata.detector_pol[same_za] == pdata.detector_pol[target_res]]
    # # same_za = same_za[~np.isin(same_za, bad_resonators)]
    # check_focus(
    #     pdata,
    #     same_za,
    #     primary_direction='az',
    #     dataset=dataset,
    # )
