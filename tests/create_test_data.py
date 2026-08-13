from kidpy3 import RawDataFile

from rfsocinterface.core.data import ConsolidatedData, ProcessedData

from unittest.mock import patch, mock_open
import h5py
import pdb
import numpy as np

def make_tod():
    """Make a fake TOD file for testing."""
    old = RawDataFile('/data/20260617/20260617_Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power_TOD_set1005.h5', 'r')
    data = RawDataFile('tests/test_data/20260709/20260709_Test_Tile_TOD_set1001.h5', 'w')

    n_samples = 500
    n_tones = 100
    tones = range(450, 550)
    data.format(n_samples, n_tones)

    print('Copying time-independent data')
    # Copy time-independent data
    data.baseband_freqs[:] = old.baseband_freqs[tones]
    data.tone_powers[:] = old.tone_powers[tones]
    data.lo_freq[0] = 400e6
    data.chanmask[:] = np.ones(n_tones, dtype=int)
    data.attenuator_settings[:] = [15.0, 15.0]
    data.sample_rate[:] = 488
    data.tile_number[:] = 0
    data.chan_number[:] = 0
    data.rfsoc_number[:] = 0
    data.ifslice_number[:] = 0
    data.n_attenuators[:] = 0

    data.detector_dx_dy_elevation_angle[:] = 89.0

    data.detector_delta_x[:] = np.zeros(n_tones)
    data.detector_delta_y[:] = np.zeros(n_tones)
    data.detector_beam_ampl[:] = np.ones(n_tones)
    data.detector_pol[:] = np.ones(n_tones, dtype=np.int32)
    data.dfoverf_per_mK[:] = np.ones(n_tones)

    print('Copying LO sweep')
    data.fh.create_dataset('/global_data/lo_sweep', data=old.lo_sweep[:, tones])
    data.fh.attrs['has_lo_sweep'] = True

    # Copy time ordered data
    print('Copying time-ordered data')
    data.adc_i.resize(n_samples, axis=1)
    data.adc_i[:] = old.adc_i[:, :n_samples]
    data.adc_q.resize(n_samples, axis=1)
    data.adc_q[:] = old.adc_q[:, :n_samples]
    data.timestamp.resize(n_samples, axis=0)
    data.timestamp[:] = old.timestamp[:n_samples]
    data.pkt_idx.resize(n_samples, axis=0)
    data.pkt_idx[:] = old.pkt_idx[:n_samples]
    data.pps.resize(n_samples, axis=0)
    data.pps[:] = old.pps[:n_samples]

def make_processed_data():
    """Create fake consolidated and processed data for testing."""
    # with open('tests/test_data/20260709_Test_Tile_TOD_set1001.h5') as tod_file:
    #     data = tod_file.read()
    # m = mock_open(read_data=data)
    # with patch('builtins.open', m):
    cdata = ConsolidatedData.from_tod('20260709', '1001', data_dir='tests/test_data', downsampling_factor=5)
    pdata = cdata.create_processed_data()


if __name__ == '__main__':
    make_tod()
    make_processed_data()
