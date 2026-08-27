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
        beam_map_mode=True,
        dataset=dataset,
        # az_trim=0,
        # za_trim=0,
        dpix=0.03,
        # r0=0,
    )
    plotter = PlotMap(show=True, max_abs_threshold=0.4, keep_figure_open=False)
    make_video = MakeVideo(
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

    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap()
    find_doubles = FindDoubleResonances(plot=False)

    pipeline = Pipeline([
        # noise_removal_offres,
        # noise_removal_onres,
        # noise_removal,
        # compute_psd,
        # psd_plotter,
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_map,
        # plotter,
        # make_video,
        # find_fwhm,
        analyze_beammap,
        # plot_beammap,
        # find_doubles,
    ])

    combine = CombinePolarizedBeamMaps()

    date = '20260617'
    setnum = 1005

    # pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)
    # pdata = ProcessedData.load(date, setnum, mode='a')
    # pipeline.run(pdata)
    vpol_data = ProcessedData.load(date, 1005, 'a')
    hpol_data = ProcessedData.load(date, 1006, 'a')
    combine._run(vpol_data, hpol_data, None)

    # for setnum in (1001, 1004, 1005, 1006):
    # # for setnum in (1005, 1006):
    #     pdata = ProcessedData.load(date, setnum, mode='a')
    #     # new_snr = pdata['beammap/new_snr'][:]
    #     # good_new_snr = new_snr[pdata.onres_ind]
    #     # good_new_snr = good_new_snr[10 < good_new_snr]
    #     # plt.hist(good_new_snr, bins=20)
    #     # plt.show()
    #     # pdb.set_trace()
    #     pipeline.run(pdata)

    # for setnum in (1001, 1004, 1005, 1006):
    # # for setnum in (1004, 1005, 1006):
    #     pdata = ProcessedData.load(date, setnum, mode='r')
    #     doubles_pos = pdata['beammap/double_resonances/positive/is_double'][:]
    #     doubles_neg = pdata['beammap/double_resonances/negative/is_double'][:]
    #     detector_f = pdata.detector_f()
    #     plt.hist(pdata['beammap/fwhm_az'][onres_ind], bins=20)
    #     plt.show()
    #     pdb.set_trace()
        # find_doubles.run(pdata)
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

    # pdata = ProcessedData.load(date, setnum)
    # pdb.set_trace()
    # pipeline.run(pdata)
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

