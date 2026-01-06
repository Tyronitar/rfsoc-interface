import pdb

import numpy as np
import matplotlib.pyplot as plt
from kidpy3 import RawDataFile
import tables
from rfsocinterface.core.data import ProcessedDataLN, ProcessedDataL0, ProcessedDataL1

if __name__ == '__main__':
    date = '20250829'
    setnum = 1012
    i_res = 500

    raw_data = RawDataFile(f'/data/{date}/{date}_thousand_tone_uniform_20250806_TOD_set{setnum}.h5', 'r')
    raw_data.timestamp = raw_data.fh['/time_ordered_data/timestamp']

    old_l2 = ProcessedDataLN.from_file(date, setnum, level=2)
    new_l2 = ProcessedDataLN.from_file('20251223', 1006, level=2)

    old_i_data = old_l2.get_data_I()[i_res]
    new_i_data = new_l2.get_data_I()[i_res]
    plt.figure()
    plt.title(f'Resonator {i_res} - I Data Comparison')
    plt.plot(new_l2.time, new_i_data, label='20251223set1006')
    plt.plot(old_l2.time, old_i_data, label='20250829set1012')
    plt.legend()

    old_data_gain = old_l2.get_data_gain()[i_res]
    new_data_gain = new_l2.get_data_gain()[i_res]
    plt.figure()
    plt.title(f'Resonator {i_res} - Gain Data Comparison')
    plt.plot(new_l2.time, new_data_gain, label='20251223set1006')
    plt.plot(old_l2.time, old_data_gain, label='20250829set1012')
    plt.legend()

    old_data_gain_normalized = old_data_gain / old_l2.carrier_amplitude_norm()
    new_data_gain_normalized = new_data_gain / new_l2.carrier_amplitude_norm()

    plt.figure()
    plt.title(f'Resonator {i_res} - Normalized Gain Data Comparison')
    plt.plot(new_l2.time, new_data_gain_normalized, label='20251223set1006')
    plt.plot(old_l2.time, old_data_gain_normalized, label='20250829set1012')
    plt.legend()


    old_freq = old_l2.get_node_value('freq')[:]
    old_psd = old_l2.get_node_value('psd_gain_phase')[:]
    new_freq = new_l2.get_node_value('freq')[:]
    new_psd = new_l2.get_node_value('psd_gain_phase')[:]

    plt.figure()
    plt.title(f'Resonator {i_res} - PSD Gain Comparison')
    plt.plot(old_freq, old_psd[0, i_res], label='PSD Gain for 20250829set1012')
    plt.plot(new_freq, new_psd[0, i_res], label='PSD Gain for 20251223set1006')
    plt.legend()
    plt.show()

    pdb.set_trace()



