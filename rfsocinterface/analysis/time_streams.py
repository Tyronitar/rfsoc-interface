
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import DATA_DIRECTORY
from matplotlib.backends.backend_pdf import PdfPages
def plot_timestream_errors( data_freq_diss,fs: float, lp_filt_freq:float = 10.0, onres_ind:npt.NDArray = None, num_processing_blocks: int = 10 ):
    """Plot noise blobs for each detector."""
    # subtract the mean from each detector

    time_stream_size = data_freq_diss.shape[2]
    n_det = len(onres_ind)
    colors = plt.cm.viridis(np.linspace(0, 1, len(data_freq_diss[0, :, 0])))
    block_freqndices = np.linspace(
        0, time_stream_size, num_processing_blocks + 1, dtype=int
    )
    z_freq = np.zeros_like(data_freq_diss[0, :, :])
    z_diss = np.zeros_like(data_freq_diss[1, :, :])
    block_freqndices = np.linspace(
            0, time_stream_size, num_processing_blocks + 1, dtype=int
        )

    for i in range(num_processing_blocks):
        start, end = block_freqndices[i], block_freqndices[i + 1]
        I = data_freq_diss[0, :, start:end]
        diss = data_freq_diss[1, :, start:end]

        mean_freq = np.mean(I, axis=1)
        mean_diss = np.mean(diss, axis=1)
        std_freq  = np.std(I, axis=1)
        std_diss  = np.std(diss, axis=1)

        std_freq[std_freq == 0] = np.nan
        std_diss[std_diss == 0] = np.nan

        z_freq[:, start:end] = np.abs(I[:] - mean_freq[:, None]) / std_freq[:, None]
        z_diss[:, start:end] = np.abs(diss[:] - mean_diss[:, None]) / std_diss[:, None]

        tone_set = np.arange(0, len(data_freq_diss[0, :, 0]))
        offres_ind_mask = ~np.isin(tone_set, onres_ind)
        offres_ind = tone_set[offres_ind_mask]

    z_freq_plot = z_freq[:,:]
    z_diss_plot = z_diss[:,:]
    num_nongaussian_freq = np.zeros_like(z_freq_plot[0, :])
    num_nongaussian_diss = np.zeros_like(z_freq_plot[0, :])

    nrows = 2
    ncols = 2
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(4 * ncols, 4 * nrows),
        squeeze=True
    )
    for det in onres_ind:
        axes[0, 0].plot(z_freq_plot[det], color = colors[det])
        axes[0, 1].plot(z_diss_plot[det], color = colors[det])
        nongaussian_mask_freq =[1 if i >=5 else 0 for i in z_freq_plot[det]]
        num_nongaussian_freq += nongaussian_mask_freq
        nongaussian_mask_diss =[1 if i >=5 else 0 for i in z_diss_plot[det]]
        num_nongaussian_diss += nongaussian_mask_diss
    axes[0,0].plot(num_nongaussian_freq, color = 'red', label = "number of non gaussian detectors")
    axes[0,1].plot(num_nongaussian_diss, color = 'red', label = "number of non gaussian detectors")

    for det in offres_ind:
        axes[1, 0].plot(z_freq_plot[det], color = colors[det])
        axes[1, 1].plot(z_diss_plot[det], color = colors[det])
    axes[0,0].set_ylabel('Z Score (I)', fontsize=16)
    axes[1,0].set_ylabel('Z Score (I)', fontsize=16)

    axes[0,1].set_ylabel('Z Score (diss)', fontsize=16)
    axes[1,1].set_ylabel('Z Score (diss)', fontsize=16)

    axes[0,0].set_title('Z Score vs Index for on resonance I')
    axes[0,1].set_title('Z Score vs Index for on resonance diss')
    axes[1,0].set_title('Z Score vs Index for off resonance I')
    axes[1,1].set_title('Z Score vs Index for off resonance diss')
    axes[0,0].legend()
    axes[0,1].legend()
    plt.show()

    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    #z_freq_on = z_freq[onres_ind, :]
    #z_diss_on = z_diss[onres_ind, :]
    #z_freq_off = z_freq[offres_ind, :]
    #z_diss_off = z_diss[offres_ind, :]
    #on_med = (
    #    (np.median(z_freq_on, axis=0)*num_nongaussian_freq + np.median(z_diss_on, axis=0)*num_nongaussian_diss)/2
    #)
    #cr_metric = on_med
    #fig = plt.figure(figsize=(9, 6))
    #ax = plt.subplot()
    
    #ax.hist(cr_metric, alpha = 0.5, bins = 50)
    #ax.set_xlabel(f'CR Metric', fontsize=16)
    #ax.set_yscale('log')
    #ax.set_ylabel("Num at CR Metric", fontsize=16)
    #ax.tick_params(labelsize=14)
    #ax.legend(fontsize=14, loc='best')
    #plt.show()




import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy import signal

def make_freq_freq_noise_blob_report(
    z_freq: np.ndarray,
    onres_ind: np.ndarray,
    output_pdf: str = "freq_freq_noise_blobs.pdf",
    lp_filt_freq: float = 1.0,
    fs: float = 488
):
    """
    Create a PDF with one plot per resonator.
    Each plot overlays freq–freq noise blobs of that resonator
    against all other resonators.
    """

    n_det = len(onres_ind)
    colors = plt.cm.viridis(np.linspace(0, 1, n_det))

    # Filter setup (once)
    if lp_filt_freq > 0:
        Ds_coef = int(fs / (5 * lp_filt_freq))
        filt_sos = signal.butter(
            5, lp_filt_freq, btype="low", fs=fs, output="sos"
        )

    # Pre-filter and decimate once per detector
    z_proc = {}
    for det in onres_ind:
        x = z_freq[det]
        if lp_filt_freq > 0:
            x = signal.sosfiltfilt(filt_sos, x)
            x = signal.decimate(x, Ds_coef, ftype="iir", zero_phase=True)
        z_proc[det] = x

    with PdfPages(output_pdf) as pdf:
        for i, det_i in enumerate(onres_ind):
            fig, ax = plt.subplots(figsize=(6, 6))

            x = z_proc[det_i]

            for j, det_j in enumerate(onres_ind):
                if det_j == det_i:
                    continue

                y = z_proc[det_j]

                ax.scatter(
                    x, y,
                    s=2,
                    alpha=0.25,
                    color=colors[j],
                    label=f"{det_j}"
                )

            ax.set_title(f"Freq–Freq Noise Blobs\nResonator {det_i}")
            ax.set_xlabel(f"Z(freq) – det {det_i}")
            ax.set_ylabel("Z(freq) – other resonators")
            ax.set_aspect("equal", adjustable="box")
            ax.grid(alpha=0.2)

            # Optional: legend for small N
            if n_det <= 12:
                ax.legend(markerscale=3, fontsize=8)

            pdf.savefig(fig)
            plt.close(fig)

    print(f"Saved PDF report to {output_pdf}")
