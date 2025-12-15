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
        title: str | None=None,
        basis: PsdBasis=PsdBasis.GAIN_PHASE,
        resonators: list[int]=None,
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
    if resonators is None:
        resonators = np.arange(psd.shape[1])

    if title is None:
        title = 'RFSoC Loopback PSD'
    match basis:
        case PsdBasis.GAIN_PHASE:
            titles = [title + ' - Gain', title + ' - Phase']
            ylabel = r'Noise PSD ($\text{dBc Hz}^{-1})$'
            yscale = 'linear'
        case PsdBasis.IQ:
            titles = [title + ' - I', title + ' - Q']
            ylabel = r'Noise PSD ($\text{dBc Hz}^{-1})$'
            yscale = 'linear'
        case PsdBasis.FREQ_DISS:
            return plot_psd_df_over_f(freq, psd, filename, title=title, resonators=resonators)
        case _:
            raise ValueError(f'Invalid basis {basis}; must be one of {VALID_BASES}')

    n_plots = psd.shape[0]
    psd_med = np.median(psd, axis=1)

    plot_data_med = 10 * np.log10(psd_med)

    psd_min = psd_med[:]
    psd_max = psd_med[:]

    if psd.shape[1] > 1:
        psd_min = np.percentile(psd, min_percentile, axis=1)
        psd_max = np.percentile(psd, max_percentile, axis=1)

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_max = 10 * np.log10(psd_max)

    # Plot 
    if not filename.exists():
        filename.touch(PERMISSIONS_ALL_FULL)
    figs = []
    with PdfPages(filename) as pdf:
        for i in range(n_plots):
            fig = create_plot(
                freq,
                plot_data_min[i],
                plot_data_med[i],
                plot_data_max[i],
                percentiles=(min_percentile, max_percentile),
                title=titles[i],
                ylabel=ylabel,
                yscale=yscale,
            )
            pdf.savefig(fig)
            figs.append(fig)
        average_fig = create_plot(
            freq,
            np.sum(plot_data_min, axis=0) / n_plots,
            np.sum(plot_data_med, axis=0) / n_plots,
            np.sum(plot_data_max, axis=0) / n_plots,
            percentiles=(min_percentile, max_percentile),
            title= title + ' - Averaged',
            ylabel=ylabel,
            yscale=yscale,
        )
        pdf.savefig(average_fig)

    return figs

@ensure_path(2)
def plot_psd_df_over_f(
        freq: npt.NDArray,
        psd: npt.NDArray,
        filename: Path,
        title: str | None=None,
        resonators: list[int]=[0],
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
    with PdfPages(filename) as pdf:
        for i, res in enumerate(resonators):
            res_title = title + f' - Resonator {res}'
            fig = plot_df_over_f(
                freq,
                psd[:, i, :],
                ylabel=ylabel,
                title=res_title,
            )
            pdf.savefig(fig)
            plt.close(fig)
            figs.append(fig)
        return figs


def plot_df_over_f(
    x_data: npt.NDArray,
    y_data: npt.ArrayLike,
    title: str | None=None,
    ylabel: str='Noise PSD (df / f)',
) -> Figure:
    """Create a plot of the noise PSD in df/f units."""
    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    for j, label in enumerate(['Frequency', 'Dissipation']):
        ax.plot(x_data, y_data[j], label=label)
    ax.set_xscale('log')
    ax.set_xlim(1, 250)
    ax.set_yscale('log')
    # ax.set_ylim(1e-17,1e-15)

    ax.set_xlabel('Frequency (Hz)', fontsize=16)
        
    ax.set_ylabel(ylabel, fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc='best')
    if title is not None:
        ax.set_title(title, fontsize=16)
    plt.tight_layout()
    return fig


def create_plot(
    xdata: npt.ArrayLike,
    ydata_min: npt.ArrayLike,
    ydata_med: npt.ArrayLike,
    ydata_max: npt.ArrayLike,
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
