import pdb

import matplotlib.pyplot as plt
import numpy as np
import tables

from rfsocinterface.core.losweep import LoSweepData
from rfsocinterface.core.data.data import ProcessedData, BAD_RFSOC_TONE_START_INDEX


if __name__ == '__main__':
    idx = 243

    sweep_off = LoSweepData.from_h5('/data/20250805/20250805_devrfsoc_rfsoc2_LO_Sweep_hour12p6867.h5')
    sweep_on = LoSweepData.from_h5('/data/20250805/20250805_devrfsoc_rfsoc2_LO_Sweep_hour12p6986.h5')
    pd = ProcessedData.from_file('20250805', 1002)
    raw_data = tables.File('/data/20250805/20250805_devrfsoc_rfsoc2_TOD_set1002.h5', 'r')

    dI_df = np.cos(pd.IQ_to_freq_diss_angle[:]) * pd.adc_units_to_hz[:]
    dQ_df = np.sin(pd.IQ_to_freq_diss_angle[:]) * pd.adc_units_to_hz[:]
    valid_tone_index = np.arange(pd.n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX
    raw_data_I = raw_data.root.time_ordered_data.adc_i
    raw_data_Q = raw_data.root.time_ordered_data.adc_q
    # plt.plot(raw_data_I[valid_tone_index[idx]])
    # plt.plot(raw_data_I[valid_tone_index[241], :1000]); plt.xlim(475, 525); plt.show()
    pdb.set_trace()

    angle_off, units_off = sweep_off.freq_direction()
    angle_on, units_on = sweep_on.freq_direction()
    dI_df_off = np.cos(angle_off[:]) * units_off[:]
    dQ_df_off = np.sin(angle_off[:]) * units_off[:]
    dI_df_on = np.cos(angle_on[:]) * units_on[:]
    dQ_df_on = np.sin(angle_on[:]) * units_on[:]
    print(f'dIQ_df with source OFF: {(dI_df_off[idx], dQ_df_off[idx])}')
    print(f'dIQ_df with source ON: {(dI_df_on[idx], dQ_df_on[idx])}')
    fig, axes = plt.subplots(1, 2)
    axes[0].plot(sweep_off.data_I[idx], label='OFF')
    axes[0].plot(sweep_on.data_I[idx], label='ON')
    axes[0].title('Data I')
    axes[0].legend()
    axes[1].plot(sweep_off.data_Q[idx], label='OFF')
    axes[1].plot(sweep_on.data_Q[idx], label='ON')
    axes[1].title('Data Q')
    axes[1].legend()
    plt.show()
    pdb.set_trace()
