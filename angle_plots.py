import tables
from rfsocinterface.core.data import MapData
import numpy as np
from numpy.polynomial import Polynomial
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
from scipy import signal
import pdb

from rfsocinterface.core.data.storage import ProcessedData
from rfsocinterface.analysis.noise_blob import plot_angle_in_blob


if __name__ == '__main__':
    # date = '20250912'
    # setnum = 1014
    # data = MapData.from_file(date, setnum, 'r')
    date = '20250916'
    setnum = 1017
    # data = ProcessedData.from_file(date, setnum, 'r')
    data = ProcessedData.from_tod(date, setnum)
    raw_data = tables.File('/data/20250916/20250916_Be231102p2_100_tones_TOD_set1017.h5', 'r')
    freq = raw_data.root.global_data.baseband_freqs[:] + raw_data.root.global_data.lo_freq[:] 
    freq *= 1e-6

    with PdfPages(f'{date}_{setnum}_IQ_rotation.pdf') as pdf:
        # for i_res in range(data.n_tones):
        for i_res in np.argwhere(data.chanmask[:] == 1).flatten():
            print(f'Resonator {i_res}:')
            fig = plot_angle_in_blob(
                data.data_IQ[:, i_res],
                data.data_freq_diss[:, i_res],
                data.IQ_to_freq_diss_angle[i_res],
                data.adc_units_to_hz[i_res],
                title=f'IQ to Frequency/Dissipation Rotation for Resonator {i_res} ($f = {freq[i_res]:.3f}$ MHz)',
                fit_order=1,
                alpha=0.1,
                sigma=4,
                markersize=1,
            )
            pdf.savefig(fig)
            plt.close(fig)

    # plt.show()
    data.close()
    raw_data.close()

    # good_chan = data.chanmask[:] == 1
    # quad_sum = np.sqrt(data.data_I[good_chan, :] ** 2 + data.data_Q[good_chan, :] ** 2)
    # source_peak_idx = np.argmax(quad_sum, axis=1)

    # peak_I = data.data_I[good_chan, source_peak_idx]
    # peak_Q = data.data_Q[good_chan, source_peak_idx]

    # angle = -np.atan2(peak_Q, peak_I)

    # plt.figure()
    # plt.scatter(data.IQ_to_freq_diss_angle[good_chan], angle)
    # one_to_one = np.arange(-4, 4) 
    # plt.plot(one_to_one, one_to_one, linestyle='--', color='red')
    # plt.plot(one_to_one, one_to_one + np.pi / 2, linestyle='--', color='green')
    # plt.figure()
    # diff = data.IQ_to_freq_diss_angle[good_chan] - angle
    # pdb.set_trace()

    # too_large_indices = np.where(diff > np.pi)
    # too_small_indices = np.where(diff < -np.pi)
    # diff[too_large_indices] -= 2 * np.pi
    # diff[too_small_indices] += 2 * np.pi

    # plt.hist(diff)

    # plt.figure()
    # plt.scatter(np.arange(np.count_nonzero(data.chanmask)), diff)

    # plt.show()
    # pdb.set_trace()
    # data.close()
    # raw_data.close()
