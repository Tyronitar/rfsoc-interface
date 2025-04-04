"""Code for computing the noise PSD."""

from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages


from rfsocinterface.core.data import load_time_ordered_IQ_data
from rfsocinterface.core.utils import ensure_path, ordinal

XLIM = (0.1, 100)
YLIM = (-110, -60)


def rotate_to_amplitude_and_phase(input_IQ_data: npt.NDArray):
    """Compute chnage of basis to amplitude/phase."""
    assert input_IQ_data.ndim == 3
    assert input_IQ_data.shape[0] == 2
    atan = np.atan2(input_IQ_data[1, :, :], input_IQ_data[0, :, :])
    rotation_angle = np.nanmedian(atan, axis=-1)

    amp = np.cos(rotation_angle)[:, np.newaxis] * input_IQ_data[0, :, :] + np.sin(rotation_angle)[:, np.newaxis] * input_IQ_data[1, :, :]
    phase = -np.sin(rotation_angle)[:, np.newaxis] * input_IQ_data[0, :, :] + np.cos(rotation_angle)[:, np.newaxis] * input_IQ_data[1, :, :]
    new_data = np.zeros(shape=input_IQ_data.shape)
    new_data[0] = amp
    new_data[1] = phase
    return new_data


def compute_noise_psd(
    input_time_ordered_data: npt.NDArray,
    timestamp: npt.NDArray,
    chanmask: npt.NDArray | None=None,
    ds_factor: int=1,
    nominal_block_length: float=1e100,
    cut_time: float=0.0,
    hp_filter_template: float=0.05,
    lp_filter_template: float=115.,
    lp_filter_template2: float=25.,
    flag_outliers: bool=True,
    outlier_sigma: float=4,
) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
    """Compute noise PSD.

    input_time_ordered_data: 2 x N_res x N_sample or N_res x N_sample
    timestamp: N_sample
    chanmask: N_res
    ds_factor: Downscaling factor
    nominal_block_length: seconds
    cut_time: seconds to cut from ends of data
    hp_filter_template: high-pass filter
    lp_filter_template: low-pass filter
    """
    first_dimension = 2 if input_time_ordered_data.ndim == 3 else 1
    if first_dimension == 1:
        input_data = input_time_ordered_data.reshape((1, *input_time_ordered_data.shape))
    else:
        input_data = input_time_ordered_data
    if chanmask is None:
        chanmask = np.ones_like(input_time_ordered_data[0, :, 0], dtype=int)
        chanmask[1000:] = 0  # This is a fix since these channels seem to be bad

    timestamp -= timestamp[0]

    if ds_factor != 1:
        new_input_data = signal.decimate(input_data, ds_factor)
    else:
        new_input_data = input_data

    timestamp = timestamp[0::ds_factor]
    fs = 1. / np.median(np.diff(timestamp))

    # Flag Outliers
    if flag_outliers:
        good_channels = np.where(chanmask == 1)[0]
        n_flag, timestream_rms = flag(new_input_data[:, good_channels], fs, sigma=outlier_sigma)
        med_flag = np.median(n_flag)
        chanmask[np.where(np.any(n_flag > 2. * med_flag, axis=0))] = -1
        _, _, bad_indices_0 = iteratively_reject_outliers(timestream_rms[0], sigma=outlier_sigma)
        _, _, bad_indices_1 = iteratively_reject_outliers(timestream_rms[1], sigma=outlier_sigma)
        bad_indices = np.union1d(bad_indices_0, bad_indices_1)
        chanmask[bad_indices] = -1

    # Cut data at start and end
    if cut_time > 0:
        n_samples_to_cut = np.round(cut_time * fs).astype(int)
        new_input_data = new_input_data[:, :, n_samples_to_cut:-n_samples_to_cut]
        timestamp = timestamp[n_samples_to_cut:-n_samples_to_cut]

    # Determine the number of blocks for computing the PSD
    n_samples = np.size(timestamp)
    n_samples_per_block = int(2**np.ceil(np.log2(nominal_block_length * fs)))
    n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
    if n_blocks == 0:
        n_blocks = 1
        n_samples_per_block = n_samples
    
    data_clean = remove_correlatred_noise(new_input_data[:, np.where(chanmask == 1)[0], :])
    freq, psd = _compute_psd(data_clean, fs, n_samples_per_block)
    return chanmask, freq, psd


def compute_templates(data: npt.NDArray) -> npt.NDArray:
    """Compute templates for correlated noise removal.
    
    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples).
    
    Returns:
        (npt.NDarray): Templates for noise removal (N_chan x 2 x N_samples).
            Computed using the first two eigenmodes of the correlation matrix.
    """
        # subtract the mean from each detector
    data_meansub = data - np.mean(data, axis=2)[:, :, np.newaxis]
    
    # select only the middle few detectors
    deproj = data_meansub[:, 8:1008, :]

    # create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(deproj, np.conj(np.transpose(deproj, axes=(0, 2, 1))))
    # calculate the eigenmodes of the correlation matrices
    _, v = np.linalg.eig(correlation_matrices)

    # create templates based on the 2 largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', v[:,:,0:2], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates


def remove_correlatred_noise(data: npt.NDArray) -> npt.NDArray:
    """Remove correlated noise templates from the data.
    
    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples).
    
    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    templates = compute_templates(data)  # N_chan x 2 x N_samples

    denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2
    numerator0 = np.einsum('ijk,ik->ij', data, templates[:, 0])  # N_chan x N_detector
    corr0 = numerator0 / denominator[:, 0:1]  # N_chan x N_detector
    deproj = data - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    numerator1 = np.einsum('ijk,ik->ij', deproj, templates[:, 1])  # N_chan x N_detector
    corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    clean_data = deproj - np.einsum('ij,ikl->ijl', corr1, templates[:, 1:])
    return clean_data


def _compute_psd(
        data: npt.NDArray,
        fs: float,
        n_samples_per_block: int,
) -> tuple[npt.NDArray, npt.NDArray]:
    """Compute the PSD."""
    Z = data[0] + 1j*data[1]
    norm = np.mean(np.abs(Z), axis=1)[:, np.newaxis]

    f, psd = signal.welch(data / norm, fs, nperseg=n_samples_per_block)
    return f, psd


@ensure_path(2)
def plot_psd(
        freq: npt.NDArray,
        psd: npt.NDArray,
        filename: Path,
        min_percentile: float=16,
        max_percentile: float=84,
        title: str | None=None,
        basis: Literal['pa', 'iq']='pa',
) -> tuple[Figure, Figure, Figure]:
    """Create plots for the psd.
    
    Args:
        freq (npt.NDArray): Array of frequencies (N_freq).
        psd: (npt.NDArray): PSD (2 x N_resonators x N_freq).
        filename (Path): PDF filename to save the  plots to.
        min_perncentile (float, optional): Percentile of lower error bound for the plot.
            Defaults to 16.
        max_perncentile (float, optional): Percentile of upper error bound for the plot
            Defaults to 84.
        title (str, optional): Title to give to each plot. Defaults to None.
        basis (str, optional): The basis of the data. Either IQ ('iq') or 
            Phase/Amplitude ('pa'). Defaults to 'pa'.
    
    Returns:
        (Figure, Figure, Figure): Three plots corresponding to the PSD along the
            first basis direction, second direction, and mean across both directions.
    
    Raises:
        ValueError: If `basis` is not 'iq' or 'pa'.
    """
   
    psd_min = np.percentile(psd, min_percentile, axis=1)
    psd_med = np.median(psd, axis=1)
    psd_max = np.percentile(psd, max_percentile, axis=1)

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_med = 10 * np.log10(psd_med)
    plot_data_max = 10 * np.log10(psd_max)

    if title is None:
        title = 'RFSoC Loopback PSD'
    match basis.lower():
        case 'pa':
            titles = [title + ' - Phase', title + ' - Amplitude']
        case 'iq':
            titles = [title + ' - I', title + ' - Q']
        case _:
            raise ValueError(f'Invalid basis {basis}; must be one of ["pa", "iq"]')

    # Plot the data
    fig0 = create_plot(
        freq,
        plot_data_min[0],
        plot_data_med[0],
        plot_data_max[0],
        percentiles=(min_percentile, max_percentile),
        title=titles[0],
    )
    fig1 = create_plot(
        freq,
        plot_data_min[1],
        plot_data_med[1],
        plot_data_max[1],
        percentiles=(min_percentile, max_percentile),
        title=titles[1],
    )
    fig2 = create_plot(
        freq,
        (plot_data_min[0] + plot_data_min[1]) / 2,
        (plot_data_med[0] + plot_data_med[1]) / 2,
        (plot_data_max[0] + plot_data_max[1]) / 2,
        percentiles=(min_percentile, max_percentile),
        title= title + ' - Combined',
    )
    with PdfPages(filename) as pdf:
        pdf.savefig(fig0)
        pdf.savefig(fig1)
        pdf.savefig(fig2)

    return fig0, fig1, fig2

def create_plot(
        xdata: npt.ArrayLike,
        ydata_min: npt.ArrayLike,
        ydata_med: npt.ArrayLike,
        ydata_max: npt.ArrayLike,
        percentiles: tuple[float, float]=(16., 84.),
        label: str='Median Measured Noise',
        title: str | None=None,
) -> Figure:
    """Create a plot of the noise PSD."""
    fig = plt.figure(figsize=(9, 6))
    ax = plt.subplot()
    ax.plot(xdata, ydata_med, color='b', label=label)
    ax.fill_between(
        xdata,
        ydata_min,
        ydata_max,
        facecolor='c',
        alpha=0.5,
        label=f'{ordinal(int(percentiles[0]))} Percentile to {ordinal(int(percentiles[1]))} Percentile'
    )
    ax.set_xscale('log')
    ax.set_xlim(0.1,100.)
    ax.set_ylim(-110, -60)
    ax.set_xlabel('Frequency (Hz)', fontsize=16)
    ax.set_ylabel(r'Noise PSD (dBc/Hz)', fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc = 'upper right')
    if title is None:
        title = 'RFSoC Loopback PSD'
    ax.set_title(title, fontsize=16)
    plt.tight_layout()

    return fig


def flag(data: npt.NDArray, fs: float, sigma: float=2):
    """Flag data outliers."""
    first_dimension, n_chan, _ = data.shape
    n_flag = np.zeros((first_dimension, n_chan))

    filt_cut = 1. / (0.5 * fs)
    b, a = signal.butter(5, filt_cut, btype='high', analog=False)
    hpf_data = signal.filtfilt(b, a, data)
    for i_complex in range(first_dimension):
        for i_res in range(n_chan):
            inliers, _, _ = iteratively_reject_outliers(hpf_data[i_complex, i_res, :], sigma=sigma)
            n_flag[i_complex, i_res] = hpf_data.shape[-1] - np.size(inliers)
    return n_flag, np.std(hpf_data, axis=-1)


def reject_outliers(data: npt.NDArray, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Return the data without outliers and the rejected indices."""
    d = np.abs(data - np.median(data, axis=axis))
    std = np.std(data, axis=axis)
    ind = np.where(d < sigma * std)
    return data[ind], ind


def iteratively_reject_outliers(data: npt.ArrayLike, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Repeatedly perform outlier rejection until there are no more outliers.
    
    Args:
        data (npt.ArrayLike): Input data (expected to be 1 dimensional)
        sigma (float, optional): The standard deviation cutoff for outliers. Defaults
            to 2.
        axis (None or int or tuple of ints, optional): The axis or axes to perform the
            outlier rejection along. Deafults to None.
    
    Returns:
        (npt.NDArray, npt.NDArray, npt.NDArray): `data` with the outliers removed,
        indices in `data` of the inliers, and indices in `data` of the outliers .
    """
    ind = np.arange(np.size(data))
    # ind = np.ones_like(data, dtype=int)
    # ind = get_all_indices(data)
    if np.ndim(data) != 1:
        data = np.flatten(data)
    while True:
        good_data, good_ind = reject_outliers(data[ind], sigma=sigma, axis=axis)
        if np.size(ind) == np.size(good_ind):
            break
        ind = ind[good_ind]
    return data[ind], ind, np.setdiff1d(np.arange(np.size(data)), ind)

if __name__ == '__main__':
    pairs = [
        # ('equal_0-256', 'RFSoC Loopback with 1000 Tones Over Full Bandwidth'),
        # ('equal_1-255', 'RFSoC Loopback with 1000 Tones in Range +/-[1, 255] MHz'),
        # ('equal_5-251', 'RFSoC Loopback with 1000 Tones in Range +/-[5, 251] MHz'),
        # ('equal_10-246', 'RFSoC Loopback with 1000 Tones in Range +/-[10, 246] MHz'),
        # ('default_0-256', 'RFSoC Loopback with Default Tones'),
        # ('default_1-255', 'RFSoC Loopback with Default Tones in Range +/-[1, 255] MHz'),
        # ('default_5-251', 'RFSoC Loopback with Default Tones in Range +/-[5, 251] MHz'),
        # ('default_10-246', 'RFSoC Loopback with Default Tones in Range +/-[10, 246] MHz'),
        ('/data/20250404/20250404_chan_1_TOD_set1001.h5', 'ASU Readout'),
    ]
    for name, title in pairs:
        # input_data, timestamp, chanmask = load_time_ordered_IQ_data(f'data/{name}.hdf5')
        input_data, timestamp, chanmask = load_time_ordered_IQ_data(f'{name}')
        
        rotated_data = rotate_to_amplitude_and_phase(input_data)
        save_name = f'new_psd_{name}'

        chanmask, freq, noise_psd = compute_noise_psd(
            rotated_data,
            timestamp,
            chanmask=None,
            ds_factor=3,
            flag_outliers=True,
            nominal_block_length=10,
            outlier_sigma=2,
        )
        plot_psd(freq, noise_psd, f'plots/asu_test.pdf', basis='pa', title=title)
        plt.close()

