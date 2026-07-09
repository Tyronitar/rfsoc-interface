import h5py
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import numpy as np

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
        (74, 87, 95, 288, 667, 755),
    )
    focal_plane_centers = (
        'top left',
        'top right',
    )
    markers = (
        'x',
        '*'
    )
    colors = (
        ('blue', 'red'),
        ('green', 'orange'),
    )

    az_centers = []
    za_centers = []
    detector_pols = []
    beam_ampls = []
    good_inds = []

    pdf = PdfPages('detector_positions.pdf')
    plt.figure(figsize=(10, 10))
    plt.title(f'Detector Positions and Polarizations')

    for i_tile in range(2):
        tile_name = tile_names[i_tile]
        this_setnums = setnums[i_tile]
        hpol_setnum = this_setnums[0]
        vpol_setnum = this_setnums[1]
        hpol_data = ProcessedData.load(date, hpol_setnum)
        vpol_data = ProcessedData.load(date, vpol_setnum)
        good_ind = np.setdiff1d(hpol_data.onres_ind, bad_resonators[i_tile])
        good_inds.append(good_ind)
        sweep = hpol_data.get_lo_sweep(0)
        angle, units, dIQ_df = sweep.freq_direction()
        az_center, za_center, detector_pol, beam_ampl = combine_polarized_beammaps(
            hpol_data,
            vpol_data,
            tile_name + '_with_detector_pol',
            bad_resonators=bad_resonators[i_tile],
            focal_plane_center=focal_plane_centers[i_tile]
        )
        az_centers.append(az_center)
        za_centers.append(za_center)
        detector_pols.append(detector_pol)
        beam_ampls.append(beam_ampl)

        hpol = np.argwhere(detector_pol == 1).flatten().astype(int)
        vpol = np.argwhere(detector_pol == 2).flatten().astype(int)
        marker = markers[i_tile]
        plt.scatter(az_center[vpol], za_center[vpol], marker=marker, color=colors[i_tile][0], label=f'Tile {i_tile + 1} V-Pol (N = {vpol.size})')
        # for i_pol in pol2:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='blue', fontsize=20.)
        plt.scatter(az_center[hpol], za_center[hpol], marker=marker, color=colors[i_tile][1], label=f'Tile {i_tile + 1} H-Pol (N = {hpol.size})')
        # for i_pol in pol1:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='red', fontsize=20.)
    tile_1_az_centers = az_centers[0][good_inds[0]]
    tile_1_za_centers = za_centers[0][good_inds[0]]
    tile_2_az_centers = az_centers[1][good_inds[1]]
    tile_2_za_centers = za_centers[1][good_inds[1]]

    # Find the center of the focal plane
    # To find the most extreme points (when y is increasing downwards):
    # Top left = min(x + y)      |      Top Right = max(x - y)
    # --------------------------------------------------------
    # Bottom left = min(x - y)   |   Bottom Right = max(x + y)
    top_left_tile_1 = np.argmin(tile_1_az_centers + tile_1_za_centers).flatten()
    top_right_tile_2 = np.argmax(tile_2_az_centers - tile_2_za_centers).flatten()
    # Use median between tiles
    focal_center_az = np.median(np.concatenate([tile_1_az_centers[top_left_tile_1], tile_2_az_centers[top_right_tile_2]]))
    focal_center_za = np.median(np.concatenate([tile_1_za_centers[top_left_tile_1], tile_2_za_centers[top_right_tile_2]]))

    plt.scatter(focal_center_az, focal_center_za, marker='o', color='black', label=f'Focal Plane Center (AZ = {focal_center_az:.2f}, ZA = {focal_center_za:.2f})')
    plt.xlabel('AZ Position (deg)')
    plt.ylabel('ZA Position (deg)')
    # plt.scatter(center_az, center_za, marker='o', color='black', label='Focal Plane Center')
    plt.gca().invert_yaxis()
    plt.legend()
    plt.tight_layout()
    pdf.savefig()
    plt.show()
    pdf.close()

    detdx_1 =  focal_center_az - tile_1_az_centers
    detdy_1 =  focal_center_za - tile_1_za_centers
    detdx_2 =  focal_center_az - tile_2_az_centers
    detdy_2 =  focal_center_za - tile_2_za_centers
    pdb.set_trace()

