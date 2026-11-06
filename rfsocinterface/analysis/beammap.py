"""Beam map analysis routines."""

import logging
import typing
from typing import ClassVar

import numpy as np
import numpy.typing as npt
import tqdm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1 import make_axes_locatable
from packaging.version import Version
from scipy.optimize import curve_fit

from rfsocinterface.core.data import (
    BIN_TOD_INTO_MAP_CHANGE_VERSION,
    MAP_CHANGE_VERSION,
    DataRoutine,
    ProcessedData,
    RoutineResult,
    get_extent,
    register_routine,
)
from rfsocinterface.core.utils import (
    BAD_RESONANCE_COLOR,
    DEFAULT_DATA_DIRECTORY,
    OFF_RESONANCE_COLOR,
    elide_text,
    get_beammap_pdf_template,
    mutual_nearest_pairs_between_groups,
)

_logger = logging.getLogger(__name__)

# Beam fit statistics at or above this magnitude (as displayed) are treated as failed
# fits and shown as "n/a" in PlotBeamMap.
_MAX_STAT_MAGNITUDE = 1e6


N_GAUSS_2D_PARAMS = 6


def gauss_2d(
    xy_coords: tuple[npt.NDArray, npt.NDArray],
    amp: float,
    x0: float,
    y0: float,
    fwhm_x: float,
    fwhm_y: float,
    offset: float,
) -> npt.NDArray:
    """Create a 2D Gaussian."""
    (x, y) = xy_coords
    sigma_x = fwhm_x / (2 * np.sqrt(2 * np.log(2)))
    sigma_y = fwhm_y / (2 * np.sqrt(2 * np.log(2)))
    return offset + amp * np.exp(
        -((x - x0) ** 2) / (2.0 * sigma_x**2) - (y - y0) ** 2 / (2.0 * sigma_y**2)
    )


@register_routine
class AnalyzeBeamMap(DataRoutine):
    """Analyze a beam map.

        Fits a 2D gaussian to the map for each reasonator to characterize the
    angular response.

    Creates the following items in the HDF5 file:
    - /beammap: group containing the beammap datasets.
    - /beammap/az_center: 1D array of length n_tones containing the center of the
        fitted gaussian in azimuth.
    - /beammap/za_center: 1D array of length n_tones containing the center of the
        fitted gaussian in zenith angle.
    - /beammap/amplitude: 1D array of length n_tones containing the amplitude of the
        fitted gaussian.
    - /beammap/chisq: 1D array of length n_tones containing the chi squared of the
        fitted gaussian.
    - /beammap/fwhm_az: 1D array of length n_tones containing the FWHM of the fitted
        gaussian in azimuth.
    - /beammap/fwhm_za: 1D array of length n_tones containing the FWHM of the fitted
        gaussian in zenith angle.
    """

    name = 'AnalyzeBeamMap'
    version = '2.2.0'

    requires: ClassVar[set[str]] = {
        '/map',
        '/map/map_val',
        '/map/map_az',
        '/map/map_za',
    }

    produces: ClassVar[set[str]] = {
        '/beammap',
        '/beammap/az_center',
        '/beammap/za_center',
        '/beammap/amplitude',
        '/beammap/snr',
        '/beammap/chisq',
        '/beammap/fwhm_az',
        '/beammap/fwhm_za',
    }

    def __init__(
        self,
        initial_fwhm: float = 0.1,
        min_fwhm: float = 0.01,
        max_fwhm: float = 1.0,
        az_bounds_offset: float = 0.2,
        za_bounds_offset: float = 0.2,
        max_radius: float = 0.1,
        maxfev: int = 10000,
    ):
        """Initialize the AnalyzeBeamMap routine.

        Arguments:
            initial_fwhm (float, optional): The initial guess for FWHM for the fit.
                Defaults to 0.1.
            min_fwhm (float, optional): The minimum FWHM for the fit. Defaults to 0.01.
            max_fwhm (float, optional): The maximum FWHM for the fit. Defaults to 1.
            az_bounds_offset (float, optional): Relative offset to use when determining
                the bounds of the center of the Gaussian in azimuth. Defaults to 0.2.
            za_bounds_offset (float, optional): Relative offset to use when determining
                the bounds of the center of the Gaussian in zenith angle. Defaults to
                0.2.
            max_radius (float, optional): The maximum radius to use when determining the
                location of the bright source in teh map. Defaults to 0.1.
            maxfev (int, optional): Maximum function evaluations to try before
                abandoning the fit. Defaults to 10000.
        """
        super().__init__(
            initial_fwhm=initial_fwhm,
            min_fwhm=min_fwhm,
            max_fwhm=max_fwhm,
            az_bounds_offset=abs(az_bounds_offset),
            za_bounds_offset=abs(za_bounds_offset),
            max_radius=max_radius,
            maxfev=maxfev,
        )

    @typing.override
    def _inputs(self, pdata: ProcessedData):
        return list(self.requires)

    def _initialize_datasets(self, pdata: ProcessedData):
        if pdata.has('/beammap', exact_match=True):
            _logger.warning(
                f'{self.name}: Beam Map group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['beammap']
        beammap_group = pdata.create_group('beammap')
        beammap_group.create_dataset(
            'az_center', (pdata.total_tones,), dtype=np.float64
        )
        beammap_group.create_dataset(
            'za_center', (pdata.total_tones,), dtype=np.float64
        )
        beammap_group.create_dataset(
            'amplitude', (pdata.total_tones,), dtype=np.float64
        )
        beammap_group.create_dataset('snr', (pdata.total_tones,), dtype=np.float64)
        beammap_group.create_dataset('chisq', (pdata.total_tones,), dtype=np.float64)
        beammap_group.create_dataset('fwhm_az', (pdata.total_tones,), dtype=np.float64)
        beammap_group.create_dataset('fwhm_za', (pdata.total_tones,), dtype=np.float64)

    @typing.override
    def _run(self, pdata: ProcessedData, inputs: list[str]):
        self._initialize_datasets(pdata)

        az = pdata['map/map_az'][:][np.newaxis, :]
        za = pdata['map/map_za'][:][:, np.newaxis]
        map_val = pdata['map/map_val'][:]

        _, most_recent_map_step = pdata.find_most_recent_history_step('BinTODIntoMap')
        bintod_version = Version(most_recent_map_step.attrs['version'].strip('"'))
        old_format = 'map/channel_map_val' not in pdata and (
            pdata.get_version() < MAP_CHANGE_VERSION
            or bintod_version < BIN_TOD_INTO_MAP_CHANGE_VERSION
        )
        if old_format:
            map_val = np.transpose(map_val, (0, 2, 1))

        az_center = pdata['beammap/az_center']
        za_center = pdata['beammap/za_center']
        amplitude = pdata['beammap/amplitude']
        snr = pdata['beammap/snr']
        chisq = pdata['beammap/chisq']
        fwhm_az = pdata['beammap/fwhm_az']
        fwhm_za = pdata['beammap/fwhm_za']

        initial_fwhm = self.params['initial_fwhm']
        min_fwhm = self.params['min_fwhm']
        max_fwhm = self.params['max_fwhm']
        az_bounds_offset = self.params['az_bounds_offset']
        za_bounds_offset = self.params['za_bounds_offset']
        maxfev = self.params['maxfev']
        max_radius = self.params['max_radius']

        n_tones = pdata.onres_ind.size
        _logger.info(f'{self.name}: Analyzing beam map...')
        for i, i_res in enumerate(pdata.onres_ind):
            if i == n_tones // 2:
                _logger.info(f'{self.name}: Halfway done analyzing beam map...')
            this_map = map_val[i_res]
            # Pixels that weren't observed, such as the rows left empty when the pixels
            # are smaller than the scan spacing, are NaN. These have no measurement, so
            # they can't be part of the fit. If they were treated as zero signal, the
            # best fit would be a spike that squeezes between the empty rows.
            has_data = np.isfinite(this_map)
            if not np.any(has_data):
                _logger.warning(f'{self.name}: Map for tone {i_res} is empty.')
                continue

            za_idx, az_idx = np.unravel_index(np.nanargmax(this_map), this_map.shape)
            separation = np.sqrt((az - az[0, az_idx]) ** 2 + (za - za[za_idx, 0]) ** 2)
            index = np.argwhere((separation < max_radius) & has_data)
            if index.shape[0] <= N_GAUSS_2D_PARAMS:
                _logger.warning(
                    f'{self.name}: Too few pixels around the peak to fit tone {i_res}.'
                )
                continue

            this_az = az[0, index[:, 1]]
            this_za = za[index[:, 0], 0]
            this_val = this_map[index[:, 0], index[:, 1]]

            az_center[i_res] = np.sum(this_az * this_val) / np.sum(this_val)
            za_center[i_res] = np.sum(this_za * this_val) / np.sum(this_val)
            amplitude[i_res] = np.max(this_val)

            sigma_z = np.full(
                int(np.size(this_val)),
                (np.percentile(this_val, 84) - np.percentile(this_val, 16)) * 0.5,
            )
            start_params = (
                np.max(this_val),
                az_center[i_res],
                za_center[i_res],
                initial_fwhm,
                initial_fwhm,
                np.median(this_val),
            )
            bounds = (
                # Lower bounds
                (
                    0.0,
                    az_center[i_res] - az_bounds_offset,
                    za_center[i_res] - za_bounds_offset,
                    min_fwhm,
                    min_fwhm,
                    -np.max(np.abs(this_val)),
                ),
                # Uppwer bounds
                (
                    10.0 * np.max(this_val),
                    az_center[i_res] + az_bounds_offset,
                    za_center[i_res] + za_bounds_offset,
                    max_fwhm,
                    max_fwhm,
                    np.max(np.abs(this_val)),
                ),
            )
            try:
                popt, pcov = curve_fit(
                    gauss_2d,
                    (this_az, this_za),
                    this_val,
                    p0=start_params,
                    sigma=sigma_z,
                    absolute_sigma=True,
                    maxfev=maxfev,
                    bounds=bounds,
                )
            except RuntimeError:
                _logger.warning(
                    f'{self.name}: Fit for tone {i_res} failed.'
                    'Setting all values to zero.'
                )
                popt = np.zeros(6)
                pcov = np.zeros((6, 6))
                continue

            az_center[i_res] = popt[1]
            za_center[i_res] = popt[2]
            amplitude[i_res] = popt[0]
            fwhm_az[i_res] = np.abs(popt[3])
            fwhm_za[i_res] = np.abs(popt[4])
            snr[i_res] = popt[0] / np.sqrt(pcov[0, 0])
            chisq[i_res] = np.sum(
                (
                    (
                        this_val
                        - gauss_2d(
                            (this_az, this_za),
                            popt[0],
                            popt[1],
                            popt[2],
                            popt[3],
                            popt[4],
                            popt[5],
                        )
                    )
                    ** 2
                    / sigma_z**2
                )
                / (np.size(this_val) - 5.0)
            )

        return RoutineResult(created={'input': self.produces})


@register_routine
class PlotBeamMap(DataRoutine):
    """Plot a beam map, post-analysis."""

    name = 'PlotBeamMap'
    version = '2.2.0'

    requires: ClassVar[set[str]] = {
        '/map',
        '/map/map_val',
        '/map/map_az',
        '/map/map_za',
        '/beammap',
        '/beammap/az_center',
        '/beammap/za_center',
        '/beammap/amplitude',
        '/beammap/snr',
        '/beammap/chisq',
        '/beammap/fwhm_az',
        '/beammap/fwhm_za',
    }

    def __init__(
        self,
        high_snr_percentile: float = 55,
        nrows: int = 10,
        ncols: int = 10,
        show_all: bool = True,
        savefile: str | None = None,
        save_dir: str = DEFAULT_DATA_DIRECTORY,
        dpi: float = 100,
        zoom_half_width: float | None = None,
    ):
        """Initialize the PlotBeamMap routine.

        Arguments:
            high_snr_percentile (float, optional): The percentile for determining a high
                SNR. Defaults to 55.
            nrows (int, optional): The number of rows for plots in one page. Defaults to
                10.
            ncols (int, optional): The number of columns for plots in one page. Defaults
                to 10.
            show_all (bool, optional): Whether to include all resonances in the pdf.
                If False, will only who on-resonance tones. Defaults to False.
            savefile (str, optional): Where to save the pdf. If `None` is provided, will
                auto-generate a file name using `get_beammap_pdf_template`. Defaults to
                `None`.
            save_dir (str, optional): The directory to save the savefile to. Passed as
                an argument to `get_beammap_pdf_template`, and as such is only used if
                `savefile` is `None`. Defaults to `DEFAULT_DATA_DIRECTORY`.
            dpi (float, optional): Dots per inch to use in the figures. Defaults to 300.
            zoom_half_width (float, optional): Half-width (in degrees) of the zoomed
                region shown next to each individual beam map. If `None`, uses 1.5x
                the larger fitted FWHM, falling back to 10% of the map size if the
                fit failed. Defaults to `None`.
        """
        super().__init__(
            high_snr_percentile=high_snr_percentile,
            nrows=nrows,
            ncols=ncols,
            show_all=show_all,
            savefile=savefile,
            save_dir=save_dir,
            dpi=dpi,
            zoom_half_width=zoom_half_width,
        )

    @typing.override
    def _inputs(self, pdata: ProcessedData):
        return list(self.requires)

    @typing.override
    def _run(self, pdata: ProcessedData, inputs: list[str]):
        # Load necessary datasets
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

        _, most_recent_map_step = pdata.find_most_recent_history_step('BinTODIntoMap')
        bintod_version = Version(most_recent_map_step.attrs['version'].strip('"'))
        old_format = 'map/channel_map_val' not in pdata and (
            pdata.get_version() < MAP_CHANGE_VERSION
            or bintod_version < BIN_TOD_INTO_MAP_CHANGE_VERSION
        )

        # Which tones to use
        tones_to_plot = (
            np.arange(pdata.total_tones, dtype=int)
            if self.params['show_all']
            else pdata.onres_ind
        )

        # Initialize PDF
        savefile = self.params['savefile']
        if savefile is None:
            savefile = get_beammap_pdf_template(
                pdata.date, pdata.setnum, data_dir=self.params['save_dir']
            )
        pdf = PdfPages(savefile)

        nrows = self.params['nrows']
        ncols = self.params['ncols']
        page_size = nrows * ncols

        # Make scatter plot of beam centers
        self._plot_beam_centers(
            pdf,
            az_center,
            za_center,
            amplitude,
            extent,
        )

        # Create the big group plots
        _logger.info(f'{self.name}: Creating grid pages...')
        fig = self._new_figure()
        axes = fig.subplots(nrows, ncols)
        for ax in axes.flatten():
            ax.set_axis_off()
        i_subplot = 1
        for i_loop, i_tone_absolute in enumerate(tones_to_plot):
            if i_loop == tones_to_plot.size // 2:
                _logger.info(f'{self.name}: Halfway done creating grid pages...')
            ax = axes.flatten()[i_subplot - 1]
            plot_data = map_val[i_tone_absolute]
            if old_format:
                plot_data = np.transpose(plot_data)
            ax.imshow(
                plot_data,
                extent=extent,
                aspect='equal',
                cmap='jet',
                interpolation='bilinear',
            )

            # Draw a rectangle around the subplot indicating off-resonance / bad tones
            if chanmask[i_tone_absolute] != 1:
                line_color = (
                    OFF_RESONANCE_COLOR
                    if chanmask[i_tone_absolute] == 0
                    else BAD_RESONANCE_COLOR
                )
                auto_axis = ax.axis()
                rec = Rectangle(
                    (auto_axis[0], auto_axis[2]),
                    auto_axis[1] - auto_axis[0],
                    auto_axis[3] - auto_axis[2],
                    fill=False,
                    lw=2,
                    edgecolor=line_color,
                )
                rec = ax.add_patch(rec)
                rec.set_clip_on(False)

            if i_subplot == page_size:
                pdf.savefig(fig)
                fig = self._new_figure()
                axes = fig.subplots(nrows, ncols)
                for ax in axes.flatten():
                    ax.set_axis_off()
                i_subplot = 0
            i_subplot += 1

        if i_subplot > 1:
            pdf.savefig(fig)

        # Create individul plots for each tone
        _logger.info(f'{self.name}: Creating individual resonance plots...')
        for i_loop, i_tone_absolute in tqdm.tqdm(enumerate(tones_to_plot)):
            if i_loop == tones_to_plot.size // 2:
                _logger.info(f'{self.name}: Halfway done creating individual plots...')

            fig = self._new_figure(figsize=(12, 5.5))
            ax, ax_zoom = fig.subplots(1, 2)

            # data_to_plot = np.flip(np.transpose(map_val[i_tone_absolute][::-1]), 1)
            data_to_plot = map_val[i_tone_absolute]
            if old_format:
                data_to_plot = np.transpose(data_to_plot)
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
            x_lim, y_lim = self._zoom_limits(
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
                self._add_stats_text(
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
            title, facecolor = self._tone_title(
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

            pdf.savefig(fig)

        pdf.close()
        return RoutineResult()

    def _new_figure(self, **kwargs) -> Figure:
        """Create a figure that is not registered with pyplot.

        Figures created through pyplot get a GUI window with interactive backends
        (e.g. QtAgg). Closing those windows only schedules their deletion for the
        GUI event loop, which never runs in a script, so each one keeps its full
        render buffer alive and memory grows with every page. A bare `Figure` has
        no window and is freed as soon as it goes out of scope.
        """
        return Figure(dpi=self.params['dpi'], **kwargs)

    @staticmethod
    def _add_stats_text(
        fig: Figure,
        extent: tuple[float, float, float, float],
        amplitude: float,
        chisq: float,
        snr: float,
        fwhm_az: float,
        fwhm_za: float,
        az_center: float,
        za_center: float,
    ):
        """Add a box with the beam fit statistics to the bottom of the figure.

        Values from failed fits (NaN, or absurd values like 1e285) are shown as
        "n/a". Centers must lie within the map and FWHMs must be between one pixel
        and the map size. The other values have no natural range, so they only need
        to be finite and print as less than `_MAX_STAT_MAGNITUDE`.
        """

        def fmt(value: float, spec: str, valid: bool = True) -> str:
            ok = valid and np.isfinite(value) and abs(value) < _MAX_STAT_MAGNITUDE
            return format(value, spec) if ok else 'n/a'

        center_ok = PlotBeamMap._center_in_map(extent, az_center, za_center)
        bbox_pad = 0.3
        t = AnchoredText(
            f'Amplitude = {fmt(amplitude * 1e5, "2f")}    '
            f'chisq = {fmt(chisq, ".3f", chisq >= 0)}    '
            f'snr = {fmt(snr, ".3f")}\n'
            f'fwhm_az = {fmt(fwhm_az, ".2f")}    '
            f'fwhm_za = {fmt(fwhm_za, ".2f")}\n'
            f'az_center = {fmt(az_center, ".2f", center_ok)}    '
            f'za_center = {fmt(za_center, ".2f", center_ok)}',
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

    @staticmethod
    def _tone_title(
        pdata: ProcessedData,
        i_tone_absolute: int,
        f0: float,
    ) -> tuple[str, str | None]:
        """Get the plot title and face color for a tone.

        The face color is `None` for good on-resonance tones.
        """
        i_chan, i_tone_relative = pdata.get_relative_tone_index(i_tone_absolute)
        if pdata.n_chan > 1:
            # Spefcify the tile name if there are multiple channels
            tile_name = pdata.get_tile_name(i_chan)
            title = (
                f'{elide_text(tile_name, max_len=30)} - Tone {i_tone_relative}\n'
                f'($f_0$={f0 * 1e-6:.3f} MHz)'
            )
        else:
            title = f'Tone {i_tone_relative} ($f_0$={f0 * 1e-6:.3f} MHz)'

        facecolor = None
        chanmask_val = pdata.chanmask[i_tone_absolute]
        if chanmask_val != 1:
            if chanmask_val == 0:
                title += ' (Off-resonance)'
                facecolor = OFF_RESONANCE_COLOR
            else:
                title += ' (Bad Resonance)'
                facecolor = BAD_RESONANCE_COLOR
        return title, facecolor

    @staticmethod
    def _map_size(extent: tuple[float, float, float, float]) -> float:
        """Get the length of the map's shorter side."""
        return min(abs(extent[1] - extent[0]), abs(extent[3] - extent[2]))

    @staticmethod
    def _center_in_map(
        extent: tuple[float, float, float, float],
        az_center: float,
        za_center: float,
    ) -> bool:
        """Check whether a fitted beam center lies within the map (False for NaN)."""
        az_min, az_max = sorted(extent[:2])
        za_min, za_max = sorted(extent[2:])
        return bool(az_min <= az_center <= az_max and za_min <= za_center <= za_max)

    def _zoom_limits(
        self,
        data: npt.NDArray,
        map_az: npt.NDArray,
        map_za: npt.NDArray,
        extent: tuple[float, float, float, float],
        dpix: float,
        az_center: float,
        za_center: float,
        fwhm_az: float,
        fwhm_za: float,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Get the x and y limits of the zoomed-in region around a beam.

        Centers on the fitted beam center, falling back to the brightest pixel if the
        fit failed. The limits preserve the axis orientation given by `extent`.

        Failed fits can produce NaN, zero, or absurdly large (e.g. 1e285) centers and
        FWHMs, so the fit values are only used when they lie within the map. Using
        them unchecked as axis limits can make matplotlib error out or exhaust memory.
        """
        az_min, az_max = sorted(extent[:2])
        za_min, za_max = sorted(extent[2:])
        map_size = self._map_size(extent)

        x0, y0 = az_center, za_center
        if not self._center_in_map(extent, x0, y0):
            if np.all(np.isnan(data)):
                x0 = (az_min + az_max) / 2
                y0 = (za_min + za_max) / 2
            else:
                i_za, i_az = np.unravel_index(np.nanargmax(data), data.shape)
                x0 = map_az[i_az]
                y0 = map_za[i_za]

        half_width = self.params['zoom_half_width']
        if half_width is None:
            fwhm = np.fmax(fwhm_az, fwhm_za)  # NaN only if both are NaN
            # A beam narrower than a pixel or wider than the map is a failed fit.
            # (Comparison is False for NaN.)
            half_width = 1.5 * fwhm if dpix <= fwhm < map_size else 0.1 * map_size
        half_width = float(np.clip(half_width, 2 * dpix, map_size / 2))

        # Keep the same axis orientation as the full map (extent may be inverted)
        x_dir = np.sign(extent[1] - extent[0]) or 1
        y_dir = np.sign(extent[3] - extent[2]) or 1
        x_lim = (x0 - x_dir * half_width, x0 + x_dir * half_width)
        y_lim = (y0 - y_dir * half_width, y0 + y_dir * half_width)
        return x_lim, y_lim

    def _plot_beam_centers(
        self,
        pdf: PdfPages,
        az_center: npt.NDArray,
        za_center: npt.NDArray,
        amplitude: npt.NDArray,
        extent: tuple[float, float, float, float],
    ):
        """Create a scatter plot of the beam cetners for each resonator."""
        high_snr_percentile = self.params['high_snr_percentile']

        high_snr_ind = np.argwhere(
            amplitude > np.percentile(amplitude, high_snr_percentile),
        ).flatten()

        # Create scatter plot of beam centers
        _logger.info(f'{self.name}: Creating beam center scatter plot...')
        fig = self._new_figure()
        ax = fig.subplots()
        ax.scatter(az_center[high_snr_ind], za_center[high_snr_ind], marker='+')
        ax.axis('equal')
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_xlabel('X Position (deg)')
        ax.set_ylabel('Y Position (deg)')
        pdf.savefig(fig)


def combine_polarized_beammaps(
    pol1_data: ProcessedData,
    pol2_data: ProcessedData,
    new_tile_name: str,  # noqa: ARG001
    bad_resonators: npt.ArrayLike | None = None,
    focal_plane_center: str = 'top left',  # noqa: ARG001
    amplitude_normalization_percentile: float = 75,  # noqa: ARG001
    pdf_filename: str | None = None,  # noqa: ARG001
):
    """Determines various tile parameters from two beam maps of opposite polarizations.

    Creates a new params_file with detector_delta_x, detector_delta_y,
        detector_beam_ampl, and detector_pol.
    """
    good_ind = pol1_data.onres_ind
    if bad_resonators is not None:
        good_ind = np.setdiff1d(good_ind, bad_resonators)
    old_tile_name = pol1_data.get_channel_group(0).attrs['tile_name']  # noqa: F841
    chanmask = pol1_data.chanmask

    az_center_pol1 = pol1_data['beammap/az_center'][:]
    za_center_pol1 = pol1_data['beammap/za_center'][:]
    amplitude_pol1 = pol1_data['beammap/amplitude'][:]
    # chisq_pol1 = pol1_data['beammap/chisq'][:]
    # fwhm_az_pol1 = pol1_data['beammap/fwhm_az'][:]
    # fwhm_za_pol1 = pol1_data['beammap/fwhm_za'][:]

    az_center_pol2 = pol2_data['beammap/az_center'][:]
    za_center_pol2 = pol2_data['beammap/za_center'][:]
    amplitude_pol2 = pol2_data['beammap/amplitude'][:]
    # chisq_pol2 = pol2_data['beammap/chisq'][:]
    # fwhm_az_pol2 = pol2_data['beammap/fwhm_az'][:]
    # fwhm_za_pol2 = pol2_data['beammap/fwhm_za'][:]

    # Normalize amplitudes
    # sorted_amp_pol1 = np.argsort(amplitude_pol1)
    # sorted_amp_pol2 = np.argsort(amplitude_pol2)
    # amplitude_pol1 /= np.percentile(
    #     amplitude_pol1[onres_ind], amplitude_normalization_percentile)
    # amplitude_pol2 /= np.percentile(
    #     amplitude_pol2[onres_ind], amplitude_normalization_percentile)

    # Correct for shifts in source position
    az_center = np.zeros(chanmask.size)
    za_center = np.zeros(chanmask.size)
    detector_pol = np.zeros(chanmask.size, dtype=np.int8)
    beam_ampl = np.zeros(chanmask.size)

    for i_res in good_ind:
        if amplitude_pol1[i_res] > amplitude_pol2[i_res]:
            detector_pol[i_res] = 1
            az_center[i_res] = az_center_pol1[i_res]
            za_center[i_res] = za_center_pol1[i_res]
            beam_ampl[i_res] = amplitude_pol1[i_res]
        else:
            detector_pol[i_res] = 2
            az_center[i_res] = az_center_pol2[i_res]
            za_center[i_res] = za_center_pol2[i_res]
            beam_ampl[i_res] = amplitude_pol2[i_res]

    # TODO: Update params file

    # # Get positions relative to the center of the tile
    # delta_dx = az_center - np.median(az_center[good_ind])
    # delta_dy = za_center - np.median(za_center[good_ind])

    # Rotate by the rotation of the focal plane
    # az_median = np.median(az_center)
    # za_median = np.median(za_center)
    # az_center = az_center - np.median(az_center)
    # za_center = za_center - np.median(za_center)
    # rot = 1./90.*np.pi/2.
    # az_center = az_center * np.cos(rot) - za_center * np.sin(rot)
    # za_center = az_center * np.sin(rot) + za_center * np.cos(rot)
    # az_center += az_median
    # za_center += za_median

    # # Save to a new parameters file
    # copy_and_update_params_file(
    #     old_tile_name,
    #     new_tile_name,
    #     detector_delta_x=az_center,
    #     detector_delta_y=za_center,
    #     detector_beam_ampl=beam_ampl,
    #     detector_pol=detector_pol
    # )

    # Find pairs of points and use the median position
    pol1 = np.argwhere(detector_pol[good_ind] == 1).flatten()
    pol2 = np.argwhere(detector_pol[good_ind] == 2).flatten()  # noqa: PLR2004

    points = np.column_stack([az_center, za_center])[good_ind]
    pairs, _dist = mutual_nearest_pairs_between_groups(points, pol1, pol2, r=0.05)
    # plt.figure(figsize=(8, 8))
    # plt.scatter(points[pol2, 0], points[pol2, 1], color='blue')
    # plt.scatter(points[pol1, 0], points[pol1, 1], color='red')
    # for (i,j) in pairs:
    #     plt.plot([points[i, 0], points[j, 0]], [points[i, 1], points[j, 1]], '-k')
    # plt.gca().set_aspect('equal')
    # plt.gca().invert_yaxis()

    for i, j in pairs:
        mean_point = (points[i] + points[j]) / 2
        az_center[good_ind[i]] = mean_point[0]
        za_center[good_ind[i]] = mean_point[1]
        az_center[good_ind[j]] = mean_point[0]
        za_center[good_ind[j]] = mean_point[1]
        points[i, :] = mean_point
        points[j, :] = mean_point

    return az_center, za_center, detector_pol, beam_ampl
