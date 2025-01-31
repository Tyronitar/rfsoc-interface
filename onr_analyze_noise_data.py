#JS - a simple routine to compute noise spectra and plot the results

import numpy as np
import sys, os
import matplotlib.pyplot as plt
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
from scipy.optimize import curve_fit
import pdb
import h5py

def reject_outliers(data,sigma=2):
  keepgoing = 1
  good_ind = np.arange(np.size(data))
  while keepgoing:
    valid = np.where(abs(data[good_ind] - np.median(data[good_ind])) < sigma * np.std(data[good_ind]))
    if np.size(valid) == np.size(good_ind):
      keepgoing = 0
    else:
      good_ind = good_ind[valid]
  return data[good_ind], good_ind

def tls_fit(freq, white_amp, tls_amp):
  return white_amp**2 + tls_amp**2 / freq**(0.5)

def butter_lowpass(f0, fsample, order=5):
  nyq = 0.5 * fsample
  norm_cutoff = f0 / nyq
  b, a = signal.butter(order, norm_cutoff, btype='low', analog=False)
  return b, a

def butter_lowpass_filter(data, f0, fsample, order=5):
  b, a = butter_lowpass(f0, fsample, order=order)
  out_data = signal.filtfilt(b, a, data)
  return out_data

def main(date, setnum, device, optical_tload=300., file_type='processed', internal_power = 1, T_bath = 0.2, plot_flag = True,outlier_test=True,no_blocks=False):

  #get the resonator parameters
  parameter_file = f"/home/onrkids/onrkidpy/params/{device}_optical_temperature_sweep_fits.npy"
  fit_params = np.load(parameter_file,allow_pickle=True,encoding='bytes').item()
  big_c = fit_params[b'big_c']

  #define some constants and optical parameters
  nu0 = 150.e9 #based on FTS
  dnu = 30.e9 #based on assumed dnu for hot/cold
  kb = 1.38e-23
  h = 6.63e-34
  L_thick = 4.e-2
  eta_phon = 0.6
  eta_opt = (big_c * L_thick) / (eta_phon * dnu)
  Delta = 0.18*1.e-3*1.6e-19 #W/Hz, Aluminum
  
  #get optical efficiency and excess load
  T_exc = fit_params[b'T_exc']
  eta_opt = eta_opt[:,0]
  valid_eta_opt = np.ndarray.flatten(np.argwhere(np.logical_and(eta_opt > 0,eta_opt < 1)))
  eta_opt = eta_opt[valid_eta_opt]
  T_exc = T_exc[:,0]
  valid_T_exc = np.ndarray.flatten(np.argwhere(np.logical_and(T_exc > 0,T_exc < 1.e3)))
  T_exc = T_exc[valid_T_exc]
  dummy, good_index = reject_outliers(eta_opt)
  typical_eta = np.median(eta_opt[good_index])
  typical_eta_std = np.std(eta_opt[good_index])
  dummy, good_index = reject_outliers(T_exc)
  typical_excess_tload = np.median(T_exc[good_index])
  typical_excess_tload_std = np.std(T_exc[good_index])

  #make some reasonable guesses to determine the thermal noise level
  q_opt = typical_eta * kb * optical_tload * dnu
  q_opt_std = typical_eta_std * kb * optical_tload * dnu
  q_exc = typical_eta * kb * typical_excess_tload * dnu
  q_exc_std = np.sqrt( (typical_eta * kb * typical_excess_tload_std * dnu)**2 + (typical_eta_std * kb * typical_excess_tload * dnu)**2)
  q_tot = q_opt + q_exc
  q_tot_std = np.sqrt(q_opt_std**2 + q_exc_std**2)
#  NEP_q = np.sqrt(2.*q_tot*h*nu0 + 2.*q_tot**2./dnu)
# find that things don't work out very well if the excess load is included, and so remove it for now
  NEP_q = np.sqrt(2.*q_opt*h*nu0 + 2.*q_opt**2./dnu)
  NEP_q_std = q_tot_std / (2. * NEP_q) * (2.*h*nu0 + 4.*q_tot/dnu)
  dqdT = typical_eta * kb * dnu * 1.e-3 #units of mK
  dqdT_std = typical_eta_std * kb * dnu * 1.e-3
  NET_mK = NEP_q / dqdT
  NET_mK_std = np.sqrt( (NEP_q_std / dqdT)**2. + (NEP_q / dqdT**2 * dqdT_std)**2.) / np.sqrt(2.)
  #errors on NET_mK and NET_gr are highly correlated, and so should not be added
  #as random. It should be approximately correct to just divide each by 2.

  #now estimate GR noise
  NEP_gr = np.sqrt(4. * Delta * q_tot / eta_phon)
  NEP_gr_std = np.sqrt(4. * Delta * q_tot_std / eta_phon)
  NET_gr = NEP_gr / dqdT
  NET_gr_std = np.sqrt( (NEP_gr_std / dqdT)**2. + (NEP_gr / dqdT**2 * dqdT_std)**2.) / np.sqrt(2.)

  #get all the data from the file
  input_file = f"/data/{date}/{date}_{file_type}_data_set{setnum}.h5"
  f = h5py.File(input_file, 'r')
  data_raw = f['data_mK'][()]
#  data_raw = f['data_diss'][()]
  chanmask = f['chanmask'][()]
  time = f['timestamp'][()]
  time = time - time[0]
  dI_df = f['dI_df'][()]
  dQ_df = f['dQ_df'][()]
  df_per_mK = f['df_per_mK'][()]

  ds_factor=1
  if ds_factor != 1:
    new_data_raw = np.zeros([np.size(chanmask), np.size(signal.decimate(data_raw[0,:],ds_factor))])
    n_flag = np.zeros(np.size(chanmask))
    n_sample_ds = np.size(new_data_raw[0,:])
    fs = float(1./ ((time[1]-time[0]) * ds_factor))
    filt_cut = 1. / (0.5 * fs)
    b, a = signal.butter(5, filt_cut, btype='high', analog=False)
    for i_res in range(np.size(chanmask)):
      new_data_raw[i_res,:] = signal.decimate(data_raw[i_res,:],ds_factor)
      this_hpf_data = signal.filtfilt(b, a, new_data_raw[i_res,:])
      dummy, _ = reject_outliers(this_hpf_data,sigma=4)
      n_flag[i_res] = np.size(this_hpf_data) - np.size(dummy)
    data_raw = new_data_raw
    goodchan = np.where(chanmask == 1)
    med_flag = np.median(n_flag[goodchan])
    chanmask[np.where(n_flag > 2.*med_flag)] = -1
    time = signal.decimate(time,ds_factor)

  if date == 20240405:
    input_file = f"/data/20240812/20240812_processed_data_set1001.h5"
    dI_df = f['dI_df'][()]
    dQ_df = f['dQ_df'][()]
    df_per_mK = f['df_per_mK'][()]
  if date == 20240822:
    data_raw = data_raw * 1.05
    if setnum == 1011:
      data_raw = data_raw / 1.2 # account for change in responsivity due to loading
  if date == 20240408:
    data_raw = data_raw * 2. # data miscalibration
  if date == 20241011:
    data_raw = data_raw * 1.9
  if date == 20241021:
    if setnum == 1021:
      data_raw = data_raw * .8 #did not set the power level correctly...
    if setnum == 1014:
      data_raw = data_raw * .9 #did not set the power level correctly..
    if setnum == 1010:
      data_raw = data_raw * .8 #account for change in calibration looking at zenith with lower loading
    if setnum == 1012:
      data_raw = data_raw * 1.7 #account for change in response due to moving off resonance with warmup


  #get the rfsoc file, which will be needed later
  input_file2 = f"/data/{date}/{date}_rfsoc2_TOD_set{setnum}.h5"
  f2 = h5py.File(input_file2, 'r')
  df_over_f = f2['global_data/dfoverf_per_mK'][()]
  bb_freq = f2['global_data/baseband_freqs'][()]
  lo_freq = f2['global_data/lo_freq'][()]
  f0 = bb_freq + lo_freq[0]

  fs = 1./(time[1]-time[0])
  n_samples = np.size(data_raw[0,:])
  if no_blocks:
    n_to_cut_at_start_end = 0
    n_samples_final = n_samples
    n_samples_per_block = n_samples
    n_blocks = 1

  else:
    #data can be glitchy at start/end of trace, and should be cut
    cut_time = 1.
    n_to_cut_at_start_end = int(np.size(np.argwhere(time < cut_time)))
    n_samples_final = n_samples - n_to_cut_at_start_end * 2

    #get the sampling frequency and make a window that can be
    #used later for the power spectrum computation
    nominal_length = 10. #in seconds
    n_samples_per_block = int(2**np.ceil(np.log2(nominal_length * fs)))
    n_blocks = int(np.floor(float(n_samples_final)/float(n_samples_per_block)))
  data_raw = data_raw[:,n_to_cut_at_start_end:-n_to_cut_at_start_end:]
  time = time[n_to_cut_at_start_end:-n_to_cut_at_start_end:]
  time = time - time[0]

  wind = signal.get_window('hamming', n_samples_per_block)

  #what frequencies to use for white noise
  white_noise_min = 3. #in Hz
  white_noise_max = 10. #in Hz
  offres_white_noise_min = 3. #in Hz
  offres_white_noise_max = 100. #in Hz
  tls_noise_min = 3.
  tls_noise_max = 10.

  #define where the pickup lines from the GM are
#  lines = (np.arange(20)+1.) * 1.152
#  lines = (np.arange(2)+1.) * 1.55
#  lines = (np.arange(15)+1.) * 1.2
  lines = [25.]

  #loop over resonators, grabbing I and Q data and interpolating to
  #regular time grid
  pdf_file_name =   input_file = f"/data/{date}/{date}_{file_type}_data_set{setnum}_noise_plots.pdf"
  with PdfPages(pdf_file_name) as pdf:

    n_chan = np.size(chanmask)
    psd_white = np.zeros(n_chan)
    psd_elec = np.zeros(n_chan)
    psd_tls = np.zeros(n_chan)
    psd_all = np.zeros((n_chan, int(n_samples_per_block / 2 + 1)))
    psd_all_clean = np.zeros((n_chan, int(n_samples_per_block / 2 + 1)))

    #start with the off resonance tones
    chanmask2 = f2['global_data/chanmask'][()]
    offres = np.ndarray.flatten(np.argwhere(chanmask2 == 0))
    chanmask[offres] = 0
    print(f0[offres])
    n_offres = np.size(offres)
    psd_all_phase = np.zeros((n_chan, int(n_samples_per_block / 2 + 1)))
    psd_all_gain = np.zeros((n_chan, int(n_samples_per_block / 2 + 1)))
    white_dBc = np.zeros(n_chan)
    phase_white_all = np.zeros(n_chan)
    data_I = f2['time_ordered_data/adc_i'][()]
    data_Q = f2['time_ordered_data/adc_q'][()]
    data_I = data_I[:,n_to_cut_at_start_end:-n_to_cut_at_start_end:]
    data_Q = data_Q[:,n_to_cut_at_start_end:-n_to_cut_at_start_end:]

    for i_offres in offres:

      #first get the I and Q data, regrid , cut start/end, and subtract mean
      this_data_I = np.ndarray.flatten(data_I[i_offres,:])
      this_data_Q = np.ndarray.flatten(data_Q[i_offres,:])

      #rotate to gain/phase direction
      data_I_lp = signal.decimate(this_data_I, 10)
      data_I_lp = signal.decimate(data_I_lp, 10)
      data_I_lp = data_I_lp - np.mean(data_I_lp)
      data_Q_lp = signal.decimate(this_data_Q, 10)
      data_Q_lp = signal.decimate(data_Q_lp, 10)
      data_Q_lp = data_Q_lp - np.mean(data_Q_lp)
      data_I_lp = data_I_lp[10:np.size(data_I_lp)-10]
      data_Q_lp = data_Q_lp[10:np.size(data_Q_lp)-10]
      linfit = np.polyfit(data_I_lp, data_Q_lp, 1)
      rot_angle = np.arctan(linfit[0])
      data_gain = (this_data_I * np.cos(rot_angle) + this_data_Q * np.sin(rot_angle))
      data_phase = (-this_data_I * np.sin(rot_angle) + this_data_Q * np.cos(rot_angle))

      #make some plots
#      if plot_flag:
      if False:
        plt.plot(data_I_lp, data_Q_lp, '.')
        plt.xlabel('I data (ADC_units)')
        plt.ylabel('Q data (ADC_units)')
        plt.plot([np.min(data_I_lp),np.max(data_I_lp)], np.polyval(linfit,[np.min(data_I_lp),np.max(data_I_lp)]))
        plt.figtext(0.2,0.8,'Angle = '+"{:.1f}".format(180. / np.pi * rot_angle)+' deg')      
        plt.title('Off Resonance Tone ' + str(i_offres))
        pdf.savefig()
        plt.close()

        plt.plot(this_data_I)
        plt.plot(this_data_Q)
        plt.ylabel('Timestream (ADC units)')
        plt.xlabel('Sample Number')
        pdf.savefig()
        plt.close()

      #now compute the power spectrum
      freq = np.zeros(int(n_samples_per_block / 2 + 1))
      psd_gain = np.zeros(int(n_samples_per_block / 2 + 1))
      psd_phase = np.zeros(int(n_samples_per_block / 2 + 1))
      for i_block in range(0, n_blocks):
        this_data = data_gain[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_data = this_data - np.mean(this_data)
        this_freq, this_psd = signal.periodogram(this_data, fs, window=wind)
        psd_gain = psd_gain + this_psd / float(n_blocks)
        this_data = data_phase[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_data = this_data - np.mean(this_data)
        this_freq, this_psd = signal.periodogram(this_data, fs, window=wind)
        psd_phase = psd_phase + this_psd / float(n_blocks)
      psd_all_gain[i_offres,:] = psd_gain
      psd_all_phase[i_offres,:] = psd_phase

      #make a rough estimate of the white noise level
      if i_offres == np.min(np.where(chanmask == 0)):
        freq_mask = np.array([1]*np.size(freq))
        for i_line in range(np.size(lines)):
          freq_mask[np.argwhere(np.abs(this_freq - lines[i_line]) < 0.1)] = 0.
        offres_white_ind = np.argwhere((this_freq > offres_white_noise_min) & \
                                (this_freq < offres_white_noise_max) & \
                                freq_mask)
      gain_clean_white, dummy = reject_outliers(np.ndarray.flatten(psd_gain[offres_white_ind]))
#      gain_clean_white, dummy = reject_outliers(np.ndarray.flatten(psd_gain))
      gain_white = np.median(np.sqrt(gain_clean_white))
      phase_clean_white, dummy = reject_outliers(np.ndarray.flatten(psd_phase[offres_white_ind]))
#      phase_clean_white, dummy = reject_outliers(np.ndarray.flatten(psd_phase))
      phase_white = np.median(np.sqrt(phase_clean_white))
      phase_white_all[i_offres] = phase_white
      #rotation isn't always working, so let's just take the lower noise value
      phase_white = np.min([gain_white, phase_white])
      phase_white_all[i_offres] = phase_white
      white_dBc[i_offres] = np.log10(phase_white**2. / np.mean(data_I[i_offres,:]**2. + data_Q[i_offres,:]**2.)) * 10.

      #make some plots
      if plot_flag:
        plt.plot(this_freq, np.sqrt(psd_gain))
        plt.plot(this_freq, np.sqrt(psd_phase))
        plt.yscale('log')
        plt.xscale('log')
        plt.xlim(0.1,np.max(this_freq))
        plt.xlabel('frequency (Hz)')
        plt.ylabel('PSD (ADC_units/rt(Hz))')
        plt.title('Off Resonance Tone ' + str(i_offres))
        plt.figtext(0.2,0.8,'Phase white noise = '+"{:.1f}".format(phase_white)+' ADC_units/rt(Hz)')
#        plt.figtext(0.2,0.85,'Gain white noise = '+"{:.1f}".format(gain_white)+' ADC_units/rt(Hz)')
        plt.figtext(0.2,0.75,'Phase white noise = '+"{:.1f}".format(white_dBc[i_offres])+' dBc/Hz')
        pdf.savefig()
        plt.close()

    print(np.median(white_dBc[offres]))
    psd_all_gain = psd_all_gain[np.ndarray.flatten(offres),:]
    psd_all_phase = psd_all_phase[np.ndarray.flatten(offres),:]
    psd_gain_median = np.median(psd_all_gain, axis=0)
    psd_phase_median = np.median(psd_all_phase, axis=0)
    psd_elec_median = psd_gain_median/2. + psd_phase_median/2.
    elec_white = np.median(phase_white_all[offres] / 10.**(8./10.)) #factor to account for excess noise found empirically
    print(elec_white)
#    elec_white = np.sqrt(np.median(psd_all_phase[:,\
#      np.ndarray.flatten(np.argwhere((this_freq > white_noise_min) & (this_freq < white_noise_max)))]))

    #figure out an average template to try to remove thermal fluctuations
    data_all = data_raw[np.ndarray.flatten(np.argwhere(chanmask == 1)),:]
    data_std = np.outer(np.std(data_all,axis=1), np.ones(n_samples_final))
    data_mean = np.mean(np.divide(data_all,data_std), axis=0)
    data_mean = data_mean - np.mean(data_mean)
    f0_template = 10. 

    chancount=0
#    chanmask[20:] = -1

    #need to bandpass filter
    hp_filt_template = 0.05
    lp_filt_template = 115.
    lp_filt_template2 = 25.
    hpfilt_sos = signal.butter(6, hp_filt_template, 'hp', fs=fs, output='sos', analog=False)
    lpfilt_sos = signal.butter(6, lp_filt_template, 'lp', fs=fs, output='sos', analog=False)
    lpfilt_sos2 = signal.butter(6, lp_filt_template2, 'lp', fs=fs, output='sos', analog=False)
    data_mean_filt = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt = signal.sosfiltfilt(lpfilt_sos, data_mean_filt)
    data_mean_filt2 = signal.sosfiltfilt(hpfilt_sos, data_mean)
    data_mean_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_mean_filt2)
    data_all_filt = signal.sosfiltfilt(hpfilt_sos, data_all, axis=1)
    data_all_filt = signal.sosfiltfilt(lpfilt_sos, data_all_filt, axis=1)
    data_all_filt2 = signal.sosfiltfilt(hpfilt_sos, data_all, axis=1)
    data_all_filt2 = signal.sosfiltfilt(lpfilt_sos2, data_all_filt2, axis=1)

    dummy_time = np.arange(n_samples_per_block)
    for chancount, i_chan in enumerate(np.ndarray.flatten(np.argwhere(chanmask == 1))):

      #extract the data for this detector
      data = np.ndarray.flatten(data_all[chancount,:])
      data_filt = np.ndarray.flatten(data_all_filt[chancount,:])
      data_filt2 = np.ndarray.flatten(data_all_filt2[chancount,:])
      
      #now compute the power spectrum, convert data to units of mK
      freq = np.zeros(int(n_samples_per_block / 2 + 1))
      psd = np.zeros(int(n_samples_per_block / 2 + 1))
      psd_clean = np.zeros(int(n_samples_per_block / 2 + 1))
      for i_block in range(1, n_blocks-1):

        #compute the power spectrum of the raw data
        this_data = data[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_freq, this_psd = signal.periodogram(this_data, fs, window=wind)
        psd = psd + this_psd / float(n_blocks)

        #correlate with average template, subtract polynomial, then computed power spectrum
        this_data_filt = data_filt[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_data_filt = this_data_filt - np.mean(this_data_filt)
        this_data_filt2 = data_filt2[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_data_filt2 = this_data_filt2 - np.mean(this_data_filt2)
        this_template_filt = data_mean_filt[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_template_filt = this_template_filt - np.mean(this_template_filt)
        this_template_filt2 = data_mean_filt2[i_block*n_samples_per_block:(i_block+1)*n_samples_per_block]
        this_template_filt2 = this_template_filt2 - np.mean(this_template_filt2)
        template_corr = np.mean(np.multiply(this_data_filt2,this_template_filt2)) / \
                        np.mean(np.multiply(this_template_filt2,this_template_filt2))
        clean_data = this_data_filt - template_corr * this_template_filt
        pfit = np.polyfit(dummy_time, clean_data, 2)
        clean_data = clean_data - np.polyval(pfit, dummy_time)
        dummy, this_psd = signal.periodogram(clean_data, fs, window=wind)
        psd_clean = psd_clean + this_psd / float(n_blocks)

      freq = this_freq
      psd_all[i_chan,:] = psd
      psd_all_clean[i_chan,:] = psd_clean
      #make a rough estimate of the white noise level
      if (i_chan == np.min(np.where(chanmask == 1))):
        freq_mask = np.array([1]*np.size(freq))
        for i_line in range(np.size(lines)):
          freq_mask[np.argwhere(np.abs(freq - lines[i_line]) < 0.1)] = 0.
        white_ind = np.argwhere((freq > white_noise_min) & (freq < white_noise_max) & freq_mask)
      psd_clean_white, dummy = reject_outliers(np.ndarray.flatten(psd[white_ind]))
      psd_white[i_chan] = np.median(np.sqrt(psd_clean_white))

      #now try to determine tls noise level
      tls_ind = np.argwhere(np.logical_and(freq > tls_noise_min, freq < tls_noise_max))
      xvals = np.ndarray.flatten(freq[tls_ind])
      yvals = np.ndarray.flatten(psd_clean[tls_ind])
      psd_elec[i_chan] = elec_white/(df_over_f[i_chan] * f0[i_chan] * np.sqrt(dI_df[i_chan]**2.+dQ_df[i_chan]**2.))
      total_predicted = np.sqrt(NET_mK**2 + NET_gr**2 + psd_elec[i_chan]**2)
      tls_params, tls_params_cov = curve_fit(tls_fit, xvals, yvals, p0=[total_predicted,1.],bounds=[[0.75*total_predicted,0.],[1.25*total_predicted,100.]])
      psd_tls[i_chan] = tls_params[1]
      
#      if plot_flag:
      if False:
        
        plt.plot(freq, np.sqrt(psd))
        plt.plot(freq, np.sqrt(psd_clean))
        plt.plot(freq, np.full(np.shape(freq), np.sqrt(NET_mK**2 + NET_gr**2 + psd_elec[i_chan]**2)))
        plt.yscale('log')
        plt.xscale('log')
        plt.xlim(0.1,np.max(freq))
        plt.xlabel('frequency (Hz)')
        plt.ylabel('PSD (mK/rt(Hz))')
        plt.title('Resonator ' + str(i_chan))
        plt.figtext(0.2,0.8,'White noise (measured) = '+"{:.1f}".format(psd_white[i_chan])+' mK/rt(Hz)')
        plt.figtext(0.2,0.75,'White noise (photon)  = '+"{:.1f}".format(NET_mK)+' mK/rt(Hz)')
        plt.figtext(0.2,0.7,'White noise (G-R)  = '+"{:.1f}".format(NET_gr)+' mK/rt(Hz)')
        plt.figtext(0.2,0.65,'White noise (electronics)  = '+"{:.1f}".format(psd_elec[i_chan])+' mK/rt(Hz)')
        pdf.savefig()
        plt.close()
        
    #set the maximum white NET to consider
    max_NET = 6.

    #determine typical noise levels
    psd_white = psd_white[np.where(chanmask == 1)]
    psd_all = psd_all[np.ndarray.flatten(np.argwhere(chanmask == 1)),:]
    psd_all_clean = psd_all_clean[np.ndarray.flatten(np.argwhere(chanmask == 1)),:]
    psd_elec = psd_elec[np.ndarray.flatten(np.argwhere(chanmask == 1))]
    if outlier_test:
        dummy, good_resonator_index = reject_outliers(psd_white)
    else:
        good_resonator_index = np.arange(np.size(psd_white))
    typical_psd_white = np.median(psd_white[good_resonator_index])
    typical_psd_white_std = np.std(psd_white[good_resonator_index])
    typical_psd_elec = np.median(psd_elec[good_resonator_index])
    typical_psd_elec_std = np.std(psd_elec[good_resonator_index])
    total_predicted = np.sqrt(NET_mK**2 + NET_gr**2 + typical_psd_elec**2)
    total_predicted_std = np.sqrt((NET_mK_std)**2 + (NET_gr_std)**2 + typical_psd_elec_std**2)
      
      #make an average PSD
#      valid_chan = np.argwhere(psd_white < max_NET)
    valid_chan = good_resonator_index
    psd_all = psd_all[np.ndarray.flatten(valid_chan),:]
    psd_all_clean = psd_all_clean[np.ndarray.flatten(valid_chan),:]
    psd_elec = psd_elec[np.ndarray.flatten(valid_chan)]
    psd_white = psd_white[np.ndarray.flatten(valid_chan)]
    n_good_chan = np.size(valid_chan)
    min_ind = int(np.round(n_good_chan * 0.16))
    med_ind = int(np.round(n_good_chan * 0.5))
    max_ind = int(np.round(n_good_chan * 0.84))
    n_freq = np.size(freq)
    psd_min = np.zeros(n_freq)
    psd_med = np.zeros(n_freq)
    psd_max = np.zeros(n_freq)
    psd_min_clean = np.zeros(n_freq)
    psd_med_clean = np.zeros(n_freq)
    psd_max_clean = np.zeros(n_freq)
    for i_freq in range(0,n_freq):
        psd_sort = np.sort(psd_all[:,i_freq])
        psd_min[i_freq] = psd_sort[min_ind]
        psd_med[i_freq] = psd_sort[med_ind]
        psd_max[i_freq] = psd_sort[max_ind]
        psd_elec = np.sort(psd_elec)
        psd_sort = np.sort(psd_all_clean[:,i_freq])
        psd_min_clean[i_freq] = psd_sort[min_ind]
        psd_med_clean[i_freq] = psd_sort[med_ind]
        psd_max_clean[i_freq] = psd_sort[max_ind]

    #make a histogram plot
    if plot_flag:
        nbins = 30
        plt.hist(psd_white, bins=nbins, range = [0,max_NET], color = 'c')
        plt.xlabel('White Noise (mK/rt(Hz))')
        plt.ylabel('Number of Resonators')
        #      plt.axvline(x=NET_mK, color = 'g')
        plt.title('White Noise')      
        plt.figtext(0.45,0.8,'Measured = '+"{:.2f}".format(typical_psd_white)+'+-'+"{:.2f}".format(typical_psd_white_std)+' mK/rt(Hz)')
        plt.figtext(0.45,0.75,'Photon = '+"{:.2f}".format(NET_mK)+'+-'+"{:.2f}".format(NET_mK_std)+' mK/rt(Hz)')
        plt.figtext(0.45,0.7,'G-R = '+"{:.2f}".format(NET_gr)+'+-'+"{:.2f}".format(NET_gr_std)+' mK/rt(Hz)')
        plt.figtext(0.45,0.65,'Electronics = '+"{:.2f}".format(typical_psd_elec)+'+-'+"{:.2f}".format(typical_psd_elec_std)+' mK/rt(Hz)')
        plt.figtext(0.45,0.60,'Total (predicted) = '+"{:.2f}".format(total_predicted)+'+-'+"{:.2f}".format(total_predicted_std)+' mK/rt(Hz)')
        #      elec_fill = [psd_elec[min_ind], psd_elec[min_ind], psd_elec[max_ind], psd_elec[max_ind]]
        #      ylim = plt.gca().get_ylim()
        #      yval_fill = [ylim[0],ylim[1],ylim[1],ylim[0]]
        #      plt.fill(elec_fill, yval_fill, 'y')
        #      plt.axvline(x=psd_elec[med_ind], color = 'r')
        #      plt.hist(psd_white, bins=20, range = [0,max_NET])
        xval = np.arange(0,max_NET,0.01)
        predictedval = np.exp(-(xval - total_predicted)**2 / (2. * total_predicted_std**2))
        predictedval = predictedval / np.sum(predictedval) * np.size(xval) / float(nbins) * np.size(psd_white)
        plt.plot(xval, predictedval, 'b')
        pdf.savefig()
        plt.close()

        #plot the average PSD
        freq_fill = np.concatenate([freq,np.flip(freq,0)])
#        psd_fill = np.concatenate([np.sqrt(signal.savgol_filter(psd_min, 5, 1)),np.flip(np.sqrt(signal.savgol_filter(psd_max, 5, 1)),0)])
        psd_fill = np.concatenate([np.sqrt(psd_min),np.flip(np.sqrt(psd_max),0)])
        psd_fill_clean = np.concatenate([np.sqrt(signal.savgol_filter(psd_min_clean, 5, 1)),np.flip(np.sqrt(signal.savgol_filter(psd_max_clean, 5, 1)),0)])
        #      elec_fill = np.concatenate([np.full(np.shape(freq),psd_elec[min_ind]),np.full(np.shape(freq),psd_elec[max_ind])])
        #      plt.fill(freq_fill, elec_fill, 'y')
        plt.fill(freq_fill, psd_fill, 'c')
        plt.fill(freq_fill, psd_fill_clean, 'y')
        #      plt.plot(freq, np.full(np.shape(freq),psd_elec[med_ind]), 'r')
#        plt.plot(freq, np.sqrt(signal.savgol_filter(psd_med, 5, 1)), 'b')
        plt.plot(freq, np.sqrt(psd_med), 'b')
        plt.plot(freq, np.sqrt(signal.savgol_filter(psd_med_clean, 5, 1)), 'r')
        plt.plot(freq, np.full(np.shape(freq), total_predicted), 'r')
        plt.yscale('log')
        plt.xscale('log')
        plt.xlim(0.1,100.)
        plt.ylim(1.,1.e3)
        #      plt.ylim(NET_mK*0.5, 50.)
        plt.xlabel('frequency (Hz)')
        plt.ylabel('PSD (mK/rt(Hz))')
        plt.title('Median Over Array')
        pdf.savefig()
        plt.close()

        valid_ind = np.ndarray.flatten(np.argwhere(chanmask == 1))
        b_tls2 = (psd_tls * df_over_f)**2. * (T_bath/0.250)**1.7 * internal_power**0.5
        dummy, tls_ind = reject_outliers(b_tls2[valid_ind])
#        plt.plot(f0[valid_ind]/1.e6,b_tls2[valid_ind],'x')
        this_good_f0 = f0[valid_ind[tls_ind]]
        this_good_btls = b_tls2[valid_ind[tls_ind]]
        psd_tls_med = np.median(psd_tls[valid_ind[tls_ind]])
        binned_tls = np.zeros(8)
        binned_tls_err = np.zeros(8)
        binned_freq = np.zeros(8)
        for i, i_freq in enumerate(np.arange(200,600,50)):
          this_index = np.ndarray.flatten(np.argwhere(np.logical_and(this_good_f0/1.e6>i_freq, this_good_f0/1.e6<(i_freq+50))))
          if np.size(this_index) > 0:
            med_tls = np.median(this_good_btls[this_index])
            med_freq = np.median(this_good_f0[this_index]/1.e6)
            med_tls_err = [np.percentile(this_good_btls[this_index],84), np.percentile(this_good_btls[this_index],16)]
            plt.plot(med_freq,med_tls,'x',color='b')
            plt.plot([med_freq,med_freq], ((med_tls_err-med_tls)/np.sqrt(np.size(this_index)) + med_tls), color='b')
            binned_tls[i] = med_tls
            binned_freq[i] = med_freq*1.e6
            binned_tls_err[i] = (med_tls_err[1]-med_tls_err[0])/np.sqrt(np.size(this_index))
        plt.xlabel('Resonator Frequency (f0)')
        plt.ylabel(r'TLS Noise at 1 Hz, 250 mK, 1000 nW $S_{\delta fres}$ $/_{fres}$ ($Hz^{-1}$)')
#        power_law_fit = np.polyfit(np.log10(f0[valid_ind[tls_ind]]), np.log10(b_tls2[valid_ind[tls_ind]]), 1)
#        power_law_fit = np.polyfit(np.log10(np.ndarray.flatten(binned_freq[np.argwhere(binned_tls>0)])), np.log10(np.ndarray.flatten(binned_tls[np.argwhere(binned_tls>0)])), 1)
#        plt.figtext(0.2,0.85,'Power Law (gamma) = '+"{:.1f}".format(power_law_fit[0]))
        plt.figtext(0.2,0.80,'B2_TLS Amplitude (1e-20) = '+"{:.2f}".format(np.median(binned_tls[np.argwhere(binned_tls>0)])*1.e20))
#        plt.plot(f0/1.e6, 10**np.polyval(power_law_fit, np.log10(f0)))
#        plt.ylim(0,10**np.polyval(power_law_fit,np.max(np.log10(f0)))*2.)
        pdf.savefig()
        plt.close()

        #plot the average PSD with the lines notched out
        psf_sigma_hz = 6.31
        if date == 20240405:
          psd_max_clean = psd_max_clean * 0.35/3.e8 #empirical factor to account for miscalibration
          psd_min_clean = psd_min_clean * 0.35/3.e8 #empirical factor to account for miscalibration
          psd_med_clean = psd_med_clean * 0.35/3.e8 #empirical factor to account for miscalibration
        freq_mask = np.array([1]*np.size(freq))
        for i_line in range(np.size(lines)):
          freq_mask[np.argwhere(np.abs(freq - lines[i_line]) < 0.1)] = 0.
          good_ind = np.where(freq_mask)
          #        pdb.set_trace()
          #        this_psd_med = psd_med[good_ind]
        freq_fill = np.concatenate([freq[good_ind],np.flip(freq[good_ind],0)])
        psd_fill = np.concatenate([np.sqrt(psd_min[good_ind]),np.flip(np.sqrt(psd_max[good_ind]),0)])
        psd_fill_clean = np.concatenate([np.sqrt(psd_min_clean[good_ind]),np.flip(np.sqrt(psd_max_clean[good_ind]),0)])
        #        elec_fill = np.concatenate([np.full(np.shape(freq[good_ind]),psd_elec[min_ind]),np.full(np.shape(freq[good_ind]),psd_elec[max_ind])])
        #        plt.fill(freq_fill, elec_fill, 'y')
#        plt.fill(freq_fill, psd_fill, 'c')
        plt.plot(freq, 10.*np.exp(-freq**2./(2.*psf_sigma_hz**2)), 'k', label='PSF Shape (Arb. Norm.)', linestyle='dashed')
#        plt.fill(freq_fill, psd_fill_clean * 0.5/typical_psd_white, 'c', alpha=0.5)
        plt.fill(freq_fill, psd_fill_clean, 'c', alpha=0.5)
        #        plt.plot(freq[good_ind], np.full(np.shape(freq[good_ind]),psd_elec[med_ind]), 'r')
        #      plt.plot(freq[good_ind], np.sqrt(signal.savgol_filter(psd_med[good_ind], 5, 1)), 'b')
#        plt.plot(freq[good_ind], np.sqrt(psd_med[good_ind]), 'b')
        #      plt.plot(freq, np.sqrt(signal.savgol_filter(psd_med_clean, 5, 1)), 'r')
#        plt.plot(freq[good_ind], np.sqrt(psd_med_clean[good_ind]) * 0.5/typical_psd_white, 'b', label='Measured Noise')
        plt.plot(freq[good_ind], np.sqrt(psd_med_clean[good_ind]), 'b', label='Measured Noise')
#        plt.plot(freq, np.full(np.shape(freq), total_predicted), 'r')
        plt.plot(freq, np.full(np.shape(freq), NET_mK), 'r', label='Photon Noise')
#        plt.plot(freq, psd_tls_med * freq**(-0.25), 'y', label='TLS-Like Noise')
#        plt.plot(freq, np.sqrt((psd_tls_med * freq**(-0.25))**2. + total_predicted**2.), 'g')
        plt.yscale('log')
        plt.xscale('log')
        plt.xlim(0.1,100.)
        #      plt.ylim(NET_mK*0.5, 20.)
        plt.ylim(0.3, 70.)
        plt.xlabel('Frequency (Hz)', fontsize=16)
        plt.ylabel(r'Noise PSD (mK Hz$^{-1/2}$)', fontsize=16)
        plt.xticks(fontsize=14)
        plt.yticks(fontsize=14)
        plt.legend(fontsize=14, loc = 'upper right')
        plt.title('Off Resonance Tones, Bypassing Cryostat', fontsize=16)
#        plt.title('No KIDs, Through Cryostat', fontsize=16)
#        plt.title('Off Resonance Tones, Through Cryostat', fontsize=16)
#        plt.title('Telescope Pointed to Horizon', fontsize=16)
#        plt.title('Telescope Pointed to Zenith', fontsize=16)
#        plt.title('Ambient BB, GM Turned Off', fontsize=16)
#        plt.title('Ambient Temperature Blackbody', fontsize=16)
#        plt.title('-18 dB Readout Power, T$_{load}$ = 300 K', fontsize=16)

        this_f = freq[good_ind]
        psf = np.exp(-this_f**2./(2.*psf_sigma_hz**2))
        psd = psd_med_clean[good_ind]
        weight = psf**2. / psd
        valid = np.ndarray.flatten(np.argwhere(this_f>1.))
        avg_psd = np.sum(np.sqrt(psd[valid]) * weight[valid]) / np.sum(weight[valid])
        print(avg_psd)
        print(NET_mK)

#        plt.figtext(0.15,0.20,'Photon NET = '+"{:.2f}".format(NET_mK) + ' mK Hz$^{-1/2}$', fontsize=14)
#        plt.figtext(0.15,0.15,'PSF-Avg. NET = '+"{:.2f}".format(avg_psd)+ ' mK Hz$^{-1/2}$', fontsize=14)

        pdf.savefig(bbox_inches='tight')
        plt.close()

  this_chanmask = np.ndarray.flatten(np.argwhere(chanmask == 1))
  this_chanmask = this_chanmask[valid_chan]

  return freq, psd_all, this_chanmask

