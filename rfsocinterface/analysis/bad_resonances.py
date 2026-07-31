"""Code for identifying bad resonances."""

import logging
import pdb
import typing
from typing import ClassVar

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.offsetbox import AnchoredText
from mpl_toolkits.axes_grid1 import make_axes_locatable

from rfsocinterface.analysis.beammap import find_gaussian_beams
from rfsocinterface.core.data import DataRoutine, ProcessedData, get_extent
from rfsocinterface.core.utils import gauss_2d

_logger = logging.getLogger(__name__)


class FindDoubleResonances(DataRoutine):
    """Routine to identify and flag same-polarization double resonances."""

    name = 'FindDoubleResonances'
    version = '1.0.0'

    requires: ClassVar[set[str]] = {
        '/map/map_val',
        '/map/map_az',
        '/map/map_za',
        '/beammap/az_center',
        '/beammap/za_center',
        '/beammap/amplitude',
        '/beammap/fwhm_az',
        '/beammap/fwhm_za',
    }

    produces: ClassVar[set[str]] = {
        '/beammap/double_resonance/az_center',
        '/beammap/double_resonance/za_center',
        '/beammap/double_resonance/amplitude',
        '/beammap/double_resonance/snr',
        '/beammap/double_resonance/chisq',
        '/beammap/double_resonance/fwhm_az',
        '/beammap/double_resonance/fwhm_za',
    }

    def __init__(
        self,
        ratio_threshold: float = 0.5,
        initial_fwhm: float = 0.1,
        min_fwhm: float = 0.01,
        max_fwhm: float = 1.0,
        az_bounds_offset: float = 0.2,
        za_bounds_offset: float = 0.2,
        max_radius: float = 0.1,
        maxfev: int = 10000,
    ):
        """Initialize the FindDoubleResonances routine.

        Arguments:
            ratio_threshold (float, optional): The minimum ratio of second resonance
                to original to flag as a double resonance. Defaults to 0.5.
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
            ratio_threshold=ratio_threshold,
            initial_fwhm=initial_fwhm,
            min_fwhm=min_fwhm,
            max_fwhm=max_fwhm,
            az_bounds_offset=abs(az_bounds_offset),
            za_bounds_offset=abs(za_bounds_offset),
            max_radius=max_radius,
            maxfev=maxfev,
        )

    @typing.override
    def inputs(self, pdata):
        return list(self.requires)

    def _initialize_datasets(self, pdata: ProcessedData):
        if pdata.has('beammap/double_resonances', exact_match=True):
            _logger.warning(
                f'{self.name}: Double resonance group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['beammap/double_resonances']
        dr_group = pdata['beammap'].create_group('double_resonances')
        map_shape = pdata['map/map_val'].shape
        dr_group.create_dataset('residual_map_val', map_shape, dtype=np.float64)

        dr_group.create_dataset('az_center', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('za_center', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('amplitude', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('snr', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('chisq', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('fwhm_az', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('fwhm_za', (pdata.n_tones,), dtype=np.float64)
        dr_group.create_dataset('offset', (pdata.n_tones,), dtype=np.float64)


    @typing.override
    def run(self, pdata: ProcessedData, inputs: list[str] | None = None):
        self._initialize_datasets(pdata)

        map_az = pdata['map/map_az'][:][:, np.newaxis]
        map_za = pdata['map/map_za'][:][np.newaxis, :]
        map_val = pdata['map/map_val'][:]
        az_center = pdata['/beammap/az_center'][:]
        za_center = pdata['/beammap/za_center'][:]
        amplitude = pdata['/beammap/amplitude'][:]
        fwhm_az = pdata['/beammap/fwhm_az'][:]
        fwhm_za = pdata['/beammap/fwhm_za'][:]
        chisq = pdata['/beammap/chisq'][:]
        snr = pdata['/beammap/snr'][:]
        offset = pdata['/beammap/offset'][:]

        residual_map_val = pdata['beammap/double_resonances/residual_map_val']
        tone_indices = []

        # Subtract any Gaussians that were found
        for i_res in pdata.onres_ind:
            # 0 indicates the fit failed, i.e. no source to begin with
            if amplitude[i_res] > 0:
                tone_indices.append(i_res)
                # Subtract the existing source
                gaussian = gauss_2d(
                    (map_az, map_za),
                    amplitude[i_res],
                    az_center[i_res],
                    za_center[i_res],
                    fwhm_az[i_res],
                    fwhm_za[i_res],
                    0,
                    # offset[i_res],
                )
                residual_map_val[i_res] = map_val[i_res] - gaussian
                # if i_res in [84, 86, 94]:
                #     fig, axes = plt.subplots(1, 3)
                #     fig.suptitle(f'Resonator {i_res}')
                #     axes[0].imshow(np.flip(np.transpose(map_val[i_res][::-1]), 1))
                #     axes[1].imshow(np.flip(np.transpose(residual_map_val[i_res][::-1]), 1))
                #     axes[2].imshow(np.flip(np.transpose(gaussian[::-1]), 1))
                #     plt.show()
                #     pdb.set_trace()

        tone_indices = np.array(tone_indices)
        new_az_center = pdata['beammap/double_resonances/az_center']
        new_za_center = pdata['beammap/double_resonances/za_center']
        new_amplitude = pdata['beammap/double_resonances/amplitude']
        new_snr = pdata['beammap/double_resonances/snr']
        new_chisq = pdata['beammap/double_resonances/chisq']
        new_fwhm_az = pdata['beammap/double_resonances/fwhm_az']
        new_fwhm_za = pdata['beammap/double_resonances/fwhm_za']
        new_offset = pdata['beammap/double_resonances/offset']
        # Find any second sources
        find_gaussian_beams(
            tone_indices,
            pdata['map/map_az'][:][:, np.newaxis],
            pdata['map/map_za'][:][np.newaxis, :],
            residual_map_val[:],
            new_az_center,
            new_za_center,
            new_amplitude,
            new_snr,
            new_chisq,
            new_fwhm_az,
            new_fwhm_za,
            new_offset,
            initial_fwhm=self.params['initial_fwhm'],
            min_fwhm=self.params['min_fwhm'],
            max_fwhm=self.params['max_fwhm'],
            az_bounds_offset=self.params['az_bounds_offset'],
            za_bounds_offset=self.params['za_bounds_offset'],
            max_radius=self.params['max_radius'],
            maxfev=self.params['maxfev'],
            caller_name=self.name,
        )

        extent = get_extent(np.squeeze(map_az), np.squeeze(map_za), dpix=0.03)
        # Compare amplitudes
        amp_ratio =  new_amplitude[tone_indices] / amplitude[tone_indices]
        bbox_pad = 0.3
        with PdfPages('double_resonances.pdf') as pdf:
            for i, i_res in enumerate(tone_indices):
                old_plot_data = np.flip(np.transpose(map_val[i_res][::-1]), 1)
                old_med = np.nanmedian(old_plot_data)
                old_plot_data -= old_med
                old_max = np.nanmax(old_plot_data)
                old_plot_data /= old_max
                vmin = np.min(old_plot_data)
                vmax = np.max(old_plot_data)
                fig, axes = plt.subplots(1, 2, sharey=True, figsize=(12, 6), layout='compressed')

                fig.suptitle(rf'Resonator {i_res} - $\frac{{A_{{res}}}}{{A_0}}$ = {amp_ratio[i]:.3f}')
                axes[0].set_title('Original Map')
                im = axes[0].imshow(old_plot_data, vmin=vmin, vmax=vmax, extent=extent, aspect='equal', cmap='jet')
                axes[0].plot(az_center[i_res], za_center[i_res], marker='+', color='white', markersize=10, mew=2)

                new_plot_data = np.flip(np.transpose(residual_map_val[i_res][::-1]), 1)
                new_plot_data -= old_med
                new_plot_data /= old_max
                axes[1].set_title('Residual Map')
                axes[1].imshow(new_plot_data, vmin=vmin, vmax=vmax, extent=extent, aspect='equal', cmap='jet')
                axes[1].plot(new_az_center[i_res], new_za_center[i_res], marker='+', color='white', markersize=10, mew=2)

                # divider = make_axes_locatable(axes[1])
                # cax = divider.append_axes('right', size='5%', pad=0.05)
                # cb = fig.colorbar(im, cax=cax)
                cb = fig.colorbar(im, ax=axes)
                cb.set_label(f'Normalized signal ({pdata["map"].attrs["units"]})', rotation=270, labelpad=15)

                t = AnchoredText(
                    f'Amplitude = {amplitude[i_res] * 1e5:2f}    '
                    f'chisq = {chisq[i_res]:.3f}    '
                    f'snr = {snr[i_res]:.3f}\n'
                    f'fwhm_az = {fwhm_az[i_res]:.2f}    '
                    f'fwhm_za = {fwhm_za[i_res]:.2f}\n'
                    f'az_center = {az_center[i_res]:.2f}    '
                    f'za_center = {za_center[i_res]:.2f}\n',
                    loc='upper center',
                    bbox_to_anchor=(0.5, -0.1),
                    bbox_transform=axes[0].transAxes,
                    pad=bbox_pad,
                    borderpad=0,
                    prop={
                        # color='white',
                        'horizontalalignment': 'center',
                    },
                )
                # t.patch.set_alpha(0.25)
                # t.patch.set_color('black')
                axes[0].add_artist(t)

                t1 = AnchoredText(
                    f'Amplitude = {new_amplitude[i_res] * 1e5:2f}    '
                    f'chisq = {new_chisq[i_res]:.3f}    '
                    f'snr = {new_snr[i_res]:.3f}\n'
                    f'fwhm_az = {new_fwhm_az[i_res]:.2f}    '
                    f'fwhm_za = {new_fwhm_za[i_res]:.2f}\n'
                    f'az_center = {new_az_center[i_res]:.2f}    '
                    f'za_center = {new_za_center[i_res]:.2f}\n',
                    loc='upper center',
                    bbox_to_anchor=(0.5, -0.1),
                    bbox_transform=axes[1].transAxes,
                    pad=bbox_pad,
                    borderpad=0,
                    prop={
                        # color='white',
                        'horizontalalignment': 'center',
                    },
                )
                axes[1].add_artist(t1)

                axes[0].set_xlabel('X Position (deg)')
                axes[1].set_xlabel('X Position (deg)')
                axes[0].set_ylabel('Y Position (deg)')
                # fig.subplots_adjust(bottom=0.18)
                # fig.tight_layout()

                pdf.savefig(fig)
                plt.close(fig)
        pdb.set_trace()

        return list(self.produces)
