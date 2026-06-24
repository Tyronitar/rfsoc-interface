import pdb
from typing import Literal

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial

from scipy.optimize import least_squares

from rfsocinterface.core.data import DataRoutine, ProcessedData, register_routine
from rfsocinterface.core.utils import sigma_to_fwhm
from rfsocinterface.core.utils import mean_histogram
from rfsocinterface.core.utils import std_histogram

def gaussian_profile(parameters: npt.NDArray, x_vals: npt.NDArray) -> npt.NDArray:
    a0, a1, mu, sigma = parameters
    return a0 + a1 * np.exp(-0.5 * ((x_vals - mu) / sigma) ** 2)


def loss_function(parameters: npt.NDArray, x_vals: npt.NDArray, y_vals: npt.NDArray) -> npt.NDArray:
    model_vals = gaussian_profile(parameters, x_vals)
    return y_vals - model_vals

def check_focus(pdata: ProcessedData, resonators: list[int], primary_direction: str='az', fractional_difference_threshold: float=0.5, dataset: str='data_mK'):
    """Check focus and timing offsets."""
    # find peak going forward / back
    # fit gaussian
    # take position of both peask
    # right is 10-15
    # left is 20-25
    amplitudes = []
    fwhms = []
    good_resonators = []
    data = pdata.data_mK[:] if dataset == 'data_mK' else pdata.data_freq_diss[0] / pdata.detector_f()[:, np.newaxis]
    units = 'mK' if dataset == 'data_mK' else 'df/f'

    # TODO: This is hard-coded specifically for 20251212set1003
    # Define this dynamically
    max_sample = np.argmax(data[282])
    samples = slice(max(max_sample-1000, 0), min(max_sample+500, pdata.n_samples))

    with PdfPages(f'peaks_{pdata.file_stub}.pdf') as pdf:

        for i_res in resonators:
            print(i_res)
            telescope_pos = pdata.detector_az[i_res] if primary_direction.lower() == 'az' else pdata.detector_za[i_res]
            first_good_sample = np.argwhere(~np.isnan(telescope_pos))[0]
            last_good_sample = np.argwhere(~np.isnan(telescope_pos))[-1]
            relative_pos = np.abs(telescope_pos - telescope_pos[first_good_sample])
            samples_0 = np.argmax((relative_pos >= 0.5) & ~np.isnan(telescope_pos))
            relative_pos = np.abs(telescope_pos - telescope_pos[last_good_sample])
            samples_1 = np.where(((relative_pos >= 0.5) & ~np.isnan(telescope_pos)))[0][-1]
            samples = slice(samples_0, samples_1)
            telescope_pos = telescope_pos[samples]

            # diff = telescope_pos - np.roll(telescope_pos, 1)
            # turn_point = np.nanargmax(diff)
            turn_point = np.nanargmax(telescope_pos)
            left_indices = np.arange(0, turn_point)
            left_slice = slice(0, turn_point)
            right_indices = np.arange(turn_point, len(telescope_pos))
            right_slice = slice(turn_point, len(telescope_pos))

            data_segment = data[i_res, samples]
            right_peak_idx = right_indices[np.argmax(data_segment[right_indices])]
            left_peak_idx = left_indices[np.argmax(data_segment[left_indices])]

            right_fit_ind = np.argwhere(np.isclose(telescope_pos, telescope_pos[right_peak_idx], atol=0.5)).flatten()
            right_fit_ind = right_fit_ind[np.isclose(right_fit_ind, right_peak_idx, atol=100)]
            left_fit_ind = np.argwhere(np.isclose(telescope_pos, telescope_pos[left_peak_idx], atol=0.5)).flatten()
            left_fit_ind = left_fit_ind[np.isclose(left_fit_ind, left_peak_idx, atol=100)]
            
            # plt.plot(telescope_pos)

            amplitude_guess = np.max(data[i_res])
            x0 = [amplitude_guess / 100, amplitude_guess, telescope_pos[right_peak_idx], 0.1 / (2 * np.sqrt(2 * np.log(2)))]
            res_right = least_squares(
                loss_function,
                x0,
                args=(telescope_pos[right_fit_ind], data_segment[right_fit_ind]),
                bounds=([-1, 0, -15, 0.05 / (2 * np.sqrt(2 * np.log(2)))], [1, 1, 15, 0.2 / (2 * np.sqrt(2 * np.log(2)))]),
            )

            amplitude_right = res_right.x[1]
            fwhm_right = np.abs(sigma_to_fwhm(res_right.x[3]))
            right_az_0 = res_right.x[2]

            x0 = [amplitude_guess / 100, amplitude_guess, telescope_pos[left_peak_idx], 0.1 / (2 * np.sqrt(2 * np.log(2)))]
            res_left = least_squares(
                loss_function,
                x0,
                args=(telescope_pos[left_fit_ind], data_segment[left_fit_ind]),
                bounds=([-1, 0, -15, 0.05 / (2 * np.sqrt(2 * np.log(2)))], [1, 1, 15, 0.2 / (2 * np.sqrt(2 * np.log(2)))]),
            )

            amplitude_left = res_left.x[1]
            fwhm_left = np.abs(sigma_to_fwhm(res_left.x[3]))
            left_az_0 = res_left.x[2]

            # if left and right agree...
            amplitude_mean = np.mean([amplitude_left, amplitude_right])
            fwhm_mean = np.mean([fwhm_left, fwhm_right])
            if np.abs(amplitude_left - amplitude_right) / amplitude_mean < fractional_difference_threshold and\
                np.abs(fwhm_left - fwhm_right) / fwhm_mean < fractional_difference_threshold:
                amplitudes.append(amplitude_mean)
                fwhms.append(fwhm_mean)
                good_resonators.append(i_res)

                # TODO: Plotting
        
            # plt.plot(telescope_pos[right_slice], data_segment[right_slice], label='Actual Data')
            # plt.plot(telescope_pos[right_slice], gaussian_profile(res_right.x, telescope_pos[right_slice]), label='Gaussian Fit')
            # plt.legend()
            # plt.show()

            # right_slice = slice(right_peak_idx - 5, right_peak_idx + 6)
            # left_slice = slice(left_peak_idx - 5, left_peak_idx + 6)

            # right_fit = Polynomial.fit(telescope_pos[right_slice], data_segment[right_slice], 2).convert()
            # left_fit = Polynomial.fit(telescope_pos[left_slice], data_segment[left_slice], 2).convert()

            # right_az_0 = (-1 * right_fit.coef[1]) / (2 * right_fit.coef[2])
            # left_az_0 = (-1 * left_fit.coef[1]) / (2 * left_fit.coef[2])


            time = pdata.timestamp[:] - pdata.timestamp[0]
            fig = plt.figure(figsize=(8,5))
            plt.title(f'Detector {i_res} Peak Finding (Polarization {pdata.detector_pol[i_res]})')
            plt.plot(telescope_pos[:], data_segment, label=f'Full Trace', color='b')
            plt.plot(telescope_pos[right_fit_ind], data_segment[right_fit_ind], label=f'Right (${{{primary_direction.upper()}}}_0$ = {right_az_0:.3f})', color='orange')
            right_gaussian = gaussian_profile(res_right.x, telescope_pos[right_fit_ind])
            plt.plot(telescope_pos[right_fit_ind], right_gaussian, linestyle='--', color='orange')
            right_patch = mpatches.Patch(color='orange', label=f'Amplitude = {amplitude_right:.3e} {units}, FWHM = {fwhm_right:.3f} deg')

            plt.plot(telescope_pos[left_fit_ind], data_segment[left_fit_ind], label=f'Left (${{{primary_direction.upper()}}}_0$ = {left_az_0:.3f})', color='green')
            left_gaussian = gaussian_profile(res_left.x, telescope_pos[left_fit_ind])
            plt.plot(telescope_pos[left_fit_ind], left_gaussian, linestyle='--', color='green')
            left_patch = mpatches.Patch(color='green', label=f'Amplitude = {amplitude_left:.3e} {units}, FWHM = {fwhm_left:.3f} deg')

            scan_rate = (telescope_pos[min(right_peak_idx + 10, len(telescope_pos) - 1)] - telescope_pos[max(right_peak_idx - 10, 0)]) \
                / (time[min(right_peak_idx + 10, len(telescope_pos) - 1)] - time[max(right_peak_idx - 10, 0)])
            time_delay = (left_az_0 - right_az_0) / scan_rate / 2  # Amount RFSoC is behind the telescope
            plt.plot([], [], label=f'Time Delay = {time_delay:.3f}s')
            plt.legend(loc="lower center", bbox_transform=fig.transFigure, bbox_to_anchor=(0.5, 0.0), ncol=3)
            handles = plt.gca().get_legend_handles_labels()[0]
            handles.append(right_patch)
            handles.append(left_patch)
            handles = [handles[i] for i in [0, 3, 1, 2, 4, 5]]
            plt.legend(loc="lower center", bbox_transform=fig.transFigure, bbox_to_anchor=(0.5, 0.0), ncol=3, handles=handles, fontsize=8)
            plt.xlim(telescope_pos[max(0, right_peak_idx - 50)], telescope_pos[min(right_peak_idx + 50, len(telescope_pos)-1)])
            plt.xlabel(f'{"Azimuth" if primary_direction.lower() == "az" else "Zenith Angle"} (degrees)')
            plt.ylabel(f'Detector Response ({units})')
            plt.tight_layout(rect=[0, 0.15, 1, 1])
            pdf.savefig(fig)
            # plt.show()
            # pdb.set_trace()
            plt.close(fig)

        amplitudes = np.array(amplitudes)
        fwhms = np.array(fwhms)

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
                plt.stairs(counts, bins, fill=True, label=rf'$\mu$ = {mean:.3f} deg; $\sigma$ = {std:.3f} deg')
                plt.legend()
                pdf.savefig(fig)
                plt.close(fig)
            except Exception as e:
                print(e)
                pass

        for i_pol in [1, 2]:
            try:
                fig = plt.figure()
                plt.title(f'Amplitude Histogram - Polarization {i_pol}')
                counts, bins = np.histogram(amplitudes[polarizations == i_pol], bins='fd')
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
            except Exception as e:
                print(e)
                pass

    return amplitudes, fwhms

    # return fig, time_delay


@register_routine
class FindFWHM(DataRoutine):
    name = 'FindFWHM'
    version = '1.0.0'

    def __init__(
        self,
        primary_direction: Literal['az', 'za'],
        resonators: list[int],
        fit_radius_deg: float=0.5,
        fit_radius_sec: float=3,
        fractional_difference_threshold: float=0.5,
    ):
        super().__init__(
            primary_direction=primary_direction,
            resonators=resonators,
            fit_radius_deg=fit_radius_deg,
            fit_radius_sec=fit_radius_sec,
            fractional_difference_threshold=fractional_difference_threshold,
        )
    
    def inputs(self, pdata: ProcessedData):
        return ['/vdsets/detector_az', '/vdsets/detector_za', '/vdsets/data_mK', '/global_data/timestamp']

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        primary_direction = self.params['primary_direction']
        resonators = self.params['resonators']
        fit_radius_deg = self.params['fit_radius_deg']
        fit_radius_sec = self.params['fit_radius_sec']
        fractional_difference_threshold = self.params['fractional_difference_threshold']

        amplitudes = []
        fwhms = []
        for i_res in resonators:

            data = pdata.data_mK[i_res]
            telescope_pos = pdata.detector_az[i_res] if primary_direction.lower() == 'az' else pdata.detector_za[i_res]
            peak_idx = np.argmax(data).flatten().item()
            amplitude_guess = data[peak_idx]
            peak_pos = telescope_pos[peak_idx]

            x0 = [amplitude_guess / 100, amplitude_guess, telescope_pos[peak_idx], 0.1]
            sample_indices = np.arange(pdata.n_samples)
            fit_radius_samples = pdata.fs * fit_radius_sec

            # Look at region around the peak, within specified degrees, but make sure the
            # sample index is close (in case the telescope crossed that point multiple times).
            fit_region = np.argwhere(
                (peak_pos - fit_radius_deg <= telescope_pos) & 
                (telescope_pos <= peak_pos + fit_radius_deg) &
                (peak_idx - fit_radius_samples <= sample_indices) &
                (sample_indices <= peak_idx + fit_radius_samples)
            ).flatten()
            res = least_squares(
                loss_function,
                x0,
                args=(telescope_pos[fit_region], data[fit_region]),
            )
            amplitude = res.x[1]
            fwhm = np.abs(sigma_to_fwhm(res.x[3]))
            pdb.set_trace()
            amplitudes.append(amplitude)
            fwhms.append(fwhm)
            plt.plot(telescope_pos, data, label='Actual Data')
            plt.plot(telescope_pos[fit_region], gaussian_profile(res.x, telescope_pos[fit_region]), label=f'Gaussian Fit (FWHM = {fwhm:.2f}')
            plt.legend()
            plt.show()
        
        amplitudes = np.array(amplitudes)
        fwhms = np.array(fwhms)
        pdb.set_trace()
            # pdb.set_trace()
            # fit = Polynomial.fit(telescope_pos[fit_region], data[fit_region], 2)

            # plt.plot(telescope_pos, data, label='Full Trace')
            # plt.plot(telescope_pos[fit_region], data[fit_region], label='Fit Region')
            # plt.legend()
            # plt.show()
            # pdb.set_trace()
        return []

