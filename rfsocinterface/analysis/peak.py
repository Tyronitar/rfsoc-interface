import pdb
from typing import Literal

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial

from scipy.optimize import least_squares

from rfsocinterface.core.data import DataRoutine, ProcessedData, register_routine
from rfsocinterface.core.utils import sigma_to_fwhm

def gaussian_profile(parameters: npt.NDArray, x_vals: npt.NDArray) -> npt.NDArray:
    a0, a1, mu, sigma = parameters
    return a0 + a1 * np.exp(-0.5 * ((x_vals - mu) / sigma) ** 2)


def loss_function(parameters: npt.NDArray, x_vals: npt.NDArray, y_vals: npt.NDArray) -> npt.NDArray:
    model_vals = gaussian_profile(parameters, x_vals)
    return y_vals - model_vals


def check_focus(data: ProcessedData, resonators: list[int], primary_direction: str='az', fractional_difference_threshold: float=0.5):
    """Check focus and timing offsets."""
    # find peak going forward / back
    # fit gaussian
    # take position of both peask
    # right is 10-15
    # left is 20-25
    amplitudes = []
    fwhms = []

    # TODO: This is hard-coded specifically for 20251212set1003
    # Define this dynamically
    max_sample = np.argmax(data.data_mK[241])
    samples = slice(max_sample-1000, max_sample+500)

    for i_res in resonators:
        print(i_res)
        telescope_pos = data.detector_az[i_res] if primary_direction.lower() == 'az' else data.detector_za[i_res]
        telescope_pos = telescope_pos[samples]

        diff = telescope_pos - np.roll(telescope_pos, 1)
        turn_point = np.argmax(np.where(diff > 0)[0])
        left_indices = np.arange(0, turn_point)
        left_slice = slice(0, turn_point)
        right_indices = np.arange(turn_point, len(telescope_pos))
        right_slice = slice(turn_point, len(telescope_pos))


        data_segment = data.data_mK[i_res, samples]
        right_peak_idx = right_indices[np.argmax(data_segment[right_indices])]
        left_peak_idx = left_indices[np.argmax(data_segment[left_indices])]
        
        # plt.plot(telescope_pos)

        amplitude_guess = np.max(data.data_mK[i_res])
        x0 = [amplitude_guess / 100, amplitude_guess, telescope_pos[right_peak_idx], 0.1]
        if i_res == 6:
            pdb.set_trace()
        res_right = least_squares(
            loss_function,
            x0,
            args=(telescope_pos[right_slice], data_segment[right_slice]),
        )

        amplitude_right = res_right.x[1]
        fwhm_right = np.abs(sigma_to_fwhm(res_right.x[3]))

        x0 = [amplitude_guess / 100, amplitude_guess, telescope_pos[left_peak_idx], 0.1]
        res_left = least_squares(
            loss_function,
            x0,
            args=(telescope_pos[left_slice], data_segment[left_slice]),
        )

        amplitude_left = res_left.x[1]
        fwhm_left = np.abs(sigma_to_fwhm(res_left.x[3]))

        # if left and right agree...
        amplitude_mean = np.mean([amplitude_left, amplitude_right])
        fwhm_mean = np.mean([fwhm_left, fwhm_right])
        if np.abs(amplitude_left - amplitude_right) / amplitude_mean < fractional_difference_threshold and\
            np.abs(fwhm_left - fwhm_right) / fwhm_mean < fractional_difference_threshold:
            amplitudes.append(amplitude_mean)
            fwhms.append(fwhm_mean)

            # TODO: Plotting
    

    amplitudes = np.array(amplitudes)
    fwhms = np.array(fwhms)
    pdb.set_trace()


    plt.plot(telescope_pos[right_slice], data_segment[right_slice], label='Actual Data')
    plt.plot(telescope_pos[right_slice], gaussian_profile(res_right.x, telescope_pos[right_slice]), label='Gaussian Fit')
    plt.legend()
    plt.show()

    pdb.set_trace()

    right_slice = slice(right_peak_idx - 5, right_peak_idx + 6)
    left_slice = slice(left_peak_idx - 5, left_peak_idx + 6)

    right_fit = Polynomial.fit(telescope_pos[right_slice], data_segment[right_slice], 2).convert()
    left_fit = Polynomial.fit(telescope_pos[left_slice], data_segment[left_slice], 2).convert()

    right_az_0 = (-1 * right_fit.coef[1]) / (2 * right_fit.coef[2])
    left_az_0 = (-1 * left_fit.coef[1]) / (2 * left_fit.coef[2])


    fig = plt.figure()
    plt.title(f'Detector {i_res} Peak Finding')
    plt.plot(telescope_pos[:], data_segment, label=f'Full Trace')
    plt.plot(telescope_pos[right_slice], data_segment[right_slice], label=f'Right {primary_direction.upper()}_0 = {right_az_0:.3f}')
    plt.plot(telescope_pos[left_slice], data_segment[left_slice], label=f'Left {primary_direction.upper()}_0 = {left_az_0:.3f}')
    scan_rate = (telescope_pos[right_peak_idx + 10] - telescope_pos[right_peak_idx - 10]) \
        / (data.time[right_peak_idx + 10] - data.time[right_peak_idx - 10])
    time_delay = (left_az_0 - right_az_0) / scan_rate / 2  # Amount RFSoC is behind the telescope
    plt.plot([], [], label=f'Time Delay (seconds RFSoC lags behind telescope)= {time_delay:.3f}s')
    plt.legend(loc="lower center", bbox_transform=fig.transFigure, bbox_to_anchor=(0.5, 0.0), ncol=2)
    plt.xlim(telescope_pos[right_peak_idx - 50], telescope_pos[right_peak_idx + 50])
    plt.tight_layout(rect=[0, 0.15, 1, 1])
    plt.xlabel(f'{"Azimuth" if primary_direction.lower() == "az" else "Zenith Angle"} (degrees)')
    plt.ylabel('Detector Response (mK)')
    return fig, time_delay


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

