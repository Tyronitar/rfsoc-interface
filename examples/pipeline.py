import pdb
import logging
import logging.config

import matplotlib.pyplot as plt
import numpy as np

from rfsocinterface.core.data import (
    ProcessedData,
    Pipeline,
    CleanTOD,
    RemoveElectronicsNoise,
    HighPassFilter,
    LowPassFilter,
    BinTODIntoMap,
    PlotMap,
    BinTODIntoVideo,
    AnimateVideo,
)
from rfsocinterface.analysis import (
    ComputeNoisePSD,
    PlotPSD,
    PsdBasis,
    AnalyzeBeamMap,
    PlotBeamMap,
    CheckFocus,
)
from rfsocinterface.core.params import RFSoCParameters, DEFAULT_DFOVERF_PER_MK


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
    # dataset = 'data_mK'
    # datasets = ['.*/data_mK']

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
        PsdBasis.GAIN_PHASE,
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
        dpix=0.02,
        r0=0.0,
    )
    plot_map_routine = PlotMap(
        show=True,
        # max_abs_threshold=0.4,
        keep_figure_open=False,
        channel=None,
        # show_optical_overlay=True,
        # vmin=-400,
        # vmax=400,
        overwrite=True,
        )
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
    animate_video = AnimateVideo(vmin=-400, vmax=400)

    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap()

    pipeline = Pipeline([
        # noise_removal_offres,
        # noise_removal_onres,
        # noise_removal,
        hp_filter,
        lp_filter,
        clean_tod,
        # compute_psd,
        # psd_plotter,
        bin_tod_to_map,
        # plot_map_routine,
        # bin_tod_to_video,
        # animate_video,
        # find_fwhm,
        analyze_beammap,
        plot_beammap,
    ])

    # date = '20260820'  # For testing normal maps
    # setnum = 1005
    # date = '20260710'  # For testing beammaps
    # setnum = 1006
    # date = '20260917'  # For testing video
    # setnum = 1007
    # date = '20261001'  # For testing normal maps
    # setnum = 1006

    date = '20261023'
    setnum = 1006


    # pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata, _ = pipeline.from_consolidated_data(date, setnum)
    # pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)
    # pdb.set_trace()

    # onres_ind = pdata.get_onres_ind(0)
    # az_centers = pdata['beammap/az_center'][onres_ind]
    # za_centers = pdata['beammap/za_center'][onres_ind]
    # fwhm_az = pdata['beammap/fwhm_az'][onres_ind]
    # fwhm_za = pdata['beammap/fwhm_za'][onres_ind]
    # amplitude  = pdata['beammap/amplitude'][onres_ind]
    # high_snr_ind = np.argwhere(
    #     amplitude > np.percentile(amplitude, 55),
    # ).flatten()

    # plt.scatter(
    #     az_centers[high_snr_ind],
    #     za_centers[high_snr_ind],
    #     c=fwhm_za[high_snr_ind],
    #     cmap='viridis',
    #     # marker='+',
    # )
    # plt.colorbar()
    # plt.show()
    # pdb.set_trace()

    pipeline = Pipeline([
        bin_tod_to_map,
        analyze_beammap,
    ])
    date = '20260617'
    for setnum in [1001, 1004, 1005, 1006]:
        pdata = ProcessedData.load(date, setnum)
        # pdb.set_trace()
        pipeline.run(pdata)

