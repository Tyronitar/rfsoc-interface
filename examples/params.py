import pdb

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

from rfsocinterface.core.utils import ChanmaskValue
from rfsocinterface.core.params import RFSoCParameters, DEFAULT_DFOVERF_PER_MK
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.core.utils import argclosest

if __name__ == '__main__':

    og_params = RFSoCParameters.load('Device_aSi1_Channel2_telescope_275mK_20260325', 'r')
    params = RFSoCParameters.load('Device_aSi1_Channel2_telescope_275mK_20260325_with_offres', 'r')
    new_params = RFSoCParameters.load('Device_aSi1_Channel2_telescope_275mK_20260804', 'r')
    pdb.set_trace()
    i_tone_og = 241
    i_match = argclosest(params.baseband_freqs[:], og_params.baseband_freqs[i_tone_og])
    print(f'Resaonator {i_tone_og} is {i_match} with off-resonance tones added')
    i_tone_old = 282
    i_tone_new = argclosest(new_params.baseband_freqs[:], params.baseband_freqs[i_tone_old])
    az_center = 5.978
    za_center = 88.748
    print(
        'Old Parameters\n'
        f'  Resonator Number: {i_tone_old}\n'
        f'  f0: {params.detector_f[i_tone_old] * 1e-6:.3f} MHz\n'
        f'  dx: {params.detector_delta_x[i_tone_old]}\n'
        f'  dy: {params.detector_delta_y[i_tone_old]}\n'
    )
    print(
        'Old Parameters Neighbors\n'
        f'  Resonator Number: {i_tone_old - 1}\n'
        f'  f0: {params.detector_f[i_tone_old - 1] * 1e-6:.3f} MHz\n'
        f'  dx: {params.detector_delta_x[i_tone_old - 1]}\n'
        f'  dy: {params.detector_delta_y[i_tone_old - 1]}\n'
        f'  Resonator Number: {i_tone_old + 1}\n'
        f'  f0: {params.detector_f[i_tone_old + 1] * 1e-6:.3f} MHz\n'
        f'  dx: {params.detector_delta_x[i_tone_old + 1]}\n'
        f'  dy: {params.detector_delta_y[i_tone_old + 1]}\n'
    )
    print(
        'New Parameters\n'
        f'  Resonator Number: {i_tone_new}\n'
        f'  f0: {new_params.detector_f[i_tone_new] * 1e-6:.3f} MHz\n'
        f'  dx: {new_params.detector_delta_x[i_tone_new]}\n'
        f'  dy: {new_params.detector_delta_y[i_tone_new]}\n'
        f'  az: {az_center - params.detector_delta_x[i_tone_new]}\n'
        f'  za: {za_center - params.detector_delta_y[i_tone_new]}\n'
    )
    print(
        'New Parameters Neighbors\n'
        f'  Resonator Number: {i_tone_new - 1}\n'
        f'  f0: {new_params.detector_f[i_tone_new - 1] * 1e-6:.3f} MHz\n'
        f'  dx: {new_params.detector_delta_x[i_tone_new - 1]}\n'
        f'  dy: {new_params.detector_delta_y[i_tone_new - 1]}\n'
        f'  az: {az_center - params.detector_delta_x[i_tone_new - 1]}\n'
        f'  za: {za_center - params.detector_delta_y[i_tone_new - 1]}\n'
        f'  Resonator Number: {i_tone_new + 1}\n'
        f'  f0: {new_params.detector_f[i_tone_new + 1] * 1e-6:.3f} MHz\n'
        f'  dx: {new_params.detector_delta_x[i_tone_new + 1]}\n'
        f'  dy: {new_params.detector_delta_y[i_tone_new + 1]}\n'
        f'  az: {az_center - params.detector_delta_x[i_tone_new + 1]}\n'
        f'  za: {za_center - params.detector_delta_y[i_tone_new + 1]}\n'
    )
    pdb.set_trace()

    # bb_freqs = np.linspace(-200, 200, 1000) * 1e6
    # bb_freqs = np.sort(np.concatenate((-tones, tones)))

    # params = RFSoCParameters.new_file('test_100_tones_20260610', 100)
    # params.baseband_freqs[:] = bb_freqs
    # params.rfin = 15
    # params.rfout = 15
    # params.close()


    # current_params = RFSoCParameters.load('Device_aSi1_Channel2_telescope_275mK_20260804', 'r')
    # params = RFSoCParameters.load('Device_aSi2_Channel3_blind', 'r')
    # plt.scatter(params.baseband_freqs, np.zeros(params.n_tones))
    # plt.show()
    # new_params = RFSoCParameters.new_file(
    #     'Device_aSi3_Channel4_blind_1000',
    #     1000,
    # )
    # new_params.baseband_freqs[:] = bb_freqs
    # new_params.rfin = 12
    # new_params.rfout = 18
    # new_params = params.copy_and_update(
    #     'Device_aSi3_Channel4_blind',
    #     rfin=12,
    #     rfout=18,
    #     dfoverf_per_mK=np.ones(1001) * DEFAULT_DFOVERF_PER_MK,
    # )
    # params = RFSoCParameters.load('ONR_Blind_180_to_620MHz_1000_tones', 'r')
    # abs_tones = np.linspace(10e3, 250e6, 500) * 1e6
    # bb_freqs = np.sort(np.concatenate((-abs_tones, abs_tones)))
    # params4 = RFSoCParameters.load('Device_aSi3_Channel4_blind', 'r')
    # params2 = RFSoCParameters.load('Device_aSi1_Channel2_telescope_275mK_20260804', 'r')
    # params3 = RFSoCParameters.load('Device_aSi2_Channel3_telescope_275mK_20260804', 'r')
    # params4 = RFSoCParameters.load('Device_aSi3_Channel4', 'r')
    # n_tones2 = np.count_nonzero(params2.chanmask[:] != ChanmaskValue.OFF_RESONANCE)
    # n_tones3 = np.count_nonzero(params3.chanmask[:] != ChanmaskValue.OFF_RESONANCE)
    # n_tones4 = np.count_nonzero(params4.chanmask[:] != ChanmaskValue.OFF_RESONANCE)

    # sweep = LoSweepData.load('/data/20261019/20261019_ONR_Blind_180_to_620MHz_1000_tones_Blind_Sweep_hour11p3267.h5')
    # # sweep.plot_full_trace()
    # f0, depths = sweep.find_resonances(
    #     min_resonance_depth_dB=0.3,
    #     spacing_threshold_Hz=3e3,
    #     min_samples_per_resonance=2,
    #     max_noise_fluctuation_dB=0.05,
    #     baseline_percentile=50,
    # )
    # fig = sweep.plot_blind_sweep(f0)
    # # for f in chanmask:
    # data = np.load(
    #     '/home/onrkids/onrkidpy/params/Device_aSi3_Channel4_20220203_optical_temperature_sweep_fits.npy',
    #     allow_pickle=True,
    #     fix_imports=True,
    #     encoding='bytes',
    # )
    # fres0_dark = data[()][b'fres0_dark'][:, 0] - 220e3
    # for f in fres0_dark:
    #     plt.axvline(f, color='g', linestyle='--')
    # plt.show()

    # pdb.set_trace()


