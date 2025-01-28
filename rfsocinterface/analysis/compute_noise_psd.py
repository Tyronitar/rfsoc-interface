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
):
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
    is_complex = len(np.shape(input_time_ordered_data)) == 3
    # for i_res in range(50):
    #     plt.plot(input_time_ordered_data[0, i_res, :])
    # plt.show()
    first_dimension = 2 if is_complex else 1
    if chanmask is None:
        chanmask = np.ones_like(input_time_ordered_data[0, :, 0])
        chanmask[1000:] = 0  # This is a fix since these channels seem to be bad
    timestamp -= timestamp[0]
    # For data for each resonator:  either 2 or 1
    #   calculate noise
    if ds_factor != 1:
        new_input_time_ordered_data = np.zeros(
            [
                first_dimension,
                np.size(chanmask),
                np.size(signal.decimate(input_time_ordered_data[0,0,:], ds_factor))
        ])
        for i_res in range(np.size(chanmask)):
            for i_complex in range(first_dimension):
                new_input_time_ordered_data[i_complex, i_res, :] = signal.decimate(
                    input_time_ordered_data[i_complex, i_res, :],
                    ds_factor,
                )
        input_time_ordered_data = new_input_time_ordered_data
        timestamp = timestamp[0::ds_factor]
    fs = 1. / (timestamp[1] - timestamp[0])

    # Cut data at start and end
    if cut_time > 0:
        n_samples_to_cut = np.round(cut_time * fs).astype(int)
        input_time_ordered_data = input_time_ordered_data[:, :, n_samples_to_cut:-n_samples_to_cut]
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

    n_chan = np.size(chanmask)
    psd_all = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    psd_all_clean = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    freq, _ = signal.periodogram(np.ones(n_samples_per_block), fs)

    #figure out an average template to try to remove thermal fluctuations
    data_all = input_time_ordered_data[:, np.argwhere(chanmask == 1).flatten(),:]
    # data_std = np.outer(np.std(data_all,axis=2), np.ones(n_samples))
    data_std = np.std(data_all, axis=2)[:,:,np.newaxis]
    data_mean = np.mean(np.divide(data_all, data_std), axis=1)
    data_mean = data_mean - np.mean(data_mean)

    # Create bandpass filters
    hpfilt_sos = signal.butter(6, hp_filter_template, 'hp', fs=fs, output='sos', analog=False)
    # lpfilt_sos = signal.butter(6, lp_filter_template, 'lp', fs=fs, output='sos', analog=False)
    lpfilt_sos = signal.butter(6, fs / 2.1, 'lp', fs=fs, output='sos', analog=False)
    lpfilt_sos2 = signal.butter(6, 25, 'lp', fs=fs, output='sos', analog=False)
    data_mean_filt = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt = signal.sosfiltfilt(lpfilt_sos, data_mean_filt)
    data_mean_filt2 = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_mean_filt2)
    data_all_filt = signal.sosfiltfilt(hpfilt_sos, data_all, axis=2)
    data_all_filt = signal.sosfiltfilt(lpfilt_sos, data_all_filt, axis=2)
    data_all_filt2 = signal.sosfiltfilt(hpfilt_sos, data_all, axis=2)
    data_all_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_all_filt2, axis=2)

    # Loop over good resonators
    for i_chan in np.where(chanmask == 1)[0]:

        # Loop over I and Q
        for i_complex in range(first_dimension):
            psd = np.zeros(int(n_samples_per_block / 2 + 1))
            psd_clean = np.zeros(int(n_samples_per_block / 2 + 1))
            data_filt = np.ndarray.flatten(data_all_filt[i_complex, i_chan, :])
            data_filt2 = np.ndarray.flatten(data_all_filt2[i_complex, i_chan, :])
            dummy_time = np.arange(n_samples_per_block)

            # Loop over blocks
            for i_block in range(n_blocks):

                # Compute the power spectrum of the raw data
                this_data = input_time_ordered_data[
                    i_complex,
                    i_chan,
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
    # plt.loglog(freq, psd_all[0, 100, :])
    # plt.loglog(freq, psd_all_clean[0, 100, :])
    # plt.xlim(freq[1], freq[-1])
    # plt.show()

    valid_chan = np.argwhere(chanmask == 1).flatten()
    n_good_chan = np.size(valid_chan)
    min_ind = int(np.round(n_good_chan * 0.16))
    med_ind = int(np.round(n_good_chan * 0.5))
    max_ind = int(np.round(n_good_chan * 0.84))
    n_freq = np.size(freq)
    psd_min = np.zeros((first_dimension, n_freq))
    psd_med = np.zeros((first_dimension, n_freq))
    psd_max = np.zeros((first_dimension, n_freq))
    psd_min_clean = np.zeros((first_dimension, n_freq))
    psd_med_clean = np.zeros((first_dimension, n_freq))
    psd_max_clean = np.zeros((first_dimension, n_freq))
    for i_complex in range(first_dimension):
        for i_freq in range(0, n_freq):
            psd_sort = np.sort(psd_all[i_complex, :, i_freq])
            psd_min[i_complex, i_freq] = psd_sort[min_ind]
            psd_med[i_complex, i_freq] = psd_sort[med_ind]
            psd_max[i_complex, i_freq] = psd_sort[max_ind]
            psd_sort = np.sort(psd_all_clean[i_complex, :, i_freq])
            psd_min_clean[i_complex, i_freq] = psd_sort[min_ind]
            psd_med_clean[i_complex, i_freq] = psd_sort[med_ind]
            psd_max_clean[i_complex, i_freq] = psd_sort[max_ind]

    good_ind = np.arange(n_freq)
    freq_fill = np.concatenate([freq[good_ind],np.flip(freq[good_ind],0)])

    psd_fill_clean = np.concatenate([10 * np.log10(psd_min_clean[0, good_ind]),np.flip(10 * np.log10(psd_max_clean[0, good_ind]),0)])
    plt.fill(freq_fill, psd_fill_clean, 'c', alpha=0.5)
    plt.plot(freq[good_ind], 10 * np.log10(psd_med_clean[0, good_ind]), 'b', label='Measured Noise')
    # plt.yscale('log')
    plt.xscale('log')
    plt.xlim(0.1,100.)
    plt.ylim(-110, -60)
    plt.xlabel('Frequency (Hz)', fontsize=16)
    plt.ylabel(r'Noise PSD (dBc/Hz)', fontsize=16)
    plt.xticks(fontsize=14)
    plt.yticks(fontsize=14)
    plt.legend(fontsize=14, loc = 'upper right')
    plt.title('RFSoC Loopback', fontsize=16)
    plt.show()


# def flag():
#     n_flag = np.zeros(np.size(chanmask))
#     fs = float(1./ ((time[1]-time[0]) * ds_factor))
#     filt_cut = 1. / (0.5 * fs)
#     b, a = signal.butter(5, filt_cut, btype='high', analog=False)
#     for i_res in range(np.size(chanmask)):
#         this_hpf_data = signal.filtfilt(b, a, new_input_time_ordered_data[i_res,:])
#         dummy, _ = reject_outliers(this_hpf_data,sigma=4)
#         n_flag[i_res] = np.size(this_hpf_data) - np.size(dummy)
#     goodchan = np.where(chanmask == 1)
#     med_flag = np.median(n_flag[goodchan])
#     chanmask[np.where(n_flag > 2.*med_flag)] = -1

if __name__ == '__main__':
    # parser = argparse.ArgumentParser()
    # parser.add_argument('data_file')
    # args = parser.parse_args()
    # path = args.data_file
    path = Path('data/data.hdf5')
    with h5py.File(path, 'r') as f:
        data_i = f['time_ordered_data/adc_i'][:]
        data_q = f['time_ordered_data/adc_q'][:]
        amp = np.sqrt(data_i ** 2. + data_q ** 2.)
        # amp = np.sqrt(float(data_i) ** 2 + float(data_q) ** 2)
        amp = np.nanmedian(amp, axis=1)
        input_data = np.empty((2, *data_i.shape))
        input_data[0, :, :] = data_i / np.outer(amp, np.ones(data_i.shape[1]))
        # input_data[0, :, :] = data_i / amp[:, np.newaxis]
        # input_data[1, :, :] = data_q / amp[:, np.newaxis]
        input_data[1, :, :] = data_q / np.outer(amp, np.ones(data_q.shape[1]))
        timestamp = f['time_ordered_data/timestamp'][:]
        chanmask = f['global_data/chanmask'][:]
    compute_noise_psd(input_data, timestamp, chanmask=None, ds_factor=3)