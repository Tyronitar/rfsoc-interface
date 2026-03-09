"""Code for computing the noise PSD."""
import pdb

from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from argparse import ArgumentParser
import tables
import h5py
import scipy.special as sp

from kidpy3 import RawDataFile


from rfsocinterface.core.data import (
    flag_outliers,
    ProcessedData,
    DataRoutine,
    ProcessingStage,
    PsdBasis,
)
from rfsocinterface.core.utils import DATA_DIRECTORY, ensure_path, get_tod_template, ordinal, PERMISSIONS_ALL_FULL 

XLIM = (0.1, 250)
YLIM = (-110, -60)
VALID_BASES = ['gp', 'iq', 'fd']
N0 = 1.71e10 # Singel spin electron density of states at the Fermi level
kb_ev = 8.617342e-5 #[eV/K] Boltzman n Constant
h_ev = 4.135e-15
hbar_ev = h_ev/(2*np.pi)
V = 3224 #Inductor volume in um^3. 
def compute_noise_psd(
    input_time_ordered_data: npt.NDArray,
    timestamp: npt.NDArray,
    chanmask: npt.NDArray | None=None,
    nominal_block_length: float=1e100,
    cut_time: float=0.0,
) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
    """Compute noise PSD.

    input_time_ordered_data: 2 x N_res x N_sample or N_res x N_sample
    timestamp: N_sample
    chanmask: N_res
    nominal_block_length: seconds
    cut_time: seconds to cut from ends of data
    """
    first_dimension = input_time_ordered_data.shape[0] if input_time_ordered_data.ndim == 3 else 1
    if first_dimension == 1:
        input_data = input_time_ordered_data.reshape((1, *input_time_ordered_data.shape))
    else:
        input_data = input_time_ordered_data
    if chanmask is None:
        chanmask = np.ones_like(input_time_ordered_data[0, :, 0], dtype=int)
        # chanmask[1000:] = 0  # This is a fix since these channels seem to be bad

    timestamp -= timestamp[0]
    fs = 1. / np.median(np.diff(timestamp))

    # Cut data at start and end
    if cut_time > 0:
        n_samples_to_cut = np.round(cut_time * fs).astype(int)
        new_input_data = input_data[:, :, n_samples_to_cut:-n_samples_to_cut]
        timestamp = timestamp[n_samples_to_cut:-n_samples_to_cut]
    else:
        new_input_data = input_data

    # Determine the number of blocks for computing the PSD
    n_samples = np.size(timestamp)
    n_samples_per_block = int(2**np.ceil(np.log2(nominal_block_length * fs)))
    n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
    if n_blocks == 0:
        n_blocks = 1
        n_samples_per_block = n_samples
    
    freq, psd = _compute_psd(new_input_data[:, np.where(chanmask == 1)[0], :], fs, n_samples_per_block)
    return chanmask, freq, psd


def get_SNqp(fres, T, Sdff_freq, delta_0,alpha, V):
    omega = fres*2*np.pi
    xi = lambda omega, T: (hbar_ev * omega)/(2*kb_ev * T)
    k2 = 1/(2*N0*delta_0)*(1+np.sqrt(2*delta_0/(np.pi*kb_ev*T))*np.exp(-xi(omega,T)*sp.iv(0, xi(omega, T))))
    SNqp = 4*V**2 * Sdff_freq/(alpha**2 * k2**2)
    return SNqp


def _compute_psd(
        data: npt.NDArray,
        fs: float,
        n_samples_per_block: int,
) -> tuple[npt.NDArray, npt.NDArray]:
    """Compute the PSD."""
    return signal.welch(data, fs, nperseg=n_samples_per_block)


class ComputeNoisePSD(DataRoutine):
    stage = ProcessingStage.PROCESSING_L2

    def __init__(self, dataset: str='data_mK'):
        # TODO: Add parameters for the PSD computation
        super().__init__()
        self.dataset = dataset
    
    def forward(self, pd: ProcessedData):
        data = getattr(pd, self.dataset)
        chanmask, psd, freq = compute_noise_psd(
            data[:],
            timestamp=pd.timestamp[:],
            chanmask=pd.chanmask[:],
            nominal_block_length=self.nominal_block_length,
        )
        with tables.File(pd.cleaned_file_template, 'a') as cfile:
            cfile.create_array('/', 'psd', psd)
            cfile.create_array('/', 'psd_freq', freq)

@ensure_path(2)
def plot_psd(
        freq: npt.NDArray,
        psd: npt.NDArray,
        filename: Path,
        min_percentile: float=16,
        max_percentile: float=84,
        f0: float | None= None,
        adc_units_to_hz: npt.NDArray | None=None,
        title: str | None=None,
        basis: PsdBasis=PsdBasis.GAIN_PHASE,
        resonators: list[int]=None,
        csd: npt.NDArray = None,
        dev_pwr:npt.NDArray = None

) -> list[Figure]:
    """Create plots for the psd.
    
    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (N_chan x N_resonators x N_freq).
        filename (Path): PDF filename to save the  plots to.
        min_perncentile (float, optional): Percentile of lower error bound for the plot.
            Defaults to 16.
        max_perncentile (float, optional): Percentile of upper error bound for the plot
            Defaults to 84.
        title (str, optional): Title to give to each plot. Defaults to None.
        basis (str, optional): The basis of the data. Either IQ ('iq'), 
            Gain/Phase ('gp'), or Frequency/Dissipation ('fd'). Defaults to 'gp.'
    
    Returns:
        (list[Figure]): N_chan + 1 plots corresponding to the PSD along the
            first basis direction, second direction, and mean across both directions.
    
    Raises:
        ValueError: If `basis` is not a valid basis (see `VALID_BASES`).
    """

    # cutoff = 250  # Number of data points to cut off at the end
    # psd = psd[:, :, :-cutoff]
    # freq = freq[:-cutoff]
    figs = []
    if resonators is None:
        resonators = np.arange(psd.shape[1])

    if title is None:
        title = 'RFSoC Loopback PSD'
    match basis:
        case PsdBasis.GAIN_PHASE:
            titles = [[f'Tile {i_chan} {title} - Gain', f'Tile {i_chan} {title} - Phase'] for i_chan in range(psd.shape[0])]
            ylabel = r'Noise PSD ($\text{dBc Hz}^{-1})$'
            yscale = 'linear'
        case PsdBasis.IQ:
            titles = [[f'Tile {i_chan} {title} - I', f'Tile {i_chan} {title} - Q'] for i_chan in range(psd.shape[0])]
            ylabel = r'Noise PSD ($\text{dBc Hz}^{-1})$'
            yscale = 'linear'
        case PsdBasis.FREQ_DISS:
            ylabel = r'Sdf/f ($Hz^{-1}$)'
            yscale = 'linear'
            figs = plot_psd_df_over_f(freq, psd, filename, f0, title=title, resonators=resonators,adc_units_to_hz=adc_units_to_hz, csds = csd, dev_pwr = dev_pwr)
            return figs
        case PsdBasis.SNqp:
            ylabel = r'Sdf/f ($Hz^{-1}$)'
            yscale = 'linear'
            title = title + "SNqp"
            figs = plot_SNqp(freq, psd[:,resonators, : ], filename,f0[resonators], title = title)
            return
        case _:
            raise ValueError(f'Invalid basis {basis}; must be one of {VALID_BASES}')

    n_plots = psd.shape[1]
    psd_med = np.median(psd, axis=2)

    plot_data_med = 10 * np.log10(psd_med)

    psd_min = psd_med[:]
    psd_max = psd_med[:]

    if psd.shape[1] > 1:
        psd_min = np.percentile(psd, min_percentile, axis=2)
        psd_max = np.percentile(psd, max_percentile, axis=2)

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_max = 10 * np.log10(psd_max)

    # Plot 
    if not filename.exists():
        filename.touch(PERMISSIONS_ALL_FULL)
    figs = []
    with PdfPages(filename) as pdf:
        for i_chan in range(psd.shape[0]):
            for i_plot in range(n_plots):
                fig = create_plot(
                    freq,
                    plot_data_min[i_chan, i_plot],
                    plot_data_med[i_chan, i_plot],
                    plot_data_max[i_chan, i_plot],
                    percentiles=(min_percentile, max_percentile),
                    title=titles[i_chan][i_plot],
                    ylabel=ylabel,
                    yscale=yscale,
                )
                pdf.savefig(fig)
                figs.append(fig)
        average_fig = create_plot(
            freq,
            np.sum(plot_data_min[i_chan], axis=0) / n_plots,
            np.sum(plot_data_med[i_chan], axis=0) / n_plots,
            np.sum(plot_data_max[i_chan], axis=0) / n_plots,
            percentiles=(min_percentile, max_percentile),
            title= f'Tile {i_chan} {title} - Averaged',
            ylabel=ylabel,
            yscale=yscale,
        )
        pdf.savefig(average_fig)

    return figs
@ensure_path(0)
def compare_psds(
        filename: Path,
        freq: npt.NDArray,
        psd_list: list,
        alpha_list:list,
        label_list:list,
        f0: float | None= None,
        title: str | None=None,
        basis: PsdBasis=PsdBasis.GAIN_PHASE,
        resonators: list[int]=None,
        dev_pwr:npt.NDArray = None

) -> list[Figure]:
    """Create plots for the psd.
    
    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (N_chan x N_resonators x N_freq).
        filename (Path): PDF filename to save the  plots to.
        min_perncentile (float, optional): Percentile of lower error bound for the plot.
            Defaults to 16.
        max_perncentile (float, optional): Percentile of upper error bound for the plot
            Defaults to 84.
        title (str, optional): Title to give to each plot. Defaults to None.
        basis (str, optional): The basis of the data. Either IQ ('iq'), 
            Gain/Phase ('gp'), or Frequency/Dissipation ('fd'). Defaults to 'gp.'
    
    Returns:
        (list[Figure]): N_chan + 1 plots corresponding to the PSD along the
            first basis direction, second direction, and mean across both directions.
    
    Raises:
        ValueError: If `basis` is not a valid basis (see `VALID_BASES`).
    """

    # cutoff = 250  # Number of data points to cut off at the end
    # psd = psd[:, :, :-cutoff]
    # freq = freq[:-cutoff]
    figs = []
    if resonators is None:
        resonators = np.arange(psd.shape[1])

    if title is None:
        title = 'RFSoC Loopback PSD'
    match basis:
        case PsdBasis.FREQ_DISS:
            for i in range(psd_list[0].shape[1]):

                if resonators is not None and not resonators[i]:
                    continue

                res_title = title + f' - Resonator {i}'

                if f0 is not None and i < len(f0):
                    res_title += f' (f0 = {f0[i]/1e6:.3f} MHz)'

                if dev_pwr is not None and i < len(dev_pwr):
                    res_title += f' at dev_pwr {dev_pwr[i]}'

                fig, ax = plt.subplots(figsize=(9, 6))
                for k in range(len(psd_list)):
                    for j, label in enumerate(['Frequency', 'Dissipation']):
                        psd = psd_list[k]
                        ax.plot(
                            freq,
                            psd[j, i, :],
                            label=f'{label} ( {label_list[k]})',
                            alpha=alpha_list[k]
                        )
                ax.set_xscale('log')
                #ax.set_xlim(1, 250)
                ax.set_yscale('log')
                ax.set_ylim(1e-21,1e-15)
            
                ax.set_xlabel('Frequency (Hz)', fontsize=16)
                    
                ax.tick_params(labelsize=14)
                ax.set_title(res_title)
                ax.set_xlabel('Frequency (Hz)')
                ax.set_ylabel(r'Sdf/f ($Hz^{-1}$)')
                ax.legend()

                figs.append(fig)

    with PdfPages(filename) as pdf:
        for fig in figs:
            pdf.savefig(fig)
        

    return figs
def mb_from_h5(path: Path) -> dict:
    """Create a LoSweepData object from a sweep file."""
    path = path.with_suffix('.h5')
    mb_dict = {'res':[],'delta_0':[],'alpha':[], 'f0':[]}
    with h5py.File(path, 'r') as f:
        res_list = f['Dark_Load/MB_fit']
        index_name = ['res' +str(j).zfill(3) for j in range(0,len(res_list))]
        for i in range(0,len(res_list)):
            mb_dict['res'].append(i)
            D = res_list[index_name[i]]['Fres_fit']['Delta'][()]
            a = res_list[index_name[i]]['Fres_fit']['alpha'][()]
            f = res_list[index_name[i]]['Fres_fit']['f0'][()]

            mb_dict['alpha'].append(a)
            mb_dict['delta_0'].append(D)
            mb_dict['f0'].append(f)

    return mb_dict
@ensure_path(2)
def plot_SNqp(
        freq: npt.NDArray,
        psd: npt.NDArray,
        filename: Path,
        f0: npt.NDArray,
        min_percentile: float=16,
        max_percentile: float=84,
        title: str | None=None,
        mb_file_name = "Be231102d2_AR_BS_dark_processed.h5"
) -> list[Figure]:
    """Create plots for the psd.
    
    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (N_chan x N_resonators x N_freq).
        filename (Path): PDF filename to save the  plots to.
        title (str, optional): Title to give to each plot. Defaults to None.
    
    Returns:
        (list[Figure]): N_chan plots corresponding to the PSD for each resonator.
    
    Raises:
        ValueError: If the length of `resonators` is greater than the number of resonators
    """
    base_temp = 0.243 #K, TODO assumed and will be updated to match thermometry value. 
    mb_file_path = Path(f'{DATA_DIRECTORY}/params/{mb_file_name}')
    mb_data = mb_from_h5(path = mb_file_path)

    ylabel = r'Sdf/f ($Hz^{-1}$)'
    # Plot 
    if not filename.exists():
        filename.touch(PERMISSIONS_ALL_FULL)
    figs = []
    yscale = 'log'
    SNqp_array = []
    combined_fig = plt.figure(figsize=(9, 6))
    combined_fig_ax = plt.subplot()
    cmap = plt.get_cmap('viridis')
    
    for i in np.arange(psd.shape[1]):
        res_title = title + f' - Resonator {i}'
        if f0 is not None and i < len(f0):
            res_title += f' (f0 = {f0[i]/1e6:.3f} MHz)'
            mb_index = np.argmin(np.abs(f0[i]-mb_data['f0']))
            alpha = mb_data['alpha'][mb_index]
            delta = mb_data['delta_0'][mb_index]
            SNqp = get_SNqp(f0[i],base_temp,np.array(psd[0, i, :]),delta, alpha, V )
            SNqp_array.append(SNqp)
            fig = create_plot(
            freq,
            SNqp,
            percentiles=(min_percentile, max_percentile),
            title= res_title,
            ylabel='Noise PSD (Nqp)',
            yscale='log',
            )
            figs.append(fig)
            combined_fig_ax.plot(freq, SNqp, label = f'Resonator {i}', color = cmap(i/psd.shape[1]))
    combined_fig_ax.set_xscale('log')
    combined_fig_ax.set_yscale('log')
    combined_fig_ax.set_xlabel('Frequency (Hz)', fontsize=16)
    combined_fig_ax.set_ylabel('Noise PSD (Nqp)', fontsize=16)
    combined_fig_ax.tick_params(labelsize=14)
    combined_fig_ax.set_title(title + ' - SNqp Comparison', fontsize=16)
    figs.append(combined_fig)

    psd_med = np.median(SNqp_array, axis=0)


    psd_min = np.percentile(SNqp_array, min_percentile, axis=0)
    psd_max = np.percentile(SNqp_array, max_percentile, axis=0)

    average_fig = create_plot(
        freq,
        psd_med,
        ydata_min = psd_min,
        ydata_max = psd_max,
        percentiles=(min_percentile, max_percentile),
        title= title + ' - Averaged',
        ylabel=ylabel,
        yscale=yscale,
    )
    SNqp_array = np.array(SNqp_array)
    print(SNqp_array.shape)
    figs.append(average_fig)
    figs.append(plot_hist(freq, SNqp_array,1.0,"Hist Freq at 1 Hz"  ))
    figs.append(plot_hist(freq, SNqp_array,10.0,"Hist Freq at 10 Hz"  ))
    figs.append(plot_hist(freq, SNqp_array,100.0,"Hist Freq at 100 Hz"  ))
    figs.append(plot_hist(freq, SNqp_array,200.0,"Hist Freq at 200 Hz"  ))

    with PdfPages(filename) as pdf:
        for fig in figs:
            pdf.savefig(fig)
        
    return figs
        

@ensure_path(2)
def plot_psd_df_over_f(
        freq: npt.NDArray,
        psd: npt.NDArray,
        filename: Path,
        f0: float | None= None,
        adc_units_to_hz: npt.NDArray | None=None,
        min_percentile: float=16,
        max_percentile: float=84,
        title: str | None=None,
        resonators: list[int]=[0],
        csds: npt.NDArray = None,
        dev_pwr:npt.NDArray = None,
        plot_offres_median: bool = False
) -> list[Figure]:
    """Create plots for the psd.
    
    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (N_chan x N_resonators x N_freq).
        filename (Path): PDF filename to save the  plots to.
        title (str, optional): Title to give to each plot. Defaults to None.
    
    Returns:
        (list[Figure]): N_chan plots corresponding to the PSD for each resonator.
    
    Raises:
        ValueError: If the length of `resonators` is greater than the number of resonators
    """
    ylabel = r'Sdf/f ($Hz^{-1}$)'
    # Plot 
    if not filename.exists():
        filename.touch(PERMISSIONS_ALL_FULL)
    figs = []
    yscale = 'log'
    onres_psd = psd[:,resonators, :]
    if plot_offres_median:
        offres_median = np.median(psd[:, ~resonators, :],axis=1)
    else:
        offres_median = None
    for i in np.arange(psd.shape[1]):
        res_title = title + f' - Resonator {i}'
        if f0 is not None and i < len(f0):
            res_title += f' (f0 = {f0[i]/1e6:.3f} MHz)'
        if dev_pwr is not None and i < len(dev_pwr):
            res_title += f' at dev_pwr {dev_pwr[i]}'
        if resonators[i]:
            if csds is not None:
                csd = csds[i,:]
            else:
                csd = None
            fig = plot_df_over_f(
                freq,
                psd[:, i, :],
                offres_median=offres_median,
                f0 = f0[i],
                adc_units_to_hz=adc_units_to_hz[i],
                ylabel=ylabel,
                title=res_title,
                csd = csd
            )
            
            plt.close(fig)
            figs.append(fig)


    figs+=(average_plots(
        freq,
        onres_psd,
        [title + ' - On-Resonance Frequency', title + ' - On-Resonance Dissipation'],
        title,
        min_percentile,
        max_percentile,
        ylabel,
        yscale,
    ))

    figs.append(plot_hist(freq, onres_psd,1.0,"Hist Freq at 1 Hz" , components=["Frequency", "Dissapation"] ))
    figs.append(plot_hist(freq, onres_psd,10.0,"Hist Freq at 10 Hz" ,components=["Frequency", "Dissapation"]  ))
    figs.append(plot_hist(freq, onres_psd,100.0,"Hist Freq at 100 Hz",components=["Frequency", "Dissapation"]   ))
    figs.append(plot_hist(freq, onres_psd,200.0,"Hist Freq at 200 Hz" ,components=["Frequency", "Dissapation"]  ))

    with PdfPages(filename) as pdf:
        for fig in figs:
            pdf.savefig(fig)
        
    return figs
        
def average_plots(freq, psd, titles,title, min_percentile, max_percentile, ylabel, yscale):
    n_plots = psd.shape[0]
    psd_med = np.median(psd, axis=1)
    psd_min = np.percentile(psd, min_percentile,axis=1)
    psd_max = np.percentile(psd, max_percentile,axis=1)
    figs = []
    for i in range(n_plots):
        fig = create_plot(
            freq,
            psd_med[i],
            ydata_min = psd_min[i],
            ydata_max = psd_max[i],
            percentiles=(min_percentile, max_percentile),
            title=titles[i],
            ylabel=ylabel,
            yscale=yscale,
        )
        figs.append(fig)

    average_fig = create_plot(
        freq,
        np.sum(psd_med, axis=0) / n_plots,
        ydata_min= np.sum(psd_min, axis=0) / n_plots,
        ydata_max= np.sum(psd_max, axis=0) / n_plots,
        percentiles=(min_percentile, max_percentile),
        title= title + ' - Averaged',
        ylabel=ylabel,
        yscale='log',
    )
    figs.append(average_fig)
    plt.close()
    return figs


def plot_hist(
    x_data: npt.NDArray,
    y_data: npt.ArrayLike,
    hist_freq: float,
    title: str | None=None,
    ylabel: str='Num Values',
    components: npt.NDArray = None,
    n_avg: int = 5
) -> Figure:
    """Create a plot of the noise PSD in df/f units."""
    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    
    freq_index = np.argmin(np.abs(x_data-hist_freq))
    if components is not None:
        for j, label in enumerate(components):
            plot_data = np.mean(y_data[j, :, freq_index-n_avg: freq_index + n_avg], axis = 1)
            y = np.arange(0 ,len(plot_data))

            ax.hist(np.log10(plot_data), label = label, alpha = 0.5, bins = 20)
            ax.scatter(np.log10(plot_data),y)
    else:
        plot_data = np.mean(y_data[:, freq_index-n_avg: freq_index + n_avg], axis = 1)
        y = np.arange(0 ,len(plot_data))
        ax.hist(np.log10(plot_data), alpha = 0.5, bins = 20)
        ax.scatter(np.log10(plot_data),y)


    ax.set_xlabel(f'log Sdf/f PSD value at {hist_freq}(Hz)', fontsize=16)
    ax.set_ylabel(ylabel, fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc='best')
    if title is not None:
        ax.set_title(title, fontsize=16)
    plt.tight_layout()
    plt.close()
    return fig

def plot_df_over_f(
    x_data: npt.NDArray,
    y_data: npt.ArrayLike,
    offres_median: npt.ArrayLike| None=None,
    adc_units_to_hz: npt.NDArray | None=None,
    f0:float = 1,
    title: str | None=None,
    ylabel: str='Noise PSD (df / f)',
    csd: npt.NDArray = None,
    make_angle_plot: bool = True,
    dev_pwr:float = 0,
) -> Figure:
    """Create a plot of the noise PSD in df/f units."""
    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    if offres_median is not None and adc_units_to_hz is not None:
        offres_median = offres_median /( adc_units_to_hz * f0)**2

    for j, label in enumerate(['Frequency', 'Dissipation']):
        ax.plot(x_data, y_data[j], label=label)
        if offres_median is not None:
            ax.plot(x_data, offres_median[j], linestyle='dashed', color='gray', label=f'Off-Resonance {label} Median')
    if csd is not None:
        ax.plot(x_data, abs(csd), label = 'CSD')
        if make_angle_plot:
            angle = 0.5*np.arctan2(2*np.real(csd), y_data[0]-y_data[1])
            freq_start = np.argmin(np.abs(x_data-20))
            freq_stop = np.argmin(np.abs(x_data-400))

            mean_angle = np.mean(angle[freq_start:freq_stop])
            ax2 = ax.twinx()
            ax2.legend(fontsize = 14, loc = 'best' )

            ax2.hlines( mean_angle,x_data[0], x_data[-1], label = 'Residual Rotation Angle',color = 'red',linestyles='dashed', alpha = 0.3)
    ax.set_xscale('log')
    #ax.set_xlim(1, 250)
    ax.set_yscale('log')
    ax.set_ylim(1e-21,1e-15)
   
    ax.set_xlabel('Frequency (Hz)', fontsize=16)
        
    ax.set_ylabel(ylabel, fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc='best')
    if title is not None:
        ax.set_title(title, fontsize=16)
    plt.tight_layout()
    plt.close()
    return fig


def create_plot(
    xdata: npt.ArrayLike,
    ydata_med: npt.ArrayLike,
    ydata_min: npt.ArrayLike = None,
    ydata_max: npt.ArrayLike = None,
    percentiles: tuple[float, float]=(16., 84.),
    label: str='Median Measured Noise',
    title: str | None=None,
    xlabel: str='Frequency (Hz)',
    ylabel: str=r'Noise PSD (dBc/Hz)',
    yscale: str='linear',
) -> Figure:
    """Create a plot of the noise PSD."""
    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    ax.plot(xdata, ydata_med, color='b', label=label)
    flat_spectrum_idx = np.where((xdata > 10) & (xdata < 50))
    flat_spectrum_noise = np.median(ydata_med[flat_spectrum_idx])
    if ydata_min is not None and ydata_max is not None:
        plt.hlines(flat_spectrum_noise, XLIM[0], XLIM[1], colors='r', linestyles='dashed', label=f'Flat Spectrum Level = {flat_spectrum_noise:.1f} dBc/Hz')
        ax.fill_between(
            xdata,
            ydata_min,
            ydata_max,
            facecolor='c',
            alpha=0.5,
            label=f'{ordinal(int(percentiles[0]))} Percentile to {ordinal(int(percentiles[1]))} Percentile'
        )
    ax.set_xscale('log')
    ax.set_xlim(*XLIM)
    ax.set_yscale(yscale)
    if yscale=='linear' and np.median(ydata_min) > -110 and np.median(ydata_max) < -60:
        ax.set_ylim(-110, -60)
        loc = 'upper right'
    else:
        loc = 'best'
    
    ax.set_xlabel(xlabel, fontsize=16)
    ax.set_ylabel(ylabel, fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc=loc)
    if title is None:
        title = 'RFSoC Loopback PSD'
    ax.set_title(title, fontsize=16)
    plt.tight_layout()

    return fig


# if __name__ == '__main__':
#     pairs = [
#         # ('equal_0-256', 'RFSoC Loopback with 1000 Tones Over Full Bandwidth'),
#         # ('equal_1-255', 'RFSoC Loopback with 1000 Tones in Range +/-[1, 255] MHz'),
#         # ('equal_5-251', 'RFSoC Loopback with 1000 Tones in Range +/-[5, 251] MHz'),
#         # ('equal_10-246', 'RFSoC Loopback with 1000 Tones in Range +/-[10, 246] MHz'),
#         # ('data/default_0-256.hdf5', 'RFSoC Loopback with Default Tones'),
#         # ('default_1-255', 'RFSoC Loopback with Default Tones in Range +/-[1, 255] MHz'),
#         # ('default_5-251', 'RFSoC Loopback with Default Tones in Range +/-[5, 251] MHz'),
#         # ('./data/default_10-246', 'RFSoC Loopback with Default Tones in Range +/-[10, 246] MHz'),
#         # ('/data/20250404/20250404_chan_1_TOD_set1001.h5', 'ASU Readout'),
#         ('/data/20250415/20250415_chan_1_TOD_set1004.h5', 'Loopback')
#     ]
#     for name, title in pairs:
#         # input_data, timestamp, chanmask = load_time_ordered_IQ_data(f'data/{name}.hdf5')
#         input_data, timestamp, chanmask = load_time_ordered_IQ_data(f'{name}')
#         # input_data = input_data[:, :-5, :]
#         rotated_data = rotate_to_amplitude_and_phase(input_data)
#         # save_name = f'new_psd_{name}'
#         save_name = Path(name).name

#         chanmask, freq, noise_psd = compute_noise_psd(
#             rotated_data,
#             timestamp,
#             chanmask=None,
#             ds_factor=3,
#             flag_outliers=True,
#             nominal_block_length=10,
#             outlier_sigma=2,
#         )
#         plot_psd(freq, noise_psd, f'plots/{save_name}.pdf', basis='gp', title=title)
#         plt.close()


if __name__ == '__main__':
    parser = ArgumentParser(description='Compute the noise PSD from RFSoC data.')
    parser.add_argument('date', type=str, help='Date of the data in YYYYMMDD format.')
    parser.add_argument('setnum', type=int, help='Set number of the data.')
    parser.add_argument('--outlier_sigma', type=float, default=2.0, help='Sigma for outlier detection.')
    parser.add_argument('-d', '--ds_factor', type=int, default=1, help='Downsampling factor.')
    parser.add_argument('-f', '--do_flag_outliers', action='store_true', help='Flag outliers in the data.')
    parser.add_argument('-n', '--remove_noise', action='store_true', help='Remove electronics noise from the data.')
    parser.add_argument('--lp_filt_freq', type=float, default=10, help='Low-pass filter frequency in HZ for electronics noise removal (defaults to 10).')
    parser.add_argument('-b', '--basis', type=str, choices=VALID_BASES, default='gp', help='Basis of the data (gp, iq, fd).')
    parser.add_argument('-p', '--show_plots', action='store_true', help='Show noise plots to screen when finished.')
    parser.add_argument('--block_length', type=float, default=10, help='Nominal block length. Time in seconds for a single "block" of data (defaults to 10s).')
    parser.add_argument('--cut_time', type=float, default=10, help='Time in seconds to cut from teh ends of the data (defaults to 10).')
    parser.add_argument('--title', type=str, default='Noise PSD', help='Title to use for the plots')
    parser.add_argument('-o', '--output', type=str, default='', help='Output filename (defaults to DATE_setSETNUM_psd_BASIS_TITLE.pdf).')
    parser.add_argument('--max_eigenmodes', type=int, default=30, help='Maximum number of eigenmodes to use for electronics noise removal (defaults to 30).')
    args = parser.parse_args()

    date = args.date
    setnum = args.setnum
    outlier_sigma = args.outlier_sigma
    ds_factor = args.ds_factor
    do_flag_outliers = args.do_flag_outliers
    remove_noise = args.remove_noise
    basis = args.basis
    nominal_block_length = args.block_length
    cut_time = args.cut_time
    lp_filt_freq = args.lp_filt_freq
    max_modes = args.max_eigenmodes
    title = args.title
    if args.output == '':
        output_file = f'{DATA_DIRECTORY}/{date}/{date}_set{setnum}_psd_{basis}_{title}.pdf'
    else:
        output = args.output

    pd = ProcessedData.from_tod(
        date,
        setnum,
        do_electronics_noise_removal=remove_noise,
        max_modes=max_modes,
        ds_factor=ds_factor,
        electronics_noise_lp_filt_freq=lp_filt_freq,
    )



    match basis:
        case 'iq':
            # IQ basis
            # input_data = rotate_basis(p.data_gain_phase, -p.IQ_to_gain_phase_angle)
            input_data = pd.data_IQ
        case 'fd':
            # Frequency/Dissipation basis
            # Get frequencies from the raw data file
            # raw_data_file = f'/data/{date}/{date}_chan_1_TOD_set{setnum}.h5'
            # TODO: Get the channel name from the processed data file? (but there's multiple in theory??)
            raw_data_file = get_tod_template(date, setnum, chan_name='Be231102p2_100_tones')
            # raw_data_file = get_tod_template(date, setnum, chan_name='1000_tone_uniform_202050829')
            fh = RawDataFile(raw_data_file, 'r')
            freq = fh.baseband_freqs[:] + fh.lo_freq[:]

            input_data = pd.data_freq_diss / freq[np.newaxis, :, np.newaxis]
        case 'gp':
            # Gain/Phase basis
            input_data = pd.data_gain_phase / pd.carrier_amplitude_norm()
        case _:
            raise ValueError(f'Invalid basis {basis}; must be one of {VALID_BASES}')

    # Fix data dimensions
    first_dimension = input_data.shape[0] if input_data.ndim == 3 else 1
    if first_dimension == 1:
        input_data = input_data.reshape((1, *input_data.shape))

    chanmask = pd.chanmask[:]

    # Flag outliers
    if do_flag_outliers:
        chanmask = flag_outliers(input_data, pd.fs, chanmask, sigma=outlier_sigma)

    filt_sos = signal.butter(6, 1, btype='highpass', fs=pd.fs, output='sos', analog=False)
    input_data[:] = signal.sosfiltfilt(filt_sos, input_data)

    chanmask, freq, noise_psd = compute_noise_psd(
        input_data,
        pd.timestamp,
        chanmask=chanmask,
        nominal_block_length=nominal_block_length,
        cut_time=cut_time,
    )
    plot_psd(
        freq,
        noise_psd,
        output_file,
        basis=basis,
        title=title,
        resonators=np.where(chanmask==1)[0],
    )
    if args.show_plots:
        plt.show()
    pd.close()
