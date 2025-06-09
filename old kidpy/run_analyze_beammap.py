import compute_frequency_direction as cdf
reload(cdf)
import analyze_beammap as abm
reload(abm)
import numpy as np
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import matplotlib.pyplot as plt

chop_freq = 24.6
#date = '20190531_beammap_2_80degPol'
#date = 'Device_aSi1_Channel2_beammap_105degPol_20220405_1145_66x62_1sec'
date = 'Device_Si1_Channel1_beammap_105degPol_20220420_1730_66x62_1sec'
#date = '20190520_beammap_2'
perform_fit = True
filter = False #set True for 66x62 map and False for 15x15 map

#chanmask = np.load('params/20190408_chanmask_restricted.npy')
#chanmask = np.load('params/20190408_chanmask_full.npy')
chanmask = np.load('params/chanmask.npy')
file_stub = date + '_' + str(chop_freq) + 'Hz'
#file_stub = date

#get the resonator frequencies
gc = np.loadtxt("./general_config", dtype = "str")
center_freq = np.float(gc[np.where(gc == 'center_freq')[0][0]][1])*1.e6
fres = (np.load('data/'+file_stub+'/target_sweep/bb_target_freqs.npy')+center_freq) / 1.e6

#first we need to determine the frequency direction
dI_df, dQ_df = cdf.main(file_stub)

#then perform the analysis
if perform_fit:
  map_xpos, map_ypos, map_val = abm.main(file_stub, chanmask, dI_df, dQ_df, chop_freq)
  np.save('data/' + file_stub + '/' + date + '_map_xpos.npy', map_xpos)
  np.save('data/' + file_stub + '/' + date + '_map_ypos.npy', map_ypos)
  np.save('data/' + file_stub + '/' + date + '_map_val.npy', map_val)
else:
  map_xpos = np.load('data/' + file_stub + '/' + date + '_map_xpos.npy')
  map_ypos = np.load('data/' + file_stub + '/' + date + '_map_ypos.npy')
  map_val = np.load('data/' + file_stub + '/' + date + '_map_val.npy')

#get the map positions and make an array for them
map_xpos_uniq = np.unique(map_xpos)
map_ypos_uniq = np.unique(map_ypos)
n_xpos = np.size(map_xpos_uniq)
n_ypos = np.size(map_ypos_uniq)

nrows, ncols = 10, 10
extent = max(map_xpos), min(map_xpos), max(map_ypos), min(map_ypos)

x_center = np.zeros(np.size(chanmask))
y_center = np.zeros(np.size(chanmask))
amplitude = np.zeros(np.size(chanmask))
snr = np.zeros(np.size(chanmask))
for i_chan in np.argwhere(chanmask == 1):
  this_val = np.ndarray.flatten(map_val[i_chan,:])
  if filter:
    this_val = signal.savgol_filter(this_val, 7, 1)
  map_val[i_chan,:] = this_val
  max_index = np.argwhere(this_val == np.max(this_val))
  x_max = map_xpos[max_index[0]]
  y_max = map_ypos[max_index[0]]
#  index = np.argwhere(this_val > 0.2 * np.max(this_val))
  separation = np.sqrt((map_xpos - x_max[0])**2 + (map_ypos - y_max[0])**2)
  index = np.argwhere(separation < 2.)
  x_center[i_chan] = np.sum(map_xpos[index]*this_val[index]) / np.sum(this_val[index])
  y_center[i_chan] = np.sum(map_ypos[index]*this_val[index]) / np.sum(this_val[index])
  amplitude[i_chan] = np.sum(this_val[index]) / fres[i_chan]
  snr[i_chan] = amplitude[i_chan] * fres[i_chan] / np.median(np.abs(this_val - np.median(this_val)))

pdf_file_name = 'data/' + file_stub + '/' + file_stub + '_beammap.pdf'
with PdfPages(pdf_file_name) as pdf:

  high_snr_ind = np.argwhere(snr > 30)
  plt.scatter(x_center[high_snr_ind], y_center[high_snr_ind], marker='+')
  plt.axis('equal')
  plt.xlim(extent[0],extent[1])
  plt.ylim(extent[2],extent[3])
  plt.xlabel('X Position (in)')
  plt.ylabel('Y Position (in)')
  pdf.savefig()
  plt.close()
  
  counter = 1

  for i_chan in np.argwhere(chanmask == 1):

    print i_chan
    map_2d = np.zeros([n_xpos, n_ypos])
    
    for i_xpos in range (n_xpos):

      for j_ypos in range (n_ypos):

        index = np.argwhere((map_xpos == map_xpos_uniq[i_xpos]) & (map_ypos == map_ypos_uniq[j_ypos]))[0]
        map_2d[i_xpos,j_ypos] = map_val[i_chan,index]

    plt.subplot(nrows, ncols, counter)
    plt.axis('off')
    plt.imshow(np.transpose(map_2d[::-1]), extent=extent, aspect='equal')
    map_2d = np.zeros([n_xpos, n_ypos])
    if counter == nrows*ncols:
      pdf.savefig()
      plt.close()
      counter = 0
    counter +=1
    
  pdf.savefig()
  plt.close()

  for i_chan in np.argwhere(chanmask == 1):

    print i_chan
    
    for i_xpos in range (n_xpos):

      for j_ypos in range (n_ypos):

        index = np.argwhere((map_xpos == map_xpos_uniq[i_xpos]) & (map_ypos == map_ypos_uniq[j_ypos]))[0]
        map_2d[i_xpos,j_ypos] = map_val[i_chan,index]

    plt.imshow(np.transpose(map_2d[::-1]), extent=extent, aspect='equal')
    plt.xlabel('X Position (in)')
    plt.ylabel('Y Position (in)')
    plt.title('Resonator Number ' + str(i_chan[0]))
    plt.plot(x_center[i_chan],y_center[i_chan],marker='+',color='white', markersize=10, mew=2)
#    pos='Center Position = (' + str(x_center[i_chan]) + ', ' + str(y_center[i_chan]) + ')' ##Added by DC 5/22/19
#    plt.text(28,2,pos)   ##Added by DC 5/22/19
    plt.text(extent[0]-2, extent[3]+2, 'Amplitude = '+"{:.2f}".format(amplitude[i_chan[0]]),color='white')
    plt.text(extent[0]-2, extent[3]+4, 'SNR = '+"{:.2f}".format(snr[i_chan[0]]),color='white')
    pdf.savefig()
    plt.close()
