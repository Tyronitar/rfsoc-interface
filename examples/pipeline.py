import logging
import logging.config

from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD, PsdBasis, plot_psd_df_over_f, plot_freq_diss
from rfsocinterface.core.data import *
from rfsocinterface.analysis import *
import pdb
import matplotlib.pyplot as plt
import numpy as np


if __name__ == '__main__':
    #logging.config.fileConfig('rfsocinterface/logging.conf')
    #_logger = logging.getLogger('rfsocinterface')
    #_logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 122
    hp_filter_freq = 0.001
    noise_removal_lp_filt_freq = 10  # Filter disabled if set to 0
    ds_factor = 2

    dataset = 'data_freq'
    datasets = ['/vdsets/data_freq_diss']

    find_fwhm = FindFWHM(
        'az',
        [241],
    )

    noise_removal_offres = RemoveElectronicsNoise(
        template_selection_indices='offres',
        lp_filt_freq=noise_removal_lp_filt_freq,
        fspace = True
    )
    noise_removal_onres = RemoveElectronicsNoise(
        template_selection_indices='onres',
        lp_filt_freq=noise_removal_lp_filt_freq,
        fspace = True
        
    )
    noise_removal = RemoveElectronicsNoise()
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, cut_time=2)
    psd_plotter = PlotPSD(
        PsdBasis.GAIN_PHASE,
        PsdBasis.FREQ_DISS,
        show=False,
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
        noise_removal_offres,
        noise_removal_onres,
        #noise_removal,
        compute_psd,
        psd_plotter,
        hp_filter,
        lp_filter,
        clean_tod,
        #bin_tod_to_map,
        # plotter,
        # make_video,
        # find_fwhm,
        # analyze_beammap,
        # plot_beammap,
    ])


    date = '20260319'
    setnums = np.array([ 1023, 1025, 1027, 1028,1031, 1032])

    psd_obj_list = []


    for setnum in setnums:
        pdata = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
        psd_obj_list.append(pdata['psd/freq_diss/psd'])

    psd_avg = np.mean(np.array(psd_obj_list), axis=0)
    psd_freq = pdata['psd/freq_diss/freq']
    plot_freq_diss(psd_avg, psd_freq[:], pdata.detector_f(),pdata.onres_ind, pdata.offres_ind,  pdata.adc_units_to_hz, 'output.pdf')
    pdb.set_trace()
    