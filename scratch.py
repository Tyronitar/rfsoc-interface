import pdb

import matplotlib.pyplot as plt
import numpy as np
import tables
from kidpy3 import RawDataFile


from rfsocinterface.core.losweep import LoSweepData
from rfsocinterface.core.data.data import ProcessedData, BAD_RFSOC_TONE_START_INDEX


if __name__ == '__main__':
    idx = 243

    actual_sweep = LoSweepData.from_h5('/data/20250902/20250902_Device_aSi1_Channel2_LO_Sweep_hour12p0617_high_res.h5')
    sweep_off = LoSweepData.from_h5('/data/20250902/20250902_Device_aSi1_Channel2_LO_Sweep_hour12p6392.h5')
    sweep_on = LoSweepData.from_h5('/data/20250902/20250902_Device_aSi1_Channel2_LO_Sweep_hour12p6572.h5')
    fig, axes = plt.subplots(2, 2)
    setnum = 1006
    date = '20250902'
    i_res = 241
    pd = ProcessedData.from_file(date, setnum)
    # raw_data = RawDataFile('/data/20250902/20250902_Device_aSi1_Channel2_TOD_set1006.h5', 'r')
    axes[0, 0].plot(sweep_off.data_I[i_res],label='I - Source OFF')
    axes[0, 0].plot(sweep_on.data_I[i_res],label='I - Source ON')
    axes[0, 0].plot(actual_sweep.data_I[i_res],label=f'I - Set {setnum}')
    # axes[0, 0].plot(np.real(raw_data.lo_sweep[1, i_res]),label=f'I - Set {setnum} raw')
    axes[0, 0].legend()
    axes[0, 0].set_title(f'Resonator {i_res} - LO Sweep I Data') 
    axes[0, 0].annotate(rf'$\cos{{\theta}} = {np.cos(pd.IQ_to_freq_diss_angle[i_res]):.3f}$', (.05, .7), xycoords='axes fraction')

    axes[0, 1].plot(pd.data_I[i_res])
    axes[0, 1].set_title(f'Resonator {i_res} - Data I')

    axes[1, 0].plot(sweep_off.data_Q[i_res],label='Q - Source OFF')
    axes[1, 0].plot(sweep_on.data_Q[i_res],label='Q - Source ON')
    axes[1, 0].plot(actual_sweep.data_Q[i_res],label=f'Q - Set {setnum}')
    # axes[1, 0].plot(np.imag(raw_data.lo_sweep[1, i_res]),label=f'Q - Set {setnum} raw')
    axes[1, 0].legend()
    axes[1, 0].set_title(f'Resonator {i_res} - LO Sweep Q Data')
    axes[1, 0].annotate(rf'$\sin{{\theta}} = {np.sin(pd.IQ_to_freq_diss_angle[i_res]):.3f}$', (.05, .7), xycoords='axes fraction')

    axes[1, 1].plot(pd.data_Q[i_res])
    axes[1, 1].set_title(f'Resonator {i_res} - Data Q')
    plt.show()
    pd.close()
    exit()

    # pd = ProcessedData.from_file('20250805', 1002)
    # raw_data = tables.File('/data/20250805/20250805_devrfsoc_rfsoc2_TOD_set1002.h5', 'r')

    # dI_df = np.cos(pd.IQ_to_freq_diss_angle[:]) * pd.adc_units_to_hz[:]
    # dQ_df = np.sin(pd.IQ_to_freq_diss_angle[:]) * pd.adc_units_to_hz[:]
    # valid_tone_index = np.arange(pd.n_tones, dtype=int) + BAD_RFSOC_TONE_START_INDEX
    # raw_data_I = raw_data.root.time_ordered_data.adc_i
    # raw_data_Q = raw_data.root.time_ordered_data.adc_q
    # # plt.plot(raw_data_I[valid_tone_index[idx]])
    # # plt.plot(raw_data_I[valid_tone_index[241], :1000]); plt.xlim(475, 525); plt.show()
    # pdb.set_trace()

    # angle_off, units_off = sweep_off.freq_direction()
    # angle_on, units_on = sweep_on.freq_direction()
    # dI_df_off = np.cos(angle_off[:]) * units_off[:]
    # dQ_df_off = np.sin(angle_off[:]) * units_off[:]
    # dI_df_on = np.cos(angle_on[:]) * units_on[:]
    # dQ_df_on = np.sin(angle_on[:]) * units_on[:]
    # print(f'dIQ_df with source OFF: {(dI_df_off[idx], dQ_df_off[idx])}')
    # print(f'dIQ_df with source ON: {(dI_df_on[idx], dQ_df_on[idx])}')
    # fig, axes = plt.subplots(1, 2)
    # axes[0].plot(sweep_off.data_I[idx], label='OFF')
    # axes[0].plot(sweep_on.data_I[idx], label='ON')
    # axes[0].title('Data I')
    # axes[0].legend()
    # axes[1].plot(sweep_off.data_Q[idx], label='OFF')
    # axes[1].plot(sweep_on.data_Q[idx], label='ON')
    # axes[1].title('Data Q')
    # axes[1].legend()
    # plt.show()
    # pdb.set_trace()
