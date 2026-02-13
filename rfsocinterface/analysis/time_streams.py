
import pdb
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import DATA_DIRECTORY
from matplotlib.backends.backend_pdf import PdfPages
def plot_timestream_errors( z_freq:npt.NDArray, z_diss:npt.NDArray, fs:float = 488.24,lp_filt_freq:float = 10.0, onres_ind:npt.NDArray = None, num_processing_blocks: int = 100 ):
    """Plot noise blobs for each detector."""
    # subtract the mean from each detector


    detection_mask_array_f = (z_freq > 7)
    detection_mask_array_d = (z_diss > 7)

    gap = 4

    # union mask: detection in either channel
    combined = detection_mask_array_f | detection_mask_array_d

    # suppress contiguous detections based on the union
    for k in range(1, gap + 1):
        combined[:, k:] &= ~combined[:, :-k]

    # apply the suppression back to both
    detection_mask_array_f &= combined
    detection_mask_array_d &= combined



    nrows, ncols = 1, 1

    fig = plt.figure(figsize=(4 * ncols, 4 * nrows))
    axes = np.empty((nrows, ncols), dtype=object)

    axes = fig.add_subplot(1, 1, 1, projection='3d')
   
    # Time axis (based on one detector trace)
    nsamples = len(z_freq[onres_ind[0]])
    t = np.arange(nsamples) / fs

    for det_idx, det in enumerate(onres_ind):

        mask = detection_mask_array_f[det].astype(bool)
        x = np.full(np.sum(mask), det_idx)
        colors = np.where(
            np.sum(detection_mask_array_f[:,mask], axis = 0) > 5,
            'red',
            'blue'
        )
        axes.scatter(
            x,
            t[mask],
            np.array(z_freq[det])[mask],
            s=5, c = colors 

        )
        mask = detection_mask_array_d[det].astype(bool)
        x = np.full(np.sum(mask), det_idx)
        colors = np.where(
            np.sum(detection_mask_array_d[:,mask], axis = 0) > 5,
            'green',
            'yellow'
        )
        axes.scatter(
            x,
            t[mask],
            np.array(z_diss[det])[mask],
            s=5, c = colors 

        )

    axes.set_xlabel("Detector index")
    axes.set_ylabel("Time (s)")
    axes.set_zlabel("z")

    plt.show()

    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    

    multiplicity_f = np.sum(detection_mask_array_f[onres_ind], axis=0)
    multiplicity_d = np.sum(detection_mask_array_d[onres_ind], axis=0)

    multiplicity_tot = multiplicity_f + multiplicity_d

    max_multiplicity = int(np.max(multiplicity_tot))

    num_glitches_f = np.zeros(max_multiplicity + 1, dtype=int)
    num_glitches_d = np.zeros(max_multiplicity + 1, dtype=int)
    num_glitches   = np.zeros(max_multiplicity + 1, dtype=int)

    for i in range(1, max_multiplicity + 1):
        num_glitches_f[i] = np.sum(multiplicity_f == i)
        num_glitches_d[i] = np.sum(multiplicity_d == i)
        num_glitches[i]   = np.sum(multiplicity_tot == i)


    ax.scatter(np.arange(max_multiplicity+1), num_glitches_f, color = 'blue', label = 'frequency')
    ax.scatter(np.arange(max_multiplicity+1), num_glitches_d, color = 'orange', label = 'dissapation')
    ax.scatter(np.arange(max_multiplicity+1), num_glitches, color = 'black', label = 'combined')
    ax.set_xlabel("Glitch Multiplicity")
    ax.set_ylabel("Number of Glitches")


    ax.set_yscale('log')
    ax.legend()
    plt.show()


    # mask time bins with at least one detection
    multiplicity_mask = multiplicity_tot >= 1

    # combine detections per resonator
    detection_mask_array = (
        detection_mask_array_f[onres_ind] |
        detection_mask_array_d[onres_ind]
    )

    # keep only time bins with detections
    detection_mask_array = detection_mask_array[:, multiplicity_mask]

    # event rate per resonator
    num_events = np.sum(detection_mask_array, axis=1) * (60 / t[-1])

    # reporting
    #print(num_glitches_f * (60 / 1000))
    #print(np.sum(num_glitches_f[6:]) * (60 / 1000),
    #    np.sum(num_glitches_f) * (60 / 1000))
    #print(np.sum(detection_mask_array, axis = 0)* (60 / 1000))


    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()

    ax.hist(num_events)
    det_num = np.arange(len(onres_ind))
    ax.set_xlabel('Number of events per minute')
    ax.scatter(num_events, det_num, color = 'red')
    
    plt.show()




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
