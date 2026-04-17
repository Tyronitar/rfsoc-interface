from rfsocinterface.analysis.psd import ComputeNoisePSD, PlotPSD
from rfsocinterface.core.data import *
from rfsocinterface.analysis.psd import *
import pdb


if __name__ == '__main__':
    # date = '20260319'
    # setnum = 1023
    date = '20260309'
    setnum = 1010

    lp_filter_freq = 15
    hp_filter_freq= 0.25
    noise_removal_lp_filt_freq = 1000
    ds_factor = 3

    noise_removal_offres = RemoveElectronicsNoise(
        template_selection_indices='offres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    noise_removal_onres = RemoveElectronicsNoise(
        template_selection_indices='onres',
        lp_filt_freq=noise_removal_lp_filt_freq,
    )
    lp_filter = LowPassFilter(filter_freq=lp_filter_freq)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq)
    clean_tod = CleanTOD()
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, cut_time=2, selection_indices='onres')
    psd_plotter = PlotPSD(
        # PsdBasis.GAIN_PHASE,
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
        show=True,
        savefile='test.gif',
    )

    pipeline = Pipeline([
        # noise_removal_offres,
        # noise_removal_onres,
        # compute_psd,
        # psd_plotter,
        # hp_filter,
        # lp_filter,
        # clean_tod,
        # make_video,
        bin_tod_to_map,
        plotter,
    ])
    # pdata = pipeline.from_tod(date, setnum, ds_factor)
    pdata = ProcessedData.load(date, setnum, mode='a')
    pipeline.run(pdata)