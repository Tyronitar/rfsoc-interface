import rfsocinterface.core.data.pipeline as pipeline
from rfsocinterface.core.data.pipeline import ComputeNoisePSD
from rfsocinterface.core.data.pipeline import PsdBasis
import numpy.typing as npt
import numpy as np
import scipy.signal as signal
from scipy.signal import get_window
from numpy.lib.stride_tricks import sliding_window_view
import matplotlib.pyplot as plt

def get_fft(time_stream:npt.NDArray):
    time_stream = time_stream - np.mean(time_stream, axis=-1, keepdims=True)
    n_samples = time_stream.shape[2]
    window = get_window('hann', n_samples)
    scale = np.sum(window**2)
    windowed_data = time_stream * window[None, None, :]
    fft = np.fft.rfft(windowed_data, axis=-1)
    return fft, scale, n_samples
def get_csd_and_psd(fft, scale, fs, n_samples):
    psd = np.abs(fft)**2 / (scale * fs)
    csd = np.einsum('ijk, ilk-> iljk', fft, np.conj(fft))/(scale)
    freqs = np.fft.rfftfreq(n_samples, 1/fs)
    print(csd.shape)
    return freqs, psd, csd

    
def spectral_pca(csds: npt.NDArray, freqs: npt.NDArray,bound_freqs: npt.NDArray,n_tones: int = 100, max_modes: int = 10,
                 ) -> tuple[list[npt.NDArray], list[npt.NDArray]]:

    n_chans = csds.shape[0]
    n_dir = csds.shape[1]
    n_freqs_total = len(freqs)
    n_bound = len(bound_freqs)

    # Convert frequency bounds to indices
    freq_indices = np.searchsorted(freqs, bound_freqs)
    freq_indices = np.clip(freq_indices, 0, n_freqs_total)

    eigvals_all = []
    eigvecs_all = []

    for i in range(n_bound-1):
        # Slice the frequency band
        band_csds = csds[:, :, :, freq_indices[i]:freq_indices[i+1]]  # shape: (n_chans, n_dir, n_chans, n_freq_slice)
        
        # Average over directions and frequencies in the bin
        C = np.mean(band_csds[0], axis=(2))+1j*np.mean(band_csds[1], axis=(2))  # shape: (n_chans, n_chans)
        # C[i,j] = average cross-spectrum magnitude
        # shape: (n_dir, n_chan, n_chan, n_freq_slice)
        #print(i)
        # Average only over frequency
        #C= np.mean(band_csds, axis=2)
        # shape: (n_dir, n_chan, n_chan)

        eigvals, eigvecs = np.linalg.eigh(C)

        idx = np.argsort(np.abs(eigvals))[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]
        if n_tones < 25:
                sigma_mult = 1.5
        elif n_tones < 50:
            sigma_mult = 2.5
        else:
            sigma_mult = 3

        n_modes = 1
        #new_modes = -1
        #while new_modes != 0 and n_modes <= max_modes:
        #    log_eigen_values = np.log10(eigvals[n_modes:])
        #    mu = np.mean(log_eigen_values)
        #    sigma = np.std(log_eigen_values)
        #    large_eigen_values = np.where(log_eigen_values > (mu + sigma_mult * sigma))
        #    i_count = large_eigen_values[0].size - np.sum(large_eigen_values[0])
        #    q_count = large_eigen_values[0].size - i_count
        #    new_modes = max(i_count, q_count)
        #    n_modes += new_modes
        eigvals_all.append(eigvals[:n_modes])
        eigvecs_all.append(eigvecs[:, :n_modes])
    # pdb.set_trace()
        n_modes = min(n_modes, max_modes)
    print(f'Using {n_modes} eigen modes')



    return np.array(eigvals_all).T, np.array(eigvecs_all)

def clean_noise_modes(fft: npt.NDArray, eigvecs: npt.NDArray, freqs: npt.NDArray, bound_freqs: npt.NDArray, correlation_threshold: float = 0.0) -> npt.NDArray:
    # Project out the noise modes
    uncleaned_data = fft[0] + 1j * fft[1]
    n = len(uncleaned_data)
    n_freqs_total = len(freqs)

    cleaned_data = uncleaned_data.copy()
    # Convert frequency bounds to indices
    freq_indices = np.searchsorted(freqs, bound_freqs)
    freq_indices = np.clip(freq_indices, 0, n_freqs_total-1)
    print(freqs[freq_indices])
    n_bound = len(bound_freqs)
    for i in range(n_bound - 1):
        f_slice = slice(freq_indices[i], freq_indices[i+1])
        data_band = cleaned_data[:, f_slice]  # (n_channels, n_freqs_in_band)

        for j in range(eigvecs.shape[-1]):
            mode = eigvecs[i, :, j]  # (n_channels,)
            mode_projection = mode.conj() @ data_band          # (n_freqs_in_band,)
            mode_power = np.abs(mode_projection)**2

            channel_power = np.sum(np.abs(data_band)**2, axis=1)  # (n_channels,)
            total_mode_power = np.sum(mode_power)

            corr = np.abs(mode.conj() * (data_band @ mode_projection.conj()))
            corr /= np.sqrt(channel_power * total_mode_power + 1e-30)  # avoid div by zero
            print(corr)
            correlated_channels = corr > correlation_threshold  
            print(f"Mode {j}, band {i}: {correlated_channels.sum()} correlated channels")

            coeffs = mode.conj() @ data_band
            cleaned_data[correlated_channels, f_slice] -= np.outer(
                mode[correlated_channels], coeffs
            )

    return np.array([np.real(cleaned_data), np.imag(cleaned_data)])

def plot_correlation_matrices(freqs: npt.NDArray, csds: npt.NDArray, bound_freqs: npt.NDArray ):
    n_chans = csds.shape[0]
    n_dir = csds.shape[1]
    n_freqs_total = csds.shape[-1]

    # Convert frequency bounds to indices
    freq_indices = np.searchsorted(freqs, bound_freqs)
    freq_indices = np.clip(freq_indices, 0, n_freqs_total)

    n_bound = len(bound_freqs)
    fig, axes = plt.subplots(n_chans, n_bound-1, figsize=(6*(n_bound-1), 5))
    axes = np.atleast_2d(axes)  # safe indexing

    for i in range(n_bound-1):
        # Slice the frequency band
        band_csds = csds[:, :, :, freq_indices[i]:freq_indices[i+1]]  # shape: (n_chans, n_dir, n_chans, n_freq_slice)
        
        # Average over directions and frequencies in the bin
        C = np.mean(band_csds, axis=(3))  # shape: (n_chans, n_chans)
        # C[i,j] = average cross-spectrum magnitude



        # Plot each channel
        for j in range(n_chans):
            # Normalize to correlation coefficient
            diag = np.sqrt(np.diag(C[j]))          # sqrt(C_ii)
            corr = C[j] / (diag[:, None] * diag[None, :])
            # Ensure values are real (CSD can be complex)
            corr = abs(np.real(corr))
            im = axes[j, i].imshow(
                corr,
                aspect='auto',
                origin='lower',
                cmap='viridis',
                #vmin=0, vmax=1
            )
            axes[j, i].set_title(f'Freq {bound_freqs[i]:.3f}-{bound_freqs[i+1]:.3f} Hz, Chan {j}')
            axes[j, i].set_xlabel('Detector Index')
            axes[j, i].set_ylabel('Detector Index')
            fig.colorbar(im, ax=axes[j, i], label='Correlation')

    fig.suptitle('Correlation Coefficient Matrices')
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    # Lab Testing
    date = '20260224'
    setnums = np.array(['1002'])
    #High Quality Dataset, miniC = [2.5, 0] No 30dB Warm Amp
    #date = '20260212'
    #setnums = np.array([1001, 1002, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011])
    #Good Dataset, miniC = [0.5, 0] No 30dB Warm Amp #Not compensated for increase in output power, so may be wrong
    #date = '20260212'
    #setnums = np.array([1012, 1013, 1014, 1015, 1016, 1017, 1018, 1019, 1020, 1021])
    #High Quality Dataset, miniC = [8.5, 0] with Rf_in at 9 db to compensate on input power
    #date = '20260212'
    #setnums = np.array([1023, 1024, 1025, 1026, 1027, 1028, 1029, 1030, 1031, 1032])
    # date = '20250829'
    # setnum = 1012

    #Telescope Testing
    # date = '20251211'
    # setnum = 1003

    dataset = 'data_freq'
    beam_map_mode = False 
    do_electronics_noise_removal = False
    do_cr_removal = True
    primary_direction = 'az'

    ds_factor = 1
    lp_filt_freq = 500
    block_length = 100
    hp_filt_freq = 1/block_length


    hpfilt = pipeline.HighPassFilter(hp_filt_freq)
    lpfilt = pipeline.LowPassFilter(lp_filt_freq)
    cleaner = pipeline.CleanTOD()
    binner = pipeline.BinTODIntoMap()
    pipeline = pipeline.DataPipeline(
        ds_factor=ds_factor,
        hp_filter_freq=hp_filt_freq,
        lp_filter_freq=lp_filt_freq,
        dataset=dataset,
        beam_map_mode=beam_map_mode,
        do_electronics_noise_removal= do_electronics_noise_removal,
        block_length = block_length,
        do_cr_removal = do_cr_removal,
        max_modes=10
    )
    psd = ComputeNoisePSD(PsdBasis.GAIN_PHASE, PsdBasis.FREQ_DISS, tone_indices=None, nominal_block_length=block_length)
    pipeline.add_routine(psd)
    pipeline.add_routine(cleaner)
    
    pd2, pd1 = pipeline.run_pipeline(date, setnums[-1], output_pd1=True)
    freq = pd2.get_node_value('freq')[:]
    adc_units_to_hz = pd2.get_node_value('adc_units_to_hz')[:]
    chanmask = pd2.chanmask[:]
    probe_freq = pd2.baseband_freqs[:] + pd2.lo_freq

    # Sort it into resonator and nonresonator data. 
    sorted_indices = np.argsort(-1*chanmask[:], kind='stable')
    #chanmask = chanmask[sorted_indices]
    probe_freq = probe_freq[sorted_indices]
    adc_units_to_hz = adc_units_to_hz[sorted_indices]
    onres_ind = np.where(chanmask == 1)[0]
    offres_ind = np.where(chanmask == 0)[0]





    gp_noise = pd1.get_node_value('data_gain_phase')[:]/ pd1.carrier_amplitude_norm()
    gp_noise = np.concatenate((gp_noise[:, onres_ind], gp_noise[:, offres_ind]), axis=1)
    fs = 1 / np.median(np.diff(pd1.timestamp[:]))
    fft, scale, n_samples = get_fft(gp_noise)
    freqs, psd, csd = get_csd_and_psd(fft, scale, fs, n_samples)
    bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])
    cleaning_bound_freqs = bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])
    plot_correlation_matrices(freqs, csd, bound_freqs)
    from psd import plot_psd
    plot_psd(freqs, psd, f'noise_gain_phase_{date}_set{setnums[-1]}.pdf', basis=PsdBasis.GAIN_PHASE)
    eigvals, eigvecs = spectral_pca(csd, freqs,bound_freqs = cleaning_bound_freqs)
    print(fft.shape)
    print(eigvecs.shape)
    clean_fft = fft.copy()
    clean_fft[:, :] = clean_noise_modes(fft, eigvecs, freqs,  cleaning_bound_freqs)
    freqs, psd_clean, csd_clean = get_csd_and_psd(clean_fft, scale, fs, n_samples)
    plot_correlation_matrices(freqs, csd_clean, bound_freqs)
    plot_psd(freqs, psd_clean, f'noise_gain_phase_clean_{date}_set{setnums[-1]}.pdf', basis=PsdBasis.GAIN_PHASE)
