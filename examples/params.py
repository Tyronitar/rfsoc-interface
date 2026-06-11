import pdb

import numpy as np

from rfsocinterface.core.params import RFSoCParameters

if __name__ == '__main__':
    tones = np.linspace(15, 250, 50) * 1e6
    bb_freqs = np.sort(np.concatenate((-tones, tones)))

    params = RFSoCParameters.new_file('test_100_tones_20260610', 100)
    params.baseband_freqs[:] = bb_freqs
    params.rfin = 15
    params.rfout = 15
    params.close()


