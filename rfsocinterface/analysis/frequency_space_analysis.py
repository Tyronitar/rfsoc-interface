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

    
def spectral_pca(
    csds: npt.NDArray,
    freqs: npt.NDArray,
    n_tones: int = 100,
    max_modes: int = 3,
    freq_limit:float = 30,
    template_ind: npt.NDArray = None,
) -> tuple:
    # csds shape: (n_dir, n_chans, n_chans, n_freqs)
    n_dir, n_chans, _, n_freqs = csds.shape
    f_mask = freqs <= freq_limit
    n_freqs_low = np.sum(f_mask)
       
    # We now pre-allocate for every individual frequency
    eigvals_all = np.zeros((n_dir, n_freqs_low, max_modes))
    eigvecs_all = np.zeros((n_dir, n_freqs_low, len(template_ind) if template_ind is not None else n_chans, max_modes), dtype=complex)
    
    transfer_all = [] # List used because non_template_ind size varies if template_ind changes
    
    all_ind = np.arange(n_chans)
    non_template_ind = np.setdiff1d(all_ind, template_ind) if template_ind is not None else []
    dir_transfer = None
    for d in range(n_dir):
        for f in range(n_freqs_low):
            C = csds[d, :, :, f] # CSD matrix for one specific frequency
            
            if template_ind is not None:
                dir_transfer = np.zeros((n_freqs_low, len(non_template_ind), len(template_ind)), dtype=complex)

                C_template = C[template_ind, :][:, template_ind]
                eigvals, eigvecs = np.linalg.eigh(C_template)
                
                cross_C = C[non_template_ind, :][:, template_ind]
                dir_transfer[f] = cross_C @ np.linalg.inv(C_template)
            else:
                eigvals, eigvecs = np.linalg.eigh(C)

            # Sort and truncate modes
            idx = np.argsort(np.abs(eigvals))[::-1]
            n_modes = max_modes
            eigvals_all[d, f, :n_modes] = eigvals[idx][:n_modes]
            eigvecs_all[d, f, :, :n_modes] = eigvecs[:, idx][:, :n_modes]
            
        transfer_all.append(dir_transfer)

    return eigvals_all, eigvecs_all, np.array(transfer_all), n_freqs_low

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
            
            # Reconstruct and subtract: (J, F) - (J, F)
            # mode.T is (J, F), coeffs is (F) -> broadcasting works
            cleaned_data[d, target_ind, :pca_limit_idx] -= (mode.T * coeffs)

    return cleaned_data
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
            corr =(np.real(corr))
            im = axes[j, i].imshow(
                corr,
                aspect='auto',
                origin='lower',
                cmap='viridis',
                vmin=-1, vmax=1
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
    output_fft[0] = np.cos(rotation_angle)[:, None]*fft[0] + np.sin(-rotation_angle)[:, None]*fft[1]
    output_fft[1] = np.sin(rotation_angle)[:, None]*fft[0] + np.cos(rotation_angle)[:, None]*fft[1]
    return output_fft
def run_multi_run_dataset(date:str, setnums:np.ndarray) -> tuple:
    psd_sum = None
    count = 0
    max_freq = 200
    import rfsocinterface.core.data.pipeline as pipeline
    from rfsocinterface.core.data.pipeline import DataPipeline


    for setnum in setnums:
        print(f'Running pipeline for {date} set {setnum}')
        
        pipeline = DataPipeline(
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
        pd2, pd1 = pipeline.run_pipeline(date, setnum, output_pd1=True)        
        adc_units_to_hz = pd2.get_node_value('adc_units_to_hz')[:]
        gain_phase_to_freq_diss_angle = -1*pd1.get_node_value('IQ_to_gain_phase_angle')[:]+pd1.get_node_value('IQ_to_freq_diss_angle')[:]
        
        # Sort it into resonator and nonresonator data. 
        chanmask = pd2.chanmask[:]

        onres_ind = np.where(chanmask == 1)[0]
        offres_ind = np.where(chanmask == 0)[0]
        chanmask = pd2.chanmask[:]
        fs = 1 / np.median(np.diff(pd1.timestamp[:]))



     
        #FFT in Gain/Phase space
        gp_noise = pd1.get_node_value('data_gain_phase')[:] / (pd1.carrier_amplitude_norm() * adc_units_to_hz[None, :, None])
        fft, scale, n_samples = get_fft(gp_noise)
        freqs = np.fft.rfftfreq(n_samples, 1/fs)
        low_f_mask = freqs <= 30


        #Limit our fft to the low frequencies, and calculate csd
        fft_low = fft[:, :, low_f_mask]
        csd_off = np.einsum('ijk, ilk-> iljk', fft_low, np.conj(fft_low)) / scale

        #plot_correlation_matrices(freqs, csd_off, bound_freqs=np.array([0.01, 0.1, 1, 10, 100]))
        
        # Calculate and apply off-res cleaning across entire array
        _, eigvecs, transfer_mat, n_low = spectral_pca(csd_off, freqs[low_f_mask], template_ind=offres_ind, max_modes=5)
        fft = clean_noise_modes(fft, eigvecs, freqs, template_ind=offres_ind, transfer_mats=transfer_mat, pca_limit_idx=n_low)
        
        #Restrict our data to only the on resonance channels

        low_f_mask = freqs <= 30

        fft_on_low = fft[:, :, :][:, :, low_f_mask]
        csd_on = np.einsum('ijk, ilk-> iljk', fft_on_low, np.conj(fft_on_low)) / scale
        #plot_correlation_matrices(freqs, csd_on, bound_freqs=np.array([0.01, 0.1, 1, 10, 100]))

        fft_on_low = fft[:, onres_ind, :][:, :, low_f_mask]
        csd_on = np.einsum('ijk, ilk-> iljk', fft_on_low, np.conj(fft_on_low)) / scale

        #plot_correlation_matrices(freqs, csd_on, bound_freqs=np.array([0.01, 0.1, 1, 10, 100]))

        
        _, eigvecs, _ , _ = spectral_pca(csd_on, freqs[low_f_mask], template_ind=None, max_modes=1) #Only Clean Lowest Frequency Modes
        fft = clean_noise_modes(fft[:, onres_ind, :], eigvecs, freqs, template_ind=None, transfer_mats=None, pca_limit_idx=n_low)

        fft_fd = rotate_fft(fft, gain_phase_to_freq_diss_angle[onres_ind])
        freqs, psd, csd_fd = get_csd_and_psd(fft_fd, scale, fs, n_samples)
        
        #plot_correlation_matrices(freqs, csd_fd, bound_freqs=np.array([0.01, 0.1, 1, 10, 100]))


        if psd_sum is None:
            data_indices = np.where(freqs < max_freq)[0]
            psd_sum = np.zeros_like(psd[:, :, data_indices])
            
        psd_sum += psd[:, :, data_indices]
        count += 1
        
        pd1.close(); pd2.close()
        del csd_off, csd_on, fft, fft_fd, csd_fd
    
    return psd_sum / count, freqs[data_indices]

if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    # Lab Testing
    date = '20260212'
    #setnums = np.array(['1002'])
    #High Quality Dataset, miniC = [2.5, 0] No 30dB Warm Amp
    #date = '20260212'
    setnums = np.array([1001, 1002, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011])
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
    pd1.close()
    pd2.close()
    psds,freqs= run_multi_run_dataset(date, setnums)
    from psd import plot_psd
    plot_psd(freqs, psds, f'noise_freq_dis_{date}_set{setnums[-1]}.pdf',f0 = probe_freq[onres_ind],adc_units_to_hz =  adc_units_to_hz, basis=PsdBasis.FREQ_DISS, csd = None)
    #plot_correlation_matrices(freqs, csds=csd, bound_freqs=bound_freqs)
    print(psds)