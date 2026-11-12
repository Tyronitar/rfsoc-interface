from PySide6.QtWidgets import QApplication

from rfsocinterface.core.sweeps import LoSweep, LoSweepData
from rfsocinterface.gui.sweep_diagnostics import BlindSweepDialog


if __name__ == '__main__':
    app = QApplication()
    sweep = LoSweepData.load('/data/20261019/20261019_Device_aSi3_Channel4_blind_Blind_Sweep_hour09p9414.h5')
    win = BlindSweepDialog(
        sweep,
    )
    win.show()
    win.find_resonances_and_plot(
        min_resonance_depth_dB=0.3,
        spacing_threshold_Hz=3e3,
        min_samples_per_resonance=2,
        max_noise_fluctuation_dB=0.05,
        baseline_percentile=50,
    )
    app.exec()
