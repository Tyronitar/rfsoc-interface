from pathlib import Path
import numpy as np
import numpy.typing as npt
import sys, os
import matplotlib.pyplot as plt
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
from scipy.optimize import curve_fit
import pdb
import h5py
import argparse

from rfsocinterface.core.utils import ensure_path, cartesian, ordinal



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
    # for i_res in range(50):
    #     plt.plot(input_time_ordered_data[0, i_res, :])
    # plt.show()
    first_dimension = 2 if input_time_ordered_data.ndim == 3 else 1
    if first_dimension == 1:
        input_data = input_time_ordered_data.reshape((1, *input_time_ordered_data.shape))
    else:
        input_data = input_time_ordered_data
    if chanmask is None:
        chanmask = np.ones_like(input_time_ordered_data[0, :, 0], dtype=int)
        chanmask[1000:] = 0  # This is a fix since these channels seem to be bad

    n_chan = np.size(chanmask)
    timestamp -= timestamp[0]

    if ds_factor != 1:
        new_input_data = signal.decimate(input_data, ds_factor)
    else:
        new_input_data = input_data

    timestamp = timestamp[0::ds_factor]
    fs = 1. / (timestamp[1] - timestamp[0])

    # Flag Outliers
    if flag_outliers:
        good_channels = np.where(chanmask == 1)[0]
        n_flag, timestream_rms = flag(new_input_data[:, good_channels], fs, sigma=outlier_sigma)
        # 2 x N_res
        # plt.plot(timestream_rms[0, good_channels])
        # plt.plot(timestream_rms[1, good_channels])
        # plt.yscale('log')
        # # plt.show(block=False)
        # plt.plot(clean_rms)
        # plt.show()
        # exit()
        med_flag = np.median(n_flag)
        chanmask[np.where(np.any(n_flag > 2. * med_flag, axis=0))] = -1
        # TODO: Also flag for high RMS
        # clean_rms = np.zeros((first_dimension, len(good_channels)))
        _, _, bad_indices_0 = iteratively_reject_outliers(timestream_rms[0], sigma=outlier_sigma)
        _, _, bad_indices_1 = iteratively_reject_outliers(timestream_rms[1], sigma=outlier_sigma)
        bad_indices = np.union1d(bad_indices_0, bad_indices_1)
        chanmask[bad_indices] = -1
        # for i_res in np.where(chanmask == 1)[0][:50]:
        #     plt.plot(new_input_data[0, i_res, :])
        # plt.show()
        # exit()

    # Cut data at start and end
    if cut_time > 0:
        n_samples_to_cut = np.round(cut_time * fs).astype(int)
        new_input_data = new_input_data[:, :, n_samples_to_cut:-n_samples_to_cut]
        timestamp = timestamp[n_samples_to_cut:-n_samples_to_cut]

    # Determine the number of blocks for computing the PSD
    n_samples = np.size(timestamp)
    n_samples_per_block = int(2**np.ceil(np.log2(nominal_block_length / fs)))
    n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
    if n_blocks == 0:
        n_blocks = 1
        # n_samples_per_block = (2 ** np.floor(np.log2(n_samples))).astype(int)
        n_samples_per_block = n_samples
    
    # Window for the PSD
    wind = signal.get_window('hamming', n_samples_per_block)

    psd_all = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    psd_all_clean = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    freq, _ = signal.periodogram(np.ones(n_samples_per_block), fs)

    #figure out an average template to try to remove thermal fluctuations
    data_all = new_input_data[:, np.where(chanmask == 1)[0],:]
    # data_std = np.outer(np.std(data_all,axis=2), np.ones(n_samples))
    data_std = np.std(data_all, axis=2)[:,:,np.newaxis]
    data_mean = np.mean(np.divide(data_all, data_std), axis=1)
    data_mean = data_mean - np.mean(data_mean)

    # Create bandpass filters
    hpfilt_sos = signal.butter(6, hp_filter_template, 'hp', fs=fs, output='sos', analog=False)
    if lp_filter_template >= fs/2:
        lpfilt_sos = signal.butter(6, fs / 2.1, 'lp', fs=fs, output='sos', analog=False)
    else:
        lpfilt_sos = signal.butter(6, lp_filter_template, 'lp', fs=fs, output='sos', analog=False)
    lpfilt_sos2 = signal.butter(6, lp_filter_template2, 'lp', fs=fs, output='sos', analog=False)
    data_mean_filt = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt = signal.sosfiltfilt(lpfilt_sos, data_mean_filt)
    data_mean_filt2 = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_mean_filt2)
    data_all_filt = signal.sosfiltfilt(hpfilt_sos, data_all, axis=2)
    data_all_filt = signal.sosfiltfilt(lpfilt_sos, data_all_filt, axis=2)
    data_all_filt2 = signal.sosfiltfilt(hpfilt_sos, data_all, axis=2)
    data_all_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_all_filt2, axis=2)

    # Loop over good resonators
    # TODO: Try enumerate
    for idx, i_chan in enumerate(np.where(chanmask == 1)[0]):

        # Loop over I and Q
        for i_complex in range(first_dimension):
            psd = np.zeros(int(n_samples_per_block / 2 + 1))
            psd_clean = np.zeros(int(n_samples_per_block / 2 + 1))
            data_filt = np.ndarray.flatten(data_all_filt[i_complex, idx, :])
            data_filt2 = np.ndarray.flatten(data_all_filt2[i_complex, idx, :])
            dummy_time = np.arange(n_samples_per_block)

            # Loop over blocks
            for i_block in range(n_blocks):

                # Compute the power spectrum of the raw data
                this_data = data_all[
                    i_complex,
                    idx,
                    i_block * n_samples_per_block : (i_block + 1) * n_samples_per_block
                ]
                _, this_psd = signal.periodogram(this_data, fs, window=wind)
                psd += this_psd / float(n_blocks)

                #correlate with average template, subtract polynomial, then computed power spectrum
                this_data_filt = data_filt[
                    i_block * n_samples_per_block : (i_block + 1) * n_samples_per_block
                ]
                this_data_filt = this_data_filt - np.mean(this_data_filt)
                this_data_filt2 = data_filt2[
                    i_block * n_samples_per_block : (i_block + 1) * n_samples_per_block
                ]
                this_data_filt2 = this_data_filt2 - np.mean(this_data_filt2)

                this_template_filt = data_mean_filt[
                    i_complex,
                    i_block * n_samples_per_block : (i_block + 1) * n_samples_per_block
                ]
                this_template_filt = this_template_filt - np.mean(this_template_filt)
                this_template_filt2 = data_mean_filt2[
                    i_complex,
                    i_block * n_samples_per_block : (i_block + 1) * n_samples_per_block
                ]
                this_template_filt2 = this_template_filt2 - np.mean(this_template_filt2)

                template_corr = np.mean(np.multiply(this_data_filt2, this_template_filt2)) / \
                                np.mean(np.multiply(this_template_filt2, this_template_filt2))
                clean_data = this_data_filt - template_corr * this_template_filt
                pfit = np.polyfit(dummy_time, clean_data, 2)
                clean_data = clean_data - np.polyval(pfit, dummy_time)
                _, this_psd = signal.periodogram(clean_data, fs, window=wind)
                psd_clean = psd_clean + this_psd / float(n_blocks)

            psd_all[i_complex, i_chan, :] = psd
            psd_all_clean[i_complex, i_chan, :] = psd_clean
    # plt.cla()
    # plt.loglog(freq, psd_all[0, 100, :])
    # plt.loglog(freq, psd_all_clean[0, 100, :])
    # plt.xlim(freq[1], freq[-1])
    # plt.show()

    return chanmask, freq, psd_all, psd_all_clean

def plot_psd(
        chanmask: npt.NDArray,
        freq: npt.NDArray,
        psd_all: npt.NDArray,
        psd_all_clean: npt.NDArray,
        min_percentile: float=16,
        max_percentile: float=84,
        title: str | None=None,
):
    n_good_chan = np.count_nonzero(chanmask)
    good_chan = np.where(chanmask == 1)[0]
    n_good_chan = len(good_chan)
    n_freq = np.size(freq)
    
    # Get the min, median, and max for plotting
    # psd_min = np.percentile(psd_all[:, good_chan, :], 16, axis=1)
    # psd_med = np.median(psd_all[:, good_chan, :], axis=1)
    # psd_max = np.percentile(psd_all[:, good_chan, :], 84, axis=1)
    psd_min_clean = np.percentile(psd_all_clean[:, good_chan, :], min_percentile, axis=1)
    psd_med_clean = np.median(psd_all_clean[:, good_chan, :], axis=1)
    # if psd_med_clean.max() == 0.0:
    #     psd_med_clean = np.mean(psd_all_clean[:, good_chan, :], axis=1)
    psd_max_clean = np.percentile(psd_all_clean[:, good_chan, :], max_percentile, axis=1)

    # Only use good data for plotting
    # TODO: Make complex index choice dynamic
    # good_ind = np.arange(n_good_chan)
    good_ind = good_chan
    plot_data_min = 10 * np.log10(psd_min_clean[0, good_ind])
    plot_data_med = 10 * np.log10(psd_med_clean[0, good_ind])
    plot_data_max = 10 * np.log10(psd_max_clean[0, good_ind])

    # Plot the data
    fig = plt.figure()
    ax = plt.subplot()
    ax.fill_between(
        freq[good_ind],
        plot_data_min,
        plot_data_max,
        facecolor='c',
        alpha=0.5,
        label=f'{ordinal(int(min_percentile))} Percentile to {ordinal(int(max_percentile))} Percentile'
    )
    ax.plot(freq[good_ind], plot_data_med, color='b', label='Median Measured Noise')
    ax.set_xscale('log')
    ax.set_xlim(0.1,100.)
    ax.set_ylim(-110, -60)
    ax.set_xlabel('Frequency (Hz)', fontsize=16)
    ax.set_ylabel(r'Noise PSD (dBc/Hz)', fontsize=16)
    ax.tick_params(labelsize=14)
    ax.legend(fontsize=14, loc = 'upper right')
    if title is None:
        title = 'RFSoC Loopback'
    ax.set_title(title, fontsize=16)

    return fig


def flag(data: npt.NDArray, fs: float, sigma: float=2):
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

    # goodchan = np.where(chanmask == 1)
    # med_flag = np.median(n_flag[goodchan])
    # chanmask[np.where(n_flag > 2.*med_flag)] = -1


def reject_outliers(data: npt.NDArray, sigma: float=2, axis: int | None=None):
    d = np.abs(data - np.median(data, axis=axis))
    std = np.std(data, axis=axis)
    ind = np.where(d < sigma * std)
    return data[ind], ind


def iteratively_reject_outliers(data: npt.NDArray, sigma: float=2, axis: int | None=None):
    ind = np.arange(np.size(data))
    # ind = np.ones_like(data, dtype=int)
    # ind = get_all_indices(data)
    if data.ndim != 1:
        data = data.flatten()
    while True:
        good_data, good_ind = reject_outliers(data[ind], sigma=sigma, axis=axis)
        if np.size(ind) == np.size(good_ind):
            break
        ind = ind[good_ind]
    return data[ind], ind, np.setdiff1d(np.arange(np.size(data)), ind)


def reject_outliers_onr(data,sigma=2):
  keepgoing = 1
  good_ind = np.arange(np.size(data))
  while keepgoing:
    d = np.abs(data[good_ind] - np.median(data[good_ind]))
    s = np.std(data[good_ind])
    valid = np.where(d < sigma * s)
    if np.size(valid) == np.size(good_ind):
      keepgoing = 0
    else:
      good_ind = good_ind[valid]
  return data[good_ind], good_ind

@ensure_path(0)
def load_data(path: Path) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
    with h5py.File(path, 'r') as f:
        data_i = f['time_ordered_data/adc_i'][:]
        data_q = f['time_ordered_data/adc_q'][:]
        amp = np.sqrt(data_i ** 2. + data_q ** 2.)
        # amp = np.sqrt(float(data_i) ** 2 + float(data_q) ** 2)
        amp = np.nanmedian(amp, axis=1)
        input_data = np.empty((2, *data_i.shape))
        input_data[0, :, :] = data_i / np.outer(amp, np.ones(data_i.shape[1]))
        input_data[1, :, :] = data_q / np.outer(amp, np.ones(data_q.shape[1]))
        timestamp = f['time_ordered_data/timestamp'][:]
        chanmask = f['global_data/chanmask'][:]
    return input_data, timestamp, chanmask

def plot(data: npt.NDArray):
    mean_data = np.nanmean(data, axis=-1)
    centered_data = data - mean_data[..., np.newaxis]
    print(centered_data)
    n_tones = 30
    for i_tone in range(530, 530 + n_tones):
        plt.plot(centered_data[0, i_tone, :] + i_tone * 1e-3)
    plt.show()


if __name__ == '__main__':
    # parser = argparse.ArgumentParser()
    # parser.add_argument('data_file')
    # args = parser.parse_args()
    # path = args.data_file
    # input_data1, timestamp1, chanmask1 = load_data('data/data.hdf5')
    input_data2, timestamp2, chanmask2 = load_data('data/equal.hdf5')

    chanmask1, freq1, psd_all1, psd_all_clean1 = compute_noise_psd(
        input_data2,
        timestamp2,
        chanmask=None,
        ds_factor=3,
        flag_outliers=False,
    )
    # chanmask2, freq2, psd_all2, psd_all_clean2 = compute_noise_psd(
    #     input_data2,
    #     timestamp2,
    #     chanmask=None,
    #     ds_factor=3,
    #     flag_outliers=True,
    # )
    # # d1, _ = iteratively_reject_outliers(psd_all_clean1[:, chanmask1, :])
    # # d2, _ = reject_outliers_onr(psd_all_clean1[:, chanmask1, :].flatten())
    # # exit()
    # # chanmask2, freq2, psd_all2, psd_all_clean2 = compute_noise_psd(input_data2, timestamp2, chanmask=None, ds_factor=3)
    fig1 = plot_psd(chanmask1, freq1, psd_all1, psd_all_clean1, title='RFSoC Loopback with 500 Equally Spaced Tones')
    # fig1 = plot_psd(chanmask1, freq1, psd_all1, psd_all_clean1, max_percentile=84, title='No Outlier Removal')
    # fig2 = plot_psd(chanmask2, freq2, psd_all2, psd_all_clean2, max_percentile=83, title='With Outlier Removal')
    # # fig3 = plot_psd(chanmask2, freq2, psd_all2, psd_all_clean2, max_percentile=84, title='84th Percentile')
    plt.show()
