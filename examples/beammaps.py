import pdb
import logging
import logging.config

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

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
from rfsocinterface.core.sweeps import LoSweepData


def flag_non_signal(
        pdata: ProcessedData,
        movement_threshold: float=1e-4,
        lower_bound_az: float=4.525,
        upper_bound_az: float=9.475,
        plot: bool = False,
        save_changes: bool = True,
    ):
    tel_az = pdata.get_telescope_az(0)[:]
    tel_za = pdata.get_telescope_za(0)[:]
    map_signal_mask = pdata.get_map_signal_mask(0)
    if not save_changes:
        # Load a copy of the mask to avoid modifying the original dataset
        map_signal_mask = map_signal_mask[:]  
    sample_idx = np.arange(tel_az.size)

    # First, flag samples during move to initial position

    d_za = np.diff(tel_za)
    diff_sample_idx = np.arange(d_za.size)

    # Telescope moves in AZ then ZA at the start

    # Find when first AZ dither stops, i.e.
    # when the telescope first starts moving in ZA 
    # AKA first time that ZA changes (i.e. d_za > 0)
    za_dither_start_idx = np.nanargmax(np.abs(d_za) >= movement_threshold)  # Finds first `True`

    # Find when the telescope gets to the intial position
    # i.e. first ZA dither stops
    # AKA first time that ZA stops changing after ZA dither starts (i.e. diff == 0)
    initial_pos_idx = np.nanargmax(
        (np.abs(d_za) < movement_threshold)
        & (diff_sample_idx > za_dither_start_idx)  # Only look after ZA dither starts
    )

    # NOTE: Porbably need to deal with off-by-one errors since using np.diff

    # Ignore samples during the move to the initial position
    map_signal_mask[:initial_pos_idx] = False


    # Flag samples that are outside of [5, 9] AZ
    outside_samples = np.argwhere((tel_az < lower_bound_az) | (tel_az > upper_bound_az)).flatten()
    map_signal_mask[outside_samples] = False

    # Flag samples where the position is unknown
    nan_idx = np.argwhere(
        np.isnan(tel_az) |
        np.isnan(tel_za)
    ).flatten()
    map_signal_mask[nan_idx] = False

    if plot:
        map_signal_mask = map_signal_mask[:]
        plt.title(f'Signal Mask - {pdata.file_stub}')
        plt.scatter(
            tel_az[map_signal_mask],
            tel_za[map_signal_mask],
            c=sample_idx[map_signal_mask] / sample_idx.size,
            cmap='viridis',
            label='Good Samples',
        )
        plt.scatter(
            tel_az[:initial_pos_idx],
            tel_za[:initial_pos_idx],
            c='r',
            label='Intial move'
        )
        plt.scatter(
            tel_az[outside_samples],
            tel_za[outside_samples],
            c='gray',
            label='Outside bounds'
        )
        plt.axvline(lower_bound_az, color='red', linestyle='--')
        plt.axvline(upper_bound_az, color='red', linestyle='--')
        plt.gca().invert_yaxis()
        plt.legend()
        plt.show()

def plot_signal_mask(
    map_signal_mask: npt.NDArray,
    tel_az: npt.NDArray,
    tel_za: npt.NDArray,
    title: str,
):
    sample_idx = np.arange(tel_az.size)
    plt.title(title)
    plt.scatter(
        tel_az[map_signal_mask],
        tel_za[map_signal_mask],
        c=sample_idx[map_signal_mask] / sample_idx.size,
        cmap='viridis',
        label='Good Samples',
    )
    plt.scatter(
        tel_az[~map_signal_mask],
        tel_za[~map_signal_mask],
        c='gray',
        label='Non-signal Samples'
    )
    plt.gca().invert_yaxis()
    plt.legend()
    plt.show()


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 15
    hp_filter_freq = 0.03

    ds_factor = 16

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']
    # dataset = 'data_mK'
    # datasets = ['.*/data_mK']

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
        r0=0.0,
    )
    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap()

    pipeline = Pipeline([
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_map,
        analyze_beammap,
        plot_beammap,
    ])

    date = '20261028'
    setnum = 1008

    # tod_file = '/data/20261028/20261028_Device_aSi1_Channel2_telescope_275mK_20260804_TOD_set1001.h5'
    # tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260804'
    # with RFSoCParameters.load(tile_name, 'r') as params:
    #     params.append_to_TOD(tod_file)
    # sweep = LoSweepData.load_most_recent(tile_name)
    # if sweep is not None:
    #     sweep.append_to_TOD(tod_file)

    pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata, _ = pipeline.from_consolidated_data(date, setnum)
    # pdata = ProcessedData.load(date, setnum)
    # plot_signal_mask(
    #     pdata.get_map_signal_mask(0)[:],
    #     pdata.get_telescope_az(0)[:],
    #     pdata.get_telescope_za(0)[:],
    #     f'Signal Mask - {pdata.file_stub}',
    # )
    # pdata.get_map_signal_mask(0)[:] = True
    # flag_non_signal(
    #     pdata,
    #     plot=True,
    #     lower_bound_az=2.525,
    #     upper_bound_az=7.475,
    # )
    # pipeline.run(pdata)
    # try:
    #     map_signal_mask = pdata.get_map_signal_mask(0)
    # except KeyError:
    #     map_signal_mask = make_signal_dset(pdata)

    # date = '20261023'
    # for setnum in [1016, 1017, 1018]:
    # for setnum in [1017]:
    #     pdata = ProcessedData.load(date, setnum)
    #     pdata.setnum = setnum
    #     flag_non_signal(pdata, movement_threshold=1e-4)
    #     # pdb.set_trace()
    #     bin_tod_to_map.apply(pdata)
    #     analyze_beammap.apply(pdata)
    #     plot_beammap.apply(pdata)
    #     pdata.close()




