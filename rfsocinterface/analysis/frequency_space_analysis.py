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
    bound_freqs: npt.NDArray,
    n_tones: int = 100,
    max_modes: int = 10,
    template_ind: npt.NDArray = None,
) -> tuple[list[npt.NDArray], list[npt.NDArray]]:

    n_freqs_total = len(freqs)
    n_bound = len(bound_freqs)

    freq_indices = np.searchsorted(freqs, bound_freqs)
    freq_indices = np.clip(freq_indices, 0, n_freqs_total)

    eigvals_all = []
    eigvecs_all = []
    transfer_all = []

    for i in range(n_bound - 1):
        band_csds = csds[:, :, :, freq_indices[i]:freq_indices[i+1]]

        if template_ind is not None:
            # Compute modes only from template (off-resonance) channels
            ind_list = np.arange(band_csds.shape[1])
            non_template_ind = np.setdiff1d(ind_list, template_ind)

            band_csds_template = band_csds[:, template_ind, :, :][ :, :, template_ind, :]
            C = np.mean(band_csds_template, axis=(0, 3))  
            print(C.shape)
        else:
            C = np.mean(band_csds, axis=(0, 3))           # (n_chans, n_chans)

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

        n_modes = 2
        n_modes = min(n_modes, max_modes)
        print(f'Using {n_modes} eigen modes in band {i}')

        # Compute transfer matrix from template to non-template channels
        if template_ind is not None:
            band_csds_cross = band_csds[:, non_template_ind, :, :][:, :, template_ind, :]  
            print(band_csds_cross.shape)          
            H = np.mean(band_csds_cross, axis=(0, 3))
            print(H.shape)
            transfer_all.append(H)

        eigvals_all.append(eigvals[:n_modes])
        eigvecs_all.append(eigvecs[:, :n_modes])

    result = (np.array(eigvals_all).T, np.array(eigvecs_all))
    if template_ind is not None:
        result = result + (np.array(transfer_all),)

    return result

def rotate_fft(fft:npt.NDArray, rotation_angle:float):
    output_fft = np.zeros_like(fft)
    output_fft[0] = np.cos(rotation_angle)[:, None]*fft[0] + np.sin(rotation_angle)[:, None]*fft[1]
    output_fft[1] = np.sin(-rotation_angle)[:, None]*fft[0] + np.cos(rotation_angle)[:, None]*fft[1]
    return output_fft

def clean_noise_modes(fft: npt.NDArray, eigvecs: npt.NDArray, freqs: npt.NDArray, bound_freqs: npt.NDArray, template_ind:npt.NDArray = None, transfer_mat:npt.NDArray = None, ) -> npt.NDArray:
    # Project out the noise modes
    uncleaned_data = fft[0] + 1j * fft[1]
    n_freqs_total = len(freqs)
    cleaned_data = uncleaned_data.copy()
    # Convert frequency bounds to indices
    freq_indices = np.searchsorted(freqs, bound_freqs)
    freq_indices = np.clip(freq_indices, 0, n_freqs_total-1)
    print(freqs[freq_indices])
    n_bound = len(bound_freqs)
    ind_list = np.arange(cleaned_data.shape[0])
    non_template_ind = np.setdiff1d(ind_list, template_ind)
    for j in range(eigvecs.shape[-1]):
        for i in range(n_bound - 1):
            f_slice = slice(freq_indices[i], freq_indices[i+1])
            if template_ind is None:
                data_band = cleaned_data[:, f_slice]  # (n_channels, n_freqs_in_band)
                mode = eigvecs[i, :,j]  # (n_channels,)
                coeffs = mode.conj() @ data_band
                cleaned_data[:, f_slice] -= np.outer(mode[:], coeffs)
            else:
                data_band_template = cleaned_data[template_ind, f_slice]  # (n_channels, n_freqs_in_band)
                mode = eigvecs[i, :,j]  # (n_channels,)
                coeffs = mode.conj() @ data_band_template
                cleaned_data[template_ind, f_slice] -= np.outer(mode[:], coeffs)
                t_mat = transfer_mat[i]
                coupling = t_mat@mode
                coupled_noise = np.outer(coupling, coeffs)
                #cleaned_data[non_template_ind, f_slice] -= coupled_noise

           
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

if __name__ == '__main__':
    import pdb
    import matplotlib.pyplot as plt
    # Lab Testing
    date = '20260212'
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
    onres_ind = np.where(chanmask == 1)[0]
    offres_ind = np.where(chanmask == 0)[0]
    gain_phase_to_freq_diss_angle = -1*pd1.get_node_value('IQ_to_gain_phase_angle')[:]+pd1.get_node_value('IQ_to_freq_diss_angle')[:]
    fs = 1 / np.median(np.diff(pd1.timestamp[:]))

    bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])
    cleaning_bound_freqs = bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])


    gp_noise = pd1.get_node_value('data_gain_phase')[:]/ pd1.carrier_amplitude_norm()
   # gp_noise = np.concatenate((gp_noise[:, onres_ind], gp_noise[:, offres_ind]), axis=1)
    fft, scale, n_samples = get_fft(gp_noise)
    
   
    from psd import plot_psd
    #plot_psd(freqs, psd, f'noise_gain_phase_{date}_set{setnums[-1]}.pdf', basis=PsdBasis.GAIN_PHASE)
    freqs, psd, csd = get_csd_and_psd(fft, scale, fs, n_samples)




    
    bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])
    cleaning_bound_freqs = bound_freqs=np.array([0.01, 0.1, 1.0, 10.0, 100, fs/2])
    plot_correlation_matrices(freqs, csd, bound_freqs)
    eigvals, eigvecs, transfer_mat = spectral_pca(csd, freqs,bound_freqs = cleaning_bound_freqs, template_ind=offres_ind)
    clean_fft = clean_noise_modes(fft, eigvecs, freqs, cleaning_bound_freqs, template_ind = offres_ind, transfer_mat = transfer_mat)
    freqs, psd, csd = get_csd_and_psd(clean_fft, scale, fs, n_samples)
    plot_correlation_matrices(freqs, csd, bound_freqs)
    fft = clean_fft
    plot_psd(freqs, psd, f'noise_gain_phase_{date}_set{setnums[-1]}.pdf', basis=PsdBasis.GAIN_PHASE)
