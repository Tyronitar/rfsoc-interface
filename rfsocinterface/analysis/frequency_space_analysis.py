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
    return freqs, psd, csd

def clean_noise_modes(
    fft: npt.NDArray, 
    eigvecs: npt.NDArray, 
    freqs: npt.NDArray, 
    template_ind: npt.NDArray = None, 
    transfer_mats: npt.NDArray = None,
    pca_limit_idx: int = -1,
) -> npt.NDArray:
    # fft shape: (n_dir, n_chans, n_freqs)
    # eigvecs shape: (n_dir, n_freqs_low, n_template_chans, n_modes)
    # transfer_mats shape: (n_dir, n_freqs_low, n_non_template, n_template)
    
    cleaned_data = fft.copy()
    n_dir, n_chans, n_freqs = cleaned_data.shape
    
    if pca_limit_idx == -1:
        pca_limit_idx = n_freqs

    all_ind = np.arange(n_chans)
    
    for d in range(n_dir):
        if template_ind is not None and transfer_mats is not None:
            non_template_ind = np.setdiff1d(all_ind, template_ind)
            data_template = cleaned_data[d, template_ind, :pca_limit_idx]
            T = transfer_mats[d] 
            
            # Calculate leakage: (freq, non_temp, temp) * (temp, freq) -> (non_temp, freq)
            coupled_noise = np.einsum('fij, jf -> if', T, data_template)
            cleaned_data[d, non_template_ind, :pca_limit_idx] -= coupled_noise

     
        target_ind = template_ind if template_ind is not None else all_ind
        data_to_clean = cleaned_data[d, target_ind, :pca_limit_idx] # (J, F)

        for m in range(eigvecs.shape[-1]):
            mode = eigvecs[d, :pca_limit_idx, :, m] 
        
            coeffs = np.einsum('fi, if -> f', mode.conj(), data_to_clean)
            
            cleaned_data[d, target_ind, :pca_limit_idx] -= (mode.T * coeffs)

    return cleaned_data
def plot_correlation_matrices(freqs: npt.NDArray, csds: npt.NDArray, bound_freqs: npt.NDArray, onres_ind:npt.NDArray = None ):
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
            corr =abs(np.real(corr))
            im = axes[j, i].imshow(
                corr,
                aspect='auto',
                origin='lower',
                cmap='magma',
                vmin=0, vmax=1
            )
            axes[j, i].set_title(f'Freq {bound_freqs[i]:.3f}-{bound_freqs[i+1]:.3f} Hz, Chan {j}')
            axes[j, i].set_xlabel('Detector Index')
            axes[j, i].set_ylabel('Detector Index')
            fig.colorbar(im, ax=axes[j, i], label='Correlation')

    fig.suptitle('Correlation Coefficient Matrices')
    plt.tight_layout()
    fig.savefig("Current_CMatrixPlot.png")
    plt.show()

def rotate_fft(fft:npt.NDArray, rotation_angle:float):
    output_fft = np.zeros_like(fft)
    output_fft[0] = np.cos(rotation_angle)[:, None]*fft[0] + -np.sin(rotation_angle)[:, None]*fft[1]
    output_fft[1] = np.sin(rotation_angle)[:, None]*fft[0] + np.cos(rotation_angle)[:, None]*fft[1]
    return output_fft

def filter_hot_pixels(eigvecs:npt.NDArray,template_ind:npt.NDArray, freqs:npt.NDArray, mask_freq:float, z_max:float = 3, make_plot:bool = False):
    mask = freqs <= mask_freq
    hot_pixels = np.array([])
    n_modes = eigvecs.shape[-1]
    n_dirs = eigvecs.shape[0]
    if make_plot:
        fig, axes = plt.subplots(n_modes, n_dirs, figsize=(4*n_dirs, 3*n_modes))
        axes = np.atleast_2d(axes)
    for m in range(eigvecs.shape[-1]):
        for d in range(eigvecs.shape[0]):
            vec_weight = abs(np.mean(eigvecs[d, mask, :, m], axis = 0))
            vec_z = abs(vec_weight-np.mean(vec_weight))/np.std(vec_weight)
            if make_plot:
                axes[m, d].plot(vec_z)
                axes[m, d].axhline(y=z_max, color='r', linestyle='--', label=f'z_max={z_max}')
                axes[m, d].set_xlabel('Channel Index')
                axes[m, d].set_ylabel('Z-score')
                axes[m, d].set_title(f'Mode {m}, Direction {d}')
                axes[m, d].legend()
        


            hot_pixels = np.append(hot_pixels, np.where(vec_z>z_max)[0])
    if make_plot:
        plt.tight_layout()
        plt.show()
    return hot_pixels

def spectral_pca(csd:np.ndarray):
    eigen_values, v = np.linalg.eig(csd)
    sorted_indices = np.argsort(eigen_values, axis=1)[:, ::-1]
    sorted_eigen_values = np.take_along_axis(eigen_values, sorted_indices, axis=1)
    sorted_v = np.take_along_axis(v, sorted_indices[:, np.newaxis, :], axis=2)
    return sorted_eigen_values, sorted_v[:, :, 0]
        
def whiten_data(Noise:np.ndarray):
    sigma = np.std(Noise, axis = 2, keepdims=True)
    whitened_noise = Noise/sigma
    return whitened_noise


if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    # Lab Testing
    date = '20260212'
    setnums = np.array([1002])
    #setnums = np.array(['1004', '1006', '1007', '1008', '1009', '1010', '1011', '1012', '1013', '1014', '1015', '1016'])
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
    onres_ind = np.where(chanmask == 1)[0]

    probe_freq = pd2.baseband_freqs[:] + pd2.lo_freq

    adc_units_to_hz = pd2.get_node_value('adc_units_to_hz')[:]    
    # Sort it into resonator and nonresonator data. 
    chanmask = pd2.chanmask[0, :]

    onres_ind = np.where(chanmask == 1)[0]
    offres_ind = np.where(chanmask == 0)[0]
    fs = 1 / np.median(np.diff(pd1.timestamp[:]))
    # Sort it into resonator and nonresonator data. 
    sorted_indices = np.argsort(-1*chanmask[:], kind='stable')
    chanmask = chanmask[sorted_indices]

    gp_noise = pd1.get_node_value('data_gain_phase')[0, :] 
    gp_noise = gp_noise[:, offres_ind]

    adc_units_to_hz = adc_units_to_hz[0, sorted_indices]
    pd1.close()
    pd2.close()


    gp_noise = gp_noise-np.mean(gp_noise, axis = 2, keepdims=True)

    whitened_noise = whiten_data(gp_noise)

    fft, scale, n_samples = get_fft(whitened_noise)
    freqs, psd, csd = get_csd_and_psd(fft, scale, fs, n_samples)
    
    # Plot all FFTs
    n_time, n_chans, n_freqs = fft.shape
    bound_freqs = np.array([1])
    bound_freqs_idx = np.searchsorted(freqs, bound_freqs)


    csd_meaned = np.mean(csd[:, :, :, 0:bound_freqs_idx[0]], axis = -1)

    _, top_eigen_vec = spectral_pca(csd_meaned)


    # build single correlated noise template
    correlated_template = np.zeros_like(gp_noise[:, 0, :])
    for d in range(correlated_template.shape[0]):
        for n in range(n_chans):
            correlated_template[d] +=  gp_noise[d, n] * np.real(top_eigen_vec[d, n])
    
    # Plot the FFT of the correlated template and one gp_noise channel
    fft_template = np.fft.rfft(correlated_template, axis = -1)
    fft_gp_noise, _, _ = get_fft(gp_noise)

    numerator = np.einsum('il, ikl-> ik', correlated_template, gp_noise)
    denominator = np.einsum('ij,ij->i', correlated_template, correlated_template)

    corr = numerator/denominator[:, None]

    cleaned_noise =gp_noise- np.einsum('ij,ik->ijk', corr, correlated_template)
    fft_cleaned_noise, _, _ = get_fft(cleaned_noise)

    pdb.set_trace()
    plt.figure(figsize=(12, 6))
    plt.loglog(freqs, np.abs(fft_template[0, :]), label='Correlated Template', linewidth=2)
    for i in range(5):
        plt.loglog(freqs, np.abs(fft_gp_noise[0, i, :]), label='GP Noise Channel 0', linewidth=2, alpha=0.7)
        plt.loglog(freqs, np.abs(fft_cleaned_noise[0, i, :]), label='Clean Noise Channel 0', linewidth=2, alpha=0.7)

    plt.xlabel('Frequency (Hz)')
    plt.ylabel('FFT Magnitude')
    plt.title('FFT: Correlated Noise Template vs GP Noise Channel')
    plt.legend()
    plt.grid(True, which='both', alpha=0.3)
    plt.tight_layout()
    plt.show()

    pdb.set_trace()

    
