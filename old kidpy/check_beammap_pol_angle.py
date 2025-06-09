import numpy as np
import sys, os
import matplotlib.pyplot as plt
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import pandas

file_stub = 'beammap_test_20220323_pol110'
chop_freq = 24.6

#get the various file paths
main_path = 'data/' + file_stub + '/'
directory_list = os.listdir(main_path)
noise_dir = filter(lambda x: '.dir' in x, directory_list)
path = main_path + noise_dir[0] + '/'
sweep_path = main_path + 'target_sweep/'

#grab the time data, will need to resample to put it
#on a regular grid
time_raw = np.fromfile(path+'time', np.float64)
time_0 = time_raw - time_raw[0]
total_time = np.max(time_0)
n_samples = np.size(time_raw)
time = np.arange(0,total_time,total_time/n_samples) + time_raw[0]

#first get the I and Q data, regrid , cut start/end, and subtract mean
i_chan = 0
data_I_0 = np.fromfile(path+'I_'+str(i_chan), np.float64)
data_I = np.interp(time, time_raw, data_I_0)
data_Q_0 = np.fromfile(path+'Q_'+str(i_chan), np.float64)
data_Q = np.interp(time, time_raw, data_Q_0)
data_I = data_I - np.mean(data_I)
data_Q = data_Q - np.mean(data_Q)

dI_df, dQ_df = cdf.main(file_stub)

start_integration = 0
end_integration = np.size(time)

block_offset = 0
n_samples_per_block = np.size(time)
fs = 1./(time[1]-time[0])
wind = signal.get_window('hamming', n_samples_per_block)

#now use the derivatives to convert to a frequency shift
#need to optimally weight the data based on the response
#in each direction (assuming the noise is identical in I and Q)
eqiv_var_I = (1. / dI_df[i_chan])**2.
eqiv_var_Q = (1. / dQ_df[i_chan])**2.
data = ( (data_I / dI_df[i_chan]) / eqiv_var_I + \
               (data_Q / dQ_df[i_chan]) / eqiv_var_Q ) / \
               (1./eqiv_var_I + 1./eqiv_var_Q)

#now compute the power spectrum, convert data to units of mK
freq = np.zeros(n_samples_per_block / 2 + 1)
psd = np.zeros(n_samples_per_block / 2 + 1)
this_data = data[start_integration:end_integration]
this_data = this_data - np.mean(this_data)
this_freq, this_psd = signal.periodogram(this_data, fs, window=wind)
diff_freq = abs(this_freq - chop_freq)
chop_ind = np.argwhere(diff_freq <= 0.5)
print(np.sqrt(np.sum(this_psd[chop_ind])))
