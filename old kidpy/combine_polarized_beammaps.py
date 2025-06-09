import compute_frequency_direction as cdf
reload(cdf)
import analyze_beammap as abm
reload(abm)
import numpy as np
from scipy import signal, ndimage, fftpack
from matplotlib.backends.backend_pdf import PdfPages
import pdb
import matplotlib.pyplot as plt

Telescope = True

if Telescope:
  date_pol1, chanmask = '20220916_Device_aSi1_Channel2_beammap_set5', np.load('params/chanmask.npy')
  date_pol2 = '20220919_Device_aSi1_Channel2_beammap_set2' #final pol2 on-telescope
  file_stub_pol1 = date_pol1
  file_stub_pol2 = date_pol2
else:
  chop_freq = 24.6
  #date_pol1 = 'Device_aSi3_Channel4_beammap_105degPol_20220324_1210'
  #date_pol2 = 'Device_aSi3_Channel4_beammap_15degPol_20220324_1412'
  #date_pol1, chanmask = 'Device_aSi1_Channel2_beammap_15degPol_20220404_1255_66x62_1sec', np.load('params/chanmask.npy')
  #date_pol2 = 'Device_aSi1_Channel2_beammap_105degPol_20220405_1145_66x62_1sec'
  date_pol1, chanmask = 'Device_aSi2_Channel3_beammap_15degPol_20220330_1635_66x62_1sec', np.load('params/chanmask.npy')
  date_pol2 = 'Device_aSi2_Channel3_beammap_105degPol_20220331_1545_66x62_1sec'
  #date_pol1, chanmask = 'Device_Si1_Channel1_beammap_15degPol_20220419_1805_66x62_1sec', np.load('params/chanmask.npy')
  #date_pol2 = 'Device_Si1_Channel1_beammap_105degPol_20220420_1730_66x62_1sec'
  #date_pol1 = '20190531_beammap_1_170degPol'
  #date_pol2 = '20190531_beammap_2_80degPol'

  #chanmask = np.load('params/20190408_chanmask_restricted.npy')
  #chanmask = np.load('params/20190408_chanmask_full.npy')
  #chanmask = np.load('params/chanmask.npy')
  file_stub_pol1 = date_pol1 + '_' + str(chop_freq) + 'Hz'
  file_stub_pol2 = date_pol2 + '_' + str(chop_freq) + 'Hz'

#get the resonator frequencies
lo_freq = np.median(np.load('data/'+file_stub_pol1+'/target_sweep/sweep_freqs.npy'))
fres = (np.load('data/'+file_stub_pol1+'/target_sweep/bb_target_freqs.npy')+lo_freq) / 1.e6

if Telescope:
  x_center_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_x_center.npy')
  y_center_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_y_center.npy')
  amplitude_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_amplitude.npy')
  chisq_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_chisq.npy')
  sigma_x_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_sigma_x.npy')
  sigma_y_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_sigma_y.npy')
  x_center_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_x_center.npy')
  y_center_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_y_center.npy')
  amplitude_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_amplitude.npy')
  chisq_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_chisq.npy')
  sigma_x_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_sigma_x.npy')
  sigma_y_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_sigma_y.npy')

  #need to normalize amplitudes
  amplitude_pol1 = amplitude_pol1 / np.median(amplitude_pol1)
  amplitude_pol2 = amplitude_pol2 / np.median(amplitude_pol2)
  fom_pol1 = amplitude_pol1 / (chisq_pol1 + 1.e-10)
  fom_pol2 = amplitude_pol2 / (chisq_pol2 + 1.e-10)

  #need to correct for shifts in source position
  x_shift = np.median(x_center_pol1 - x_center_pol2)
  y_shift = np.median(y_center_pol1 - y_center_pol2)
  x_center_pol2 = x_center_pol2 + x_shift
  y_center_pol2 = y_center_pol2 + y_shift

  x_center = np.zeros(np.size(chanmask))
  y_center = np.zeros(np.size(chanmask))
  polarization = np.zeros(np.size(chanmask))
  polarization_ratio = np.zeros(np.size(chanmask))
  for i_chan in np.argwhere(chanmask == 1):
    if amplitude_pol1[i_chan] > amplitude_pol2[i_chan]:
#      if np.bitwise_and(chisq_pol1[i_chan] > 0.1, fom_pol1[i_chan] > 0.1):
      if np.bitwise_or(sigma_x_pol1[i_chan]/sigma_y_pol1[i_chan] < 1.5, x_center_pol1[i_chan] > -0.5):
        x_center[i_chan] = x_center_pol1[i_chan]
        y_center[i_chan] = y_center_pol1[i_chan]
        polarization[i_chan] = 1
        polarization_ratio[i_chan] = amplitude_pol2[i_chan] / amplitude_pol1[i_chan]
      else:
        x_center[i_chan] = -1.e9
        x_center_pol1[i_chan] = -1.e9
    else:
#      if np.bitwise_and(chisq_pol2[i_chan] > 0.1, fom_pol2[i_chan] > 0.1):
      if np.bitwise_or(sigma_x_pol2[i_chan]/sigma_y_pol2[i_chan] < 1.5, x_center_pol2[i_chan] > -0.5):
        x_center[i_chan] = x_center_pol2[i_chan]
        y_center[i_chan] = y_center_pol2[i_chan]
        polarization[i_chan] = 2
        polarization_ratio[i_chan] = amplitude_pol1[i_chan] / amplitude_pol2[i_chan]
      else:
        x_center[i_chan] = -1.e9
        x_center_pol2[i_chan] = -1.e9
        
else:
  map_xpos_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_map_xpos.npy')
  map_ypos_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_map_ypos.npy')
  map_val_pol1 = np.load('data/' + file_stub_pol1 + '/' + date_pol1 + '_map_val.npy')
  map_xpos_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_map_xpos.npy')
  map_ypos_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_map_ypos.npy')
  map_val_pol2 = np.load('data/' + file_stub_pol2 + '/' + date_pol2 + '_map_val.npy')

  #get the map positions and make an array for them
  map_xpos_uniq = np.unique(map_xpos_pol1)
  map_ypos_uniq = np.unique(map_ypos_pol1)
  n_xpos = np.size(map_xpos_uniq)
  n_ypos = np.size(map_ypos_uniq)

  x_center = np.zeros(np.size(chanmask))
  y_center = np.zeros(np.size(chanmask))
  amplitude_pol1 = np.zeros(np.size(chanmask))
  amplitude_pol2 = np.zeros(np.size(chanmask))
  polarization = np.zeros(np.size(chanmask))
  polarization_ratio = np.zeros(np.size(chanmask))
  for i_chan in np.argwhere(chanmask == 1):
    this_val = np.ndarray.flatten(map_val_pol1[i_chan,:])
    max_index = np.argwhere(this_val == np.max(this_val))
    x_max = map_xpos_pol1[max_index[0]]
    y_max = map_ypos_pol1[max_index[0]]
    separation = np.sqrt((map_xpos_pol1 - x_max[0])**2 + (map_ypos_pol1 - y_max[0])**2)
    index = np.argwhere(separation < 2.)
    x_center_pol1 = np.sum(map_xpos_pol1[index]*this_val[index]) / np.sum(this_val[index])
    y_center_pol1 = np.sum(map_ypos_pol1[index]*this_val[index]) / np.sum(this_val[index])
    amplitude_pol1[i_chan] = np.sum(this_val[index]) / fres[i_chan]

    this_val = np.ndarray.flatten(map_val_pol2[i_chan,:])
    max_index = np.argwhere(this_val == np.max(this_val))
    x_max = map_xpos_pol2[max_index[0]]
    y_max = map_ypos_pol2[max_index[0]]
    separation = np.sqrt((map_xpos_pol2 - x_max[0])**2 + (map_ypos_pol2 - y_max[0])**2)
    index = np.argwhere(separation < 2.)
    x_center_pol2 = np.sum(map_xpos_pol2[index]*this_val[index]) / np.sum(this_val[index])
    y_center_pol2 = np.sum(map_ypos_pol2[index]*this_val[index]) / np.sum(this_val[index])
    amplitude_pol2[i_chan] = np.sum(this_val[index]) / fres[i_chan]

    if amplitude_pol1[i_chan] > amplitude_pol2[i_chan]:
      x_center[i_chan] = x_center_pol1
      y_center[i_chan] = y_center_pol1
      polarization[i_chan] = 1
      polarization_ratio[i_chan] = amplitude_pol2[i_chan] / amplitude_pol1[i_chan]
    else:
      x_center[i_chan] = x_center_pol2
      y_center[i_chan] = y_center_pol2
      polarization[i_chan] = 2
      polarization_ratio[i_chan] = amplitude_pol1[i_chan] / amplitude_pol2[i_chan]



pdf_file_name = 'data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_combined_beammap.pdf'
with PdfPages(pdf_file_name) as pdf:

#  pol1 = np.argwhere((polarization == 1) & (polarization_ratio < 0.2))
#  pol1 = np.argwhere((polarization == 1) & (amplitude_pol1 > 0.1))
  pol1 = np.argwhere(polarization == 1)
#  pol2 = np.argwhere((polarization == 2) & (polarization_ratio < 0.2))
#  pol2 = np.argwhere((polarization == 2) & (amplitude_pol2 > 0.1))
  pol2 = np.argwhere(polarization == 2)
  plt.scatter(x_center[pol2], y_center[pol2], marker='x', color='blue')
#  for i_pol in pol2:
#    plt.text(x_center[i_pol[0]], y_center[i_pol[0]], "{}".format(i_pol[0]),color='blue', fontsize=5.)
  plt.scatter(x_center[pol1], y_center[pol1], marker='+', color='red')
#  for i_pol in pol1:
#    plt.text(x_center[i_pol[0]], y_center[i_pol[0]], "{}".format(i_pol[0]),color='red', fontsize=5.)
  if Telescope:
    plt.xlim(-1.3,1.1)
    plt.ylim(87.8,90.2)
  else:
    plt.xlim(0,28)
    plt.ylim(28,0)
#  plt.axis('equal')
  plt.xlabel('AZ Position (deg)')
  plt.ylabel('ZA Position (deg)')
  pdb.set_trace()
  pdf.savefig()
  plt.close()

#  index = np.concatenate((pol1,pol2),axis=None)
#  xval = np.concatenate((x_center[pol1],x_center[pol2]),axis=None)
#  yval = np.concatenate((y_center[pol1],y_center[pol2]),axis=None)


  #get rid of center position and angle
  x_center = x_center - np.median(x_center)
  y_center = y_center - np.median(y_center)
  rot = 1./90.*np.pi/2.
  x_center = x_center * np.cos(rot) - y_center * np.sin(rot)
  y_center = x_center * np.sin(rot) + y_center * np.cos(rot)
  
  index = np.concatenate((pol1),axis=None)
  xval = np.concatenate((x_center[pol1]),axis=None)
  yval = np.concatenate((y_center[pol1]),axis=None)
  ampl = np.concatenate((amplitude_pol1[pol1]),axis=None)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_channel_index_1.npy',index)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_x_position_1.npy',xval)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_y_position_1.npy',yval)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_amplitude_1.npy',ampl)

  index = np.concatenate((pol2),axis=None)
  xval = np.concatenate((x_center[pol2]),axis=None)
  yval = np.concatenate((y_center[pol2]),axis=None)
  ampl = np.concatenate((amplitude_pol2[pol2]),axis=None)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_channel_index_2.npy',index)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_x_position_2.npy',xval)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_y_position_2.npy',yval)
  np.save('data/' + file_stub_pol1 + '/' + file_stub_pol1 + '_amplitude_2.npy',ampl)

#  x_center = x_center - np.median(x_center)
#  y_center = y_center - np.median(y_center)
#  ang = np.pi/8.5
#  x_center = x_center * np.cos(ang) + y_center * np.sin(ang)
#  y_center = -x_center * np.sin(ang) + y_center * np.cos(ang)
  plt.scatter(x_center[pol2], y_center[pol2], marker='x', color='blue')
  plt.scatter(x_center[pol1], y_center[pol1], marker='+', color='red')
  plt.xlim([-1.2,1.2])
  plt.ylim([-1.2,1.2])
#  plt.axis('equal')
  plt.xlabel('X Position (deg)')
  plt.ylabel('Y Position (deg)')
  pdf.savefig()
  plt.close()

  
  
