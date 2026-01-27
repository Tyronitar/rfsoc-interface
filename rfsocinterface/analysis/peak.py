import pdb

from kidpy3 import RawDataFile
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial

from scipy.optimize import least_squares

from rfsocinterface.core.data import ProcessedData, ProcessedDataL0, ProcessedDataLN
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


if __name__ == '__main__':
    date = '20251212'
    setnum = 1002

    raw = RawDataFile(f'/data/{date}/{date}_Device_aSi1_Channel2_telescope_275mK_TOD_set{setnum}.h5', 'r')
    i_res = 241
    dy = raw.detector_delta_y[i_res]
    same_dy = np.where(np.isclose(raw.detector_delta_y[:], dy, atol=0.05))[0]

    # l0 = ProcessedDataL0.from_file(date, setnum)
    # packet_indices = l0.get_node_value('packet_index')[:]
    # packet_indices = np.arange(np.min(packet_indices), np.max(packet_indices)+1)

    # plt.plot(raw.fh['time_ordered_data/pkt_idx'][:], raw.timestamp[:])
    # plt.plot(packet_indices, l0.timestamp[:])
    # plt.show()

    data = ProcessedDataLN.from_file(date, setnum, level=2)
    # plt.figure()
    # plt.plot(data.timestamp[:], data.data_mK[i_res])
    # plt.axvline(data.timestamp[max_sample], color='r')


    # plt.figure()
    # plt.plot(data.timestamp[slice_around_max], data.detector_az[i_res, slice_around_max])
    # plt.axvline(data.timestamp[max_sample], color='r')
    # plt.show()
    # pdb.set_trace()

    same_dy = same_dy[data.chanmask[same_dy] == 1]
    fig, delay = check_focus(data, same_dy)
    pdb.set_trace()
    # same_dy = np.setdiff1d(same_dy, [389, 390, 617, 618])
    delays = np.zeros(len(same_dy))
    with PdfPages('timing_offsets.pdf') as pdf:
        for i, i_res in enumerate(same_dy):
            print(i_res)
            fig, delay = check_focus(data, i_res)
            delays[i] = delay
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)
    pdb.set_trace()
    exit()

