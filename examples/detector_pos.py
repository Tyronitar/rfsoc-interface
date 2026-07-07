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

    date = '20260617'
    tile_names = (
        'Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power',
        'Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power'
    )
    setnums = (
        (1001, 1004),
        (1006, 1005)
    )

    bad_resonators = (
        (256, 292, 580, 791),
        (74, 82, 88, 95, 241, 256, 302, 416, 637, 667),
    )

    for i_tile in range(2):
        tile_name = tile_names[i_tile]
        this_setnums = setnums[i_tile]
        hpol_setnum = this_setnums[0]
        vpol_setnum = this_setnums[1]
        hpol_data = ProcessedData.load(date, hpol_setnum)
        vpol_data = ProcessedData.load(date, vpol_setnum)
        sweep = hpol_data.get_lo_sweep(0)
        angle, units, dIQ_df = sweep.freq_direction()
        pdb.set_trace()
        combine_polarized_beammaps(
            hpol_data,
            vpol_data,
            tile_name + '_with_detector_pol',
        )
