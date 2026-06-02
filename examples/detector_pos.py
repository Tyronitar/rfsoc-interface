import h5py
import matplotlib.pyplot as plt
import pdb

from rfsocinterface.core.data import ProcessedData
from rfsocinterface.analysis.beammap import combine_polarized_beammaps


if __name__ == '__main__':
    # params_file = h5py.File('/data/params/params_tile_Device_aSi1_Channel2_telescope_275mK_20260304.h5')
    # dx = params_file['detector_delta_x'][:]
    # dy = params_file['detector_delta_y'][:]
    # plt.scatter(dx, dy, marker='+')
    # plt.show()

    date = '20260515'
    pol1_setnum = 1002
    pol2_setnum = 1003
    pol1_data = ProcessedData.load(date, pol1_setnum)
    pol2_data = ProcessedData.load(date, pol2_setnum)
    combine_polarized_beammaps(
        pol1_data,
        pol2_data,
        'test',
    )
