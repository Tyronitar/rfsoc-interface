import pdb

import numpy as np
import matplotlib.pyplot as plt

from kidpy3 import RawDataFile
from rfsocinterface.analysis.peak import check_focus
from rfsocinterface.core.data import ProcessedDataLN


if __name__ == '__main__':
    date = '20251212'
    setnum = 1003

    raw = RawDataFile('/data/20251212/20251212_Device_aSi1_Channel2_telescope_275mK_TOD_set1003.h5', 'r')
    dy241 = raw.detector_delta_y[241]
    same_dy = np.where(np.isclose(raw.detector_delta_y[:], dy241, atol=0.05))[0]

    data = ProcessedDataLN.from_file(date, setnum, level=2)
    max_sample = np.argmax(data.data_mK[241])
    # plt.figure()
    # plt.plot(data.timestamp[:], data.data_mK[241])
    # plt.axvline(data.timestamp[max_sample], color='r')

    slice_around_max = slice(max_sample-1400, max_sample+500)
    # plt.figure()
    # plt.plot(data.timestamp[slice_around_max], data.detector_az[241, slice_around_max])
    # plt.axvline(data.timestamp[max_sample], color='r')
    # plt.show()

    check_focus(data, 241, slice_around_max)


