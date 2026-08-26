#JS - this is a simple routine that uses the target sweep data to determine
#the values of dI/df and dQ/df

import numpy as np
import sys, os
from scipy import signal, ndimage, fftpack

import pdb
import matplotlib.pyplot as plt

def main(file_stub, single_chan = -1):

  if single_chan == -1:

    path = 'data/' + file_stub + '/target_sweep/'

    #load in the frequency information
    bb_freqs = np.load(path+'bb_target_freqs.npy')
    freq_list = np.load(path+'sweep_freqs.npy')
    freq_span = max(freq_list) - min(freq_list)
    delta_f = freq_list[1] - freq_list[0]
    mid_ind = freq_list.size / 2
    f0 = freq_list[mid_ind]
    n_freq = np.size(freq_list)
    n_chan = np.size(bb_freqs)
    tone_freqs = bb_freqs + f0
    deriv_length = 5

    #load in the I and Q data
    for i_freq in range(0,n_freq):
      this_i_data = np.load(path+'I'+str(freq_list[i_freq])+'.npy')
      this_q_data = np.load(path+'Q'+str(freq_list[i_freq])+'.npy')
      if i_freq == 0:
        data_I = np.zeros([n_freq,np.size(this_i_data)])
        data_Q = np.zeros([n_freq,np.size(this_q_data)])
        n_res = np.size(this_i_data)
      data_I[i_freq,:] = this_i_data
      data_Q[i_freq,:] = this_q_data

  else:

    path = 'data/' + file_stub + '/'

    #read in the IQ sweep
    data = np.loadtxt(path + 'IQsweep')
    delta_f = data[1,2] - data[0,2]
    n_freq = np.size(data[:,0])
    mid_ind = n_freq / 2
    n_chan = 1
    data_I = np.zeros([n_freq, n_chan])
    data_Q = np.zeros([n_freq, n_chan])
    data_I[:,0] = data[:,0]
    data_Q[:,0] = data[:,1]
    deriv_length = 3
    
  #we'll fit a polynomial to the I and Q data versus frequency. deriv_length
  #gives the number of samples on either side of the tone frequency to use and
  #fit_order gives the order of the polynomial fit
  fit_order = 3

  #perform the fit and then compute the derivative to obtain dI/df and dQ/df
  dI_df = np.zeros(n_chan)
  dQ_df = np.zeros(n_chan)
  ind_val = np.arange(mid_ind-deriv_length, mid_ind+deriv_length, 1)
  for i_chan in range(0,n_chan):
    fit_I = np.polyfit(ind_val, data_I[mid_ind-deriv_length:mid_ind+deriv_length,i_chan], fit_order)
    fit_I_deriv = np.polyder(fit_I)
    dI_df[i_chan] = np.polyval(fit_I_deriv, mid_ind) / delta_f
    fit_Q = np.polyfit(ind_val, data_Q[mid_ind-deriv_length:mid_ind+deriv_length,i_chan], fit_order)
    fit_Q_deriv = np.polyder(fit_Q)
    dQ_df[i_chan] = np.polyval(fit_Q_deriv, mid_ind) / delta_f
  return dI_df, dQ_df
