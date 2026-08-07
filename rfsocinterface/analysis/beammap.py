"""Beam map analysis routines."""

import logging
import typing
from typing import ClassVar

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.offsetbox import AnchoredText
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy.optimize import curve_fit

from rfsocinterface.core.data import (
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
    get_beammap_pdf_template,
    get_detector_pos_pdf_template,
)

_logger = logging.getLogger(__name__)


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
    version = '1.0.0'

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
    def inputs(self, pdata: ProcessedData):
        return list(self.requires)

    def _initialize_datasets(self, pdata: ProcessedData):
        if pdata.has('beammap', exact_match=True):
            _logger.warning(
                f'{self.name}: Beam Map group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['beammap']
        beammap_group = pdata.create_group('beammap')
        beammap_group.create_dataset('az_center', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('za_center', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('amplitude', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('snr', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('chisq', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('fwhm_az', (pdata.n_tones,), dtype=np.float64)
        beammap_group.create_dataset('fwhm_za', (pdata.n_tones,), dtype=np.float64)

    @typing.override
    def run(self, pdata: ProcessedData, inputs: list[str]):
        self._initialize_datasets(pdata)

        az = pdata['map/map_az'][:][:, np.newaxis]
        za = pdata['map/map_za'][:][np.newaxis, :]
        map_val = pdata['map/map_val'][:]

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
            this_val = np.ndarray.flatten(map_val[i_res])
            this_val[np.isnan(this_val)] = 0

            max_index = np.argwhere(this_val == np.max(this_val))
            az_idx, za_idx = np.unravel_index(max_index[0], map_val[i_res].shape)
            az_max = az[az_idx, :]
            za_max = za[:, za_idx]
            separation = np.sqrt((az - az_max[0]) ** 2 + (za - za_max[0]) ** 2)
            index = np.argwhere(separation < max_radius)
            flat_index = np.ravel_multi_index(
                (index[:, 0], index[:, 1]), map_val[i_res].shape
            )

            az_center[i_res] = np.sum(
                az[index[:, 0]].squeeze() * this_val[flat_index]
            ) / np.sum(this_val[flat_index])
            za_center[i_res] = np.sum(
                za[:, index[:, 1]].squeeze() * this_val[flat_index]
            ) / np.sum(this_val[flat_index])
            amplitude[i_res] = np.max(this_val[index])

            this_az = np.ndarray.flatten(az[index[:, 0], :])
            this_za = np.ndarray.flatten(za[:, index[:, 1]])
            this_val = this_val[flat_index]
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
    version = '1.1.0'

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
        fom_cutoff: float = 50,
        nrows: int = 10,
        ncols: int = 10,
        show_all: bool = True,
        savefile: str | None = None,
        save_dir: str = DEFAULT_DATA_DIRECTORY,
        dpi: float = 300,
    ):
        """Initialize the PlotBeamMap routine.

        Arguments:
            high_snr_percentile (float, optional): The percentile for determining a high
                SNR. Defaults to 55.
            fom_cutoff (float, optional): The minimum FOM value to consider for high
                SNR. Defaults to 50.
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
        """
        super().__init__(
            high_snr_percentile=high_snr_percentile,
            fom_cutoff=fom_cutoff,
            nrows=nrows,
            ncols=ncols,
            show_all=show_all,
            savefile=savefile,
            save_dir=save_dir,
            dpi=dpi,
        )

    @typing.override
    def inputs(self, pdata: ProcessedData):
        return list(self.requires)

    @typing.override
    def run(self, pdata: ProcessedData, inputs: list[str]):
        # Load necessary datasets
        az_center = pdata['beammap/az_center'][:]
        za_center = pdata['beammap/za_center'][:]
        amplitude = pdata['beammap/amplitude'][:]
        snr = pdata['beammap/snr'][:]
        chisq = pdata['beammap/chisq'][:]
        fwhm_az = pdata['beammap/fwhm_az'][:]
        fwhm_za = pdata['beammap/fwhm_za'][:]
        map_val = pdata['map/map_val'][:]
        dpix = pdata['map'].attrs['dpix']
        units = pdata['map'].attrs.get('units', 'mK')
        extent = get_extent(pdata['map/map_az'][:], pdata['map/map_za'][:], dpix=dpix)
        chanmask = pdata.chanmask
        detector_f = pdata.detector_f()

        # Which tones to use
        tones_to_plot = (
            np.arange(pdata.n_tones, dtype=int)
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
        dpi = self.params['dpi']
        fom_cutoff = self.params['fom_cutoff']
        high_snr_percentile = self.params['high_snr_percentile']

        fom = np.divide(
            amplitude, chisq, out=np.zeros_like(amplitude), where=chisq != 0
        )
        high_snr_ind = np.argwhere(
            np.bitwise_and(
                amplitude > np.percentile(amplitude, high_snr_percentile),
                fom > fom_cutoff,
            )
        ).flatten()

        # Create scatter plot of beam centers
        _logger.info(f'{self.name}: Creating beam center scatter plot...')
        plt.scatter(az_center[high_snr_ind], za_center[high_snr_ind], marker='+')
        plt.axis('equal')
        plt.xlim(extent[0], extent[1])
        plt.ylim(extent[2], extent[3])
        plt.xlabel('X Position (deg)')
        plt.ylabel('Y Position (deg)')
        pdf.savefig()
        plt.close()

        # Create the big group plots
        _logger.info(f'{self.name}: Creating grid pages...')
        fig, axes = plt.subplots(nrows, ncols)
        fig.set_dpi(dpi)  # Sharper plots
        for ax in axes.flatten():
            ax.set_axis_off()
        i_subplot = 1
        for i_loop, i_res in enumerate(tones_to_plot):
            if i_loop == tones_to_plot.size // 2:
                _logger.info(f'{self.name}: Halfway done creating grid pages...')
            ax = axes.flatten()[i_subplot - 1]
            plot_data = np.flip(np.transpose(map_val[i_res][::-1]), 1)
            ax.imshow(
                plot_data,
                extent=extent,
                aspect='equal',
                cmap='jet',
                interpolation='bilinear',
            )

            # Draw a rectangle around the subplot indicating off-resonance / bad tones
            if chanmask[i_res] != 1:
                line_color = (
                    OFF_RESONANCE_COLOR if chanmask[i_res] == 0 else BAD_RESONANCE_COLOR
                )
                auto_axis = ax.axis()
                rec = plt.Rectangle(
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
                plt.close()
                fig, axes = plt.subplots(nrows, ncols)
                fig.set_dpi(dpi)  # Sharper plots
                for ax in axes.flatten():
                    ax.set_axis_off()
                i_subplot = 0
            i_subplot += 1

        if i_subplot > 1:
            pdf.savefig(fig)
        plt.close()

        # Create individul plots for each tone
        _logger.info(f'{self.name}: Creating individual resonance plots...')
        for i_loop, i_res in enumerate(tones_to_plot):
            if i_loop == tones_to_plot.size // 2:
                _logger.info(f'{self.name}: Halfway done creating individual plots...')

            fig, ax = plt.subplots()

            data_to_plot = np.flip(np.transpose(map_val[i_res][::-1]), 1)
            data_to_plot -= np.nanmedian(data_to_plot)
            data_to_plot /= np.nanmax(data_to_plot)
            # data_to_plot = 10 * np.log10(np.abs(data_to_plot))

            # All map data
            im = ax.imshow(
                data_to_plot,
                # vmin=-10,
                # vmax=0,
                extent=extent,
                aspect='equal',
                cmap='jet',
                # interpolation='bilinear',
            )

            # Color bar
            divider = make_axes_locatable(ax)
            cax = divider.append_axes('right', size='5%', pad=0.05)
            cb = fig.colorbar(im, cax=cax)
            cb.set_label(f'Normalized signal ({units})', rotation=270, labelpad=15)

            # Center of bright source
            ax.plot(
                az_center[i_res],
                za_center[i_res],
                marker='+',
                color='white',
                markersize=10,
                mew=2,
            )

            # Stats
            if chanmask[i_res] != 0:
                bbox_pad = 0.3
                t = AnchoredText(
                    f'Amplitude = {amplitude[i_res] * 1e5:2f}    '
                    f'chisq = {chisq[i_res]:.3f}    '
                    f'snr = {snr[i_res]:.3f}\n'
                    f'fwhm_az = {fwhm_az[i_res]:.2f}    '
                    f'fwhm_za = {fwhm_za[i_res]:.2f}\n'
                    f'az_center = {az_center[i_res]:.2f}    '
                    f'za_center = {za_center[i_res]:.2f}\n',
                    loc='upper center',
                    bbox_to_anchor=(0.5, 0.15),
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
                ax.add_artist(t)

            title = rf'Tone {i_res} ($f_0$={detector_f[i_res] * 1e-6:.3f} MHz)'

            # Indicate in plot title and face color if off-resonance / bad tone
            if chanmask[i_res] != 1:
                if chanmask[i_res] == 0:
                    title += ' (Off-resonance)'
                    facecolor = OFF_RESONANCE_COLOR
                else:
                    title += ' (Bad Resonance)'
                    facecolor = BAD_RESONANCE_COLOR
                fig.set_facecolor(facecolor)

            ax.set_xlabel('X Position (deg)')
            ax.set_ylabel('Y Position (deg)')
            ax.set_xlim(extent[0], extent[1])
            ax.set_ylim(extent[2], extent[3])
            ax.set_title(title)
            fig.set_dpi(dpi)

            plt.subplots_adjust(bottom=0.18)
            # if chanmask[i_res] != 0:
            #     plt.tight_layout(rect=[0, 0.10, 1, 1])
            # else:
            plt.tight_layout()
            pdf.savefig(fig)
            plt.close()

        pdf.close()
        return RoutineResult()


def combine_polarized_beammaps(
    pol1_data: ProcessedData,
    pol2_data: ProcessedData,
    new_tile_name: str,
    amplitude_normalization_percentile: float = 75,  # noqa: ARG001
    pdf_filename: str | None = None,
):
    """Determines various tile parameters from two beam maps of opposite polarizations.

    Creates a new params_file with detector_delta_x, detector_delta_y,
        detector_beam_ampl, and detector_pol.
    """
    onres_ind = pol1_data.onres_ind
    # old_tile_name = pol1_data.get_channel_group(0).attrs['tile_name']
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

    for i_res in onres_ind:
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

    # # Get positions relative to boresight of the telescope
    # delta_dx = az_center - np.median(az_center[onres_ind])
    # delta_dy = za_center - np.median(za_center[onres_ind])

    # # Save to a new parameters file
    # copy_and_update_params_file(
    #     old_tile_name,
    #     new_tile_name,
    #     detector_delta_x=az_center,
    #     detector_delta_y=za_center,
    #     detector_beam_ampl=beam_ampl,
    #     detector_pol=detector_pol
    # )

    # Plot centers
    if pdf_filename is None:
        pdf_filename = get_detector_pos_pdf_template(pol1_data.date, new_tile_name)
    pol1 = np.argwhere(detector_pol == 1).flatten()
    pol2 = np.argwhere(detector_pol == 2).flatten()  # noqa: PLR2004
    with PdfPages(pdf_filename) as pdf:
        plt.scatter(
            az_center[pol2],
            za_center[pol2],
            marker='x',
            color='blue',
            label=f'Polarization 2 (N = {pol2.size})',
        )
        for i_pol in pol2:
            plt.text(
                az_center[i_pol],
                za_center[i_pol],
                f'{i_pol}',
                color='blue',
                fontsize=20.0,
            )
        plt.scatter(
            az_center[pol1],
            za_center[pol1],
            marker='+',
            color='red',
            label=f'Polarization 1 (N = {pol1.size})',
        )
        for i_pol in pol1:
            plt.text(
                az_center[i_pol],
                za_center[i_pol],
                f'{i_pol}',
                color='red',
                fontsize=20.0,
            )
        plt.xlabel('AZ Position (deg)')
        plt.ylabel('ZA Position (deg)')
        plt.gca().invert_yaxis()
        # plt.legend()
        pdf.savefig()
        plt.show()
