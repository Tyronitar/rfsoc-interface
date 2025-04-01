
from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
from scipy.optimize import curve_fit
import scipy
import pdb
import argparse


from rfsocinterface.core.data import load_time_ordered_IQ_data
from rfsocinterface.core.utils import ensure_path, cartesian, ordinal

XLIM = (0.1, 100)
YLIM = (-110, -60)


def rotate_to_amplitude_and_phase(input_IQ_data: npt.NDArray):
    """Compute chnage of basis to amplitude/phase."""
    assert input_IQ_data.ndim == 3
    assert input_IQ_data.shape[0] == 2
    atan = np.atan2(input_IQ_data[1, :, :], input_IQ_data[0, :, :])
    rotation_angle = np.nanmedian(atan, axis=-1)

    idx = 200
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
    cody_title: str='',
    cody_file: str='',
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
    # plt.plot(timestamp, timestamp - np.roll(timestamp, 1))
    # plt.plot(timestamp, np.diff(timestamp))
    # plt.xlim(0, 10)
    # plt.ylim(-0.01, 0.01)
    # plt.show()
    # exit()
    # fs = 1. / (timestamp[1] - timestamp[0])
    fs = 1. / np.median(np.diff(timestamp))

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
    n_samples_per_block = int(2**np.ceil(np.log2(nominal_block_length * fs)))
    n_blocks = np.floor(float(n_samples) / float(n_samples_per_block)).astype(int)
    if n_blocks == 0:
        n_blocks = 1
        # n_samples_per_block = (2 ** np.floor(np.log2(n_samples))).astype(int)
        n_samples_per_block = n_samples
    
    if cody_title:
        return cody_psd(new_input_data[:, np.where(chanmask == 1)[0], :], fs, n_samples_per_block, cody_file, cody_title)
    else:
        return old_psd(
            new_input_data,
            fs,
            chanmask,
            n_samples_per_block,
            n_blocks,
            hp_filter_template=hp_filter_template,
            lp_filter_template=lp_filter_template,
            lp_filter_template2=lp_filter_template2,
    )

def old_psd(
        new_input_data: npt.NDArray,
        fs: float,
        chanmask: npt.NDArray,
        n_samples_per_block: int,
        n_blocks: int,
        hp_filter_template: float=0.05,
        lp_filter_template: float=115,
        lp_filter_template2: float=25
):
    n_chan = np.size(chanmask)
    first_dimension = new_input_data.shape[0]

    # Window for the PSD
    wind = signal.get_window('hamming', n_samples_per_block)

    psd_all = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    psd_all_clean = np.zeros((first_dimension, n_chan, int(n_samples_per_block / 2 + 1)))
    # freq, _ = signal.welch(np.ones(n_samples_per_block), fs)
    freq, _ = signal.periodogram(np.ones(n_samples_per_block), fs)


    #figure out an average template to try to remove thermal fluctuations
    data_all = new_input_data[:, np.where(chanmask == 1)[0],:]
    # data_std = np.outer(np.std(data_all,axis=2), np.ones(n_samples))
    data_std = np.std(data_all, axis=2)[:,:,np.newaxis]
    data_mean = np.mean(np.divide(data_all, data_std), axis=1)
    data_mean = data_mean - np.mean(data_mean)

    # Create bandpass filters
    hpfilt_sos = signal.butter(6, hp_filter_template, 'hp', fs=fs, output='sos', analog=False)
    if lp_filter_template > fs / 2:
        lpfilt_sos = signal.butter(6, fs / 2.1, 'lp', fs=fs, output='sos', analog=False)
    else:
        lpfilt_sos = signal.butter(6, lp_filter_template, 'lp', fs=fs, output='sos', analog=False)
    lpfilt_sos2 = signal.butter(6, lp_filter_template2, 'lp', fs=fs, output='sos', analog=False)
    data_mean_filt = signal.sosfiltfilt(lpfilt_sos, data_mean)
    data_mean_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_mean)
    data_all_filt = signal.sosfiltfilt(lpfilt_sos, data_all, axis=2)
    data_all_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_all, axis=2)

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
                # _, this_psd = signal.periodogram(this_data, fs, window=wind)
                _, this_psd = signal.welch(this_data, fs, window=wind)
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
                # _, this_psd = signal.periodogram(clean_data, fs, window=wind)
                _, this_psd = signal.welch(clean_data, fs, window=wind)
                psd_clean = psd_clean + this_psd / float(n_blocks)

            psd_all[i_complex, i_chan, :] = psd
            psd_all_clean[i_complex, i_chan, :] = psd_clean
    # plt.cla()
    # plt.loglog(freq, psd_all[0, 100, :])
    # plt.loglog(freq, psd_all_clean[0, 100, :])
    # plt.xlim(freq[1], freq[-1])
    # plt.show()

    return chanmask, freq, psd_all, psd_all_clean


def compute_templates(data: npt.NDArray) -> npt.NDArray:
    """Compute templates for correlated noise removal.
    
    Arguments:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples)
    
    Returns:
        (npt.NDarray): Template for noise removal (N_chan x 2 x N_samples).
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
    
    Arguments:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples)
    
    Returns:
        (npt.NDarray): Cleaned data (N_chan x N_detector x N_samples).
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


def psd(
        data: npt.NDArray,
        fs: float,
        n_samples_per_block: int,
) -> npt.NDArray:
    I = data[0]
    Q = data[1]
    Z = I+ 1j*Q
    norm = np.mean(np.abs(Z), axis=1)[:, np.newaxis]
    f,Spp_i=scipy.signal.welch(np.real(Z)/norm,fs=fs,nperseg=n_samples_per_block)
    f,Spp_q=scipy.signal.welch(np.imag(Z)/norm,fs=fs,nperseg=n_samples_per_block)
    Spp = (Spp_i + Spp_q) / 2
    plt.semilogx(f, 10*np.log10(np.mean(Spp, axis=0)))

    wind = signal.get_window('hamming', n_samples_per_block)
    # _, psd1 = signal.periodogram(data, fs, window=wind)
    f2, psd2 = signal.welch(data, fs, window=wind)
    psd2_plot = (psd2[0] + psd2[1]) / 2
    plt.semilogx(f2, 10*np.log10(np.mean(psd2_plot, axis=0)))
    plt.xscale('log')
    plt.show()
    pdb.set_trace()



def cody_psd(data, fs, npoints, file_name, title):
    I = data[0]
    Q = data[1]
    # templates = cody_template(I, Q)
    # compute_templates(data)
    # I_clean, Q_clean = cody_clean(I, Q, *templates)
    data_clean = remove_correlatred_noise(data)
    noise_psd = psd(data, fs, npoints)
    exit()
    # fig1 = cody_plot(I, Q, 8192, fs, file_name)
    fig = cody_plot(I_clean, Q_clean, npoints, fs, title)
    with PdfPages(f'plots/cody_{file_name}.pdf') as pdf:
        pdf.savefig(fig)


def cody_template(I, Q):
    # subtract the mean from each detector
    Imeansub = np.zeros_like(I)
    Qmeansub = np.zeros_like(Q)
    for i in range(len(I[:,0])):
        Imeansub[i,:] = I[i,:] - np.mean(I[i,:])
        Qmeansub[i,:] = Q[i,:] - np.mean(Q[i,:])
    
    # select only the middle few detectors
    deproj_I = Imeansub[8:1008 ,:]
    deproj_Q = Qmeansub[8:1008,:]

    # create a separate correlation matrix for I and Q
    correlation_matrix_I = np.matmul(deproj_I,np.conj(np.transpose(deproj_I)))
    correlation_matrix_Q = np.matmul(deproj_Q,np.conj(np.transpose(deproj_Q)))
    # calculate the eigenmodes of each correlation matrix
    wI,vI = np.linalg.eig(correlation_matrix_I)
    wQ,vQ = np.linalg.eig(correlation_matrix_Q)
    # create templates based on the largest eigenmode of each
    templateI0 = np.matmul(vI[:,0],deproj_I)    
    templateQ0 = np.matmul(vQ[:,0],deproj_Q)

    # subtract the mean again to be sure
    template_real0 = np.real(templateI0)-np.mean(np.real(templateI0))
    template_imag0 = np.real(templateQ0)-np.mean(np.real(templateQ0))

    # create templates based on the second largest eigenmode of each
    templateI1 = np.matmul(vI[:,1],deproj_I)    
    templateQ1 = np.matmul(vQ[:,1],deproj_Q)

    # subtract the mean again to be sure
    template_real1 = np.real(templateI1)-np.mean(np.real(templateI1))
    template_imag1 = np.real(templateQ1)-np.mean(np.real(templateQ1))
   
    #plt.figure()
    #plt.subplot(2,1,1)
    #plt.semilogy(wI,"x")
    #plt.grid("on")
    #plt.subplot(2,1,2)
    #plt.semilogy(wQ,"x")
    #plt.grid("on")
    
    return template_real0,template_imag0,template_real1,template_imag1

def cody_clean(I,Q,template_I0,template_Q0,template_I1,template_Q1):
    Iclean = np.zeros_like(I)
    Qclean = np.zeros_like(Q)
    
    for idet in range(len(I[:,0])):
        samp_chan_I = I[idet,:]
        samp_chan_Q = Q[idet,:]
    
        corr0 = np.matmul(samp_chan_I,np.transpose(template_I0))/np.matmul(template_I0,np.transpose(template_I0))
        deprojected_samp_detector_I = samp_chan_I-corr0*template_I0
        corr1 = np.matmul(deprojected_samp_detector_I,np.transpose(template_I1))/np.matmul(template_I1,np.transpose(template_I1))
        deprojected_samp_detector_I = deprojected_samp_detector_I-corr1*template_I1
        
        corr0 = np.matmul(samp_chan_Q,np.transpose(template_Q0))/np.matmul(template_Q0,np.transpose(template_Q0))
        deprojected_samp_detector_Q = samp_chan_Q-corr0*template_Q0
        corr1 = np.matmul(deprojected_samp_detector_Q,np.transpose(template_Q1))/np.matmul(template_Q1,np.transpose(template_Q1))
        deprojected_samp_detector_Q = deprojected_samp_detector_Q-corr1*template_Q1
    
        Iclean[idet,:] = deprojected_samp_detector_I
        Qclean[idet,:] = deprojected_samp_detector_Q
    return Iclean,Qclean

def cody_plot(I, Q, npoints, fs, title):
    # initialize variables
    nfs = int(np.log2(npoints))
    f_interp = np.zeros(nfs)
    Spp_i_interp = np.zeros((1024,nfs))
    Spp_q_interp = np.zeros((1024,nfs))
    Spp_interp = np.zeros((1024,nfs))

    # find the power in each detector
    rms_per_det = np.std(I,axis=1) + np.std(Q,axis=1)
    # find the detector with median power
    idet_median = np.argsort(rms_per_det)[int(len(rms_per_det)/2)]
    fig = plt.figure(figsize=(12,8))
    #for idet in range(4,14):
    for idet in range(len(I[:,0])):
        # form the complex signal of this detector
        Z = I[idet,:] + 1j*Q[idet,:]

        # calculate the DC value for this detector
        norm = np.mean(np.abs(Z))

        # take the Welch periodogram (viewer-friendly FFT)
        # of the real and imaginary parts of the signal
        # f,Spp_i=scipy.signal.welch(np.real(Z)/norm,fs=512e6/2**(10+10),nperseg=npoints)
        # f,Spp_q=scipy.signal.welch(np.imag(Z)/norm,fs=512e6/2**(10+10),nperseg=npoints)
        f,Spp_i=scipy.signal.welch(np.real(Z)/norm,fs=fs,nperseg=npoints)
        f,Spp_q=scipy.signal.welch(np.imag(Z)/norm,fs=fs,nperseg=npoints)

        # smooth the curve further for plotting
        for j in range(0,nfs-1):
            f_interp[j] = np.mean(f[2**j:2**(j+1)])
            Spp_i_interp[idet,j] = np.mean(Spp_i[2**j:2**(j+1)])
            Spp_q_interp[idet,j] = np.mean(Spp_q[2**j:2**(j+1)])

        # combine I and Q spectra for plotting
        Spp_interp[idet,:] = (Spp_i_interp[idet,:] + Spp_q_interp[idet,:])/2

        # plot this detector
        plt.semilogx(f_interp[:],10*np.log10(Spp_i_interp[idet,:])[:],"-",color="cyan",alpha=0.2)#,label="All Detectors")
        plt.semilogx(f_interp[:],10*np.log10(Spp_q_interp[idet,:])[:],"-",color="cyan",alpha=0.2)#,label="All Detectors")
        # plot non smoothed data
        # plt.semilogx(f[:],10*np.log10(Spp_i[:])[:],"-",color="blue",alpha=0.04)#,label="All Detectors")
        # plt.semilogx(f[:],10*np.log10(Spp_q[:])[:],"-",color="orange",alpha=0.04)#,label="All Detectors")
        # if we are at the detector with median power
        if idet == idet_median:
            # plot this again, but with a solid black line to highlight it
            plt.semilogx(f_interp[:],10*np.log10(Spp_interp[idet,:])[:],"-",color="black",alpha=1.00,label="Median Detectors", zorder=99999)
    
    # fname = 'OUT/'+file.split('/')[1].split('.')[0]
    #fname = filename
    
    plt.title(title)# 20-900 Channel 2")
    plt.ylabel(r"$S_{\phi \phi}$ [dBc/Hz]", fontsize=16); 
    plt.xlabel("Hz", fontsize=16)
    plt.ylim(-140,-40)
    plt.yticks(np.linspace(-40, -140, 21))
    #plt.yticks(np.linspace(-110, -50, abs(110-50)-1))
    plt.grid()
    # plt.savefig(fname)
    # plt.show()
    # print(fname)
    return fig

@ensure_path(4)
def plot_psd(
        chanmask: npt.NDArray,
        freq: npt.NDArray,
        psd_all: npt.NDArray,
        psd_all_clean: npt.NDArray,
        filename: Path,
        min_percentile: float=16,
        max_percentile: float=84,
        title: str | None=None,
        basis: Literal['pa', 'iq']='pa',
) -> Figure:
    good_chan = np.where(chanmask == 1)[0]
    
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
    plot_data_min = 10 * np.log10(psd_min_clean)
    plot_data_med = 10 * np.log10(psd_med_clean)
    plot_data_max = 10 * np.log10(psd_max_clean)

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


if __name__ == '__main__':
    pairs = [
        # ('equal_0-256', 'RFSoC Loopback with 1000 Tones Over Full Bandwidth'),
        # ('equal_1-255', 'RFSoC Loopback with 1000 Tones in Range +/-[1, 255] MHz'),
        # ('equal_5-251', 'RFSoC Loopback with 1000 Tones in Range +/-[5, 251] MHz'),
        # ('equal_10-246', 'RFSoC Loopback with 1000 Tones in Range +/-[10, 246] MHz'),
        ('default_0-256', 'RFSoC Loopback with Default Tones'),
        # ('default_1-255', 'RFSoC Loopback with Default Tones in Range +/-[1, 255] MHz'),
        # ('default_5-251', 'RFSoC Loopback with Default Tones in Range +/-[5, 251] MHz'),
        # ('default_10-246', 'RFSoC Loopback with Default Tones in Range +/-[10, 246] MHz'),
    ]
    for name, title in pairs:
        input_data, timestamp, chanmask = load_time_ordered_IQ_data(f'data/{name}.hdf5')
        
        # rotated_data = rotate_to_amplitude_and_phase(input_data)
        save_name = f'welch_{name}'
        # Do Cody's stuff with the I/Q data
        compute_noise_psd(
            input_data,
            timestamp,
            chanmask=None,
            ds_factor=3,
            flag_outliers=True,
            nominal_block_length=10,
            outlier_sigma=2,
            cody_file=save_name,
            cody_title=title,
        )
        # chanmask, freq, psd_all, psd_all_clean = compute_noise_psd(
        #     rotated_data,
        #     timestamp,
        #     chanmask=None,
        #     ds_factor=3,
        #     flag_outliers=True,
        #     nominal_block_length=10,
        #     outlier_sigma=2,
        # )
        # figs = plot_psd(chanmask, freq, psd_all, psd_all_clean, f'plots/{save_name}.pdf', basis='pa', title=title)
    # plt.show()

