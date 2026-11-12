import pdb
import logging
import logging.config
from typing import ClassVar

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import tqdm
from scipy import signal
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.offsetbox import AnchoredText
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

from rfsocinterface.core.data import (
    ConsolidatedData,
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
    get_extent,
    DataRoutine,
    RoutineResult,
)
from rfsocinterface.analysis import (
    ComputeNoisePSD,
    PlotPSD,
    PsdBasis,
    AnalyzeBeamMap,
    PlotBeamMap,
    CheckFocus,
    plot_psd_df_over_f,
)
from rfsocinterface.core.utils import (
    BAD_RESONANCE_COLOR,
    OFF_RESONANCE_COLOR,
    elide_text,
    ChanmaskValue,
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

def plot_one_beammap(
    pdata: ProcessedData,
    plotter: PlotBeamMap,
    i_tone_absolute: int,
):
    az_center = pdata['beammap/az_center'][:]
    za_center = pdata['beammap/za_center'][:]
    amplitude = pdata['beammap/amplitude'][:]
    snr = pdata['beammap/snr'][:]
    chisq = pdata['beammap/chisq'][:]
    fwhm_az = pdata['beammap/fwhm_az'][:]
    fwhm_za = pdata['beammap/fwhm_za'][:]
    map_val = pdata['map/map_val']
    map_az = pdata['map/map_az'][:]
    map_za = pdata['map/map_za'][:]
    dpix = pdata['map'].attrs['dpix']
    units = pdata['map'].attrs.get('units', 'mK')
    extent = get_extent(map_az, map_za, dpix=dpix)
    chanmask = pdata.chanmask
    detector_f = pdata.detector_f()

    fig = plotter._new_figure(figsize=(12, 5.5))
    ax, ax_zoom = fig.subplots(1, 2)

    # data_to_plot = np.flip(np.transpose(map_val[i_tone_absolute][::-1]), 1)
    data_to_plot = map_val[i_tone_absolute]
    data_to_plot -= np.nanmedian(data_to_plot)
    data_to_plot /= np.nanmax(data_to_plot)
    # data_to_plot = 10 * np.log10(np.abs(data_to_plot))

    imshow_kwargs = {
        'extent': extent,
        'aspect': 'equal',
        'cmap': 'jet',
        # Embed the raw map pixels in the PDF instead of an image resampled
        # to the figure dpi. This keeps each image small regardless of dpi
        # (the PdfPages backend holds every image in memory until it is
        # closed) and keeps pixels sharp when zooming in on the PDF.
        'interpolation': 'none',
    }

    # All map data
    im = ax.imshow(data_to_plot, **imshow_kwargs)

    # Zoomed-in map data (same color scale so the colorbar applies to both)
    ax_zoom.imshow(data_to_plot, norm=im.norm, **imshow_kwargs)

    # Color bar (shared, to the right of the zoomed panel)
    divider = make_axes_locatable(ax_zoom)
    cax = divider.append_axes('right', size='5%', pad=0.05)
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(f'Normalized signal ({units})', rotation=270, labelpad=15)
    # Matplotlib rasterizes colorbars by default. In a PDF, that renders a
    # full-page raster buffer and stores a cropped *view* of it, which keeps
    # the whole buffer (~24 MB at 300 dpi) alive until the PdfPages is
    # closed. Over hundreds of pages this exhausts memory, so draw the
    # colorbar as vectors instead (it's only a few hundred quads).
    cb.solids.set_rasterized(False)

    # Center of bright source (full map only, so it doesn't hide the beam)
    ax.plot(
        az_center[i_tone_absolute],
        za_center[i_tone_absolute],
        marker='+',
        color='white',
        markersize=10,
        mew=2,
    )

    # Zoom in around the beam
    x_lim, y_lim = plotter._zoom_limits(
        data_to_plot,
        map_az,
        map_za,
        extent,
        dpix,
        az_center[i_tone_absolute],
        za_center[i_tone_absolute],
        fwhm_az[i_tone_absolute],
        fwhm_za[i_tone_absolute],
    )
    ax_zoom.set_xlim(*x_lim)
    ax_zoom.set_ylim(*y_lim)

    # Stats
    show_stats = chanmask[i_tone_absolute] != 0
    if show_stats:
        plotter._add_stats_text(
            fig,
            extent,
            amplitude[i_tone_absolute],
            chisq[i_tone_absolute],
            snr[i_tone_absolute],
            fwhm_az[i_tone_absolute],
            fwhm_za[i_tone_absolute],
            az_center[i_tone_absolute],
            za_center[i_tone_absolute],
        )

    # Indicate in plot title and face color if off-resonance / bad tone
    title, facecolor = plotter._tone_title(
        pdata, i_tone_absolute, detector_f[i_tone_absolute]
    )
    if facecolor is not None:
        fig.set_facecolor(facecolor)

    for a in (ax, ax_zoom):
        a.set_xlabel('X Position (deg)')
        a.set_ylabel('Y Position (deg)')
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title('Full map')
    ax_zoom.set_title('Beam (zoomed)')
    fig.suptitle(title)

    # Leave room at the bottom for the stats box
    fig.tight_layout(rect=(0, 0.14 if show_stats else 0, 1, 1))

    # Outline the zoomed region on the full map. The connector lines are
    # hidden since they cross the zoomed panel's tick labels.
    indicator = ax.indicate_inset_zoom(ax_zoom, edgecolor='white', alpha=0.9)
    for connector in indicator.connectors:
        connector.set_visible(False)

    fig.savefig(f'{pdata.file_stub}_beammap_tone_{i_tone_absolute}.png', dpi=300)



def plot_single_beammap(
    pdata: ProcessedData,
    i_tone_absolute: int,
    zoom_half_width: float | None = None,
):
    """Plot the beammap results for a single resonator.

    The left panel shows the full map with the fitted beam center marked. The
    right panel shows a zoomed-in view around the beam with no markers, and the
    zoomed region is outlined on the full map.

    Args:
        pdata: Processed data containing the ``map`` and ``beammap`` groups.
        i_tone_absolute: Absolute tone index to plot.
        zoom_half_width: Half-width of the zoomed region in degrees. Defaults
            to 1.5x the larger fitted FWHM.
    """
    az_center = pdata['beammap/az_center'][:]
    za_center = pdata['beammap/za_center'][:]
    amplitude = pdata['beammap/amplitude'][:]
    snr = pdata['beammap/snr'][:]
    chisq = pdata['beammap/chisq'][:]
    fwhm_az = pdata['beammap/fwhm_az'][:]
    fwhm_za = pdata['beammap/fwhm_za'][:]
    map_val = pdata['map/map_val'][:]
    map_az = pdata['map/map_az'][:]
    map_za = pdata['map/map_za'][:]
    dpix = pdata['map'].attrs['dpix']
    units = pdata['map'].attrs.get('units', 'mK')
    extent = get_extent(map_az, map_za, dpix=dpix)
    chanmask = pdata.chanmask
    detector_f = pdata.detector_f()

    fig, (ax, ax_zoom) = plt.subplots(1, 2, figsize=(12, 5.5))

    data_to_plot = map_val[i_tone_absolute]
    data_to_plot -= np.nanmedian(data_to_plot)
    data_to_plot /= np.nanmax(data_to_plot)
    # data_to_plot = 10 * np.log10(np.abs(data_to_plot))

    imshow_kwargs = {
        'extent': extent,
        'aspect': 'equal',
        'cmap': 'jet',
        # 'interpolation': 'bilinear',
    }

    # All map data
    im = ax.imshow(data_to_plot, **imshow_kwargs)

    # Zoomed-in map data (same color scale so the colorbar applies to both)
    ax_zoom.imshow(data_to_plot, norm=im.norm, **imshow_kwargs)

    # Color bar (shared, to the right of the zoomed panel)
    divider = make_axes_locatable(ax_zoom)
    cax = divider.append_axes('right', size='5%', pad=0.05)
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(f'Normalized signal ({units})', rotation=270, labelpad=15)

    # Center of bright source (full map only, so it doesn't hide the beam)
    ax.plot(
        az_center[i_tone_absolute],
        za_center[i_tone_absolute],
        marker='+',
        color='white',
        markersize=10,
        mew=2,
    )

    # Determine zoom window around the beam. Fall back to the brightest pixel
    # and/or a fraction of the map if the fit failed.
    x0 = az_center[i_tone_absolute]
    y0 = za_center[i_tone_absolute]
    if not (np.isfinite(x0) and np.isfinite(y0)):
        i_za, i_az = np.unravel_index(np.nanargmax(data_to_plot), data_to_plot.shape)
        x0 = map_az[i_az]
        y0 = map_za[i_za]
    if zoom_half_width is None:
        fwhm = np.nanmax([fwhm_az[i_tone_absolute], fwhm_za[i_tone_absolute]])
        if np.isfinite(fwhm) and fwhm > 0:
            zoom_half_width = max(2 * fwhm, 0.25)
        else:
            zoom_half_width = 0.1 * min(np.ptp(map_az), np.ptp(map_za))
    zoom_half_width = max(zoom_half_width, 2 * dpix)

    # Keep the same axis orientation as the full map (extent may be inverted)
    x_dir = np.sign(extent[1] - extent[0]) or 1
    y_dir = np.sign(extent[3] - extent[2]) or 1
    ax_zoom.set_xlim(x0 - x_dir * zoom_half_width, x0 + x_dir * zoom_half_width)
    ax_zoom.set_ylim(y0 - y_dir * zoom_half_width, y0 + y_dir * zoom_half_width)

    # Stats
    show_stats = chanmask[i_tone_absolute] != 0
    if show_stats:
        bbox_pad = 0.3
        t = AnchoredText(
            f'Amplitude = {amplitude[i_tone_absolute] * 1e5:2f}    '
            f'chisq = {chisq[i_tone_absolute]:.3f}    '
            f'snr = {snr[i_tone_absolute]:.3f}\n'
            f'fwhm_az = {fwhm_az[i_tone_absolute]:.2f}    '
            f'fwhm_za = {fwhm_za[i_tone_absolute]:.2f}\n'
            f'az_center = {az_center[i_tone_absolute]:.2f}    '
            f'za_center = {za_center[i_tone_absolute]:.2f}',
            loc='lower center',
            bbox_to_anchor=(0.5, 0.01),
            bbox_transform=fig.transFigure,
            pad=bbox_pad,
            borderpad=0,
            prop={
                # color='white',
                'horizontalalignment': 'center',
            },
        )
        # t.patch.set_alpha(0.25)
        # t.patch.set_color('black')
        fig.add_artist(t)

    i_chan, i_tone_relative = pdata.get_relative_tone_index(i_tone_absolute)
    if pdata.n_chan > 1:
        # Spefcify the tile name if there are multiple channels
        tile_name = pdata.get_tile_name(i_chan)
        title = (
            f'{elide_text(tile_name, max_len=30)} - Tone {i_tone_relative}\n'
            f'($f_0$={detector_f[i_tone_absolute] * 1e-6:.3f} MHz)'
        )
    else:
        title = (
            f'Tone {i_tone_relative} '
            f'($f_0$={detector_f[i_tone_absolute] * 1e-6:.3f} MHz)'
        )

    # Indicate in plot title and face color if off-resonance / bad tone
    if chanmask[i_tone_absolute] != 1:
        if chanmask[i_tone_absolute] == 0:
            title += ' (Off-resonance)'
            facecolor = OFF_RESONANCE_COLOR
        else:
            title += ' (Bad Resonance)'
            facecolor = BAD_RESONANCE_COLOR
        fig.set_facecolor(facecolor)

    for a in (ax, ax_zoom):
        a.set_xlabel('X Position (deg)')
        a.set_ylabel('Y Position (deg)')
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title('Full map')
    ax_zoom.set_title('Beam (zoomed)')
    fig.suptitle(title)
    # fig.set_dpi(300)

    # Leave room at the bottom for the stats box
    fig.tight_layout(rect=(0, 0.14 if show_stats else 0, 1, 1))

    # Outline the zoomed region on the full map. The connector lines are
    # hidden since they cross the zoomed panel's tick labels.
    indicator = ax.indicate_inset_zoom(ax_zoom, edgecolor='white', alpha=0.9)
    for connector in indicator.connectors:
        connector.set_visible(False)

    plt.show()
    pdb.set_trace()


def get_psd_sizes(
    n_samples: int,
    cut_time: float,
    nominal_block_length: float,
    fs: float,
):
    n_samples_to_cut = 0
    if cut_time > 0:
        n_samples_to_cut = np.round(
            cut_time * fs
        ).astype(int)
    n_samples = n_samples - (2 * n_samples_to_cut)
    n_samples_per_block = int(
        2 ** np.ceil(np.log2(nominal_block_length * fs))
    )
    n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
    if n_blocks == 0:
        n_blocks = 1
        n_samples_per_block = n_samples
    n_freq = n_samples_per_block // 2 + 1
    return n_samples_per_block, n_freq, n_samples_to_cut



class AnalyzeNoisePickup(DataRoutine):
    name = 'AnalyzeNoisePickup'
    version = '1.0.0'

    produces: ClassVar[set] = {
        '/noise_pickup/',
        '/noise_pickup/freq_good',
        '/noise_pickup/freq_pickup',
        '/noise_pickup/psd_good',
        '/noise_pickup/psd_pickup',
    }

    def __init__(
        self,
        za_range: tuple[int, int],
        select_detectors: list[int],
        nominal_block_length: float = 10,
        cut_time: float = 0.0,
    ):
        super().__init__(
            za_range=za_range,
            select_detectors=select_detectors,
            nominal_block_length=nominal_block_length,
            cut_time=cut_time,
        )

    def _run(self, pdata, inputs):
        created = []
        if pdata.has('/noise_pickup', exact_match=True):
            _logger.warning(
                f'{self.name}: noise_pickup group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['noise_pickup']
        hdf5_group = pdata.create_group('noise_pickup')
        created.append(hdf5_group.name)

        za_range = self.params['za_range']
        select_detectors = self.params['select_detectors']
        cut_time = self.params['cut_time']
        nominal_block_length = self.params['nominal_block_length']

        tel_az = pdata.get_telescope_az(0)[:]
        tel_za = pdata.get_telescope_za(0)[:]
        timestamp = pdata.get_timestamp(0)[:]
        data_freq_diss = pdata.get_data_freq_diss(0)[:]

        f = pdata.get_detector_f(0)
        f[pdata.get_offres_ind(0)] = 1
        data = (
            data_freq_diss
            / f[np.newaxis, :, np.newaxis]
        )

        # Find pickup samples
        pickup_samples = np.argwhere((za_range[0] <= tel_za) & (tel_za <= za_range[1])).flatten()
        good_samples = np.arange(pickup_samples[-1] + 1, pdata.get_n_samples(0))

        # Determine the number of blocks for computing the PSD
        fs = pdata.get_fs(0)
        n_tones = pdata.get_n_tones(0)

        n_samples_per_block_pickup, n_freq_pickup, n_samples_to_cut_pickup = get_psd_sizes(
            pickup_samples.size,
            cut_time,
            nominal_block_length,
            fs
        )
        n_samples_per_block_good, n_freq_good, n_samples_to_cut_good = get_psd_sizes(
            good_samples.size,
            cut_time,
            nominal_block_length,
            fs
        )

        freq_pickup = np.zeros(n_freq_pickup)
        psd_pickup = np.zeros((2, n_tones, n_freq_pickup))
        freq_good = np.zeros(n_freq_good)
        psd_good = np.zeros((2, n_tones, n_freq_good))

        sample_idx = pickup_samples[n_samples_to_cut_pickup:-n_samples_to_cut_pickup] if n_samples_to_cut_pickup > 0 else pickup_samples
        data_pickup = data[
            ..., sample_idx,
        ]
        this_freq, this_psd = signal.welch(
            data_pickup,
            fs,
            nperseg=n_samples_per_block_pickup,
        )
        freq_pickup[:] = this_freq
        psd_pickup[:] = this_psd

        sample_idx = good_samples[n_samples_per_block_good] if n_samples_to_cut_good > 0 else good_samples
        data_good = data[
            ..., sample_idx,
        ]
        this_freq, this_psd = signal.welch(
            data_good,
            fs,
            nperseg=n_samples_per_block_good,
        )
        freq_good[:] = this_freq
        psd_good[:] = this_psd

        hdf5_group.create_dataset('freq_good', data=freq_good)
        hdf5_group.create_dataset('freq_pickup', data=freq_pickup)
        hdf5_group.create_dataset('psd_good', data=psd_good)
        hdf5_group.create_dataset('psd_pickup', data=psd_pickup)

        self._plot_psds(pdata)

        return RoutineResult(
            created={'input': list(self.produces)}
        )

    def _plot_psds(self, pdata: ProcessedData):
        freq_pickup = pdata['noise_pickup/freq_pickup'][:]
        psd_pickup = pdata['noise_pickup/psd_pickup'][:]
        freq_good = pdata['noise_pickup/freq_good'][:]
        psd_good = pdata['noise_pickup/psd_good'][:]
        detector_f = pdata.get_detector_f(0)
        chanmask = pdata.get_chanmask(0)

        pdf_path = pdata.folder / f'{pdata.file_stub}_noise_pickup_psd.pdf'
        with PdfPages(pdf_path) as pdf:
            avg_fig = plot_psd_df_over_f(
                freq_good,
                psd_good,
                show_error_band=True,
                show_flat_spectrum_level=True,
                title='Average PSDs',
                add_legend=False,
                freq_color='b',
                diss_color='r',
                ylim=(1e-20, 1e-11),
                label='Good Samples'
            )
            avg_ax = avg_fig.get_axes()[0]
            plot_psd_df_over_f(
                freq_pickup,
                psd_pickup,
                ax=avg_ax,
                show_error_band=True,
                show_flat_spectrum_level=True,
                add_legend=True,
                legend_fontsize=10,
                freq_color='o',
                diss_color='g',
                label='Pickup Samples'
            )
            pdf.savefig(avg_fig)
            plt.close(avg_fig)
            for i_tone in tqdm.tqdm(range(pdata.get_n_tones(0))):
            # for i_tone in [0, 183, 213, 300, 318]:
                suffix = 'Off-Resonance' if chanmask[i_tone] == ChanmaskValue.OFF_RESONANCE else ''
                title = ' - '.join(filter(None, [f'Tone {i_tone}', suffix]))
                fig = plot_psd_df_over_f(
                    freq_good,
                    psd_good[:, i_tone],
                    f0=detector_f[i_tone],
                    show_flat_spectrum_level=True,
                    title=title,
                    add_legend=False,
                    freq_color='b',
                    diss_color='r',
                    # ylim=(1e-20, 1e-11),
                    label='Good Samples'
                )
                ax = fig.get_axes()[0]
                plot_psd_df_over_f(
                    freq_pickup,
                    psd_pickup[:, i_tone],
                    ax=ax,
                    f0=detector_f[i_tone],
                    show_flat_spectrum_level=True,
                    # title=title,
                    add_legend=True,
                    legend_fontsize=10,
                    freq_color='o',
                    diss_color='g',
                    # ylim=(1e-20, 1e-11),
                    label='Pickup Samples'
                )
                if chanmask[i_tone] == ChanmaskValue.OFF_RESONANCE:
                    fig.set_facecolor(OFF_RESONANCE_COLOR)
                    # ax.set_facecolor(OFF_RESONANCE_COLOR)
                pdf.savefig(fig)
                plt.close(fig)






def analyze_noise_pickup(
    date: str,
    setnum: int,
    za_range: tuple[float, float],
    select_detectors: list[int],
):
    """Analyze the noise pickup present in 20261105 datasets."""
    cdata = ConsolidatedData.load(date, setnum, 'r')
    pdata = cdata.create_processed_data()
    cdata.close()

    # Load datasets
    tel_az = pdata.get_telescope_az(0)[:]
    tel_za = pdata.get_telescope_za(0)[:]
    timestamp = pdata.get_timestamp(0)[:]
    data_freq_diss = pdata.get_data_freq_diss(0)[:]
    detector_f = pdata.get_detector_f(0)

    # Find pickup samples
    pickup_samples = np.argwhere((za_range[0] <= tel_za) & (tel_za <= za_range[1])).flatten()

    # Plot raw data streams of select detectors, before any cleaning
    plot_select_detectors(
        pdata,
        select_detectors,
        pickup_samples,
        f'{pdata.file_stub} - Selected Detectors (Before Processing)',
    )



def plot_select_detectors(
    pdata: ProcessedData,
    select_detectors: list[int],
    pickup_samples: npt.NDArray,
    title: str,
    show: bool=False,
):
    # timestamp = pdata.get_timestamp(0)[:]
    data_freq_diss = pdata.get_data_freq_diss(0)[:]
    detector_f = pdata.get_detector_f(0)

    pickup_length = np.ptp(pickup_samples)
    start = max(pickup_samples[0] - pickup_length // 4, 0)
    end = min(pickup_samples[-1] + pickup_length // 4, pdata.get_n_samples(0))
    samples = np.arange(start, end, dtype=int)

    # Plot raw data streams of select detectors, before any cleaning
    # fig = Figure()
    fig = plt.figure(figsize=(20, 10))
    fig.suptitle(title)
    ax = fig.subplots(1, 1)
    for i_tone, i_res in enumerate(select_detectors):
        df_over_f = data_freq_diss[0, i_res] / detector_f[i_res]
        # Normalize to [-1, 1]
        normalized_data = df_over_f / np.nanmax(np.abs(df_over_f))
        normalized_data -= (2 * i_tone)  # Offset on y axis
        ax.plot(samples, normalized_data[start:end], label=f'Tone {i_res}')
        ax.plot(pickup_samples, normalized_data[pickup_samples], linestyle='--', color='k')

    ax.set_xlabel('Sample')
    ax.set_ylabel('Normalized Signal (df/f)')
    ax.set_yticks([])
    fig.legend()
    fig.savefig('pickup.png', dpi=300)
    ax.set_xlim(1750, 4250)
    fig.savefig('pickup_zoom.png', dpi=300)

    if show:
        fig.show()
        # plt.show()





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
    noise_removal_lp_filt_freq_offres = 0  # Filter disabled if set to 0
    noise_removal_lp_filt_freq_onres = 0  # Filter disabled if set to 0
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
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=True,
        dataset=dataset,
        az_trim=0,
        za_trim=0,
        dpix=0.02,
        r0=0.0,
    )
    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap(dpi=100)

    pipeline = Pipeline([
        noise_removal_offres,
        noise_removal_onres,
        hp_filter,
        lp_filter,
        clean_tod,
        bin_tod_to_map,
        analyze_beammap,
        plot_beammap,
    ])

    date = '20261105'
    setnum = 1001


    # tod_file = '/data/20261028/20261028_Device_aSi1_Channel2_telescope_275mK_20260804_TOD_set1001.h5'
    # tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260804'
    # with RFSoCParameters.load(tile_name, 'r') as params:
    #     params.append_to_TOD(tod_file)
    # sweep = LoSweepData.load_most_recent(tile_name)
    # if sweep is not None:
    #     sweep.append_to_TOD(tod_file)

    # pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata, _ = pipeline.from_consolidated_data(date, setnum)
    pdata = ProcessedData.load(date, setnum)
    # pipeline.run(pdata)

    # pdata.print_history()
    # pdb.set_trace()

    # bin_tod_to_map.apply(pdata)
    # analyze_beammap.apply(pdata)

    # cdata = ConsolidatedData.load(date, setnum, 'r')
    # pdata = cdata.create_processed_data()
    # plt.imshow(pdata['map/map_val'][300], extent=get_extent(pdata['map/map_az'][:], pdata['map/map_za'][:], 0.02))
    # plt.show()
    # pdb.set_trace()
    plot_one_beammap(
        pdata,
        plot_beammap,
        213,
    )
    # za_range = (88.5, 88.8)
    # tel_za = pdata.get_telescope_za(0)[:]
    # pickup_samples = np.argwhere((za_range[0] <= tel_za) & (tel_za <= za_range[1])).flatten()
    # tod_file = '/data/20261105/20261105_Device_aSi2_Channel3_telescope_275mK_20260804_TOD_set1002.h5'
    # raw_data = RawDataFile(tod_file, 'r')
    # i = raw_data.adc_i[:]
    # plt.plot(i[318, :pickup_samples[-1] * 16])
    # plt.show()
    # pdb.set_trace()
    # plot_select_detectors(
    #     pdata,
    #     [
    #         50, 51,
    #         170,
    #         232,
    #         300, 318, 328,
    #         437,
    #         575,
    #         635,
    #         701, 711, 768,
    #         860, 896,
    #         913, 914, 925
    #     ],
    #     # [
    #     #     183, 213, 300, 318
    #     # ],
    #     pickup_samples,
    #     f'{pdata.file_stub} Noise Pickup in Selected Data Streams (Before Processing)',
    #     # f'{pdata.file_stub} Noise Pickup in Selected Data Streams (After Processing)',
    #     show=True,
    # )
    # pdb.set_trace()

    # analyze_pickup = AnalyzeNoisePickup(
    #     za_range,
    #     [
    #         183, 213, 300, 318
    #     ],
    # )
    # analyze_pickup.apply(pdata)


    # pdata = ProcessedData.load(date, setnum)

    # date = '20261105'
    # for setnum in [1001, 1002, 1003, 1004]:
    #     pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    #     # pdata = ProcessedData.loaddate, setnum)
    #     pipeline.run(pdata)
    #     print(f'Finished processing {date}_set{setnum}\n')
    #     pdata.close()
    # pipeline.run(pdata)

    # bin_tod_to_map.apply(pdata)
    # analyze_beammap.apply(pdata)
    # plot_beammap.apply(pdata)
    # pdb.set_trace()

    # for setnum in [1001, 1004, 1005, 1006]:
    #     pdata = ProcessedData.load(date, setnum)
    #     pipeline.run(pdata)
    #     pdata.close()

    # pdb.set_trace()
    # bin_tod_to_map.apply(pdata)
    # analyze_beammap.apply(pdata)
    # plot_single_beammap(
    #     pdata,
    #     112,
    # )
    # plot_beammap.apply(pdata)
    # pdb.set_trace()
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




