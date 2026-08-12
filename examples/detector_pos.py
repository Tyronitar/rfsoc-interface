import h5py
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patches as patches
import pdb
import numpy as np

from rfsocinterface.core.data import ProcessedData, plot_map, get_extent
from rfsocinterface.core.params import RFSoCParameters
from rfsocinterface.core.utils import get_params_file_template, create_axis_formatter, ChanmaskValue, COLLIDED_RESONANCE_COLOR, DOUBLE_RESONANCE_COLOR, BAD_RESONANCE_COLOR
from rfsocinterface.analysis.beammap import combine_polarized_beammaps

collision_threshold = 5e-5


def plot_collided_resonances(
    hpol_data: ProcessedData,
    vpol_data: ProcessedData,
    params: RFSoCParameters,
    tile_name: str,
):
    map_az_hpol = hpol_data['map/map_az']
    map_za_hpol = hpol_data['map/map_za']
    map_az_vpol = vpol_data['map/map_az']
    map_za_vpol = vpol_data['map/map_za']
    detector_f = hpol_data.detector_f()
    sweep = hpol_data.get_lo_sweep(0)
    indices = params.bad_ind
    split_indices = np.where(np.diff(indices) != 1)[0] + 1
    chunks = np.split(indices, split_indices)
    file_name = f'{tile_name}_collisions_{collision_threshold:.2e}'.replace('.', '_') + '.pdf'
    with PdfPages(file_name) as pdf:
        for neighborhood in chunks:
            n_res = neighborhood.size
            # neighborhood = list(range(max(i_res - 1, 0), min(i_res + 3, params.n_tones)))
            # neighborhood = list(range(max(i_res - 1, 0), min(i_res + 3, params.n_tones)))
            fig, axes = plt.subplots(3, n_res, figsize=(5 * n_res, 9))
            if n_res == 1:
                axes = axes[..., np.newaxis]
            for i, i_res in enumerate(neighborhood):
                chanmask_val = params.chanmask[i_res]
                polarization = params.detector_pol[i_res]
                s = ''
                match chanmask_val:
                    case ChanmaskValue.DOUBLE_RESONANCE:
                        s = 'Double Resonance'
                    case ChanmaskValue.COLLIDED:
                        s = 'Collided Resonance'
                    case ChanmaskValue.LOW_RESPONSE:
                        s = 'Low Response'
                    case _:
                        s = 'Other'
                title = (
                    f'Tone {i_res}, {"H" if polarization == 1 else "V"}-Pol '
                    f'({s})\n'
                    rf'($f_0$={detector_f[i_res] * 1e-6:.3f} MHz)'
                )
                map_val_hpol = hpol_data['map/map_val'][i_res]
                map_val_hpol -= np.nanmedian(map_val_hpol)
                map_val_hpol /= np.max(map_val_hpol)
                plot_map(
                    map_val_hpol,
                    map_az_hpol,
                    map_za_hpol,
                    ax=axes[0, i],
                    vmax=np.max(map_val_hpol),
                    vmin=np.min(map_val_hpol),
                    dpix=0.03,
                    cmap='jet',
                    title=title + '\n\nH-Pol',
                )

                map_val_vpol = vpol_data['map/map_val'][i_res]
                map_val_vpol -= np.nanmedian(map_val_vpol)
                map_val_vpol /= np.max(map_val_vpol)
                plot_map(
                    map_val_vpol,
                    map_az_vpol,
                    map_za_vpol,
                    ax=axes[1, i],
                    vmax=np.max(map_val_vpol),
                    vmin=np.min(map_val_vpol),
                    dpix=0.03,
                    cmap='jet',
                    title='V-Pol',
                )
                axes[2, i].plot(sweep.freq[i_res], sweep.s21[i_res])
                axes[2, i].set_title(rf'LO Sweep $S_{{21}}$ for Detector {i_res}')
                axes[2, i].xaxis.set_major_formatter(create_axis_formatter(3))
                axes[2, i].set_xlabel('Frequency (MHz)')
                axes[2, i].set_ylabel(r'$S_{21}$')
                axes[2, i].axvline(sweep.fit_f0[i_res], color='red')


            fig.tight_layout()
            for i, i_res in enumerate(neighborhood):
                chanmask_val = params.chanmask[i_res]
                match chanmask_val:
                    case ChanmaskValue.DOUBLE_RESONANCE:
                        facecolor = DOUBLE_RESONANCE_COLOR
                    case ChanmaskValue.COLLIDED:
                        facecolor = COLLIDED_RESONANCE_COLOR
                    case ChanmaskValue.LOW_RESPONSE:
                        facecolor = BAD_RESONANCE_COLOR
                    case _:
                        facecolor = BAD_RESONANCE_COLOR

                # Change color of column to reflect chanmask value
                # Get position of the first and last axes in the first column
                bbox_top = axes[0, i].get_position()
                bbox_bot = axes[-1, i].get_position()

                # Define rectangle coordinates covering the first column vertically
                x0 = bbox_top.x0
                y0 = bbox_bot.y0
                width = bbox_top.width
                height = bbox_top.y1 - bbox_bot.y0

                rect = patches.Rectangle(
                    (x0, y0),
                    width,
                    height,
                    transform=fig.transFigure,
                    facecolor=facecolor,
                    edgecolor='none',
                    zorder=-1,
                )
                fig.add_artist(rect)

            pdf.savefig(fig)
            plt.close(fig)

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
    new_tile_names = (
        'Device_aSi1_Channel2_telescope_275mK_20260810',
        'Device_aSi2_Channel3_telescope_275mK_20260810'
    )
    setnums = (
        (1001, 1004),
        (1006, 1005)
    )

    bad_resonators = (
        # (256, 292, 342, 364, 580, 791),
        # (74, 87, 95, 288, 320, 416, 667, 755),
        None,
        None,
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
    chanmasks = []

    pdf = PdfPages('detector_positions.pdf')
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    fig.suptitle(f'Detector Positions and Polarizations')

    for i_tile in range(2):
        tile_name = tile_names[i_tile]
        this_setnums = setnums[i_tile]
        hpol_setnum = this_setnums[0]
        vpol_setnum = this_setnums[1]
        hpol_data = ProcessedData.load(date, hpol_setnum)
        vpol_data = ProcessedData.load(date, vpol_setnum)
        good_ind = np.setdiff1d(hpol_data.onres_ind, bad_resonators[i_tile])
        sweep = hpol_data.get_lo_sweep(0)
        angle, units, dIQ_df = sweep.freq_direction()
        az_center, za_center, detector_pol, beam_ampl, new_chanmask = combine_polarized_beammaps(
            hpol_data,
            vpol_data,
            tile_name + '_with_detector_pol',
            bad_resonators=bad_resonators[i_tile],
            focal_plane_center=focal_plane_centers[i_tile]
        )
        good_inds.append(np.argwhere(new_chanmask == ChanmaskValue.ON_RESONANCE).flatten())
        az_centers.append(az_center)
        za_centers.append(za_center)
        detector_pols.append(detector_pol)
        beam_ampls.append(beam_ampl)
        chanmasks.append(new_chanmask)

        hpol = np.argwhere((detector_pol == 1) & (new_chanmask == 1)).flatten().astype(int)
        vpol = np.argwhere((detector_pol == 2) & (new_chanmask == 1)).flatten().astype(int)
        marker = markers[i_tile]
        ax.scatter(az_center[vpol], za_center[vpol], marker=marker, color=colors[i_tile][0], label=f'Tile {i_tile + 2} V-Pol (N = {vpol.size})')
        # for i_pol in pol2:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='blue', fontsize=20.)
        ax.scatter(az_center[hpol], za_center[hpol], marker=marker, color=colors[i_tile][1], label=f'Tile {i_tile + 2} H-Pol (N = {hpol.size})')
        # for i_pol in pol1:
        #     plt.text(az_center[i_pol], za_center[i_pol], f'{i_pol}', color='red', fontsize=20.)
    tile_2_az_centers = az_centers[0][good_inds[0]]
    tile_2_za_centers = za_centers[0][good_inds[0]]
    tile_3_az_centers = az_centers[1][good_inds[1]]
    tile_3_za_centers = za_centers[1][good_inds[1]]

    # Find the center of the focal plane
    # To find the most extreme points (when y is increasing downwards):
    # Top left = min(x + y)      |      Top Right = max(x - y)
    # --------------------------------------------------------
    # Bottom left = min(x - y)   |   Bottom Right = max(x + y)
    top_left_tile_3_idx = np.argmin(tile_3_az_centers + tile_3_za_centers).flatten()
    top_left_tile_3 = np.array([tile_3_az_centers[top_left_tile_3_idx], tile_3_za_centers[top_left_tile_3_idx]]).squeeze()
    top_right_tile_2_idx = np.argmax(tile_2_az_centers - tile_2_za_centers).flatten()
    top_right_tile_2 = np.array([tile_2_az_centers[top_right_tile_2_idx], tile_2_za_centers[top_right_tile_2_idx]]).squeeze()
    # Top right of tile 1 is more complicated, since there's no detector in the corner
    bottom_right_tile_2_idx = np.argmax(tile_2_az_centers + tile_2_za_centers).flatten()
    bottom_right_tile_2 = np.array([tile_2_az_centers[bottom_right_tile_2_idx], tile_2_za_centers[bottom_right_tile_2_idx]]).squeeze()
    bottom_left_tile_3_idx = np.argmin(tile_3_az_centers - tile_3_za_centers).flatten()
    bottom_left_tile_3 = np.array([tile_3_az_centers[bottom_left_tile_3_idx], tile_3_za_centers[bottom_left_tile_3_idx]]).squeeze()
    diff_vector = bottom_left_tile_3 - bottom_right_tile_2
    true_top_right = top_left_tile_3 - diff_vector

    # Use median between tiles
    focal_center = (top_left_tile_3 + true_top_right) / 2
    # focal_center_az = np.median(np.concatenate([tile_2_az_centers[top_left_tile_2_idx], tile_1_az_centers[top_right_tile_1_idx]]))
    # focal_center_za = np.median(np.concatenate([tile_2_za_centers[top_left_tile_2_idx], tile_1_za_centers[top_right_tile_1_idx]]))
    center_offset = top_left_tile_3 - focal_center
    # center_offset_az = (tile_2_az_centers[top_left_tile_2_idx] - focal_center_az).item()
    # center_offset_za = (tile_2_za_centers[top_left_tile_2_idx] - focal_center_za).item()
    angle = np.atan2(center_offset[1], center_offset[0])
    az_shift = np.cos(-np.pi / 2) * center_offset[0] - np.sin(-np.pi/2) * center_offset[1]
    za_shift = np.cos(-np.pi / 2) * center_offset[1] + np.sin(-np.pi/2) * center_offset[0]
    first_distance = np.sqrt(center_offset[0] ** 2 + center_offset[1] ** 2)
    second_distance = np.sqrt(az_shift ** 2 + za_shift ** 2)
    focal_center[0] += az_shift
    focal_center[1] += za_shift
    # focal_center_za += za_shift
    # focal_center_az += az_shift

    ax.scatter(focal_center[0], focal_center[1], marker='o', color='black', label=f'Focal Plane Center (AZ = {focal_center[0]:.2f}, ZA = {focal_center[1]:.2f})')
    # plt.scatter(tile_2_az_centers[top_left_tile_2_idx], tile_2_za_centers[top_left_tile_2_idx], marker='o', color='red')
    # plt.scatter(true_top_right[0], true_top_right[1], marker='o', color='orange')
    # plt.scatter(focal_center[0] + az_shift, focal_center[1] + za_shift, marker='o', color='purple', label=f'Focal Plane Center with offset')
    ax.set_xlabel('AZ Position (deg)')
    ax.set_ylabel('ZA Position (deg)')
    # plt.scatter(center_az, center_za, marker='o', color='black', label='Focal Plane Center')
    ax.invert_yaxis()
    ax.set_aspect('equal')
    fig.legend()
    fig.tight_layout()
    pdf.savefig()
    plt.show()
    pdf.close()

    # Make new parameters files
    detdx_2 =  focal_center[0] - tile_2_az_centers
    detdy_2 =  focal_center[1] - tile_2_za_centers
    detdx_3 =  focal_center[0] - tile_3_az_centers
    detdy_3 =  focal_center[1] - tile_3_za_centers


    with RFSoCParameters.load(tile_names[0], mode='r') as old_tile_2_params, \
            old_tile_2_params.copy_and_update(new_tile_names[0]) as new_tile_2_params:
        new_tile_2_params.detector_delta_x[good_inds[0]] = detdx_2
        new_tile_2_params.detector_delta_y[good_inds[0]] = detdy_2
        new_tile_2_params.detector_pol[:] = detector_pols[0]
        new_tile_2_params.detector_beam_ampl[:] = beam_ampls[0]
        new_tile_2_params.chanmask[:] = chanmasks[0]
        # bad_res_tile_2 = np.setdiff1d(
        #     np.argwhere(detector_pols[0] == 0).flatten(), old_tile_2_params.offres_ind)
        # new_tile_2_params.chanmask[bad_res_tile_2] = -1
        new_tile_2_params.focal_plane_center_za = focal_center[1]
        new_tile_2_params.flag_collided_resonances(collision_threshold=collision_threshold)
        n_tones = new_tile_2_params.n_tones
        n_on_res = new_tile_2_params.onres_ind.size
        n_off_res = new_tile_2_params.offres_ind.size
        n_low = new_tile_2_params.low_response_ind.size
        n_double = new_tile_2_params.double_ind.size
        n_coll = new_tile_2_params.collided_ind.size
        n_bad = new_tile_2_params.bad_ind.size
        n_misc = new_tile_2_params.misc_bad_ind.size
        print(
            'Tile 2 tone breakdown:\n'
            f'\tTotal tones: {n_tones}\n'
            f'\tOn-resonance: {n_on_res} ({n_on_res / n_tones * 100:.2f}%)\n'
            f'\tOff-resonance: {n_off_res} ({n_off_res / n_tones * 100:.2f}%)\n'
            f'\tTotal Flagged resonances: {n_bad} ({n_bad / n_tones * 100:.2f}%)\n'
            f'\t\tLow response: {n_low} ({n_low / n_tones * 100:.2f}%)\n'
            f'\t\tDouble resonance: {n_double} ({n_double / n_tones * 100:.2f}%)\n'
            f'\t\tCollided resonance: {n_coll} ({n_coll / n_tones * 100:.2f}%)\n'
            f'\t\tOther: {n_misc} ({n_misc / n_tones * 100:.2f}%)\n'
        )
        # this_setnums = setnums[-1]
        # hpol_setnum = this_setnums[0]
        # vpol_setnum = this_setnums[1]
        # hpol_data = ProcessedData.load(date, hpol_setnum)
        # vpol_data = ProcessedData.load(date, vpol_setnum)
        # plot_collided_resonances(hpol_data, vpol_data, new_tile_2_params, new_tile_names[0])

    with RFSoCParameters.load(tile_names[1], mode='r') as old_tile_3_params, \
            old_tile_3_params.copy_and_update(new_tile_names[1]) as new_tile_3_params:
        new_tile_3_params.detector_delta_x[good_inds[1]] = detdx_3
        new_tile_3_params.detector_delta_y[good_inds[1]] = detdy_3
        new_tile_3_params.detector_pol[:] = detector_pols[1]
        new_tile_3_params.detector_beam_ampl[:] = beam_ampls[1]
        new_tile_3_params.chanmask[:] = chanmasks[1]
        # bad_res_tile_3 = np.setdiff1d(
        #     np.argwhere(detector_pols[1] == 0).flatten(), old_tile_3_params.offres_ind)
        # new_tile_3_params.chanmask[bad_res_tile_3] = -1
        new_tile_3_params.focal_plane_center_za = focal_center[1]
        new_tile_3_params.flag_collided_resonances(collision_threshold=collision_threshold)
        n_tones = new_tile_3_params.n_tones
        n_on_res = new_tile_3_params.onres_ind.size
        n_off_res = new_tile_3_params.offres_ind.size
        n_low = new_tile_3_params.low_response_ind.size
        n_double = new_tile_3_params.double_ind.size
        n_coll = new_tile_3_params.collided_ind.size
        n_bad = new_tile_3_params.bad_ind.size
        n_misc = new_tile_3_params.misc_bad_ind.size
        print(
            'Tile 3 tone breakdown:\n'
            f'\tTotal tones: {n_tones}\n'
            f'\tOn-resonance: {n_on_res} ({n_on_res / n_tones * 100:.2f}%)\n'
            f'\tOff-resonance: {n_off_res} ({n_off_res / n_tones * 100:.2f}%)\n'
            f'\tTotal Flagged resonances: {n_bad} ({n_bad / n_tones * 100:.2f}%)\n'
            f'\t\tLow response: {n_low} ({n_low / n_tones * 100:.2f}%)\n'
            f'\t\tDouble resonance: {n_double} ({n_double / n_tones * 100:.2f}%)\n'
            f'\t\tCollided resonance: {n_coll} ({n_coll / n_tones * 100:.2f}%)\n'
            f'\t\tOther: {n_misc} ({n_misc / n_tones * 100:.2f}%)\n'
        )
        # this_setnums = setnums[1]
        # hpol_setnum = this_setnums[0]
        # vpol_setnum = this_setnums[1]
        # hpol_data = ProcessedData.load(date, hpol_setnum)
        # vpol_data = ProcessedData.load(date, vpol_setnum)
        # plot_collided_resonances(hpol_data, vpol_data, new_tile_3_params, new_tile_names[1])
