import logging
import logging.config

from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD, PsdBasis
from rfsocinterface.core.data import *
from rfsocinterface.analysis.psd import *
import pdb


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)
    # date = '20260319'
    # setnum = 1023
    # date = '20260309'
    # setnum = 1010
    date = '20260420'
    setnum = 1024
    # date = '20260325'
    # setnum = 1002

    lp_filter_freq = 15
    hp_filter_freq= 0.25
    noise_removal_lp_filt_freq = 0  # Filter disabled if set to 0
    ds_factor = 1

    noise_removal_offres = RemoveElectronicsNoise(
        template_selection_indices='offres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    noise_removal_onres = RemoveElectronicsNoise(
        template_selection_indices='onres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    noise_removal = RemoveElectronicsNoise()
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq)
    clean_tod = CleanTOD()
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, cut_time=2, selection_indices='onres')
    psd_plotter = PlotPSD(
        PsdBasis.GAIN_PHASE,
        PsdBasis.FREQ_DISS,
        show=True,
    )
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        # az_trim=0,
        # za_trim=0,
        # dpix=0.03,
    )
    plotter = PlotMap(show=True)
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

    pipeline = Pipeline([
        # noise_removal_offres,
        # noise_removal_onres,
        # noise_removal,
        # compute_psd,
        # psd_plotter,
        # hp_filter,
        # lp_filter,
        # clean_tod,
        make_video,
        # bin_tod_to_map,
        # plotter,
    ])
    # pdata = pipeline.from_tod(date, setnum, ds_factor)
    setnum = 1005
    pdata = ProcessedData.load(date, setnum, mode='a')
    pipeline.run(pdata)
    # freq = pdata['psd/freq_diss/freq'][:]
    # psd = pdata['psd/freq_diss/psd'][:]
    # # convert to dBc/Hz
    # psd_adc = psd * (pdata.detector_f()[np.newaxis, pdata.onres_ind, np.newaxis] * pdata.adc_units_to_hz[np.newaxis, pdata.onres_ind, np.newaxis]) ** 2
    # psd_adc /= (pdata.carrier_amplitude_norm() ** 2)
    # fig = plot_psd_dbc_hz(freq, psd_adc[0], label='Frequency', color='purple', add_legend=False, xlim=(0.1, 250), ylim=(-108, -68))
    # ax = fig.get_axes()[0]
    # plot_psd_dbc_hz(freq, psd_adc[1], ax=ax, label='Dissipation', color='o')
    # plt.show()