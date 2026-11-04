
import pdb

import h5py
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from kidpy3 import RawDataFile

from rfsocinterface.core.data.utils import interpolate_telescope_positions, find_missed_packets_with_indices, interpolate_timestamp_streaming, align_telescope_positions

from rfsocinterface.core.utils import compute_chunk_shape, iterate_chunks
from examples.beammaps import plot_signal_mask

if __name__ == '__main__':
    azel = '/data/20261104/20261104_AZEL_set1003.h5'
    f = h5py.File(azel, 'r')
    x = f['timestamp_tel'][:]
    x -= x[0]
    diff_za = np.concatenate([[0], np.diff(f['za_pps'][:])])
    is_diff_za = (diff_za != 0).astype(int)
    diff_az = np.concatenate([[0], np.diff(f['az_pps'][:])])
    is_diff_az = (diff_az != 0).astype(int)
    plt.scatter(x, is_diff_za, label='za_pps', marker='+')
    plt.scatter(x, f['za_pps_latch'][:], label='za_pps_latch', marker='x')
    plt.scatter(x, is_diff_az, label='az_pps', marker='.')
    plt.legend()
    plt.show()
    pdb.set_trace()


    downsampling_factor = 16

    date = '20260617'
    setnum = 1004
    tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power'
    tod_path = f'/data/{date}/{date}_{tile_name}_TOD_set{setnum}.h5'
    azel_path = f'/data/{date}/{date}_AZEL_set{setnum}.h5'
    azel_file = h5py.File(azel_path, 'r')
    raw_data = RawDataFile(tod_path, 'r')
    new_file = h5py.File('tel_pos.h5', 'a')

    n_samples_raw = raw_data.adc_i.shape[-1]
    pkt_idx = raw_data.pkt_idx
    missed_packets = find_missed_packets_with_indices(pkt_idx)

    n_missed = int(np.sum(missed_packets[:, 1]))
    n_samples = n_samples_raw + n_missed
    n_samples_ds = int(np.ceil(n_samples / downsampling_factor))

    chunk_shape_1d = compute_chunk_shape((), 8, max_chunk_size=n_samples)
    chunk_shape_1d_ds = compute_chunk_shape((), 8, max_chunk_size=n_samples_ds)
    azel_shape_1d_ds = (n_samples_ds,)


    # Get interpolated timestamp
    if 'full_timestamp' not in new_file:
        full_timestamp = new_file.create_dataset(
            'full_timestamp',
            shape=(n_samples,),
            chunks=chunk_shape_1d,
            dtype=np.float64,
        )
        interpolate_timestamp_streaming(
            raw_data.timestamp,
            full_timestamp,
            pkt_idx,
        )
    else:
        full_timestamp = new_file['full_timestamp'][:]

    # Copy pps
    if 'full_pps' not in new_file:
        full_pps = new_file.create_dataset(
            'full_pps',
            shape=(n_samples,),
            dtype=np.uint8,
            chunks=chunk_shape_1d,
        )
        for chunk_start, chunk_end, chunk in iterate_chunks(
            raw_data.pps, chunk_size=4096
        ):
            sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
            full_pps[sample_indices] = chunk
    else:
        full_pps = new_file['full_pps'][:]


    # Load telescope datasets
    timestamp_tel = azel_file['timestamp_tel']
    az_tel = azel_file['az_tel']
    za_tel = azel_file['za_tel']
    az_pps_tel = azel_file['az_pps']
    za_pps_tel = azel_file['za_pps']
    if 'map_signal_mask' in azel_file:
        raw_map_signal_mask = azel_file['map_signal_mask']
    else:
        # For backwards compatibility, the entire dataset is marked as signal
        raw_map_signal_mask = np.ones(za_tel.size, dtype=bool)

    tel_alignment = align_telescope_positions(
        full_timestamp,
        full_pps,
        timestamp_tel,
        az_tel,
        za_tel,
        az_pps_tel,
        za_pps_tel,
        raw_map_signal_mask,
        primary_axis='az',
    )
    corrected_az_tel = tel_alignment.az
    corrected_za_tel = tel_alignment.za
    map_signal_mask = tel_alignment.signal_mask

    corrected_az_tel_old, corrected_signal_mask_az = (
        interpolate_telescope_positions(
            full_timestamp,
            timestamp_tel[:],
            az_tel[:],
            az_pps_tel[:],
            full_pps[:],
            raw_map_signal_mask[:],
            direction='az',
        )
    )

    corrected_za_tel_old, corrected_signal_mask_za = (
        interpolate_telescope_positions(
            full_timestamp,
            timestamp_tel[:],
            za_tel[:],
            za_pps_tel[:],
            full_pps[:],
            raw_map_signal_mask[:],
            direction='za',
        )
    )

    # plot_signal_mask(
    #     map_signal_mask,
    #     corrected_az_tel,
    #     corrected_za_tel,
    #     f'{date}_set{setnum}'
    # )
    plt.figure()
    plt.title(f'{date}_set{setnum} - Azimuth vs Time')
    plt.xlabel('Time')
    plt.ylabel('Azimuth (deg)')
    plt.plot(timestamp_tel[:], az_tel[:], label='Raw telescope positions')
    plt.plot(full_timestamp[:], corrected_az_tel_old, label='Old method')
    plt.plot(full_timestamp[:], corrected_az_tel, label='New method')
    plt.legend()

    plt.figure()
    plt.title(f'{date}_set{setnum} - Zenith Angle vs Time')
    plt.xlabel('Time')
    plt.ylabel('Zenith Angle (deg)')
    plt.plot(timestamp_tel[:], za_tel[:], label='Raw telescope positions')
    plt.plot(full_timestamp[:], corrected_za_tel_old, label='Old method')
    plt.plot(full_timestamp[:], corrected_za_tel, label='New method')
    plt.legend()

    plt.show()


    idx = np.arange(n_samples)
    plt.figure()
    plt.title(f'{date}_set{setnum} - Telescope Position Over Time - Old Method')
    plt.xlabel('Azimuth (deg)')
    plt.ylabel('Zenith Angle (deg)')
    plt.scatter(corrected_az_tel_old, corrected_za_tel_old, c=idx / n_samples, cmap='viridis')

    plt.figure()
    plt.title(f'{date}_set{setnum} - Telescope Position Over Time - New Method')
    plt.xlabel('Azimuth (deg)')
    plt.ylabel('Zenith Angle (deg)')
    plt.scatter(corrected_az_tel, corrected_za_tel, c=idx / n_samples, cmap='viridis')

    plt.show()
    pdb.set_trace()


