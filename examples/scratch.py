import pdb

import matplotlib.pyplot as plt
import numpy as np
import tables
from kidpy3 import RawDataFile
from scipy.signal import decimate


from PySide6.QtWidgets import QApplication
from kidpy3 import RawDataFile

from rfsocinterface.core.data import ProcessedData
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.gui.sweep_diagnostics import DiagnosticsDialog


if __name__ == '__main__':

    tile2_sweep_file1 = '/data/20260820/20260820_Device_aSi1_Channel2_telescope_275mK_20260804_LO_Sweep_hour9p4725_high_res.h5'
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

    tile2_sweep1 = pd1.get_lo_sweep(0)
    tile2_sweep2 = pd2.get_lo_sweep(0)
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

        sweep1_angle, sweep1_unit = sweep1.freq_direction()
        sweep2_angle, sweep2_unit = sweep2.freq_direction()
        sweep1_ff_angle, sweep1_ff_unit = sweep1_ff.freq_direction()
        sweep2_ff_angle, sweep2_ff_unit = sweep2_ff.freq_direction()

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
