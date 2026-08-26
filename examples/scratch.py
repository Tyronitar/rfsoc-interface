import pdb

import matplotlib.pyplot as plt
import numpy as np
from kidpy3 import RawDataFile
from scipy.signal import decimate
import matplotlib.patches as mpatches
import h5py


from PySide6.QtWidgets import QApplication
from kidpy3 import RawDataFile

from rfsocinterface.core.data import ProcessedData
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.gui.sweep_diagnostics import DiagnosticsDialog
from rfsocinterface.core.utils import mHz_axis_formatter, BAD_RESONANCE_COLOR


def plot_sweep(sweep: LoSweepData, i_res: int, rotation_angle, dIQ_df):
    axis_formatter = mHz_axis_formatter

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    # if i_res in pos_res:
    #     suffix = '(Positive)'
    # else:
    #     suffix = '(Negative)'
    #     fig.set_facecolor(BAD_RESONANCE_COLOR)
    suffix = ''
    fig.suptitle(
        f'LO Sweep for Resonator {i_res} {suffix}\n'
        f'$f_0$ = {sweep.detector_f[i_res] * 1e-6:3f} MHz\n'
        f'IQ-to-Freq/Diss Rotation Angle = {rotation_angle[i_res]:.2f} deg'
    )
    axes[0].set_title('Data I')
    axes[0].plot(sweep.freq[i_res], sweep.data_I[i_res], label='Full Trace')
    axes[0].plot(sweep.freq[i_res, ind_val], sweep.data_I[i_res, ind_val], label='Center Indices')
    handles, labels = axes[0].get_legend_handles_labels()
    label = rf'$\frac{{dI}}{{df}}$ = {dIQ_df[0, i_res]:.3f}'
    extra_text_patch = mpatches.Patch(color="none", label=label)
    handles.append(extra_text_patch)
    labels.append(label)
    axes[0].legend(handles=handles, labels=labels)
    axes[0].xaxis.set_major_formatter(axis_formatter)
    axes[0].set_xlabel('Frequency (MHz)')


    axes[1].set_title('Data Q')
    axes[1].plot(sweep.freq[i_res], sweep.data_Q[i_res], label='Full Trace')
    axes[1].plot(sweep.freq[i_res, ind_val], sweep.data_Q[i_res, ind_val], label='Center Indices')
    handles, labels = axes[1].get_legend_handles_labels()
    label = rf'$\frac{{dQ}}{{df}}$ = {dIQ_df[1, i_res]:.3f}'
    extra_text_patch = mpatches.Patch(color="none", label=label)
    handles.append(extra_text_patch)
    labels.append(label)
    axes[1].legend(handles=handles, labels=labels)
    axes[1].xaxis.set_major_formatter(axis_formatter)
    axes[1].set_xlabel('Frequency (MHz)')

    axes[2].set_title(r'$S_{21}$')
    axes[2].plot(sweep.freq[i_res], sweep.s21[i_res], label='Full Trace')
    axes[2].plot(sweep.freq[i_res, ind_val], sweep.s21[i_res, ind_val], label='Center Indices')
    axes[2].legend()
    axes[2].xaxis.set_major_formatter(axis_formatter)
    axes[2].set_xlabel('Frequency (MHz)')

    fig.tight_layout()


if __name__ == '__main__':

    tile2_sweep_file1 = '/data/20260820/20260820_Device_aSi1_Channel2_telescope_275mK_20260804_LO_Sweep_hour9p4725_high_res.h5'
    tile2_sweep_lores_file1 = '/data/20260820/20260820_Device_aSi1_Channel2_telescope_275mK_20260804_LO_Sweep_hour9p3953.h5'
    tile2_sweep_file2 = '/data/20260820/20260820_Device_aSi1_Channel2_telescope_275mK_20260804_LO_Sweep_hour10p6600_high_res.h5 '

    tile3_sweep_file1 = '/data/20260820/20260820_Device_aSi2_Channel3_telescope_275mK_20260804_LO_Sweep_hour9p5714_high_res.h5'
    tile3_sweep_file2 = '/data/20260820/20260820_Device_aSi2_Channel3_telescope_275mK_20260804_LO_Sweep_hour10p6600_high_res.h5'

    # tile2_tod = RawDataFile('/data/20260820/20260820_Device_aSi1_Channel2_telescope_275mK_20260804_TOD_set1005.h5', 'a')
    # tile3_tod = RawDataFile('/data/20260820/20260820_Device_aSi2_Channel3_telescope_275mK_20260804_TOD_set1005.h5', 'a')
    # tile2_sweep = LoSweepData.load(tile2_sweep_file2)
    # tile3_sweep = LoSweepData.load(tile3_sweep_file2)
    # tile2_tod.lo_sweep[:] = tile2_sweep.data[:]
    # tile3_tod.lo_sweep[:] = tile3_sweep.data[:]
    # pdb.set_trace()

    # tile2_sweep1 = LoSweepData.load(tile2_sweep_file1)
    # tile2_sweep2 = LoSweepData.load(tile2_sweep_file2)
    # tile3_sweep1 = LoSweepData.load(tile3_sweep_file1)
    # tile3_sweep2 = LoSweepData.load(tile3_sweep_file2)

    date = '20260820'
    pd1 = ProcessedData.load(date, 1004)
    pd2 = ProcessedData.load(date, 1005)
    norms_1 = np.abs(pd1.carrier_amplitudes[:, 0] + 1j * pd1.carrier_amplitudes[:, 1])
    norms_2 = np.abs(pd2.carrier_amplitudes[:, 0] + 1j * pd2.carrier_amplitudes[:, 1])
    norm_ratio1 = pd1.get_carrier_amplitude_norm(0) / pd1.get_carrier_amplitude_norm(1)
    norm_tile2_1 = np.abs(
        pd1.carrier_amplitudes[pd1.get_onres_ind(0), 0] +
        1j *  pd1.carrier_amplitudes[pd1.get_onres_ind(0), 1]
    )
    norm_tile3_1 = np.abs(
        pd1.carrier_amplitudes[pd1.get_onres_ind(1), 0] +
        1j *  pd1.carrier_amplitudes[pd1.get_onres_ind(1), 1]
    )
    norm_tile2_2 = np.abs(
        pd2.carrier_amplitudes[pd2.get_onres_ind(0), 0] +
        1j *  pd2.carrier_amplitudes[pd2.get_onres_ind(0), 1]
    )
    norm_tile3_2 = np.abs(
        pd2.carrier_amplitudes[pd2.get_onres_ind(1), 0] +
        1j *  pd2.carrier_amplitudes[pd2.get_onres_ind(1), 1]
    )
    # norm_ratio2 = pd2.get_carrier_amplitude_norm(0) / pd2.get_carrier_amplitude_norm(1)
    ind = pd1.get_onres_ind(0)
    iq_ratio_1 = np.abs(pd1.carrier_amplitudes[ind, 0] / pd1.carrier_amplitudes[ind, 1])
    iq_ratio_2 = np.abs(pd2.carrier_amplitudes[ind, 0] / pd2.carrier_amplitudes[ind, 1])
    plt.plot(norm_tile2_1)
    plt.plot(norm_tile2_2)
    plt.show()
    plt.plot(norm_tile3_1)
    plt.plot(norm_tile3_2)
    plt.show()
    # plt.plot(iq_ratio_2)
    pdb.set_trace()
    for i_res in range(48, 52):
        plt.figure()
        plt.suptitle('Set 1004')
        plt.plot(pd1.get_data_IQ(0)[0, i_res])
        plt.plot(pd1.get_data_IQ(0)[1, i_res])
        plt.figure()
        plt.suptitle('Set 1005')
        plt.plot(pd2.get_data_IQ(0)[0, i_res])
        plt.plot(pd2.get_data_IQ(0)[1, i_res])
        plt.show()
        pdb.set_trace()
    pdb.set_trace()

    tile2_sweep1 = pd1.get_lo_sweep(0)
    tile2_sweep2 = pd2.get_lo_sweep(0)
    tile2_lo_res_sweep = LoSweepData.load(tile2_sweep_lores_file1)
    mid_ind = tile2_sweep1.nfreq // 2
    edge_indices = [mid_ind - 5, mid_ind + 5+ 1]
    ind_val = np.arange(edge_indices[0], edge_indices[1])
    freq_val = tile2_sweep1.freq[:, ind_val] - tile2_sweep1.detector_f[:, np.newaxis]

    for sweep in (tile2_sweep1, tile2_sweep2):
        rotation_angle, sweep_adc_units_to_hz, dIQ_df = sweep.freq_direction()
        rotation_angle = np.rad2deg(rotation_angle)
        mid_ind = sweep.nfreq // 2
        edge_indices = [mid_ind - 5, mid_ind + 5+ 1]
        ind_val = np.arange(edge_indices[0], edge_indices[1])
        freq_val = sweep.freq[:, ind_val] - sweep.detector_f[:, np.newaxis]
        for i_res in range(51, 52):
            plot_sweep(sweep, i_res, rotation_angle, dIQ_df)
    plt.show()
    pdb.set_trace()
    tile3_sweep1 = pd1.get_lo_sweep(1)
    tile3_sweep2 = pd2.get_lo_sweep(1)

    # tile2_msr = LoSweepData.load_most_recent(pd2.get_tile_name(0), date=date)
    # tile3_msr = LoSweepData.load_most_recent(pd2.get_tile_name(1), date=date)
    # pdb.set_trace()

    # app = QApplication()
    # tile2_dial1 = DiagnosticsDialog.from_h5(tile2_sweep_file1)
    # tile2_dial1.set_window_name('Tile 2 - Lo Sweep 1')
    # tile2_dial2 = DiagnosticsDialog.from_h5(tile2_sweep_file2)
    # tile2_dial2.set_window_name('Tile 2 - Lo Sweep 2')
    # tile3_dial1 = DiagnosticsDialog.from_h5(tile3_sweep_file1)
    # tile3_dial2 = DiagnosticsDialog.from_h5(tile3_sweep_file2)
    # tile2_sweep1 = tile2_dial1.sweep_data
    # tile2_sweep2 = tile2_dial2.sweep_data
    # tile3_sweep1 = tile3_dial1.sweep_data
    # tile3_sweep2 = tile3_dial2.sweep_data

    # tile2_dial1.show()
    # tile2_dial2.show()
    # tile3_dial1.show()
    # tile3_dial2.show()
    # app.exec()
    # pdb.set_trace()

    sweep1_ = (tile2_sweep1, tile3_sweep1)
    sweep1_files = (tile2_sweep_file1, tile3_sweep_file1)
    sweep2_ = (tile2_sweep2, tile3_sweep2)
    sweep2_files = (tile2_sweep_file2, tile3_sweep_file2)

    sweep1_angles = []
    sweep2_angles = []
    sweep1_units = []
    sweep2_units = []

    for i in range(2):
        sweep1 = sweep1_[i]
        sweep2 = sweep2_[i]
        sweep1_ff = LoSweepData.load(sweep1_files[i])
        sweep2_ff = LoSweepData.load(sweep2_files[i])

        sweep1_angle, sweep1_unit, _ = sweep1.freq_direction()
        sweep2_angle, sweep2_unit, _ = sweep2.freq_direction()
        sweep1_ff_angle, sweep1_ff_unit, _ = sweep1_ff.freq_direction()
        sweep2_ff_angle, sweep2_ff_unit, _ = sweep2_ff.freq_direction()

        sweep1_angles.append(sweep1_angle)
        sweep1_units.append(sweep1_unit)
        sweep2_angles.append(sweep2_angle)
        sweep2_units.append(sweep2_unit)

        plt.figure()
        plt.suptitle(f'Tile {i + 2} LO sweeps - Difference in $dI/df$')
        n_tones = sweep2.n_tones
        # n_tones = 50
        # tones = np.arange(50, 50 + n_tones)
        tones = np.arange(n_tones)
        diff = sweep2_angle - sweep1_angle
        diff_ff = sweep2_ff_angle - sweep1_ff_angle
        colors = np.where(diff >= 0, 'green', 'red')
        plt.vlines(
            tones,
            sweep1_angle[tones],
            sweep2_angle[tones],
            colors=colors[tones],
        )
        plt.scatter(tones, sweep1_angle[tones], color='blue', label='Sweep 1')
        plt.scatter(tones, sweep2_angle[tones], color='orange', label='Sweep 2')
        plt.legend()
        plt.show()
        pdb.set_trace()

    pdb.set_trace()
