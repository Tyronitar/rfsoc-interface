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

    for i_tile in range(1):
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
        # plt.scatter(az_center[vpol], za_center[vpol], marker=marker, color=colors[i_tile][0], label=f'Tile {i_tile + 1} V-Pol (N = {vpol.size})')
        # for i_pol in pol2:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='blue', fontsize=20.)
        # plt.scatter(az_center[hpol], za_center[hpol], marker=marker, color=colors[i_tile][1], label=f'Tile {i_tile + 1} H-Pol (N = {hpol.size})')
        # for i_pol in pol1:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='red', fontsize=20.)
    tile_1_az_centers = az_centers[0][good_inds[0]]
    tile_1_za_centers = za_centers[0][good_inds[0]]
    # tile_2_az_centers = az_centers[1][good_inds[1]]
    # tile_2_za_centers = za_centers[1][good_inds[1]]

    # Find angle the focal plane makes with the axes
    # To find the most extreme points (when y is increasing downwards):
    # Top left = min(x + y)      |      Top Right = max(x - y)
    # --------------------------------------------------------
    # Bottom left = min(x - y)   |   Bottom Right = max(x + y)
    top_left_tile_1_idx = np.argmin(tile_1_az_centers + tile_1_za_centers).flatten()
    top_left_tile_1 = np.array([tile_1_az_centers[top_left_tile_1_idx], tile_1_za_centers[top_left_tile_1_idx]]).squeeze()
    top_right_tile_1_idx = np.argmax(tile_1_az_centers - tile_1_za_centers).flatten()
    top_right_tile_1 = np.array([tile_1_az_centers[top_right_tile_1_idx], tile_1_za_centers[top_right_tile_1_idx]]).squeeze()
    bottom_left_tile_1_idx = np.argmin(tile_1_az_centers - tile_1_za_centers).flatten()
    bottom_left_tile_1 = np.array([tile_1_az_centers[bottom_left_tile_1_idx], tile_1_za_centers[bottom_left_tile_1_idx]]).squeeze()
    bottom_right_tile_1_idx = np.argmax(tile_1_az_centers + tile_1_za_centers).flatten()
    bottom_right_tile_1 = np.array([tile_1_az_centers[bottom_right_tile_1_idx], tile_1_za_centers[bottom_right_tile_1_idx]]).squeeze()

    # median = np.array(np.median(tile_1_az_centers), np.median(tile_1_za_centers))
    # diff_vector = median - bottom_left_tile_1

    # The angle from corner to corner should be 45 degrees, hence the pi / 4
    angle = np.atan2(
        bottom_left_tile_1[1] - top_right_tile_1[1],
        top_right_tile_1[0] - bottom_left_tile_1[0],
    ) + np.pi / 4


    near_field_v_pol_data = ProcessedData.load('20260710', 1006, mode='r')
    # good_ind = good_inds[0]
    near_field_az_centers = near_field_v_pol_data['beammap/az_center'][:]
    near_field_za_centers = near_field_v_pol_data['beammap/za_center'][:]
    near_field_amplitude = near_field_v_pol_data['beammap/amplitude'][:]
    high_snr = near_field_amplitude > np.percentile(near_field_amplitude, 55)
    # good_ind = np.setdiff1d(good_ind, bad_resonators[0])
    # good_ind = np.argwhere(high_snr & (detector_pol == 2)).flatten()
    good_ind = np.argwhere(high_snr & (near_field_v_pol_data.chanmask == 1)).flatten()
    good_ind = np.setdiff1d(good_ind, 660)
    # good_ind = np.argwhere(high_snr).flatten()
    # pdb.set_trace()

    near_field_centers= np.stack((near_field_az_centers, near_field_za_centers))[:, good_ind]
    plt.scatter(near_field_centers[0], near_field_centers[1], marker=marker, color='blue', label=f'Tile {i_tile + 1} V-Pol (N = {vpol.size})')
    # for i, i_res in enumerate(good_ind):
    #     plt.text(near_field_centers[0, i], near_field_centers[1, i], f'{i_res}', color='blue', fontsize=20.)
    top_left_near_field_idx = np.argmin(near_field_centers[0] + near_field_centers[1]).flatten()
    top_left_near_field = near_field_centers[:, top_left_near_field_idx].squeeze()
    top_right_near_field_idx = np.argmax(near_field_centers[0] - near_field_centers[1]).flatten()
    top_right_near_field = near_field_centers[:, top_right_near_field_idx].squeeze()
    bottom_left_near_field_idx = np.argmin(near_field_centers[0] - near_field_centers[1]).flatten()
    bottom_left_near_field = near_field_centers[:, bottom_left_near_field_idx].squeeze()
    plt.scatter(bottom_left_near_field[0], bottom_left_near_field[1], color='red', marker='o')
    plt.scatter(top_left_near_field[0], top_left_near_field[1], color='purple', marker='o')
    plt.scatter(top_right_near_field[0], top_right_near_field[1], color='green', marker='o')
    near_field_diff_vector = top_right_near_field - top_left_near_field

    # The angle from corner to corner should be 45 degrees, hence the pi / 4
    near_field_angle = np.atan2(
        bottom_left_near_field[1] - top_right_near_field[1],
        top_right_near_field[0] - bottom_left_near_field[0]
    ) + np.pi / 4

    # near_field_angle = (near_field_angle + near_field_angle1) / 2
    print(f'Far field angle: {np.rad2deg(angle):.2f} degrees')
    print(f'Near field angle: {np.rad2deg(near_field_angle):.2f} degrees')

    plt.gca().invert_yaxis()
    plt.gca().set_aspect('equal')
    plt.show()
    pdb.set_trace()
