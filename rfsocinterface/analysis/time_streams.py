
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import DATA_DIRECTORY


def plot_timestream_errors( data_IQ,fs: float, lp_filt_freq:float = 10.0, onres_ind:npt.NDArray = None ):
    """Plot noise blobs for each detector."""
    # subtract the mean from each detector

    if lp_filt_freq>0:
        Ds_coef = int(fs/(1*lp_filt_freq)) #down sampling coefficient
        filt_sos = signal.butter(5, lp_filt_freq, btype='low', fs=fs, output='sos', analog=False)
        data_IQ = signal.sosfiltfilt(filt_sos, data_IQ)
        data_IQ = signal.decimate(data_IQ, Ds_coef, axis=2, ftype='iir', zero_phase=True)
        fs = lp_filt_freq
    n_det = len(data_IQ[0,:,0])
    if onres_ind is None:
        ncols = 1  
    else:
        ncols = 2
    nrows = 2
    colors = plt.cm.viridis(np.linspace(0, 1, n_det))
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(4 * ncols, 4 * nrows),
        squeeze=True
    )
    t_final = len(data_IQ[0, 0])/fs
    t = np.arange(0, t_final, fs)


    det_std_I  = np.std(data_IQ[0], axis=1)
    det_std_Q  = np.std(data_IQ[1], axis=1)
    det_mean_I  = np.mean(data_IQ[0], axis=1)
    det_mean_Q  = np.mean(data_IQ[1], axis=1)

    for det in range(n_det):
        if det_std_I[det] == 0 or det_std_Q[det] == 0:
            continue

        var_I = (data_IQ[0, det, :]-det_mean_I[det]) / det_std_I[det]
        var_Q = (data_IQ[1, det, :]-det_mean_Q[det]) / det_std_Q[det]
        if onres_ind is None:
            axes[0].plot(var_I, '.', color=colors[det])
            axes[1].plot(var_Q, '.', color=colors[det])
            axes[0].set_ylabel('Z Score(I)')
            axes[1].set_ylabel('Z Score(Q)')

        else:
            if det in onres_ind:
                axes[0, 0].plot(var_I, '.', color=colors[det])
                axes[0, 1].plot(var_Q, '.', color=colors[det])
            else:
                axes[1, 0].plot(var_I, '.', color=colors[det])
                axes[1, 1].plot(var_Q, '.', color=colors[det])
           
            axes[0,0].set_ylabel('Z Score (I)', fontsize=16)
            axes[1,0].set_ylabel('Z Score (I)', fontsize=16)

            axes[0,1].set_ylabel('Z Score (Q)', fontsize=16)
            axes[1,1].set_ylabel('Z Score (Q)', fontsize=16)

            axes[0,0].set_title('Z Score vs Index for on resonance I')
            axes[0,1].set_title('Z Score vs Index for on resonance Q')
            axes[1,0].set_title('Z Score vs Index for off resonance I')
            axes[1,1].set_title('Z Score vs Index for off resonance Q')



            

    if onres_ind is None:
        mean_var_I = np.mean(abs(data_IQ[0, :, :]-det_mean_I[:, None]) / det_std_I[:, None], axis = 0)
        mean_var_Q = np.mean(abs(data_IQ[1, :, :]-det_mean_Q[:, None]) / det_std_Q[:, None], axis = 0)

        axes[0].plot(mean_var_I, color = 'red', label = 'average')
        axes[1].plot(mean_var_Q, color = 'red', label = 'average')
    else:
        onres_mean_var_I = np.mean(abs(data_IQ[0, onres_ind, :]-det_mean_I[onres_ind, None]) / det_std_I[onres_ind, None], axis = 0)
        onres_mean_var_Q = np.mean(abs(data_IQ[1, onres_ind, :]-det_mean_Q[onres_ind, None]) / det_std_Q[onres_ind, None], axis = 0)

        tone_set = np.arange(0, len(data_IQ[0, :, 0]))
        offres_ind_mask = ~np.isin(tone_set, onres_ind)
        offres_ind = tone_set[offres_ind_mask]
        offres_mean_var_I = np.mean(abs(data_IQ[0, offres_ind, :]-det_mean_I[offres_ind, None]) / det_std_I[offres_ind, None], axis = 0)
        offres_mean_var_Q = np.mean(abs(data_IQ[1, offres_ind, :]-det_mean_Q[offres_ind, None]) / det_std_Q[offres_ind, None], axis = 0)

        axes[0, 0].plot(onres_mean_var_I, color = 'red', label = 'average')
        axes[0, 1].plot(onres_mean_var_Q, color = 'red', label = 'average')
        axes[1, 0].plot(offres_mean_var_I, color = 'red', label = 'average')
        axes[1, 1].plot(offres_mean_var_Q, color = 'red', label = 'average')

        bad_indices_I = np.where(onres_mean_var_I>= 3)
        bad_indices_Q = np.where(onres_mean_var_Q >= 3)
    plt.legend()
    fig.suptitle('timestream_data', fontsize=16)
    plt.tight_layout()
    plt.show()