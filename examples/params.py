import pdb

from pathlib import Path
import numpy as np

from rfsocinterface.core.params import RFSoCParameters, update_params_file_format

if __name__ == '__main__':
    files = Path('/data/params/').glob('*.h5')
    update_params_file_format(*files)
    # tones = np.linspace(15, 250, 50) * 1e6
    # bb_freqs = np.sort(np.concatenate((-tones, tones)))

    # params = RFSoCParameters.new_file('test_100_tones_20260610', 100)
    # params.baseband_freqs[:] = bb_freqs
    # params.rfin = 15
    # params.rfout = 15
    # params.close()


