import pdb
from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import DATA_DIRECTORY


def plot_noise_blob( data_IQ,fs: float, lp_filt_freq: float = 0, IQ_to_freq_diss_angle:npt.NDArray = None, IQ_to_gain_phase_angle:npt.NDArray = None, savepath: Path|None = None):
    """Plot noise blobs for each detector."""
    # subtract the mean from each detector
    deproj_IQ = data_IQ - np.mean(data_IQ, axis=2)[:, :, np.newaxis]
    if lp_filt_freq>0:
        Ds_coef = int(fs/(5*lp_filt_freq)) #down sampling coefficient
        filt_sos = signal.butter(5, lp_filt_freq, btype='low', fs=fs, output='sos', analog=False)
        deproj_IQ = signal.sosfiltfilt(filt_sos, deproj_IQ)
        deproj_IQ = signal.decimate(deproj_IQ, Ds_coef, axis=2, ftype='iir', zero_phase=True)
    n_det = deproj_IQ.shape[1]
    ncols = int(np.ceil(np.sqrt(n_det)))
    nrows = int(np.ceil(n_det / ncols)+1)
    color = np.arange(len(deproj_IQ[0,0].ravel()))  #Color by timestream
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(4 * ncols, 4 * nrows),
        squeeze=True
    )

    labelIQ = 'IQ Noise Data'
    labelFreqDiss = 'Freq/Diss Axis'
    labelGainPhase = 'Gain/Phase Axis'
    for det, ax in enumerate(axes.flat):
        if det >= n_det:
            ax.axis('off')
            continue
        if det != 0:
            labelIQ = None
            labelFreqDiss = None
            labelGainPhase = None
        ax.scatter(
            deproj_IQ[0, det].ravel(),
            deproj_IQ[1, det].ravel(),
            s=1,
            alpha=0.5,
            c = color,
            label =labelIQ
        )

        if IQ_to_freq_diss_angle is not None:
            ax.axline((0, 0),
                    slope=np.tan(-IQ_to_freq_diss_angle[det]), label = labelFreqDiss,
                    color='red', linestyle='--')

        if IQ_to_gain_phase_angle is not None:
            ax.axline((0, 0),
                    slope=np.tan(-IQ_to_gain_phase_angle[det]),
                    color='blue', linestyle='--', label = labelGainPhase)

        ax.set_title(f'Detector {det}')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
    fig.legend()
    fig.suptitle('Noise Blobs', fontsize=16)
    plt.tight_layout()
    plt.show()



