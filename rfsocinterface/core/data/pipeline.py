from __future__ import annotations

import logging

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
import pdb

from rfsocinterface.core.data.storage import ProcessedData
from rfsocinterface.core.data.routines import DataRoutine, ROUTINE_REGISTRY
from rfsocinterface.core.data.storage import ConsolidatedData

_logger = logging.getLogger(__name__)

class Pipeline:

    def __init__(self, routines: list[DataRoutine]=[]):
        self.routines = routines
    
    def from_tod(self, date: str, setnum: int, downsampling_factor: int=1) -> ProcessedData:
        _logger.info(f'Pipeline: Running pipeline on TOD {date}_set{setnum}')
        cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=downsampling_factor)
        _logger.info('Pipeline: Creating processed data...')
        pd = cd.create_processed_data()
        self.run(pd)
        return pd
    
    def add_routine(self, name: str, **params):
        routine_cls = ROUTINE_REGISTRY[name]
        routine = routine_cls(**params)
        self.routines.append(routine)
        _logger.debug(f'Pipeline: Added routine {name} with params {params} to pipeline.')
    
    def load_config(self, config: dict):
        """Loads a pipeline configuration from a dictionary.
        
        The dictionary should have the following format:
        {
            "routine_name_1": {
                "param1": value1,
                "param2": value2,
                ...
            },
            "routine_name_2": {
                "param1": value1,
                "param2": value2,
                ...
            },
            ...
        }
        """
        for name, params in config.items():
            self.add_routine(name, **params)

    def run(self, pdata: ProcessedData):
        for routine in self.routines:
            routine.apply(pdata)

def plot_psd(
        ax: plt.Axes,
        color: str,
        label: str,
        freq: npt.NDArray,
        psd: npt.NDArray,
        min_percentile: float=16,
        max_percentile: float=84,
        flat_spectrum: bool=True,
        flat_spectrum_search_bounds: tuple=(10, 50),
) -> list[Figure]:

    # cutoff = 250  # Number of data points to cut off at the end
    # psd = psd[:, :, :-cutoff]
    # freq = freq[:-cutoff]

    # for i_tone in range(psd.shape[1]):
    #     ax.plot(freq[:], np.mean(10 * np.log10(psd[:, i_tone]), axis=0))
    # return

    psd_med = np.median(psd, axis=1)

    match color.lower():
        case 'b' | 'blue;':
            med_color = 'b'
            fill_color = 'cyan'
        case 'r' | 'red':
            med_color = 'r'
            fill_color = 'lightcoral'
        case 'g' | 'green':
            med_color = 'g'
            fill_color = 'lightgreen'
        case 'k' | 'black':
            med_color = 'k'
            fill_color = 'lightgrey'
        case 'o' | 'orange':
            med_color = 'darkorange'
            fill_color = 'bisque'
        case 'gold':
            med_color = 'gold'
            fill_color = 'khaki'
        case 'turquoise' | 'teal':
            med_color = 'teal'
            fill_color = 'turquoise'
        case 'purple':
            med_color = 'purple'
            fill_color = 'violet'
        # case 31:
        #     med_color = 'g'
        #     fill_color = 'lightgreen'


    plot_data_med = 10 * np.log10(psd_med)

    psd_min = psd_med[:]
    psd_max = psd_med[:]

    if psd.shape[1] > 1:
        psd_min = np.percentile(psd, min_percentile, axis=1)
        psd_max = np.percentile(psd, max_percentile, axis=1)

    # means = np.mean(np.mean(psd, axis=0), axis=-1)
    # idx = np.argsort(means)
    # pdb.set_trace()

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_max = 10 * np.log10(psd_max)

    xdata = freq[:]
    ydata_min = np.mean(plot_data_min, axis=0)
    ydata_med = np.mean(plot_data_med, axis=0)
    ydata_max = np.mean(plot_data_max, axis=0)


    if flat_spectrum:
        flat_spectrum_idx = np.where((xdata > flat_spectrum_search_bounds[0]) & (xdata < flat_spectrum_search_bounds[1]))
        flat_spectrum_noise = np.median(ydata_med[flat_spectrum_idx])
        ax.plot(xdata, ydata_med, color=med_color, label=rf'{label} ({flat_spectrum_noise:.1f} dBc Hz$^{{-1}}$)')
        plt.axhline(flat_spectrum_noise, color=med_color, linestyle='dashed')
    else:
        ax.plot(xdata, ydata_med, color=med_color, label=label)

    ax.fill_between(
        xdata,
        ydata_min,
        ydata_max,
        facecolor=fill_color,
        alpha=0.5,
    )


if __name__ == '__main__':
    from rfsocinterface.core.data.routines import *
    from rfsocinterface.core.data.utils import PsdBasis
    import pdb
    # date = '20260319'
    # setnum = 1023
    date = '20260309'
    setnum = 1013

    lp_filter_freq = 15
    hp_filter_freq= 0.25
    noise_removal_lp_filt_freq = 1000
    ds_factor = 8

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
    compute_psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, cut_time=2, selection_indices='onres')
    psd_plotter = PlotPSD(
        PsdBasis.GAIN_PHASE,
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
    )

    pipeline = Pipeline([
        noise_removal_offres,
        noise_removal_onres,
        # compute_psd,
        # psd_plotter,
        hp_filter,
        lp_filter,
        clean_tod,
        make_video,
        # bin_tod_to_map,
        # plotter,
    ])
    pdata = pipeline.from_tod(date, setnum, ds_factor)
    # pdata = ProcessedData.load(date, setnum, mode='a')
    # pipeline.run(pdata)
    pdb.set_trace()
