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
        delta_sigma_fwhm_threshold: float= 1.5,
        delta_sigma_chisq_threshold: float = 3,
        snr_threshold: float = 0.5,
        amplitude_threshold: float = 0.2,
        delta_sigma_fwhm_ratio_threshold: float = 1.5,
        initial_fwhm: float = 0.1,
        min_fwhm: float = 0.01,
        max_fwhm: float = 1.0,
        az_bounds_offset: float = 0.2,
        za_bounds_offset: float = 0.2,
        max_radius: float = 0.1,
        maxfev: int = 10000,
        plot: bool = False,
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
            delta_sigma_fwhm_threshold=delta_sigma_fwhm_threshold,
            delta_sigma_chisq_threshold=delta_sigma_chisq_threshold,
            delta_sigma_fwhm_ratio_threshold=delta_sigma_fwhm_ratio_threshold,
            snr_threshold=snr_threshold,
            amplitude_threshold=amplitude_threshold,
            initial_fwhm=initial_fwhm,
            min_fwhm=min_fwhm,
            max_fwhm=max_fwhm,
            az_bounds_offset=abs(az_bounds_offset),
            za_bounds_offset=abs(za_bounds_offset),
            max_radius=max_radius,
            maxfev=maxfev,
            plot=plot,
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

        pos_group = dr_group.create_group('positive')
        pos_group.create_dataset('az_center', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('za_center', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('amplitude', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('snr', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('new_snr', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('chisq', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('fwhm_az', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('fwhm_za', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('offset', (pdata.n_tones,), dtype=np.float64)
        pos_group.create_dataset('is_double', (pdata.n_tones,), dtype=np.bool)

        neg_group = dr_group.create_group('negative')
        neg_group.create_dataset('az_center', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('za_center', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('amplitude', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('snr', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('new_snr', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('chisq', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('fwhm_az', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('fwhm_za', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('offset', (pdata.n_tones,), dtype=np.float64)
        neg_group.create_dataset('is_double', (pdata.n_tones,), dtype=np.bool)

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
        new_snr = pdata['/beammap/new_snr'][:]
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
        new_az_center_pos = pdata['beammap/double_resonances/positive/az_center']
        new_za_center_pos = pdata['beammap/double_resonances/positive/za_center']
        new_amplitude_pos = pdata['beammap/double_resonances/positive/amplitude']
        new_snr_pos = pdata['beammap/double_resonances/positive/snr']
        new_new_snr_pos = pdata['beammap/double_resonances/positive/new_snr']
        new_chisq_pos = pdata['beammap/double_resonances/positive/chisq']
        new_fwhm_az_pos = pdata['beammap/double_resonances/positive/fwhm_az']
        new_fwhm_za_pos = pdata['beammap/double_resonances/positive/fwhm_za']
        new_offset_pos = pdata['beammap/double_resonances/positive/offset']

        new_az_center_neg = pdata['beammap/double_resonances/negative/az_center']
        new_za_center_neg = pdata['beammap/double_resonances/negative/za_center']
        new_amplitude_neg = pdata['beammap/double_resonances/negative/amplitude']
        new_snr_neg = pdata['beammap/double_resonances/negative/snr']
        new_new_snr_neg = pdata['beammap/double_resonances/negative/new_snr']
        new_chisq_neg = pdata['beammap/double_resonances/negative/chisq']
        new_fwhm_az_neg = pdata['beammap/double_resonances/negative/fwhm_az']
        new_fwhm_za_neg = pdata['beammap/double_resonances/negative/fwhm_za']
        new_offset_neg = pdata['beammap/double_resonances/negative/offset']

        # Find any second sources in the positive residual map
        find_gaussian_beams(
            tone_indices,
            pdata['map/map_az'][:][:, np.newaxis],
            pdata['map/map_za'][:][np.newaxis, :],
            residual_map_val[:],
            new_az_center_pos,
            new_za_center_pos,
            new_amplitude_pos,
            new_snr_pos,
            new_new_snr_pos,
            new_chisq_pos,
            new_fwhm_az_pos,
            new_fwhm_za_pos,
            new_offset_pos,
            initial_fwhm=self.params['initial_fwhm'],
            min_fwhm=self.params['min_fwhm'],
            max_fwhm=self.params['max_fwhm'],
            az_bounds_offset=self.params['az_bounds_offset'],
            za_bounds_offset=self.params['za_bounds_offset'],
            max_radius=self.params['max_radius'],
            maxfev=self.params['maxfev'],
            caller_name=self.name,
        )
        # Find any second sources in the negative residual map
        find_gaussian_beams(
            tone_indices,
            pdata['map/map_az'][:][:, np.newaxis],
            pdata['map/map_za'][:][np.newaxis, :],
            -1 * residual_map_val[:],
            new_az_center_neg,
            new_za_center_neg,
            new_amplitude_neg,
            new_snr_neg,
            new_new_snr_neg,
            new_chisq_neg,
            new_fwhm_az_neg,
            new_fwhm_za_neg,
            new_offset_neg,
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

        # identify double resonances

        amp_ratio_pos =  new_amplitude_pos[:] / amplitude[:]
        amp_ratio_neg =  new_amplitude_neg[:] / amplitude[:]

        snr_ratio_pos = new_snr_pos[:] / snr[:]
        snr_ratio_neg = new_snr_neg[:] / snr[:]

        new_snr_ratio_pos = new_new_snr_pos[:] / new_snr[:]
        new_snr_ratio_neg = new_new_snr_neg[:] / new_snr[:]

        amp_weight = 0.75

        amp_matrix = np.hstack([amplitude[:, np.newaxis], np.ones((amplitude.size, 1))])
        idx = tone_indices[np.isfinite(amplitude[tone_indices])]
        idx = idx[~np.isnan(amplitude[idx])]
        idx = idx[np.isfinite(snr[idx])]
        idx = idx[~np.isnan(snr[idx])]
        beta, ssr, rank, s = np.linalg.lstsq(amp_matrix[idx], snr[idx])
        expected_snr = amp_matrix.dot(beta)
        resid = snr - expected_snr
        squared_resid = resid ** 2
        squared_resid_med = np.nanmedian(squared_resid[idx])
        squared_resid_std = np.nanstd(squared_resid[idx])

        amp_matrix_pos = np.hstack([new_amplitude_pos[:][:, np.newaxis], np.ones((new_amplitude_pos.size, 1))])
        expected_snr_pos = amp_matrix_pos.dot(beta)
        resid_pos = new_snr_pos - expected_snr_pos
        squared_resid_pos = resid_pos ** 2

        amp_matrix_neg = np.hstack([new_amplitude_neg[:][:, np.newaxis], np.ones((new_amplitude_neg.size, 1))])
        expected_snr_neg = amp_matrix_neg.dot(beta)
        resid_neg = new_snr_neg - expected_snr_neg
        squared_resid_neg = resid_neg ** 2

        # _, bins, _ = plt.hist(squared_resid_pos[~np.isnan(squared_resid_pos) & np.isfinite(squared_resid_pos)], bins=20)
        # plt.hist(squared_resid_neg[~np.isnan(squared_resid_neg) & np.isfinite(squared_resid_neg)], bins=bins)
        # plt.show()
        # pdb.set_trace()

        chisq_med = np.median(chisq[pdata.onres_ind])
        chisq_std = np.std(chisq[pdata.onres_ind])
        # remove outliers and recompute std
        onres_chisq = chisq[pdata.onres_ind]
        filt_chisq = onres_chisq[((onres_chisq - chisq_med) / chisq_std) <= 3]
        filt_chisq = filt_chisq[filt_chisq <= 0.05]
        chisq_med = np.median(filt_chisq)
        chisq_std = np.std(filt_chisq)
        delta_sigma_chisq_pos = np.abs(new_chisq_pos - chisq_med) / chisq_std
        delta_sigma_chisq_neg = np.abs(new_chisq_neg - chisq_med) / chisq_std

        fwhm_az_med = np.median(fwhm_az[pdata.onres_ind])
        fwhm_az_std = np.std(fwhm_az[pdata.onres_ind])
        fwhm_za_med = np.median(fwhm_za[pdata.onres_ind])
        fwhm_za_std = np.std(fwhm_za[pdata.onres_ind])

        fwhm_ratio_pos = new_fwhm_az_pos[:] / new_fwhm_za_pos[:]
        fwhm_ratio_neg = new_fwhm_az_neg[:] / new_fwhm_za_neg[:]
        fwhm_ratio_med = np.nanmedian(fwhm_az[pdata.onres_ind] / fwhm_za[pdata.onres_ind])
        fwhm_ratio_std = np.nanstd(fwhm_az[pdata.onres_ind] / fwhm_za[pdata.onres_ind])

        delta_sigma_fwhm_az_pos = np.abs(new_fwhm_az_pos - fwhm_az_med) / fwhm_az_std
        delta_sigma_fwhm_za_pos = np.abs(new_fwhm_za_pos - fwhm_za_med) / fwhm_za_std
        delta_sigma_fwhm_ratio_pos = np.abs(fwhm_ratio_pos - fwhm_ratio_med) / fwhm_ratio_std
        delta_sigma_resid_pos = np.abs(squared_resid_pos - squared_resid_med) / squared_resid_std
        delta_sigma_fwhm_az_neg = np.abs(new_fwhm_az_neg - fwhm_az_med) / fwhm_az_std
        delta_sigma_fwhm_za_neg = np.abs(new_fwhm_za_neg - fwhm_za_med) / fwhm_za_std
        delta_sigma_fwhm_ratio_neg = np.abs(fwhm_ratio_neg - fwhm_ratio_med) / fwhm_ratio_std
        delta_sigma_resid_neg = np.abs(squared_resid_neg - squared_resid_med) / squared_resid_std

        delta_sigma_fwhm_threshold = self.params['delta_sigma_fwhm_threshold']
        delta_sigma_fwhm_ratio_threshold = self.params['delta_sigma_fwhm_ratio_threshold']
        delta_sigma_chisq_threshold = self.params['delta_sigma_chisq_threshold']
        snr_threshold = self.params['snr_threshold']
        amplitude_threshold = self.params['amplitude_threshold']

        is_double_pos = (
            # Only care about tones we're already considering
            np.isin(np.arange(pdata.n_tones, dtype=int), tone_indices) &
            # Amplitude is relatively large
            (amp_ratio_pos >= amplitude_threshold) &
            # SNR is similar in magnitude
            (snr_ratio_pos >= snr_threshold) &
            (new_snr_ratio_pos >= 0.2) &
            # # Source has a relative SNR proportional to the relative amplitude
            # (delta_sigma_resid_pos <= 1) &
            # Make sure the source isn't too large
            (delta_sigma_fwhm_az_pos <= delta_sigma_fwhm_threshold) &
            (delta_sigma_fwhm_za_pos <= delta_sigma_fwhm_threshold) &
            # Make sure the source is approximately circular
            (delta_sigma_fwhm_ratio_pos <= delta_sigma_fwhm_ratio_threshold) &
            # Check chi squared
            (delta_sigma_chisq_pos <= delta_sigma_chisq_threshold)
        )
        pdata['/beammap/double_resonances/positive/is_double'][:] = is_double_pos

        is_double_neg = (
            # Only care about tones we're already considering
            np.isin(np.arange(pdata.n_tones, dtype=int), tone_indices) &
            # Amplitude is relatively large
            (amp_ratio_neg >= amplitude_threshold) &
            # SNR is similar in magnitude
            (snr_ratio_neg >= snr_threshold) &
            (new_snr_ratio_neg >= 0.2) &
            # # Source has a relative SNR proportional to the relative amplitude
            # (delta_sigma_resid_neg <= 1) &
            # Make sure the source isn't too large
            (delta_sigma_fwhm_az_neg <= delta_sigma_fwhm_threshold) &
            (delta_sigma_fwhm_za_neg <= delta_sigma_fwhm_threshold) &
            # Make sure the source is approximately circular
            (delta_sigma_fwhm_ratio_neg <= delta_sigma_fwhm_ratio_threshold) &
            # Check chi squared
            (delta_sigma_chisq_neg <= delta_sigma_chisq_threshold)
        )
        pdata['/beammap/double_resonances/negative/is_double'][:] = is_double_neg
        is_double = np.logical_or(is_double_pos, is_double_neg)
        # is_double = np.logical_and(is_double, amplitude >= 5e-7)  # Minimum amplitude


        # tone_indices = np.array([
        #     154, 155, 156, 172, 181, 182, 186, 187, 293, 348, 350, 515, 516, 543, 544, 
        #     545, 552, 553, 705, 804, 806, 847,
        # ])
        if self.params['plot']:
            bbox_pad = 0.3
            _logger.info(f'{self.name}: Plotting results...')
            with PdfPages(f'{pdata.folder}/{pdata.file_stub}_double_resonances.pdf') as pdf:
                for i, i_res in enumerate(tone_indices):
                    if i == tone_indices.size // 2:
                        _logger.info(f'{self.name}: Halfway done plotting results...')
                    old_plot_data = np.flip(np.transpose(map_val[i_res][::-1]), 1)
                    old_med = np.nanmedian(old_plot_data)
                    old_plot_data -= old_med
                    old_max = np.nanmax(old_plot_data)
                    old_plot_data /= old_max
                    vmin = np.min(old_plot_data)
                    vmax = np.max(old_plot_data)
                    fig, axes = plt.subplots(1, 3, sharey=True, figsize=(16, 6), layout='compressed')
                    if is_double[i_res]:
                        fig.set_facecolor('orange')

                    fig.suptitle(f'Resonator {i_res}')
                    axes[0].set_title('Original Map')
                    im = axes[0].imshow(old_plot_data, vmin=vmin, vmax=vmax, extent=extent, aspect='equal', cmap='jet')
                    axes[0].plot(az_center[i_res], za_center[i_res], marker='+', color='white', markersize=10, mew=2)

                    new_plot_data = np.flip(np.transpose(residual_map_val[i_res][::-1]), 1)
                    new_plot_data_pos = new_plot_data - old_med
                    new_plot_data_pos /= old_max

                    axes[1].set_title('Residual Map')
                    axes[1].imshow(new_plot_data_pos, vmin=vmin, vmax=vmax, extent=extent, aspect='equal', cmap='jet')
                    axes[1].plot(new_az_center_pos[i_res], new_za_center_pos[i_res], marker='+', color='white', markersize=10, mew=2)

                    if is_double_pos[i_res]:
                        axes[1].set_facecolor('orange')

                    new_plot_data_neg =  old_med - new_plot_data
                    new_plot_data_neg /= old_max

                    axes[2].set_title('Residual Map (Inverted)')
                    axes[2].imshow(new_plot_data_neg, vmin=vmin, vmax=vmax, extent=extent, aspect='equal', cmap='jet')
                    axes[2].plot(new_az_center_neg[i_res], new_za_center_neg[i_res], marker='+', color='white', markersize=10, mew=2)


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
                        f'za_center = {za_center[i_res]:.2f}\n'
                        f'new snr = {new_snr[i_res]:.3f}\n',
                        loc='upper center',
                        bbox_to_anchor=(0.5, -0.2),
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
                        f'Amplitude = {new_amplitude_pos[i_res] * 1e5:2f}    '
                        f'chisq = {new_chisq_pos[i_res]:.3f}    '
                        f'snr = {new_snr_pos[i_res]:.3f}\n'
                        f'fwhm_az = {new_fwhm_az_pos[i_res]:.2f}    '
                        f'fwhm_za = {new_fwhm_za_pos[i_res]:.2f}\n'
                        f'az_center = {new_az_center_pos[i_res]:.2f}    '
                        f'za_center = {new_za_center_pos[i_res]:.2f}\n\n'
                        f'new snr = {new_new_snr_pos[i_res]:.3f}    '
                        f'new snr ratio = {new_snr_ratio_pos[i_res]:.3f}\n'
                        f'Amplitude ratio = {amp_ratio_pos[i_res]:.2f}    '
                        f'SNR ratio = {snr_ratio_pos[i_res]:.2f}\n'
                        rf'$\delta\sigma_{{\chi^2}}$ = {delta_sigma_chisq_pos[i_res]:.2f}    '
                        rf'$\delta\sigma_{{az}}$ = {delta_sigma_fwhm_az_pos[i_res]:.2f}    '
                        rf'$\delta\sigma_{{za}}$ = {delta_sigma_fwhm_za_pos[i_res]:.2f}',
                        loc='upper center',
                        bbox_to_anchor=(0.5, -0.2),
                        bbox_transform=axes[1].transAxes,
                        pad=bbox_pad,
                        borderpad=0,
                        prop={
                            # color='white',
                            'horizontalalignment': 'center',
                        },
                    )
                    if is_double[i_res] and is_double_pos[i_res]:
                        t1.patch.set_facecolor('red')
                    axes[1].add_artist(t1)

                    t2 = AnchoredText(
                        f'Amplitude = {new_amplitude_neg[i_res] * 1e5:2f}    '
                        f'chisq = {new_chisq_neg[i_res]:.3f}    '
                        f'snr = {new_snr_neg[i_res]:.3f}\n'
                        f'fwhm_az = {new_fwhm_az_neg[i_res]:.2f}    '
                        f'fwhm_za = {new_fwhm_za_neg[i_res]:.2f}\n'
                        f'az_center = {new_az_center_neg[i_res]:.2f}    '
                        f'za_center = {new_za_center_neg[i_res]:.2f}\n\n'
                        f'new snr = {new_new_snr_neg[i_res]:.3f}    '
                        f'new snr ratio = {new_snr_ratio_neg[i_res]:.3f}\n'
                        f'Amplitude ratio = {amp_ratio_neg[i_res]:.2f}    '
                        f'SNR ratio = {snr_ratio_neg[i_res]:.2f}\n'
                        rf'$\delta\sigma_{{\chi^2}}$ = {delta_sigma_chisq_neg[i_res]:.2f}    '
                        rf'$\delta\sigma_{{az}}$ = {delta_sigma_fwhm_az_neg[i_res]:.2f}    '
                        rf'$\delta\sigma_{{za}}$ = {delta_sigma_fwhm_za_neg[i_res]:.2f}',
                        loc='upper center',
                        bbox_to_anchor=(0.5, -0.2),
                        bbox_transform=axes[2].transAxes,
                        pad=bbox_pad,
                        borderpad=0,
                        prop={
                            # color='white',
                            'horizontalalignment': 'center',
                        },
                    )
                    if is_double[i_res] and is_double_neg[i_res]:
                        t2.patch.set_facecolor('red')
                    axes[2].add_artist(t2)

                    axes[0].set_xlabel('X Position (deg)')
                    axes[1].set_xlabel('X Position (deg)')
                    axes[2].set_xlabel('X Position (deg)')
                    axes[0].set_ylabel('Y Position (deg)')
                    # fig.subplots_adjust(bottom=0.18)
                    # fig.tight_layout()

                    pdf.savefig(fig)
                    plt.close(fig)

        return list(self.produces)
