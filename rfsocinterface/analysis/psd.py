"""Code for computing the noise PSD."""
from enum import StrEnum
import pdb
import logging

from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from argparse import ArgumentParser

from kidpy3 import RawDataFile

from rfsocinterface.core.data import (
    DataRoutine,
    ProcessedData,
    flag_outliers,
    register_routine,
)
from rfsocinterface.core.data.routines import decode_tone_indices
from rfsocinterface.core.utils import DEFAULT_DATA_DIRECTORY, MetaEnum, ensure_path, get_tod_template, ordinal, PERMISSIONS_ALL_FULL 


_logger = logging.getLogger(__name__)

XLIM = (0.1, 250)
YLIM = (-110, -60)

N0 = 1.71e10 # Singel spin electron density of states at the Fermi level
kb_ev = 8.617342e-5 #[eV/K] Boltzman n Constant
h_ev = 4.135e-15
hbar_ev = h_ev/(2*np.pi)
V = 3000 #Inductor volume in um^3. 

class PsdBasis(StrEnum, metaclass=MetaEnum):
    """Enum for the different bases to use for computing the PSD."""
    IQ = 'IQ'
    GAIN_PHASE = 'gain_phase'
    FREQ_DISS = 'freq_diss'


@register_routine
class ComputeNoisePSD(DataRoutine):
    """Routine to compute the noise PSD for the data.
    
    Creates the following items in the HDF5 file:
    - /psd: group containing the PSD datasets for each basis.
    - /psd/{basis}: group containing the PSD datasets for the selected basis, 
        where {basis} is one of the bases specified in the `bases` parameter (e.g. 
        'gain_phase').
    - /psd/{basis}/freq: 1D array of length N_freq containing the frequency values for 
        the PSD.
    - /psd/{basis}/psd: 3D array of shape (2, N_tones, N_freq) containing the PSD values
         for the selected basis.
    """
    name = 'ComputeNoisePSD'
    version = '1.0.0'

    def __init__(
            self,
            *bases: PsdBasis,
            nominal_block_length: float=10,
            cut_time: float=0.0,
            selection_indices: npt.NDArray | str='all',
    ):
        """Initialize the ComputeNoisePSD routine.

        Uses Welch's method to compute the PSD in the specified bases.

        Will overwrite existing PSD datasets in the file if they already exist.

        Arguments:
            *bases (PsdBasis): Variable length of bases to compute the PSD for.
            nominal_block_length (float): Nominal block length in seconds to use for 
                computing the PSD. Defaults to 10 seconds.
            cut_time (float): Time in seconds to cut from the beginning and end of the
                data before computing the PSD. Defaults  to 0.0 (no cutting).
            selection_indices (npt.NDArray | str): Indices of the tones to include in 
                the PSD computation. Can be any value supported by the 
                `decode_tone_indices` function. Defaults to 'all'.
        """
        super().__init__(
            bases=bases,
            nominal_block_length=nominal_block_length,
            cut_time=cut_time,
            selection_indices=selection_indices,
        )

    def inputs(self, pdata: ProcessedData) -> list[str]:
        dsets = []
        bases = self.params['bases']
        for basis in bases:
            match basis:
                case PsdBasis.IQ:
                    dsets.append('/vdsets/data_IQ')
                case PsdBasis.GAIN_PHASE:
                    dsets.append('/vdsets/data_gain_phase')
                    dsets.append('/vdsets/carrier_amplitudes')
                case PsdBasis.FREQ_DISS:
                    dsets.append('/vdsets/data_freq_diss')
                    dsets.append('/vdsets/tones')
                case _:
                    raise ValueError(f'Cannot compute noise PSD for unknown basis "{basis}"')
        return dsets

    def run(self, pdata: ProcessedData, inputs: list[str]=None) -> list[str]:
        # Initialize PSD group in the file if needed
        if not pdata.has('psd', exact_match=True):
            psd_group = pdata.create_group('psd')

        psd_group = pdata['psd']

        time = pdata.timestamp[:] - pdata.timestamp[0]
        bases = self.params['bases']
        cut_time = self.params['cut_time']
        nominal_block_length = self.params['nominal_block_length']
        selection_indices = decode_tone_indices(pdata, self.params['selection_indices'])

        outputs = []

        for basis in bases:
            match basis:
                case PsdBasis.IQ:
                    data = pdata.data_IQ[:]
                case PsdBasis.GAIN_PHASE:
                    data = pdata.data_gain_phase[:] / pdata.carrier_amplitude_norm()
                case PsdBasis.FREQ_DISS:
                    f = pdata.detector_f()
                    f[pdata.offres_ind] = 1
                    data = pdata.data_freq_diss[:] / f[np.newaxis, :, np.newaxis]
                case _:
                    raise ValueError(f'{self.name}: Cannot compute noise PSD for unknown basis "{basis}"')
            if cut_time > 0:
                n_samples_to_cut = np.round(cut_time * pdata.fs).astype(int)
                data = data[..., n_samples_to_cut:-n_samples_to_cut]
                time = time[n_samples_to_cut:-n_samples_to_cut]

            # Determine the number of blocks for computing the PSD
            n_samples = np.size(time)
            n_samples_per_block = int(2**np.ceil(np.log2(nominal_block_length * pdata.fs)))
            n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
            if n_blocks == 0:
                n_blocks = 1
                n_samples_per_block = n_samples

            # Compute the PSD
            freq, psd = signal.welch(
                data[:, selection_indices],
                pdata.fs,
                nperseg=n_samples_per_block,
            )

            if basis in psd_group:
                del psd_group[basis]
            basis_group = psd_group.create_group(basis)
            psd_dset = basis_group.create_dataset('psd', data=psd)
            outputs.append(psd_dset.name)
            freq_dset = basis_group.create_dataset('freq', data=freq)
            outputs.append(freq_dset.name)
            indices = basis_group.create_dataset('selection_indices', data=selection_indices, dtype=int)
            outputs.append(indices.name)

        return outputs


def decode_color_string(color: str) -> tuple[str, str]:
    """Decode a color string into a median and fill color for PSD plotting.
    
    Supported colors are:
        - 'b' or 'blue': blue median line with cyan error band
        - 'r' or 'red': red median line with light coral error band
        - 'g' or 'green': green median line with light green error band
        - 'k' or 'black': black median line with light grey error band
        - 'o' or 'orange': dark orange median line with bisque error band
        - 'gold': gold median line with khaki error band
        - 'turquoise' or 'teal': teal median line with turquoise error band
        - 'purple': purple median line with violet error band
    """
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
        case _:
            msg = f'Unknown color "{color}" specified for PSD plotting; defaulting to ' \
            'blue with cyan error band.'
            _logger.warning(msg)
            med_color = 'b'
            fill_color = 'cyan'
    return med_color, fill_color


def plot_psd_df_over_f(
    freq: npt.NDArray,
    psd: npt.NDArray,
    ax: plt.Axes=None,
    f0: float | None=None,
    dev_pwr: float | None=None,
    adc_units_to_hz: float | None=None,
    csd: npt.NDArray | None=None,
    offres_median: npt.NDArray | None=None,
    show_error_band: bool=False,
    error_band_min_percentile: float=16,
    error_band_max_percentile: float=84,
    show_flat_spectrum_level: bool=False,
    flat_spectrum_search_bounds: tuple[float, float]=(10, 50),
    xlim: tuple[float, float]=None,
    ylim: tuple[float, float]=None,
    title: str | None=None,
    label: str=None,
    add_legend: bool=True,
    figure_kwargs: dict={},
    freq_color: str='b',
    diss_color: str='o',
    offres_color: str='r',
    title_fontsize: int=16,
    axis_label_fontsize: int=16,
    legend_fontsize: int=14,
    tick_size: int=14,
) -> Figure | None:
    """Plot df/f noise for a single resonator.
    basis_group,

    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): Frequency / disspiation PSD (2 x N_freq) or (2 x N_tones x
             N_freq).
        ax (plt.Axes, optional): Axes to plot in. If None, a new figure and axes will 
            be created.
        f0 (float, optional): Resonator frequency to include in the title.
            Defaults to None (not included in the title).
        dev_pwr (float, optional): Drive power to include in the title. Defaults to
            None (not included in the title).
        show_error_band (bool, optional): Whether to show the error band. Defaults
            to True.
        error_band_min_perncentile (float, optional): Percentile of lower error bound 
            for the plot. Defaults to 16.
        error_band_max_perncentile (float, optional): Percentile of upper error bound 
            for the plot. Defaults to 84.
        offres_median (npt.NDArray, optional): Median PSD of the off-resonance tones to 
            plot as a dashed line.
        flat_spectrum_search_bounds (tuple[float, float], optional): Frequency bounds to
            search for the flat spectrum level. Defaults to (10, 50) Hz.
        xlim (tuple[float, float], optional): x-axis limits for the plot. Defaults to 
            None (automatic limits).
        ylim (tuple[float, float], optional): y-axis limits for the plot. Defaults to 
            None (automatic limits).
        title (str, optional): Title to give to the plot. Defaults to None.
        label (str, optional): Label for the plot to use in the legend. Defaults to None.
        add_legend (bool, optional): Whether to add a legend to the plot. Defaults to 
            True.
        figure_kwargs (dict, optional): Keyword arguments to pass to `plt.figure` if a 
            new figure is created. Defaults to {}.
        freq_color (str, optional): Color to use for the frequency PSD. Defaults to 'b' 
            (blue).
        diss_color (str, optional): Color to use for the dissipation PSD. Defaults to 
            'o' (orange).
        offres_color (str, optional): Color to use for the off-resonance median PSD. 
            Defaults to 'r' (red).
        title_fontsize (int, optional): Font size for the plot title. Defaults to 16.
        axis_label_fontsize (int, optional): Font size for the axis labels. Defaults to 
            16.
        legend_fontsize (int, optional): Font size for the legend. Defaults to 14.
        tick_size (int, optional): Font size for the tick labels. Defaults to 14.

    Returns:
        (Figure | None): If no `ax` was provided, a new figure is generated to
            create the plot and is returned.
    """
    fig = None

    # Create figure if needed
    if ax is None:
        fig = plt.figure(**figure_kwargs)
        ax = fig.add_subplot()

        # Setup plot
        ax.set_xscale('log')
        ax.set_yscale('log')
        if xlim is not None:
            ax.set_xlim(*xlim)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.set_xlabel('Frequency (Hz)', fontsize=axis_label_fontsize)
        ax.set_ylabel(r'Sdf/f ($Hz^{-1}$)', fontsize=axis_label_fontsize)
        ax.tick_params(labelsize=tick_size)
        if f0 is not None:
            title += f' (f0 = {f0 / 1e6:.3f} MHz)'
        if dev_pwr is not None:
            title += f' at dev_pwr {dev_pwr}'
        if title is not None:
            ax.set_title(title, fontsize=title_fontsize)

    # Select color
    med_color_freq, fill_color_freq = decode_color_string(freq_color)
    med_color_diss, fill_color_diss = decode_color_string(diss_color)
    med_colors = [med_color_freq, med_color_diss]
    fill_colors=  [fill_color_freq, fill_color_diss]

    super_labels = ['Frequency', 'Dissipation']
    labels = [' - '.join(filter(None, (super_label, label))) for super_label in super_labels]

    if psd.ndim == 3:
        psd_med = np.median(psd, axis=1)
        plot_data_med = psd_med
    else:
        plot_data_med = psd

    # Flat spectrum level
    if show_flat_spectrum_level:
        flat_spectrum_idx = np.where(
            (freq > flat_spectrum_search_bounds[0]) &
            (freq < flat_spectrum_search_bounds[1])
        )
        new_labels = []
        flat_spectrum_noise_levels = np.zeros(2)
        for j, this_label in enumerate(labels):
            flat_spectrum_noise_levels[j] = np.median(plot_data_med[j, ..., flat_spectrum_idx])
            new_labels.append(rf'{this_label} ({flat_spectrum_noise_levels[j]:.1e} Hz$^{{-1}}$)')
        labels = new_labels

    # Plot PSD
    for j, this_label in enumerate(labels):
        # Error band
        if show_error_band:
            if psd.ndim != 3:
                _logger.error('Cannot show error band for PSD with dimensions != 3.')
            else:
                psd_min = np.percentile(psd[j], error_band_min_percentile, axis=0)
                psd_max = np.percentile(psd[j], error_band_max_percentile, axis=0)
                ax.fill_between(
                    freq,
                    psd_min,
                    psd_max,
                    facecolor=fill_colors[j],
                    alpha=0.5,
                )

        # Flat spectrum level
        if show_flat_spectrum_level:
            ax.axhline(
                flat_spectrum_noise_levels[j],
                color=med_colors[j],
                linestyle='dashed',
            )
        ax.plot(freq, plot_data_med[j], color=med_colors[j], label=this_label)
        if offres_median is not None:
            ax.plot(freq, offres_median[j], linestyle='dashed', color=offres_color, label=f'Off-Resonance {super_labels[j]} Median')

    # Add legend
    if add_legend:
        ax.legend(fontsize=legend_fontsize)

    if fig is not None:
        fig.tight_layout()
        return fig
def plot_freq_diss(
    psd,
    freq,
    detector_f,
    onres_ind,
    offres_ind,
    adc_units_to_hz,
    pdf_path,
    title=None,
    show_error_band=False,
    error_band_min_percentile=None,
    error_band_max_percentile=None,
):
   

    pdf_path = Path(pdf_path)
    #pdf_path.parent.mkdir(parents=True, exist_ok=True)
    # On-resonance tones
    onres_psd = psd[:, onres_ind]    
    offres_median = np.median(psd[:, offres_ind], axis=1)
    figs = []

    
    onres_fig = plot_psd_df_over_f(
        freq,
        onres_psd,
        title=" - ".join(filter(None, (title, "On-Resonance Tones"))),
        show_error_band=show_error_band,
        error_band_min_percentile=error_band_min_percentile,
        error_band_max_percentile=error_band_max_percentile,
        add_legend=True,
        show_flat_spectrum_level=True,
    )
    figs.append(onres_fig)

    plt.close(onres_fig)

    for tone in onres_ind:
        f0 = detector_f[tone]

        if offres_median is not None:
            this_offres_median = (
                offres_median
                / (adc_units_to_hz[tone] * f0)**2 
            )
        else:
            this_offres_median = None

        fig = plot_psd_df_over_f(
            freq,
            psd[:, tone],
            f0=f0,
            offres_median=None,
            title=" - ".join(filter(None, (title, f"Resonator {tone}"))),
            add_legend=True,
            show_flat_spectrum_level=True,
            ylim=(1e-21, 1e-15)
        )
        figs.append(fig)
    
    # Save all figures to PDF
    with PdfPages(pdf_path) as pdf:
        for fig in figs:
            pdf.savefig(fig)
            plt.close(fig)
    
def plot_psd_dbc_hz(
    freq: npt.NDArray,
    psd: npt.NDArray,
    ax: plt.Axes=None,
    show_error_band: bool=True,
    error_band_min_percentile: float=16,
    error_band_max_percentile: float=84,
    show_flat_spectrum_level: bool=True,
    flat_spectrum_search_bounds: tuple[float, float]=(10, 50),
    xlim: tuple[float, float]=None,
    ylim: tuple[float, float]=None,
    title: str | None=None,
    label: str=None,
    add_legend: bool=True,
    figure_kwargs: dict={},
    color: str='b',
    title_fontsize: int=16,
    axis_label_fontsize: int=16,
    legend_fontsize: int=14,
    tick_size: int=14,
) -> Figure | None:
    """Plot a PSD in dBc/Hz over frequency.

    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (N_tones x N_freq) in dBc/Hz.
        ax (plt.Axes, optional): Axes to plot in. If None, a new figure and axes will 
            be created.
        show_error_band (bool, optional): Whether to show the error band. Defaults
            to True.
        error_band_min_perncentile (float, optional): Percentile of lower error bound 
            for the plot. Defaults to 16.
        error_band_max_perncentile (float, optional): Percentile of upper error bound 
            for the plot. Defaults to 84.
        flat_spectrum_search_bounds (tuple[float, float], optional): Frequency bounds to
            search for the flat spectrum level. Defaults to (10, 50) Hz.
        xlim (tuple[float, float], optional): x-axis limits for the plot. Defaults to 
            None (automatic limits).
        ylim (tuple[float, float], optional): y-axis limits for the plot. Defaults to 
            None (automatic limits).
        title (str, optional): Title to give to the plot. Defaults to None.
        label (str, optional): Label for the plot to use in the legend. Defaults to None.
        add_legend (bool, optional): Whether to add a legend to the plot. Defaults to 
            True.
        figure_kwargs (dict, optional): Keyword arguments to pass to `plt.figure` if a 
            new figure is created. Defaults to {}.
        color (str, optional): Color to use for the PSD. Defaults to 'b' 
            (blue).
        title_fontsize (int, optional): Font size for the plot title. Defaults to 16.
        axis_label_fontsize (int, optional): Font size for the axis labels. Defaults to 
            16.
        legend_fontsize (int, optional): Font size for the legend. Defaults to 14.
        tick_size (int, optional): Font size for the tick labels. Defaults to 14.

    Returns:
        (Figure | None): If no `ax` was provided, a new figure is generated to
            create the plot and is returned.
    """
    fig = None

    # Create figure if needed
    if ax is None:
        fig = plt.figure(**figure_kwargs)
        ax = fig.add_subplot()

        # Setup plot
        ax.set_xscale('log')
        ax.set_yscale('linear')
        if xlim is not None:
            ax.set_xlim(*xlim)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.set_xlabel('Frequency (Hz)', fontsize=axis_label_fontsize)
        ax.set_ylabel(r'Noise PSD (dBc/Hz)', fontsize=axis_label_fontsize)
        ax.tick_params(labelsize=tick_size)
        if title is not None:
            ax.set_title(title, fontsize=title_fontsize)

    # Select color
    med_color, fill_color = decode_color_string(color)

    # Plot median
    psd_med = np.median(psd, axis=0)
    plot_data_med = 10 * np.log10(psd_med)

    # Error band
    if show_error_band:
        psd_min = np.percentile(psd, error_band_min_percentile, axis=0)
        psd_max = np.percentile(psd, error_band_max_percentile, axis=0)
        plot_data_min = 10 * np.log10(psd_min)
        plot_data_max = 10 * np.log10(psd_max)
        ax.fill_between(
            freq,
            plot_data_min,
            plot_data_max,
            facecolor=fill_color,
            alpha=0.5,
        )

    # Flat spectrum level
    if show_flat_spectrum_level:
        flat_spectrum_idx = np.where(
            (freq > flat_spectrum_search_bounds[0]) &
            (freq < flat_spectrum_search_bounds[1])
        )
        flat_spectrum_noise_level = np.median(plot_data_med[flat_spectrum_idx])
        lines = ax.plot(
            freq,
            plot_data_med,
            color=med_color,
        )
        if label is not None:
            lines[0].set_label(rf'{label} ({flat_spectrum_noise_level:.1f} dBc Hz$^{{-1}}$)')
        ax.axhline(
            flat_spectrum_noise_level,
            color=med_color,
            linestyle='dashed',
        )
    else:
        lines = ax.plot(freq, plot_data_med, color=med_color, label=label)

    # Add legend
    if add_legend and label is not None:
        ax.legend(fontsize=legend_fontsize)

    if fig is not None:
        fig.tight_layout()
        return fig


@register_routine
class PlotPSD(DataRoutine):
    """Routine to plot noise PSDs in the specified bases.

    For more flexibility in plotting, the `plot_psd_df_over_f` and `plot_psd_dbc_hz` 
    functions should be used directly instead of this routine.
    """
    name = 'PlotPSD'
    version = '1.1.0'

    @ensure_path('savefile')
    def __init__(
            self,
            *bases: PsdBasis,
            show_error_band: bool=True,
            error_band_min_percentile: float=16,
            error_band_max_percentile: float=84,
            title: str=None,
            show: bool=False,
            savefile: Path=None,
    ):
        """Initialize the PlotPSD routine.
        
        Arguments:
            *bases (PsdBasis): Variable length of bases to plot the PSD for.
            show_error_band (bool, optional): Whether to show the error band. Defaults
                to True.
            error_band_min_perncentile (float, optional): Percentile of lower error 
                bound for the plot. Defaults to 16.
            error_band_max_perncentile (float, optional): Percentile of upper error 
                bound for the plot. Defaults to 84.
            title (str, optional): Title to give to the plots. Defaults to None.
            show (bool, optional): Whether to show the plots after creating them. Defaults
                to False. Frequency / Disspiation plots for individual resonators will
                never be shown to screen, but this controls whether the on-resonance 
                tone PSD plot will be shown.
            savefile (Path, optional): Path to save the plots to as a PDF. If None, the
                plots will be saved to the same directory as the data with a default 
                name based on the data file. Defaults to None.
        """
        super().__init__(
            bases=bases,
            show_error_band=show_error_band,
            error_band_min_percentile=error_band_min_percentile,
            error_band_max_percentile=error_band_max_percentile,
            title=title,
            show=show,
            savefile=savefile,
        )

    def inputs(self, pdata: ProcessedData) -> list[str]:
        dsets = []
        bases = self.params['bases']
        for basis in bases:
            if basis not in PsdBasis:
                raise ValueError(f'{self.name}: Unknown PSD basis "{basis}"')
            dsets.append(f'/psd/{basis}/psd')
            dsets.append(f'/psd/{basis}/freq')
            if basis == PsdBasis.FREQ_DISS:
                dsets.append(f'/psd/{basis}/selection_indices')
        return dsets

    def run(self, pdata: ProcessedData, inputs: list[str]=None) -> list[str]:
        bases = self.params['bases']
        title = self.params['title']
        show_error_band = self.params['show_error_band']
        error_band_min_percentile = self.params['error_band_min_percentile']
        error_band_max_percentile = self.params['error_band_max_percentile']
        if title is None:
            title = ''
        for basis in bases:
            if self.params['savefile'] is not None:
                pdf_path = self.params['savefile']
            else:
                pdf_path = pdata.folder / f'{pdata.file_stub}_psd_{basis}.pdf'
            basis_group = pdata[f'psd/{basis}']
            match basis:
                case PsdBasis.IQ | PsdBasis.GAIN_PHASE:
                    if basis == PsdBasis.IQ:
                        subtitles = ['I', 'Q', 'Average']
                    else:
                        subtitles = ['Gain', 'Phase', 'Average']
                    titles = list(' - '.join(filter(None, (title, subtitle))) for subtitle in subtitles)
                    with PdfPages(pdf_path) as pdf:
                        fig0 = plot_psd_dbc_hz(
                            basis_group['freq'][:],
                            basis_group['psd'][0],
                            title=titles[0],
                            show_error_band=show_error_band,
                            error_band_min_percentile=error_band_min_percentile,
                            error_band_max_percentile=error_band_max_percentile,
                        )
                        fig1 = plot_psd_dbc_hz(
                            basis_group['freq'][:],
                            basis_group['psd'][1],
                            title=titles[1],
                            show_error_band=show_error_band,
                            error_band_min_percentile=error_band_min_percentile,
                            error_band_max_percentile=error_band_max_percentile,
                        )
                        fig2 = plot_psd_dbc_hz(
                            basis_group['freq'][:],
                            np.mean(basis_group['psd'], axis=0),
                            title=titles[2],
                            show_error_band=show_error_band,
                            error_band_min_percentile=error_band_min_percentile,
                            error_band_max_percentile=error_band_max_percentile,
                        )
                        pdf.savefig(fig0)
                        pdf.savefig(fig1)
                        pdf.savefig(fig2)
                        if self.params['show']:
                            plt.show()
                        plt.close(fig0)
                        plt.close(fig1)
                        plt.close(fig2)
                case PsdBasis.FREQ_DISS:
                    tones = basis_group['selection_indices'][:]
                    freq = basis_group['freq'][:]
                    psd = basis_group['psd'][:]
                    detector_f = pdata.detector_f()

                    onres_tones = np.intersect1d(tones, pdata.onres_ind)
                    onres_indices = np.isin(tones, onres_tones).nonzero()
                    onres_psd = psd[:, onres_indices[0]]
                    offres_tones = np.intersect1d(tones, pdata.offres_ind)
                    if offres_tones.size != 0:
                        offres_indices = np.isin(tones, offres_tones).nonzero()
                        offres_median = np.median(psd[:, offres_indices[0]], axis=1)
                    else:
                        offres_median = None
                    with PdfPages(pdf_path) as pdf:
                        # Plot all on-resonance tones
                        onres_fig = plot_psd_df_over_f(
                            freq,
                            onres_psd,
                            title=' - '.join(filter(None, (title, f'On-Resonance Tones'))),
                            show_error_band=show_error_band,
                            error_band_min_percentile=error_band_min_percentile,
                            error_band_max_percentile=error_band_max_percentile,
                            add_legend=True,
                            show_flat_spectrum_level=True,
                        )
                        if self.params['show']:
                            plt.show()
                        pdf.savefig(onres_fig)
                        plt.close(onres_fig)

                        # Plot individual tones
                        for i, i_tone in enumerate(tones):
                            f0 = detector_f[i_tone]
                            if offres_median is not None:
                                this_offres_median = offres_median / (pdata.adc_units_to_hz[i_tone] * f0) ** 2
                            else:
                                this_offres_median = None
                            fig = plot_psd_df_over_f(
                                freq,
                                psd[:, i],
                                f0=detector_f[i_tone],
                                offres_median=this_offres_median,
                                title=' - '.join(filter(None, (title, f'Resonator {i_tone}'))),
                                add_legend=True,
                                show_flat_spectrum_level=True,
                            )
                            pdf.savefig(fig)
                            plt.close(fig)
        return []

