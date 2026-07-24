"""Code for finding and characterizing peaks in the detector response."""

import logging
import typing
from collections.abc import Sequence
from typing import ClassVar, Literal

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.backends.backend_pdf import PdfPages
from scipy.optimize import least_squares

from rfsocinterface.core.data import DataRoutine, ProcessedData, register_routine
from rfsocinterface.core.utils import sigma_to_fwhm

_logger = logging.getLogger(__name__)


def gaussian_profile(parameters: npt.NDArray, x_vals: npt.NDArray) -> npt.NDArray:
    """Return a Gaussian. Used for peak fitting."""
    a0, a1, mu, sigma = parameters
    return a0 + a1 * np.exp(-0.5 * ((x_vals - mu) / sigma) ** 2)


def loss_function(
    parameters: npt.NDArray, x_vals: npt.NDArray, y_vals: npt.NDArray
) -> npt.NDArray:
    """Compare the expected Gaussian to the expected result."""
    model_vals = gaussian_profile(parameters, x_vals)
    return y_vals - model_vals


def mean_histogram(val: npt.NDArray, freq: npt.NDArray) -> float:
    """Compute a weighted mean using historgram frequencies as weights."""
    return np.average(val, weights=freq)


def var_histogram(val: npt.NDArray, freq: npt.NDArray) -> float:
    """Compute variance using historgram frequencies as weights."""
    dev = freq * (val - mean_histogram(val, freq)) ** 2
    return dev.sum() / freq.sum()


def std_histogram(val: npt.NDArray, freq: npt.NDArray) -> float:
    """Compute standard deviation using historgram frequencies as weights."""
    return np.sqrt(var_histogram(val, freq))


@register_routine
class CheckFocus(DataRoutine):
    """Routine to check the detector's focus determine timing offsets.

    Assumes the data was collected in two dithers, out and back, with no secondary
    dither.
    """

    name = 'CheckFocus'
    version = '1.0.0'

    produces: ClassVar[set] = {
        '/focus/fwhms',
        '/focus/amplitudes',
        '/focus/good_resonators',
    }

    def __init__(
        self,
        primary_direction: Literal['az', 'za'],
        resonators: Sequence[int],
        fit_radius_deg: float = 0.5,
        fractional_difference_threshold: float = 0.5,
        dataset: Literal['data_mK', 'data_freq'] = 'data_mK',
    ):
        """Initialize the CheckFocus routine.

        Arguments:
            primary_direction (str): What the primary direction of the dither was. Must
                be either 'az' (azimuth) or 'za' (zenith angle).
            resonators (Sequence[int]): The index of each resonator to analyze.
            fit_radius_deg (float, optional): The radius of the data to use in fitting,
                in degrees. Defaults to 3.
            fractional_difference_threshold (float, optional): The maximum allowed
                fractional difference between the fit on the left and right passes.
                Defaults to 0.5.
            dataset (str, optional): The name of the dataset to clean. Must be either
                'data_mK' or 'data_freq'. Defaults to 'data_mK'.
        """
        super().__init__(
            primary_direction=primary_direction,
            resonators=resonators,
            fit_radius_deg=fit_radius_deg,
            fractional_difference_threshold=fractional_difference_threshold,
            dataset=dataset,
        )

    @typing.override
    def inputs(self, pdata: ProcessedData):
        dset = (
            '/vdsets/data_mK'
            if self.params['dataset'] == 'data_mK'
            else '/vdsets/data_freq_diss'
        )
        direction = self.params['primary_direction']
        return [
            f'/vdsets/detector_{direction}',
            dset,
            '/global_data/timestamp',
        ]

    def _initialize_arrays(self, pdata: ProcessedData):
        """Initialize the new arrays in the processed data file."""
        if pdata.has('focus', exact_match=True):
            _logger.info(
                f'{self.name}: CheckFocus group already exists in the file. '
                'Using existing datasets.'
            )
            return
        focus_group = pdata.create_group('focus')
        focus_group.create_dataset('fwhms', shape=(pdata.n_tones,), dtype=np.float64)
        focus_group.create_dataset(
            'amplitudes', shape=(pdata.n_tones,), dtype=np.float64
        )
        focus_group.create_dataset(
            'good_resonators', shape=(pdata.n_tones,), dtype=np.uint8
        )

    @typing.override
    def run(self, pdata: ProcessedData, inputs: list[str] | None = None):
        primary_direction = self.params['primary_direction']
        resonators = self.params['resonators']
        fit_radius_deg = self.params['fit_radius_deg']
        dataset = self.params['dataset']
        data = (
            pdata.data_mK[:]
            if dataset == 'data_mK'
            else pdata.data_freq_diss[0] / pdata.detector_f()[:, np.newaxis]
        )
        units = 'mK' if dataset == 'data_mK' else 'df/f'
        fractional_difference_threshold = self.params['fractional_difference_threshold']

        amplitudes = []
        fwhms = []
        good_resonators = []
        with PdfPages(f'peaks_{pdata.file_stub}.pdf') as pdf:
            for i_res in resonators:
                _logger.info(f'{self.name}: Analyzing resonator {i_res}...')
                data = pdata.data_mK[i_res]
                telescope_pos = (
                    pdata.detector_az[i_res]
                    if primary_direction.lower() == 'az'
                    else pdata.detector_za[i_res]
                )

                first_good_sample = np.argwhere(~np.isnan(telescope_pos))[0]
                last_good_sample = np.argwhere(~np.isnan(telescope_pos))[-1]
                relative_pos = np.abs(telescope_pos - telescope_pos[first_good_sample])
                samples_0 = np.argmax(
                    (relative_pos >= fit_radius_deg) & ~np.isnan(telescope_pos)
                )
                relative_pos = np.abs(telescope_pos - telescope_pos[last_good_sample])
                samples_1 = np.where(
                    (relative_pos >= fit_radius_deg) & ~np.isnan(telescope_pos)
                )[0][-1]
                samples = slice(samples_0, samples_1)
                telescope_pos = telescope_pos[samples]

                # diff = telescope_pos - np.roll(telescope_pos, 1)
                # turn_point = np.nanargmax(diff)
                turn_point = np.nanargmax(telescope_pos)
                left_indices = np.arange(0, turn_point)
                right_indices = np.arange(turn_point, len(telescope_pos))

                data_segment = data[i_res, samples]
                right_peak_idx = right_indices[np.argmax(data_segment[right_indices])]
                left_peak_idx = left_indices[np.argmax(data_segment[left_indices])]

                right_fit_ind = np.argwhere(
                    np.isclose(telescope_pos, telescope_pos[right_peak_idx], atol=0.5)
                ).flatten()
                right_fit_ind = right_fit_ind[
                    np.isclose(right_fit_ind, right_peak_idx, atol=100)
                ]
                left_fit_ind = np.argwhere(
                    np.isclose(telescope_pos, telescope_pos[left_peak_idx], atol=0.5)
                ).flatten()
                left_fit_ind = left_fit_ind[
                    np.isclose(left_fit_ind, left_peak_idx, atol=100)
                ]

                amplitude_guess = np.max(data[i_res])
                x0 = [
                    amplitude_guess / 100,
                    amplitude_guess,
                    telescope_pos[right_peak_idx],
                    0.1 / (2 * np.sqrt(2 * np.log(2))),
                ]
                res_right = least_squares(
                    loss_function,
                    x0,
                    args=(telescope_pos[right_fit_ind], data_segment[right_fit_ind]),
                    bounds=(
                        [-1, 0, -15, 0.05 / (2 * np.sqrt(2 * np.log(2)))],
                        [1, 1, 15, 0.2 / (2 * np.sqrt(2 * np.log(2)))],
                    ),
                )

                amplitude_right = res_right.x[1]
                fwhm_right = np.abs(sigma_to_fwhm(res_right.x[3]))
                right_az_0 = res_right.x[2]

                x0 = [
                    amplitude_guess / 100,
                    amplitude_guess,
                    telescope_pos[left_peak_idx],
                    0.1 / (2 * np.sqrt(2 * np.log(2))),
                ]
                res_left = least_squares(
                    loss_function,
                    x0,
                    args=(telescope_pos[left_fit_ind], data_segment[left_fit_ind]),
                    bounds=(
                        [-1, 0, -15, 0.05 / (2 * np.sqrt(2 * np.log(2)))],
                        [1, 1, 15, 0.2 / (2 * np.sqrt(2 * np.log(2)))],
                    ),
                )

                amplitude_left = res_left.x[1]
                fwhm_left = np.abs(sigma_to_fwhm(res_left.x[3]))
                left_az_0 = res_left.x[2]

                # if left and right agree...
                amplitude_mean = np.mean([amplitude_left, amplitude_right])
                fwhm_mean = np.mean([fwhm_left, fwhm_right])
                if (
                    np.abs(amplitude_left - amplitude_right) / amplitude_mean
                    < fractional_difference_threshold
                    and np.abs(fwhm_left - fwhm_right) / fwhm_mean
                    < fractional_difference_threshold
                ):
                    amplitudes.append(amplitude_mean)
                    fwhms.append(fwhm_mean)
                    good_resonators.append(i_res)

                time = pdata.timestamp[:] - pdata.timestamp[0]
                fig = plt.figure(figsize=(8, 5))
                plt.title(
                    f'Detector {i_res} Peak Finding '
                    '(Polarization {pdata.detector_pol[i_res]})'
                )
                plt.plot(telescope_pos[:], data_segment, label='Full Trace', color='b')
                plt.plot(
                    telescope_pos[right_fit_ind],
                    data_segment[right_fit_ind],
                    label=(
                        f'Right (${{{primary_direction.upper()}}}_0$ = '
                        f'{right_az_0:.3f})'
                    ),
                    color='orange',
                )
                right_gaussian = gaussian_profile(
                    res_right.x, telescope_pos[right_fit_ind]
                )
                plt.plot(
                    telescope_pos[right_fit_ind],
                    right_gaussian,
                    linestyle='--',
                    color='orange',
                )
                right_patch = mpatches.Patch(
                    color='orange',
                    label=(
                        f'Amplitude = {amplitude_right:.3e} {units}, '
                        f'FWHM = {fwhm_right:.3f} deg'
                    ),
                )

                plt.plot(
                    telescope_pos[left_fit_ind],
                    data_segment[left_fit_ind],
                    label=(
                        f'Left (${{{primary_direction.upper()}}}_0$ = {left_az_0:.3f})',
                    ),
                    color='green',
                )
                left_gaussian = gaussian_profile(
                    res_left.x, telescope_pos[left_fit_ind]
                )
                plt.plot(
                    telescope_pos[left_fit_ind],
                    left_gaussian,
                    linestyle='--',
                    color='green',
                )
                left_patch = mpatches.Patch(
                    color='green',
                    label=(
                        f'Amplitude = {amplitude_left:.3e} {units}, '
                        f'FWHM = {fwhm_left:.3f} deg'
                    ),
                )

                scan_rate = (
                    telescope_pos[min(right_peak_idx + 10, len(telescope_pos) - 1)]
                    - telescope_pos[max(right_peak_idx - 10, 0)]
                ) / (
                    time[min(right_peak_idx + 10, len(telescope_pos) - 1)]
                    - time[max(right_peak_idx - 10, 0)]
                )
                time_delay = (
                    (left_az_0 - right_az_0) / scan_rate / 2
                )  # Amount RFSoC is behind the telescope
                plt.plot([], [], label=f'Time Delay = {time_delay:.3f}s')
                plt.legend(
                    loc='lower center',
                    bbox_transform=fig.transFigure,
                    bbox_to_anchor=(0.5, 0.0),
                    ncol=3,
                )
                handles = plt.gca().get_legend_handles_labels()[0]
                handles.append(right_patch)
                handles.append(left_patch)
                handles = [handles[i] for i in [0, 3, 1, 2, 4, 5]]
                plt.legend(
                    loc='lower center',
                    bbox_transform=fig.transFigure,
                    bbox_to_anchor=(0.5, 0.0),
                    ncol=3,
                    handles=handles,
                    fontsize=8,
                )
                plt.xlim(
                    telescope_pos[max(0, right_peak_idx - 50)],
                    telescope_pos[min(right_peak_idx + 50, len(telescope_pos) - 1)],
                )
                plt.xlabel(
                    f'{
                        "Azimuth"
                        if primary_direction.lower() == "az"
                        else "Zenith Angle"
                    } (degrees)'
                )
                plt.ylabel(f'Detector Response ({units})')
                plt.tight_layout(rect=[0, 0.15, 1, 1])
                pdf.savefig(fig)
                plt.close(fig)

            amplitudes = np.array(amplitudes)
            fwhms = np.array(fwhms)
            pdata['focus/fwhms'][good_resonators] = fwhms
            pdata['focus/amplitudes'][good_resonators] = amplitudes
            pdata['focus/good_resonators'][good_resonators] = 1
            self._plot_summary_statistics(
                fwhms, amplitudes, good_resonators, pdf, pdata
            )

        return ['/focus/fwhms', '/focus/amplitudes', '/focus/good_resonators']

    def _plot_summary_statistics(
        self,
        fwhms: npt.NDArray,
        amplitudes: npt.NDArray,
        good_resonators: npt.NDArray,
        pdf: PdfPages,
        pdata: ProcessedData,
    ):
        dataset = self.params['dataset']
        units = 'mK' if dataset == 'data_mK' else 'df/f'
        polarizations = pdata.detector_pol[good_resonators]

        for i_pol in [1, 2]:
            try:
                fig = plt.figure()
                plt.title(f'FWHM Histogram - Polarization {i_pol}')
                counts, bins = np.histogram(fwhms[polarizations == i_pol], bins='fd')
                mean = mean_histogram(bins[:-1], counts)
                std = std_histogram(bins[:-1], counts)
                plt.ylabel('Frequency')
                plt.xlabel('FWHM (Degrees)')
                plt.stairs(
                    counts,
                    bins,
                    fill=True,
                    label=rf'$\mu$ = {mean:.3f} deg; $\sigma$ = {std:.3f} deg',
                )
                plt.legend()
                pdf.savefig(fig)
                plt.close(fig)
            except Exception:  # noqa: BLE001
                pass

        for i_pol in [1, 2]:
            try:
                fig = plt.figure()
                plt.title(f'Amplitude Histogram - Polarization {i_pol}')
                counts, bins = np.histogram(
                    amplitudes[polarizations == i_pol], bins='fd'
                )
                mean = mean_histogram(bins[:-1], counts)
                std = std_histogram(bins[:-1], counts)
                plt.ylabel('Frequency')
                plt.xlabel(f'Amplitude ({units})')
                if dataset == 'data_mK':
                    label = rf'$\mu$ = {mean:.3f} {units}; $\sigma$ = {std:.3f} {units}'
                else:
                    label = rf'$\mu$ = {mean:.2e}; $\sigma$ = {std:.2e}'
                plt.stairs(counts, bins, fill=True, label=label)
                plt.legend()
                pdf.savefig(fig)
                plt.close(fig)
            except Exception:  # noqa: BLE001
                pass
