#JS - a simple routine to compute noise spectra and plot the results

import numpy as np
import sys, os
import matplotlib.pyplot as plt
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import pandas

def main(file_stub, chanmask, dI_df, dQ_df, chop_freq, Telescope=False):

  #get some preliminaries
  n_chan = np.size(dI_df)

  if Telescope:
    values = np.load('/home/peter/telescope_control/' + file_stub + '.npz')
    map_tstart = values['start_time']
    map_tend = values['end_time']
    map_xpos = values['az']
    map_ypos = values['el']
  else:
    #get the beam mapper data
    mapper_pos = np.loadtxt('data/' + file_stub + '.csv', skiprows=1, delimiter = ',')
    map_tstart = mapper_pos[:,0]
    map_tend = mapper_pos[:,1]
    map_xpos = mapper_pos[:,2]
    map_ypos = mapper_pos[:,3]
  n_blocks = np.size(map_ypos)
#  pdb.set_trace()
  #get the various file paths
  main_path = 'data/' + file_stub + '/'
  directory_list = os.listdir(main_path)
  noise_dir = filter(lambda x: '.dir' in x, directory_list)
  path = main_path + noise_dir[0] + '/'
  sweep_path = main_path + 'target_sweep/'

  #load in the frequency information
  bb_freqs = np.load(sweep_path+'bb_target_freqs.npy')
  freq_list = np.load(sweep_path+'sweep_freqs.npy')
  mid_ind = freq_list.size / 2
  f0 = bb_freqs + freq_list[mid_ind]

  #grab the time data, will need to resample to put it
  #on a regular grid
  time_raw = np.fromfile(path+'time', np.float64)
  time_0 = time_raw - time_raw[0]
  total_time = np.max(time_0)
  n_samples = np.size(time_raw)
  time = np.arange(0,total_time,total_time/n_samples) + time_raw[0]

  #loop over mirror positions
  start_integration = np.zeros(n_blocks)
  end_integration = np.zeros(n_blocks)
  for i_pos in range (n_blocks):

    #figure out the start and end samples
    test = np.size(np.argwhere(time > map_tend[i_pos]))
    if test > 0:
      start_integration[i_pos] = np.min(np.argwhere(time > map_tstart[i_pos]))
      end_integration[i_pos] = np.max(np.argwhere(time < map_tend[i_pos]))

  if Telescope:
    block_offset = 50
  else:
    block_offset = 50
  n_samples_per_block = int(np.median(end_integration - start_integration + 1 - 2.*block_offset))
  fs = 1./(time[1]-time[0])
  wind = signal.get_window('hamming', n_samples_per_block)

  #loop over resonators, grabbing I and Q data and interpolating to
  #regular time grid
  map_val = np.zeros([np.size(chanmask), n_blocks])
  for i_chan in np.argwhere(chanmask == 1):

    #first get the I and Q data, regrid , cut start/end, and subtract mean
    i_chan = i_chan[0]
    print i_chan
    data_I_0 = np.fromfile(path+'I_'+str(i_chan), np.float64)
    data_I = np.interp(time, time_raw, data_I_0)
    data_Q_0 = np.fromfile(path+'Q_'+str(i_chan), np.float64)
    data_Q = np.interp(time, time_raw, data_Q_0)
    data_I = data_I - np.mean(data_I)
    data_Q = data_Q - np.mean(data_Q)
    
    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    eqiv_var_I = (1. / dI_df[i_chan])**2.
    eqiv_var_Q = (1. / dQ_df[i_chan])**2.
    data = ( (data_I / dI_df[i_chan]) / eqiv_var_I + \
               (data_Q / dQ_df[i_chan]) / eqiv_var_Q ) / \
               (1./eqiv_var_I + 1./eqiv_var_Q)
    data = data / f0[i_chan]

    #now compute the power spectrum, convert data to units of mK
    freq = np.zeros(n_samples_per_block / 2 + 1)
    psd = np.zeros(n_samples_per_block / 2 + 1)
    for i_block in range(0, n_blocks):
      if end_integration[i_block] > 0:
        start_ind = int(start_integration[i_block]+block_offset)
        end_ind = int(start_ind+n_samples_per_block)
        this_data = data[start_ind:end_ind]
        this_data = this_data - np.mean(this_data)
        this_freq, this_psd = signal.periodogram(this_data, fs, window=wind)
        diff_freq = abs(this_freq - chop_freq)
        chop_ind = np.argwhere(diff_freq <= 1.)
        map_val[i_chan,i_block] = np.sqrt(np.sum(this_psd[chop_ind]))
#      if np.abs(map_ypos[i_block]-89.585) < 0.01:
#        plt.plot(this_freq,this_psd),plt.show()
#        print(np.max(map_val[i_chan,:]))
#        pdb.set_trace()
  return map_xpos, map_ypos, map_val

