from rfsocinterface.core.data import ProcessedData, MapData
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import pdb


if __name__ == '__main__':
    date = '20250912'
    setnum = 1014
    data = MapData.from_file(date, setnum, 'r')

    quad_sum = np.sqrt(data.data_I[:] ** 2 + data.data_Q[:] ** 2)
    source_peak_idx = np.argmax(quad_sum, axis=1)

    peak_I = data.data_I[np.arange(data.n_tones, dtype=int), source_peak_idx]
    peak_Q = data.data_Q[np.arange(data.n_tones, dtype=int), source_peak_idx]

    angle = -np.atan2(peak_Q, peak_I)

    plt.figure()
    plt.scatter(data.IQ_to_freq_diss_angle[:], angle)
    one_to_one = np.arange(-4, 4) 
    plt.plot(one_to_one, one_to_one, linestyle='--', color='red')
    plt.plot(one_to_one, one_to_one + np.pi / 2, linestyle='--', color='green')
    plt.figure()
    diff = data.IQ_to_freq_diss_angle[:] - angle

    too_large_indices = np.where(diff > np.pi)
    too_small_indices = np.where(diff < -np.pi)
    diff[too_large_indices] -= 2 * np.pi
    diff[too_small_indices] += 2 * np.pi

    plt.hist(diff)

    plt.figure()
    plt.scatter(np.arange(data.n_tones), diff)

    plt.show()
    pdb.set_trace()
