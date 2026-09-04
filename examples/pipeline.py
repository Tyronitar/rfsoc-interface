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
    ds_factor = 12

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
        hp_filter,
        lp_filter,
        clean_tod,
        # compute_psd,
        # psd_plotter,
        # bin_tod_to_map,
        # plotter,
        bin_tod_to_video,
        animate_video,
        # find_fwhm,
        # analyze_beammap,
        # plot_beammap,
    ])

    date = '20260828'
    setnum = 1002


    pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata = pipeline.from_consolidated_data(date, setnum)

    # pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)
    # pdb.set_trace()

    # hits_map = pdata['video/hits_map'][:]
    # sum_map = pdata['video/sum_map'][:]
    # map_az = pdata['video/map_az'][:]
    # map_za = pdata['video/map_za'][:]
    # extent = get_extent(map_az, map_za, 0.08)
    # zero_mask = sum_map[10, :, 0] == 0
    # np.sum(zero_mask, axis=1)
    # im = np.zeros(sum_map.shape[-2:])
    # im[zero_mask[0]] = 1
    # im[zero_mask[1]] = -1
    # im[np.all(zero_mask, axis=0)] = 2
    # im[~zero_mask[0]] += 0.5
    # im[~zero_mask[1]] -= 0.5
    # plt.imshow(im, extent=extent)
    # indices_tile2 = pdata.get_onres_ind(0)
    # indices_tile3 = pdata.get_onres_ind(1)
    # # az_centers = pdata.detector_delta_x[indices]
    # # za_centers = pdata.detector_delta_y[indices]
    # az_centers_tile2 = np.nanmedian(pdata.get_detector_az(0), axis=1)[indices_tile2]
    # za_centers_tile2 = np.nanmedian(pdata.get_detector_za(0), axis=1)[indices_tile2]

    # az_centers_tile3 = np.nanmedian(pdata.get_detector_az(1), axis=1)[indices_tile3]
    # za_centers_tile3 = np.nanmedian(pdata.get_detector_za(1), axis=1)[indices_tile3]
    # az_centers = (az_centers_tile2, az_centers_tile3)
    # za_centers = (za_centers_tile2, za_centers_tile3)

    # from scipy.spatial import Delaunay
    # for i_chan in range(pdata.n_chan):
    #     triangluation = Delaunay(np.stack((za_centers[i_chan], az_centers[i_chan]), axis=1))
    #     y, x = np.meshgrid(map_za, map_az)
    #     outside_mask = None
    #     for i in [-0.08, 0.08]:
    #         for j in [-0.08, 0.08]:
    #             map_coords = np.column_stack((y.flatten() + i,  x.flatten() + j))
    #             this_outside_mask = triangluation.find_simplex(map_coords) < 0
    #             if outside_mask is None:
    #                 outside_mask = this_outside_mask
    #             else:
    #                 outside_mask &= this_outside_mask

    #     outside_mask = outside_mask.reshape(map_az.size, map_za.size).T

    #     hits_map[:, i_chan, :, outside_mask] = 0


    # polsum = np.sum(hits_map, axis=(1, 2))

    # plt.imshow(polsum[10], extent=extent)
    # plt.scatter(az_centers_tile2, za_centers_tile2, c='white')
    # plt.scatter(az_centers_tile3, za_centers_tile3, c='white')
    # plt.show()
    # pdb.set_trace()


    # plt.show()
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

