import compute_frequency_direction_convert as cdf
import importlib
importlib.reload(cdf)
import analyze_beammap_convert as abm
importlib.reload(abm)
import numpy as np
from scipy import signal, ndimage, fftpack, optimize
from scipy.ndimage import zoom
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import matplotlib.pyplot as plt

chop_freq = 24.6
#date = '20190531_beammap_2_80degPol'
#date = 'Device_aSi1_Channel2_beammap_105degPol_20220405_1145_66x62_1sec'
date = '20220916_Device_aSi1_Channel2_beammap_set5' #final pol1 on-telescope
#date = '20220919_Device_aSi1_Channel2_beammap_set2' #final pol2 on-telescope
#date = '20190520_beammap_3'
perform_fit = False
filter = False #set True for 66x62 map and False for 15x15 map

### MAYA: As my file set up is different, I've edited the following lines to match my file structure ###
#chanmask = np.load('params/20190408_chanmask_restricted.npy')
#chanmask = np.load('params/20190408_chanmask_full.npy')
chanmask = np.load('params/chanmask.npy')
#chanmask[120:] = -1
#chanmask[:223] = -1
#file_stub = date + '_' + str(chop_freq) + 'Hz'
file_stub = date

#get the resonator frequencies
gc = np.loadtxt("./general_config", dtype = "str")
center_freq = float(gc[np.where(gc == 'center_freq')[0][0]][1])*1.e6
fres = (np.load('data/'+file_stub+'/target_sweep/bb_target_freqs.npy')+center_freq) / 1.e6

#first we need to determine the frequency direction
dI_df, dQ_df = cdf.main(file_stub)

def Gauss_2d(xxx_todo_changeme, amp, x0, y0, sigma_x, sigma_y, offset):
#  return offset + amp * np.exp(-((x-x0)**2 + (y-y0)**2)/ (2. * sigma**2))
  (x,y) = xxx_todo_changeme
  return offset + amp * np.exp(-(x-x0)**2/(2.*sigma_x**2) - (y-y0)**2/(2.*sigma_y**2))

#perform the analysis
if perform_fit:
  map_xpos, map_ypos, map_val = abm.main(file_stub, chanmask, dI_df, dQ_df, chop_freq, Telescope=True)
  np.save('data/' + file_stub + '/' + date + '_map_xpos.npy', map_xpos)
  np.save('data/' + file_stub + '/' + date + '_map_ypos.npy', map_ypos)
  np.save('data/' + file_stub + '/' + date + '_map_val.npy', map_val)
  print(f"DEBUG: map_val min = {np.min(map_val)}, max = {np.max(map_val)}")

else:
  map_xpos = np.load('data/' + file_stub + '/' + date + '_map_xpos.npy')
  map_ypos = np.load('data/' + file_stub + '/' + date + '_map_ypos.npy')
  map_val = np.load('data/' + file_stub + '/' + date + '_map_val.npy')

#round the positions given the telescope isn't perfectly repeatable
typical_dy = np.median(np.abs(map_ypos - np.roll(map_ypos,1)))
n_y_pos = np.round((max(map_ypos) - min(map_ypos))//typical_dy)
n_x_pos = np.round((max(map_xpos) - min(map_xpos))//typical_dy)

#get the map positions and make an array for them
if True:
  map_xpos_uniq = np.unique(map_xpos)
  map_ypos_uniq = np.unique(map_ypos)
else:
  map_xpos_uniq = min(map_xpos) + np.arange(n_x_pos+1)*typical_dy
  map_ypos_uniq = min(map_ypos) + np.arange(n_y_pos+1)*typical_dy
  for i_y in np.arange(np.size(map_ypos)):
    min_diff = np.argwhere(np.abs(map_ypos[i_y]-map_ypos_uniq) == min(np.abs(map_ypos[i_y]-map_ypos_uniq)))
    map_ypos[i_y] = map_ypos_uniq[min_diff[0]]
  for i_x in np.arange(np.size(map_xpos)):
    min_diff = np.argwhere(np.abs(map_xpos[i_x]-map_xpos_uniq) == min(np.abs(map_xpos[i_x]-map_xpos_uniq)))
    map_xpos[i_x] = map_xpos_uniq[min_diff[0]]
n_xpos = np.size(map_xpos_uniq)
n_ypos = np.size(map_ypos_uniq)

nrows, ncols = 10, 10
dx = map_xpos_uniq[1] - map_xpos_uniq[0]
dy = map_ypos_uniq[1] - map_ypos_uniq[0]
extent = max(map_xpos)+dx/2., min(map_xpos)-dx/2., max(map_ypos)+dy/2., min(map_ypos)-dy/2.

x_center = np.zeros(np.size(chanmask))
y_center = np.zeros(np.size(chanmask))
amplitude = np.zeros(np.size(chanmask))
snr = np.zeros(np.size(chanmask))
chisq = np.zeros(np.size(chanmask))
sigma_x = np.zeros(np.size(chanmask))
sigma_y = np.zeros(np.size(chanmask))
#chanmask[20:] = -1 # Set all channels after 20 to -1
for idx in np.flatnonzero(chanmask == 1):
  this_val = np.ndarray.flatten(map_val[idx,:])
  if filter:
    this_val = signal.savgol_filter(this_val, 7, 1)
  #map_val[idx,:] = this_val
  max_index = np.argwhere(this_val == np.max(this_val))
  x_max = map_xpos[max_index[0]]
  y_max = map_ypos[max_index[0]]
  #index = np.argwhere(this_val > 0.2 * np.max(this_val))
  separation = np.sqrt((map_xpos - x_max[0])**2 + (map_ypos - y_max[0])**2)
  index = np.argwhere(separation < 0.21)

  x_center[idx] = np.sum(map_xpos[index]*this_val[index]) / np.sum(this_val[index])
  y_center[idx] = np.sum(map_ypos[index]*this_val[index]) / np.sum(this_val[index])
  amplitude[idx] = np.max(this_val[index])
  denom = np.nanstd(this_val)
  
  signal_region = index.flatten()
  background_mask = np.ones(len(this_val), dtype=bool)
  background_mask[signal_region] = False
  background_std = np.std(this_val[background_mask])
  snr[idx] = amplitude[idx] / background_std
  



### MAYA: Integer to Array issues python 2 to 3 formatting different ###
  ### MAYA: Adding calculation check ###
  print(f"chan={idx}, max={np.max(this_val)}, fres={fres[idx]}, index size={len(index)}")
  if True:
    this_x = np.ndarray.flatten(map_xpos[index])
    this_y = np.ndarray.flatten(map_ypos[index])
    this_z = np.ndarray.flatten(this_val[index])
    # sigma_z = np.full(int(np.size(this_z)), np.std(this_val))
    #sigma_z = np.full(this_z.shape, np.nanstd(this_val))
    sigma_z = np.full(int(np.size(this_z)), (np.percentile(this_val, 84) - np.percentile(this_val, 16)) * 0.5)
    start_params = (
        np.max(this_z),
        x_center[idx],
        y_center[idx],
        0.1,
        0.1,
        np.median(this_z)
    )  
    bounds = (
        (0., x_center[idx] - 0.2, y_center[idx] - 0.2, 0.01, 0.01, -np.max(np.abs(this_z))),
        (10. * np.max(this_z), x_center[idx] + 0.2, y_center[idx] + 0.2, 1., 1., np.max(np.abs(this_z)))
    )
    popt, pcov = optimize.curve_fit(
        Gauss_2d,
        (this_x, this_y),
        this_z,
        p0=start_params,
        sigma=sigma_z,
        absolute_sigma=True,
        maxfev=1000000,
        bounds=bounds
    )
    x_center[idx] = popt[1]
    y_center[idx] = popt[2]
    amplitude[idx] = popt[0]
    sigma_x[idx] = np.abs(popt[3])
    sigma_y[idx] = np.abs(popt[4])
    snr[idx] = popt[0] / np.sqrt(pcov[0, 0])
    #if idx == 14:
      #pdb.set_trace()  # Debugging breakpoint for channel 14
    chisq[idx] = np.sum(
        ((this_z - Gauss_2d(
            (this_x, this_y),
            popt[0], popt[1], popt[2], popt[3], popt[4], popt[5]
            )) ** 2 / sigma_z ** 2) / (np.size(this_z) - 5.)
      )

#save outputs
np.save('data/' + file_stub + '/' + date + '_x_center.npy', x_center)
np.save('data/' + file_stub + '/' + date + '_y_center.npy', y_center)
np.save('data/' + file_stub + '/' + date + '_amplitude.npy', amplitude)
np.save('data/' + file_stub + '/' + date + '_snr.npy', snr)
np.save('data/' + file_stub + '/' + date + '_chisq.npy', chisq)
np.save('data/' + file_stub + '/' + date + '_sigma_x.npy', sigma_x)
np.save('data/' + file_stub + '/' + date + '_sigma_y.npy', sigma_y)

pdf_file_name = 'data/' + file_stub + '/' + file_stub + '_beammap.pdf'
with PdfPages(pdf_file_name) as pdf:

#  high_snr_ind = np.argwhere(snr > 30)
  #FOM = amplitude / chisq
  FOM = np.divide(amplitude, chisq, out=np.zeros_like(amplitude), where=chisq!=0)
#  high_snr_ind = np.argwhere(FOM > 50)
  high_snr_ind = np.argwhere(np.bitwise_and(amplitude > np.percentile(amplitude,55), FOM > 50))
  plt.scatter(x_center[high_snr_ind], y_center[high_snr_ind], marker='+')
  plt.axis('equal')
  plt.xlim(extent[0],extent[1])
  plt.ylim(extent[2],extent[3])
#  plt.hlines(extent[2:3],-1.e10,1.e10)
#  plt.vlines(extent[0:1],-1.e10,1.e10)
  plt.xlabel('X Position (in)')
  plt.ylabel('Y Position (in)')
  pdf.savefig()
  plt.close()
  
  counter = 1
  #for idx in np.argwhere(chanmask == 1):
  for idx in np.argwhere(chanmask == 1).flatten():

    print(idx)
    map_2d = np.zeros([n_xpos, n_ypos])
    
    for i_xpos in range (n_xpos):

      for j_ypos in range (n_ypos):

        index = np.argwhere((map_xpos == map_xpos_uniq[i_xpos]) & (map_ypos == map_ypos_uniq[j_ypos]))
        if np.size(index) > 0:
          map_2d[i_xpos,j_ypos] = map_val[idx,index[0]]
    
    plt.subplot(nrows, ncols, counter)
    plt.axis('off')
### MAYA: Added cmap = 'jet' ###
    this_map = np.transpose(map_2d[::-1])
    #plt.imshow(this_map, extent=extent, aspect='equal', cmap='jet', interpolation='bilinear')
    upsampled_map = zoom(this_map, 2, order=3)
    plt.imshow(upsampled_map, extent=extent, aspect='equal', cmap='jet', interpolation='bilinear')

    map_2d = np.zeros([n_xpos, n_ypos])
    if counter == nrows*ncols:
      plt.gcf().set_dpi(300)  # Sharper plots
      pdf.savefig()
      plt.close()
      counter = 0
    counter +=1
  
  plt.gcf().set_dpi(300)  # Sharper plots  
  pdf.savefig()
  plt.close()

  for idx in np.argwhere(chanmask == 1):
    ### MAYA: Had to add paranthesis around idx to avoid TypeError ###
    print(idx)
    
    for i_xpos in range (n_xpos):

      for j_ypos in range (n_ypos):

        index = np.argwhere((map_xpos == map_xpos_uniq[i_xpos]) & (map_ypos == map_ypos_uniq[j_ypos]))
        if np.size(index) > 0:
          map_2d[i_xpos,j_ypos] = map_val[idx,index[0]]

    this_map = np.transpose(map_2d[::-1])
### MAYA: Added cmap = 'jet' ###
    #plt.imshow(this_map, extent=extent, aspect='equal', cmap = 'jet')
    upsampled_map = zoom(this_map, 2, order=3)
    plt.imshow(upsampled_map, extent=extent, aspect='equal', cmap='jet', interpolation='bilinear')
    plt.xlabel('X Position (in)')
    plt.ylabel('Y Position (in)')
    plt.xlim(extent[0],extent[1])
    plt.ylim(extent[2],extent[3])
    plt.title('Resonator Number ' + str(idx[0]))
    plt.plot(x_center[idx],y_center[idx],marker='+',color='white', markersize=10, mew=2)
#    pos='Center Position = (' + str(x_center[idx]) + ', ' + str(y_center[idx]) + ')' ##Added by DC 5/22/19
#    plt.text(28,2,pos)   ##Added by DC 5/22/19
    #plt.text(extent[0]-0.05, extent[3]+0.05, f'Amplitude = {amplitude[idx[0]]:.2e}', color='white')
    plt.text(extent[0]-0.05, extent[3]+0.05, 'Amplitude = '+"{:.2f}".format(amplitude[idx[0]]),color='white')
    plt.text(extent[0]-0.05, extent[3]+0.15, 'SNR = '+"{:.2f}".format(snr[idx[0]]),color='white')
    plt.text(extent[0]-0.05, extent[3]+0.25, 'chisq = '+"{:.2f}".format(chisq[idx[0]]),color='white')
    plt.text(extent[0]-0.05, extent[3]+0.35, 'sigma_x = '+"{:.2f}".format(sigma_x[idx[0]]),color='white')
    plt.text(extent[0]-0.05, extent[3]+0.45, 'sigma_y = '+"{:.2f}".format(sigma_y[idx[0]]),color='white')
    plt.gcf().set_dpi(300)  # Sharper plots
    pdf.savefig()
    plt.close()
