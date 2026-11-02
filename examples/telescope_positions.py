
import pdb

import h5py
import numpy as np
import numpy.typing as npt
from kidpy3 import RawDataFile

from rfsocinterface.core.data.utils import interpolate_telescope_positions, find_missed_packets_with_indices, interpolate_timestamp_streaming

from rfsocinterface.core.utils import compute_chunk_shape, iterate_chunks

if __name__ == '__main__':
    downsampling_factor = 16

    setnum = 1018
    tod_path = f'/data/20261023/20261023_Device_aSi3_Channel4_with_max_power_and_offres_TOD_set{setnum}.h5'
    azel_path = f'/data/20261023/20261023_AZEL_set{setnum}.h5'
    azel_file = h5py.File(azel_path, 'r')
    raw_data = RawDataFile(tod_path, 'r')
    new_file = h5py.File('tel_pos.h5', 'a')

    n_samples_raw = raw_data.adc_i.shape[-1]
    pkt_idx = raw_data.pkt_idx
    missed_packets = find_missed_packets_with_indices(pkt_idx)

    n_missed = int(np.sum(missed_packets[:, 1]))
    n_samples = n_samples_raw + n_missed
    n_samples_ds = int(np.ceil(n_samples / downsampling_factor))
    pdb.set_trace()

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
        full_pps = new_file['full_pps']


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


    corrected_az_tel, corrected_signal_mask_az = (
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
    pdb.set_trace()

