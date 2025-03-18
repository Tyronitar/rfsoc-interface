import numpy as np
import pdb
import random
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as colors
import time
import glob
from datetime import date, datetime
import sys, os
from scipy import signal, ndimage, fftpack, ndimage
import h5py
import math
from sklearn.cluster import DBSCAN
from scipy.optimize import curve_fit
from scipy import stats
#from plotWindow.plotWindow import plotWindow
import warnings
warnings.filterwarnings('ignore', message='No contour levels*')
warnings.filterwarnings('ignore', message='invalid value encountered in true_divide')
warnings.filterwarnings('ignore', message='invalid value encountered in subtract')

#new function to actually call to make the map
def create_map(date, setnum, map_param_file = 'Default_map_params'):

    #eventually we'll do this with params file
    downsample_factor = 6
    hp_filt_freq = 0.5
    lp_filt_freq = 10.
    az_trim = 2.3
    el_trim = 0.2
    map_dpix = 0.04
    Gauss_smooth_sigma = [0.5,0.33]
#    visibility = '****'
    Point_Loma_pickup_flagging = True

    #get all the data from the file
    processed_file = f"/data/{date}/{date}_processed_data_set{setnum}.h5"
    file_stub = f"{date}_set{setnum}"
    main_path = f"/data/{date}/"
    f = h5py.File(processed_file, 'r')
    data_raw = f['data_mK'][()]
    detector_az = f['detector_az'][()]
    detector_el = f['detector_el'][()]
    chanmask = f['chanmask'][()]
    detector_pol = f['detector_pol'][()]
    visibility = str(f['optical_visibility'][0])
    optical_image = f['optical_image'][()]

    time = f['timestamp'][()]
    time_raw = time
    time = time - time[0]

    #see if we need to flag pickup
    if Point_Loma_pickup_flagging:
        pickup_good_index = remove_Point_Loma_pickup(data_raw, chanmask, downsample_factor, time)
    else:
        pickup_good_index = []

    #clean the data
    clean_data, time_ds, detector_az_ds, detector_el_ds = \
                clean_tod(data_raw, downsample_factor, time, \
                          hp_filt_freq, lp_filt_freq, detector_az, detector_el, chanmask)
    fs_ds = 1./time_ds[1]
    cfile = h5py.File(f"/data/{date}/{date}_cleaned_data_set{setnum}.h5", 'w') # note that this overwrites!
    cfile.create_dataset("chanmask", data=chanmask)
    cfile.create_dataset("detector_pol", data=detector_pol)
    cfile.create_dataset("clean_data", data=clean_data)
    cfile.create_dataset("time", data=time_ds)
    cfile.create_dataset("detector_az", data=detector_az_ds)    
    cfile.create_dataset("detector_el", data=detector_el_ds)
    cfile.close()
    
    #determine map size
    n_pix_x, n_pix_y, map_az, map_el = get_map_size(detector_az_ds, detector_el_ds, az_trim, el_trim, map_dpix)

    #now make a map of the first polarization
    sum_map_1 = np.zeros([n_pix_x,n_pix_y])
    hits_map_1 = np.zeros([n_pix_x,n_pix_y])
    channel_index_1 = np.ndarray.flatten(np.argwhere(detector_pol == 1))
    NETD_1 = np.zeros(int(np.size(channel_index_1)))
    for index, i_chan in enumerate(channel_index_1):

      if chanmask[i_chan] == 1:

        this_clean_data = clean_data[i_chan,:]
        this_detector_az = detector_az_ds[i_chan,:]
        this_detector_el = detector_el_ds[i_chan,:]
        sum_map_1, hits_map_1, NETD_1 = \
               bin_tod_into_map(sum_map_1, hits_map_1, NETD_1, map_dpix, index, this_clean_data, \
                     this_detector_az, this_detector_el, fs_ds, map_az, map_el, \
                     hp_filt_freq, lp_filt_freq, pickup_good_index = pickup_good_index)
    map_1 = sum_map_1 / hits_map_1
    map_1_filt = ndimage.gaussian_filter(map_1, Gauss_smooth_sigma, mode='reflect', truncate = 1./Gauss_smooth_sigma[1])
    valid_cov_1 = np.argwhere(hits_map_1 > 0.5 * np.median(hits_map_1))
    map_goodcov_1 = np.zeros(np.size(valid_cov_1[:,0]))
    for i_cov in np.arange(np.size(valid_cov_1[:,0])):
        map_goodcov_1[i_cov] = map_1[valid_cov_1[i_cov,0],valid_cov_1[i_cov,1]]

    #and the second polarization
    sum_map_2 = np.zeros([n_pix_x,n_pix_y])
    hits_map_2 = np.zeros([n_pix_x,n_pix_y])
    channel_index_2 = np.ndarray.flatten(np.argwhere(detector_pol == 2))
    NETD_2 = np.zeros(int(np.size(channel_index_2)))
    for index, i_chan in enumerate(channel_index_2):

      if chanmask[i_chan] == 1:

        this_clean_data = clean_data[i_chan,:]
        this_detector_az = detector_az_ds[i_chan,:]
        this_detector_el = detector_el_ds[i_chan,:]
        sum_map_2, hits_map_2, NETD_2 = \
               bin_tod_into_map(sum_map_2, hits_map_2, NETD_2, map_dpix, index, this_clean_data, \
                     this_detector_az, this_detector_el, fs_ds, map_az, map_el, \
                     hp_filt_freq, lp_filt_freq, pickup_good_index = pickup_good_index)
    map_2 = sum_map_2 / hits_map_2
    map_2_filt = ndimage.gaussian_filter(map_2, Gauss_smooth_sigma, mode='reflect', truncate = 1./Gauss_smooth_sigma[1])
    valid_cov_2 = np.argwhere(hits_map_2 > 0.5 * np.median(hits_map_2))
    map_goodcov_2 = np.zeros(np.size(valid_cov_2[:,0]))
    for i_cov in np.arange(np.size(valid_cov_2[:,0])):
        map_goodcov_2[i_cov] = map_2[valid_cov_2[i_cov,0],valid_cov_2[i_cov,1]]

    #and then the combined map of total intensity
    map_tot = (sum_map_1 + sum_map_2) / (hits_map_1 + hits_map_2)
    map_tot_filt = ndimage.gaussian_filter(map_tot, Gauss_smooth_sigma, mode='reflect', truncate = 1./Gauss_smooth_sigma[1])

    #Sage's source detection code---------------------------------------------------------------------------------------------

    #flatten the maps for processing
    map_1_filt_flat_array = np.array(map_1_filt).flatten()
    map_2_filt_flat_array = np.array(map_2_filt).flatten()
    map_tot_filt_flat_array = np.array(map_tot_filt).flatten()

    #get rid of nans
    map_1_filt_flat_array_of_nans_removed= [x for x in map_1_filt_flat_array if math.isnan(x)]
    map_2_filt_flat_array_of_nans_removed= [x for x in map_2_filt_flat_array if math.isnan(x)]
    map_tot_filt_flat_array_of_nans_removed= [x for x in map_tot_filt_flat_array if math.isnan(x)]
    map_1_filt_pixel_values = np.array([x for x in map_1_filt_flat_array if not math.isnan(x)])
    map_2_filt_pixel_values = np.array([x for x in map_2_filt_flat_array if not math.isnan(x)])
    map_tot_filt_pixel_values = np.array([x for x in map_tot_filt_flat_array if not math.isnan(x)])
    map_1_filt_intial_length = len(map_1_filt_pixel_values)
    map_2_filt_intial_length = len(map_2_filt_pixel_values)
    map_tot_filt_intial_length = len(map_tot_filt_pixel_values)

    #first the outlier removal
    map_1_filt_with_rejection, map_1_filt_outlier_pixels = outlier_removal(map_1_filt_pixel_values)
    map_2_filt_with_rejection, map_2_filt_outlier_pixels = outlier_removal(map_2_filt_pixel_values)
    map_tot_filt_with_rejection, map_tot_filt_outlier_pixels = outlier_removal(map_tot_filt_pixel_values)
    map_1_filt_flagged_values, map_1_filt_basic_removal_map, map_1_filt_contour_levels = \
        basic_map_removal(map_1_filt_outlier_pixels, map_1_filt_flat_array_of_nans_removed, map_1_filt_flat_array)
    map_2_filt_flagged_values, map_2_filt_basic_removal_map, map_2_filt_contour_levels = \
        basic_map_removal(map_2_filt_outlier_pixels, map_2_filt_flat_array_of_nans_removed, map_2_filt_flat_array)
    map_tot_filt_flagged_values, map_tot_filt_basic_removal_map, map_tot_filt_contour_levels = \
        basic_map_removal(map_tot_filt_outlier_pixels, map_tot_filt_flat_array_of_nans_removed, map_tot_filt_flat_array)

    #apply DBscan
    map_1_filt_flagged_values_after_dbscan, map_1_filt_DBSCAN_map = \
        DBSCAN_map(map_1_filt_flagged_values, map_1_filt_flat_array)
    map_2_filt_flagged_values_after_dbscan, map_2_filt_DBSCAN_map = \
        DBSCAN_map(map_2_filt_flagged_values, map_2_filt_flat_array)
    map_tot_filt_flagged_values_after_dbscan, map_tot_filt_DBSCAN_map = \
        DBSCAN_map(map_tot_filt_flagged_values, map_tot_filt_flat_array)
    if np.size(map_1_filt_flagged_values_after_dbscan) == 0:
        map_1_filt_flagged_values_after_dbscan = np.asarray([np.max(map_1_filt)])
    if np.size(map_2_filt_flagged_values_after_dbscan) == 0:
        map_2_filt_flagged_values_after_dbscan = np.asarray([np.max(map_2_filt)])
    if np.size(map_tot_filt_flagged_values_after_dbscan) == 0:
        map_tot_filt_flagged_values_after_dbscan = np.asarray([np.max(map_tot_filt)])
    map_1_filt_filtered_flagged_values, map_1_filt_filtered_map, map_1_filt_filtered_map_nans = \
        neighbor_removal(map_1_filt_flagged_values_after_dbscan, np.array(map_1_filt))
    map_2_filt_filtered_flagged_values, map_2_filt_filtered_map, map_2_filt_filtered_map_nans = \
        neighbor_removal(map_2_filt_flagged_values_after_dbscan, np.array(map_2_filt))
    map_tot_filt_filtered_flagged_values, map_tot_filt_filtered_map, map_tot_filt_filtered_map_nans = \
        neighbor_removal(map_tot_filt_flagged_values_after_dbscan, np.array(map_tot_filt))

    map_1_filt_final_map, map_1_filt_final_map= neighbor_flagging(map_1_filt_filtered_flagged_values, map_1_filt, map_1_filt_flat_array)
    map_2_filt_final_map, map_2_filt_final_map= neighbor_flagging(map_2_filt_filtered_flagged_values, map_2_filt, map_2_filt_flat_array)
    map_tot_filt_final_map, map_tot_filt_final_map= neighbor_flagging(map_tot_filt_filtered_flagged_values, map_tot_filt, map_tot_filt_flat_array)

    mfile = h5py.File(f"/data/{date}/{date}_mapped_data_set{setnum}.h5", 'w') # note that this overwrites!
    integration_time_1 = np.flip(np.transpose(hits_map_1[::-1])*np.median(NETD_1)**2./fs_ds,1)
    integration_time_2 = np.flip(np.transpose(hits_map_2[::-1])*np.median(NETD_2)**2./fs_ds,1)
    mfile.create_dataset("map_az", data=map_az)
    mfile.create_dataset("map_el", data=map_el)
    mfile.create_dataset("map_pol_1", data=np.flip(np.transpose(map_1[::-1]),1))
    mfile.create_dataset("map_pol_2", data=np.flip(np.transpose(map_2[::-1]),1))
    mfile.create_dataset("map_tot", data=np.flip(np.transpose(map_tot[::-1]),1))
    mfile.create_dataset("map_pol_1_smoothed", data=np.flip(np.transpose(map_1_filt[::-1]),1))
    mfile.create_dataset("map_pol_2_smoothed", data=np.flip(np.transpose(map_2_filt[::-1]),1))
    mfile.create_dataset("map_tot_smoothed", data=np.flip(np.transpose(map_tot_filt[::-1]),1))
    mfile.create_dataset("map_pol_1_integration", data=integration_time_1)
    mfile.create_dataset("map_pol_2_integration", data=integration_time_2)
    mfile.create_dataset("map_tot_integration", data=integration_time_1+integration_time_2)
    mfile.close()
    
    #Optical camera determine pixel scale
        #Aspect Ratio 4/3
        #Sensorsize 5.76mm by 4.29mm
        #lens focal length is 12mm
        #horizontal crop factor is 6.25
        #vertical crop factor is 5.59
        #effective horizontal focal length is 75 mm
        #effective vertical focal length is 67 mm
        #horizontal FOV is 27.0 degrees
        #vertical FOV is 20.4 degrees 
        #total pixel count 2592 (H) × 1944 (V)
        #horizontal pixel size 0.0104 degrees
        #vertical pixel size (same)
    
    opt_npix_per_tel_npix = map_dpix/0.0104
    opt_npix_az = int(np.size(map_az)*opt_npix_per_tel_npix/2)*2
    opt_npix_el = int(np.size(map_el)*opt_npix_per_tel_npix/2)*2
    opt_center_az = int(2592/2)+70
    opt_center_el = int(1944/2)+10
    optical_image = optical_image[opt_center_el-int(opt_npix_el/2):opt_center_el+int(opt_npix_el/2),\
                                  opt_center_az-int(opt_npix_az/2):opt_center_az+int(opt_npix_az/2)]
    

    maps_to_screen(map_az, map_el, az_trim, el_trim, map_1_filt, map_2_filt, map_tot_filt, NETD_1, NETD_2, map_dpix, \
                   map_goodcov_1, map_goodcov_2, map_1_filt_final_map, map_2_filt_final_map, map_tot_filt_final_map, \
                   file_stub, main_path, time_raw, visibility, map_1_filt_intial_length, map_2_filt_intial_length, \
                   map_tot_filt_intial_length, map_1, map_2, map_tot,optical_image)
  
#Function that goes from TOD to map-----------------------------------------------------------------------------------------------------
def bin_tod_into_map(sum_map, hits_map, NETD, map_dpix, index, data_cleaned, detector_az, detector_el, fs, \
                     map_az, map_el, hp_filt_freq, lp_filt_freq, pickup_good_index = []):

    #get the good samples if they haven't been specified
    if np.size(pickup_good_index) == 0:
      pickup_good_index = np.arange(np.size(data_cleaned))

    #compute NETD in white noise regime
    wind = signal.get_window('hamming', np.size(data_cleaned))
    this_freq, this_psd = signal.periodogram(data_cleaned, fs, window=wind)
    valid_freq = np.where(np.logical_and(this_freq>hp_filt_freq,this_freq<lp_filt_freq))
    NETD[index] = np.sqrt(np.median(this_psd[valid_freq]))
#    NETD[index] = np.sqrt(np.median(this_psd[-int(np.size(this_psd)/2):]*30.))
    weight = 1./NETD[index]**2.
 
    #get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
    x_ind = np.round((detector_az-map_az[0])/map_dpix)
    x_ind = x_ind.astype('int64')
    y_ind = np.round((detector_el-map_el[0])/map_dpix)
    y_ind = y_ind.astype('int64')

    #eliminate samples outside the map
    valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
        np.logical_and(x_ind[pickup_good_index] >= 0, x_ind[pickup_good_index] < np.size(sum_map[:,0])), \
        np.logical_and(y_ind[pickup_good_index] >= 0, y_ind[pickup_good_index] < np.size(sum_map[0,:])))))
    pickup_good_index = pickup_good_index[valid_index]

#    pdb.set_trace()
    #loop over samples to create sum and hits maps
    for time_sample in pickup_good_index:
      sum_map[x_ind[time_sample],y_ind[time_sample]] += data_cleaned[time_sample] * weight
      hits_map[x_ind[time_sample],y_ind[time_sample]] += 1. * weight

    return sum_map, hits_map, NETD

#Function that cleans timestream data -----------------------------------------------------------------------------------------------------
def clean_tod(data_raw, downsample_factor, time, hp_filt_freq, lp_filt_freq, detector_az, detector_el, chanmask):

    #Setup filters that will be used later
    #get the sampling frequency and make a window that can be
    #used later for the power spectrum computation
    dtime = time - np.roll(time,1)
    fs = float(1./np.median(dtime))
    hpfilt_sos = signal.butter(6, hp_filt_freq, 'hp', fs=fs/downsample_factor, output='sos', analog=False)
    lpfilt_sos = signal.butter(6, lp_filt_freq, 'lp', fs=fs/downsample_factor, output='sos', analog=False)

    #downsample the data and apply hp filter
    data_ds = signal.decimate(data_raw, downsample_factor)
    data_filt_1 = signal.sosfiltfilt(hpfilt_sos, data_ds)
    data_filt = signal.sosfiltfilt(lpfilt_sos, data_filt_1)

    #average template subtraction
    goodchan = np.ndarray.flatten(np.argwhere(chanmask == 1))
    data_filt_chanmask = data_filt[goodchan,:]
    template = np.sum(data_filt_chanmask, axis=0)
    template = template - np.mean(template)
    template_corr = np.sum(np.multiply(data_filt_chanmask,template), axis=1) / \
                    np.sum(np.multiply(template,template))
    data_clean_chanmask = data_filt_chanmask - np.outer(template_corr, template)
    data_clean = data_filt
    data_clean[goodchan,:] = data_clean_chanmask

    #downsample ancillary data
    time_ds = signal.decimate(time, downsample_factor)
    detector_az_ds = signal.decimate(detector_az, downsample_factor, n=5, axis=1)
    detector_el_ds = signal.decimate(detector_el, downsample_factor, n=5, axis=1)

    return data_clean, time_ds, detector_az_ds, detector_el_ds

#Function to get map size  -----------------------------------------------------------------------------------------------------
def get_map_size(detector_az, detector_el, az_trim, el_trim, map_dpix):

    max_az = np.max(detector_az) - az_trim
    min_az = np.min(detector_az) + az_trim
    max_el = np.max(detector_el) - el_trim
    min_el = np.min(detector_el) + el_trim
    n_pix_x = int(np.ceil((max_az - min_az) / map_dpix))
    n_pix_y = int(np.ceil((max_el - min_el) / map_dpix))
    map_x = np.arange(n_pix_x)*map_dpix + min_az + map_dpix/2.
    map_y = np.arange(n_pix_y)*map_dpix + min_el + map_dpix/2. + 0.1 #0.1 accounts for assymmetry in array

    return n_pix_x, n_pix_y, map_x, map_y

#Have some kind of pickup at the Point Loma site-----------------------------------------------------------------------------------
def remove_Point_Loma_pickup(data_raw, chanmask, downsample_factor, time):

    #need to high pass filter the data to remove basline drift
    pickup_hp_filt_freq = 1
    dtime = time - np.roll(time,1)
    fs = float(1./np.median(dtime))
    pickup_hpfilt_sos = signal.butter(6, pickup_hp_filt_freq, 'hp', fs=fs, output='sos', analog=False)

    #sum all the data at each time sample, then look for outliers in this sum
    data_sum_raw = np.zeros(np.size(data_raw[0,:]))
    for i_chan in range(np.size(chanmask)):
        if chanmask[i_chan] == 1:      
            data_sum_raw += np.abs(data_raw[i_chan,:])
    data_sum = signal.sosfiltfilt(pickup_hpfilt_sos, data_sum_raw)

    pickup_data = np.ndarray.flatten(np.argwhere(np.abs(data_sum) > 5.*np.median(np.abs(data_sum))))
    pickup_good_index = []
    valid_time = np.arange(np.size(data_sum))
    if np.size(pickup_data > 0):
        pickup_start = pickup_data[np.argwhere(pickup_data - np.roll(pickup_data,1) != 1)]
        pickup_end = pickup_data[np.argwhere(np.roll(pickup_data,-1) - pickup_data != 1)]
        for i_start in pickup_start:
            pickup_data = np.append(pickup_data, i_start - 1 - np.arange(10))
        for i_end in pickup_end:
            pickup_data = np.append(pickup_data, i_end + 1 + np.arange(10))
        pickup_data.sort()
        valid_pickup = np.ndarray.flatten(np.argwhere(np.bitwise_and(pickup_data >= 0,pickup_data < np.size(valid_time))))
        pickup_data = pickup_data[valid_pickup]
        pickup_good_index = [element for element in np.arange(np.size(valid_time)) if element not in pickup_data]
        pickup_good_index = np.divide(pickup_good_index[0::downsample_factor], downsample_factor)
        pickup_good_index = pickup_good_index.astype(int)

    return pickup_good_index

#Plot the maps to the screen--------------------------------------------------------------------------------------------------------------
def maps_to_screen(map_x, map_y, telescope_az, telescope_el, map_1_filt, map_2_filt, map_tot_filt, NETD_1, NETD_2, map_dpix, \
                   map_goodcov_1, map_goodcov_2, map_1_filt_final_map, map_2_filt_final_map, map_tot_filt_final_map, \
                   file_stub, main_path, time_raw, visibility, map_1_filt_intial_length, map_2_filt_intial_length, \
                   map_tot_filt_intial_length, map_1, map_2, map_tot,optical_image):

    cb_shrink = 0.95
    this_xlim = min(map_x),max(map_x)
    this_ylim = max(map_y),min(map_y)
    max_abs = np.max(np.abs(np.append(map_goodcov_1,map_goodcov_2)))*0.75
    valid_netd_1 = np.argwhere(NETD_1 > 0)
    med_NETD_1 = 1./np.sqrt(np.sum(1./NETD_1[valid_netd_1]**2)/np.size(valid_netd_1))
    valid_netd_2 = np.argwhere(NETD_2 > 0)
    med_NETD_2 = 1./np.sqrt(np.sum(1./NETD_2[valid_netd_2]**2)/np.size(valid_netd_2))

    #Sage's plotting code---------------------------------------------------------------------------------------------

    contour_levels, final_map_1_filt, final_map_2_filt, final_map_tot_filt, flagged_map_1_filt, flagged_map_2_filt, \
      flagged_map_tot_filt, final_flagged_coordinates = combined_map(map_1_filt_final_map, map_2_filt_final_map, map_tot_filt_final_map)

#    pw = plotWindow()
    this_fig = plt.figure(figsize=(15,7.5))
    plt.subplot(4,1,1)
    plt.imshow(np.flip(np.transpose(map_1[::-1]),1), \
      extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
      aspect='equal', vmin=-max_abs, vmax=max_abs, cmap='Blues_r')
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)
    plt.contour(np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
      extent=(min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), colors='red')
    plt.title(file_stub + '\n' + 'Local Time = ' + time.asctime(time.localtime(time_raw[0]-7500.)) + \
      ', Optical Visibility = ' + visibility + ' meters \n' + 'NETD V-Pol (30Hz) = ' + "{:.1f}".format(med_NETD_1) + \
      ' mK, ' + 'NETD H-Pol (30Hz) = ' + "{:.1f}".format(med_NETD_2) + ' mK')
    plt.ylabel('ZA (degrees)')
    plt.xlim(this_xlim), plt.ylim(this_ylim)

    plt.subplot(4,1,2)
    plt.imshow(np.flip(np.transpose(map_2[::-1]),1), \
      extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
      aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Reds_r')
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)
    plt.contour(np.flip(np.flip(np.transpose(flagged_map_2_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
      extent=(min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), colors='black')
    plt.ylabel('ZA (degrees)')
    plt.xlim(this_xlim), plt.ylim(this_ylim)

    plt.subplot(4,1,3)
    plt.imshow(np.flip(np.transpose(map_tot[::-1]),1), \
      extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
      aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Greys_r')
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
    plt.contour(np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
      extent=(min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), colors='red')
    plt.ylabel('ZA (degrees)')
    plt.xlim(this_xlim), plt.ylim(this_ylim)
    
    plt.subplot(4,1,4)
    valid_opt_pix = np.where(optical_image < 240)
    opt_vmax = 255. #np.percentile(optical_image[valid_opt_pix], 90)
    opt_vmin = -255. #np.percentile(optical_image[valid_opt_pix], 10)
    plt.imshow(optical_image, \
               extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
               aspect='equal', vmax=255, vmin=-255)
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label('Optical Signal (rgb)', rotation=270, labelpad=15)
    ##Need to match aspect ratio of plots (and get rid of colorbar).
    plt.xlabel('Azimuth (degrees)'), plt.ylabel('ZA (degrees)')
    plt.xlim(this_xlim), plt.ylim(this_ylim)
        
    this_fig.subplots_adjust(wspace=0, hspace=0)
    plt.show(block=False)
#    pw.addPlot("Raw Image", this_fig)
    plt.savefig(main_path + file_stub + '_Source_Finder_Image.png', bbox_inches='tight')

#     this_fig2 = plt.figure(figsize=(15,7.5))
#     plt.subplot(3,1,1)
#     plt.imshow(np.flip(np.transpose(map_1[::-1]),1), \
#       extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
#       aspect='equal', vmin=-max_abs, vmax=max_abs, cmap='Blues_r')
#     plt.title(file_stub + '\n' + 'Local Time = ' + time.asctime(time.localtime(time_raw[0]-7500.)) + \
#       ', Optical Visibility = ' + visibility + ' meters \n' + 'NETD V-Pol (30Hz) = ' + "{:.1f}".format(med_NETD_1) + \
#       ' mK, ' + 'NETD H-Pol (30Hz) = ' + "{:.1f}".format(med_NETD_2) + ' mK')
#     plt.ylabel('Zenith Angle (degrees)')
#     plt.xlim(this_xlim), plt.ylim(this_ylim)
#     cb = plt.colorbar(shrink=cb_shrink)
#     cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)

#     plt.subplot(3,1,2)
#     plt.imshow(np.flip(np.transpose(map_2[::-1]),1), \
#       extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
#       aspect='equal', vmin=-max_abs, vmax=max_abs, cmap='Reds_r')
#     plt.ylabel('Zenith Angle (degrees)')
#     plt.xlim(this_xlim), plt.ylim(this_ylim)
#     cb = plt.colorbar(shrink=cb_shrink)
#     cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)

#     plt.subplot(3,1,3)
#     plt.imshow(np.flip(np.transpose(map_tot[::-1]),1), \
#       extent = (min(map_x)-map_dpix/2.,max(map_x)+map_dpix/2,max(map_y)+map_dpix/2.,min(map_y)-map_dpix/2.), \
#       aspect='equal', vmin=-max_abs/2., vmax=max_abs/2., cmap='Greys_r')
#     plt.xlabel('Azimuth (degrees)'), plt.ylabel('Zenith Angle (degrees)')
#     plt.xlim(this_xlim), plt.ylim(this_ylim)
#     cb = plt.colorbar(shrink=cb_shrink)
#     cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
           
#     this_fig.subplots_adjust(wspace=0, hspace=0)
# #    plt.show(block=False)
# #    pw.addPlot("Source Identification Image", this_fig)
#     plt.savefig(main_path + file_stub + '_Raw_Image.png', bbox_inches='tight')
# #    pw.show(block=False)
    
#     this_fig3 = plt.figure(figsize=(15,7.5))

#     # First column
#     plt.subplot(3,2,1)
#     x_map_1_filt= histogram_info(final_map_1_filt, map_1_filt_intial_length,'map_1_filt')
#     plt.subplot(3,2,3)
#     x_map_2_filt= histogram_info(final_map_2_filt, map_2_filt_intial_length,'map_2_filt')
#     plt.subplot(3,2,5)
#     x_map_tot_filt= histogram_info(final_map_tot_filt, map_tot_filt_intial_length, 'map_tot_filt')

#     # Second column
#     plt.subplot(3,2,2)
#     KSTEST(final_map_1_filt, 'map_1_filt' ,x_map_1_filt)
#     plt.subplot(3,2,4)
#     KSTEST(final_map_2_filt,'map_2_filt' ,x_map_2_filt)
#     plt.subplot(3,2,6)
#     KSTEST(final_map_tot_filt, 'map_tot_filt',x_map_tot_filt)

#     this_fig.subplots_adjust(wspace=0, hspace=0)
# #    plt.show(block=False)
#     plt.savefig(main_path + file_stub + '_Histogram.png', bbox_inches='tight')

# #    pdb.set_trace()

#Sage's functions------------------------------------------------------------------------------------------------------------------------
def gaussian(x, mu, sigma, A):
    return A * np.exp(-(x - mu)**2 / (2 * sigma**2))

def outlier_removal(data):
    map_pixels= data
    counter=0
    outlier_pixels = []
    sigma = np.std(map_pixels)
    
    while np.any((map_pixels > 3*sigma) | (map_pixels < -3*sigma)):
        counter+= 1
        #print(f'************starting round {counter}************')
        for x in map_pixels:
            if x > 3*sigma or x < -3*sigma:
               outlier_pixels.append(x)
        map_pixels= [x for x in map_pixels if (x < 3*sigma) and (x > -3*sigma)]
        map_pixels=  np.array(map_pixels)
        sigma = np.std(map_pixels)
        #print(f'Max Pixel Value: {max(map_pixels):>5}', f'Min Pixel Value: {min(map_pixels):>10}')
        #print('Deviation:', sigma)
        if np.all((map_pixels < 3*sigma) & (map_pixels > -3*sigma)):
            final_pixels = map_pixels
        #print('done')
    if np.size(outlier_pixels) == 0:
        outlier_pixels = map_pixels[0:1].tolist()
        final_pixels = map_pixels[1:]
    return final_pixels, outlier_pixels

def histogram_info(data, original_length ,mapname):
    
    hist, bins, _ = plt.hist(data, bins=200, label='Data')
    initial_params = [np.mean(data), np.std(data), 0.053545]
    # Fit the curve to the histogram data
    params, _ = curve_fit(gaussian, bins[:-1], hist, p0=initial_params)

    # Generate x values for plotting the fitted curve
    x = np.linspace(bins[0], bins[-1], 100)

    # Plot the histogram
    plt.plot(x, gaussian(x, *params), 'r-', label='Fitted Curve')

    # Add labels and legend
    plt.xlabel('Value')
    plt.ylabel('Frequency')
    plt.title('Histogram of '+ mapname +' Pixel Values without Target Signal and Fitted Curve')
    plt.legend()

    legend_text = [
        'Mean: {:.2f}'.format(params[0]),
        'Median: {:.2f}'.format(np.median(data)),
        'Sigma: {:.2f}'.format(abs(params[1])),
        'Total Pixels Removed: {}'.format(original_length - len(data))
    ]

    # Add text annotations to the plot
    plt.text(0.68, 0.62, '\n'.join(legend_text), transform=plt.gca().transAxes, bbox=dict(facecolor='white', alpha=0.8))
    return x

def KSTEST(data, mapname, x):
    
    mean= np.mean(data)
    sigma= np.std(data)

    plt.plot(x, stats.norm.cdf(x, loc = np.median(data), scale= np.std(data)), label= 'gaussian cdf')

    sorted_vals = np.sort(data)
    cdf_vals = (np.arange(np.size(sorted_vals)) + 1)/np.size(sorted_vals)

    plt.plot(sorted_vals, cdf_vals, label='measured values')
    plt.legend()
    p_value, D_stat= stats.kstest((data-mean)/sigma, stats.norm.cdf)
    legend_text = [
        'KS p-value: {:.5f}'.format(p_value),
        'KS statistic: {:.2E}'.format(D_stat)
    ]

    plt.text(0.0235, 0.725, '\n'.join(legend_text), transform=plt.gca().transAxes, bbox=dict(facecolor='white', alpha=0.8))
    plt.title(mapname + ' KS Test Guassian Fit')

def histogram_KSTEST(data, response):
   
    hist, bins, _ = plt.hist(data, bins=200, density=True, label='Data')

    initial_params = [np.mean(data), np.std(data), 0.053545]
    params, _ = curve_fit(gaussian, bins[:-1], hist, p0=initial_params)

    # Generate x values for plotting the fitted curve
    x = np.linspace(bins[0], bins[-1], 100)

    # Plot the histogram
    plt.plot(x, gaussian(x, *params), 'r-', label='Fitted Curve')

    # Add labels and legend
    plt.xlabel('Value')
    plt.ylabel('Frequency')
    plt.title('Histogram with Rejection and Fitted Curve')
    plt.legend()
    legend_text = [
    'Mean: {:.2f}'.format(params[0]),
    'Median: {:.2f}'.format(statistics.median(data)),
    'Sigma: {:.2f}'.format(abs(params[1])),
    'Pixels Removed: {}'.format(abs(params[1]))
]
     # Add text annotations to the plot
    plt.text(0.68, 0.67, '\n'.join(legend_text), transform=plt.gca().transAxes, bbox=dict(facecolor='white', alpha=0.8))
#    plt.show()
    
    if response=='yes':
        pass
    else: 
        return
   
    mean= np.mean(data)
    sigma= np.std(data)

    plt.plot(x, stats.norm.cdf(x, loc = np.median(data), scale= np.std(data)), label= 'gaussian cdf')

    sorted_vals = np.sort(data)
    cdf_vals = (np.arange(np.size(sorted_vals)) + 1)/np.size(sorted_vals)

    plt.plot(sorted_vals, cdf_vals, label='measured values')
    plt.legend()
    p_value, D_stat= stats.kstest((data-mean)/sigma, stats.norm.cdf)
    legend_text = [
        'KS p-value: {:.5f}'.format(p_value),
        'KS statistic: {:.2E}'.format(D_stat)
    ]
    plt.text(0.025, 0.75, '\n'.join(legend_text), transform=plt.gca().transAxes, bbox=dict(facecolor='white', alpha=0.8))
    plt.title(' KS Test Guassian Fit')
#    plt.show()
    
def basic_map_removal(outlier_pixels, nans_removed, map_pixels_copy):

    flagged_values = nans_removed + outlier_pixels  # Add any flagged values to this list

    # Create a copy of map for later use if needed
    basic_removal_map = np.copy(map_pixels_copy)

    for value in flagged_values:
        basic_removal_map[np.isclose(basic_removal_map, value)] = 1

    basic_removal_map[basic_removal_map != 1] = 0
    contour_levels = [1]
    return flagged_values, basic_removal_map, contour_levels

def DBSCAN_map(flagged_values, map_pixels_copy):

    # Create a copy of the map_pixels_copy array
    DBSCAN_map = np.copy(map_pixels_copy)

    # Find the indices of the flagged pixels
    flagged_indices = np.where(np.isin(DBSCAN_map, flagged_values))
    flagged_points = np.column_stack(flagged_indices)

    dbscan = DBSCAN(eps=3, min_samples=1)  # Adjust eps and min_samples as needed
    #**eps**: Two points are considered neighbors if the distance between the two points is below the threshold epsilon.
    #**min_samples**: The minimum number of neighbors a given point should have in order to be classified as a core point
    #(^^^ this includes the point itself) 
    labels = dbscan.fit_predict(flagged_points)

    # Extract the original values of pixels that are flagged in the map    
    flagged_pixel_values = DBSCAN_map[flagged_indices]

    # Create a new variable to store only the flagged values that pass the DBSCAN
    flagged_values_passing_dbscan = []

    # Iterate through each cluster label and mark the pixels that PASS the DBSCAN as 1s
    for cluster_label in np.unique(labels):
        if cluster_label == -1:  # Skip noise points
            continue

        cluster_indices = flagged_indices[0][labels == cluster_label]
        cluster_values = flagged_pixel_values[labels == cluster_label]

        # Check if the cluster has at least two samples (min_samples) to PASS the DBSCAN
        if len(cluster_values) >= 2:
            DBSCAN_map[cluster_indices] = 1
            # Add the values that passed DBSCAN to the new variable
            flagged_values_passing_dbscan.extend(cluster_values)


    DBSCAN_map[DBSCAN_map != 1] = 0
    
    flagged_values_passing_dbscan = np.array(flagged_values_passing_dbscan) #Newly flagged values
    
    return flagged_values_passing_dbscan, DBSCAN_map

def neighbor_removal(flagged_values, map_type):
    # Flatten map
    map_for_1s_and_0s= np.copy(map_type)
    map_for_nans= np.copy(map_type)
    map_flat= map_for_1s_and_0s.flatten()

    # empty list to store the indices of flagged pixels
    flagged_indices = []

    # Find the indices of the flagged values in the flattened map
    for value in flagged_values:
        flagged_indices.extend(np.where(map_flat == value)[0])

    # Convert these indices to 2D coordinates
    flagged_coords = np.unravel_index(flagged_indices, map_for_1s_and_0s.shape)

    indices_to_keep = []

    for i, coord in enumerate(zip(*flagged_coords)):
        distances = []
        for j, other_coord in enumerate(zip(*flagged_coords)):
            if i != j:
                distance = np.sqrt((coord[0] - other_coord[0])**2 + (coord[1] - other_coord[1])**2)
                distances.append(distance)
        if np.sum(np.array(distances) < 4) >= 3:
            indices_to_keep.append(i)

    # Create a new variable for the flagged values that meet the criteria
    filtered_flagged_values_passing_dbscan = [flagged_values[i] for i in indices_to_keep]

    # Now set the corresponding pixels in maps to NaN and 1
    for index in indices_to_keep:
        map_for_nans[flagged_coords[0][index], flagged_coords[1][index]] = np.nan
        map_for_1s_and_0s[flagged_coords[0][index], flagged_coords[1][index]] = 1

    map_for_1s_and_0s[map_for_1s_and_0s != 1] = 0
    return filtered_flagged_values_passing_dbscan, map_for_1s_and_0s, map_for_nans

def neighbor_flagging(flagged_values, map_type, map_pixels_copy):
    final_map = np.copy(map_pixels_copy)
    final_map = final_map.reshape(np.shape(map_type))
    final_map1 = np.copy(map_pixels_copy)
    final_map1 = final_map1.reshape(np.shape(map_type))


    # Define the margin and radius
    margin = 3
    radius = 4

    # Create a grid of indices
    x_indices, y_indices = np.indices(final_map.shape)

    # Iterate over all flagged values
    for value in flagged_values:
        # Find the indices of flagged pixels
        indices = np.where(np.isclose(final_map, value))

        for idx in range(len(indices[0])):
            x, y = indices[0][idx], indices[1][idx]

            # Skip flagged pixels near the borders
            if x < margin or x >= final_map.shape[0] - margin or y < margin or y >= final_map.shape[1] - margin:
                continue

            # Iterate through neighbors within the radius
            for i in range(-radius, radius+1):
                for j in range(-radius, radius+1):
                    # Check if the neighbor is within the circular radius
                    if i**2 + j**2 > radius**2:
                        continue

                    #neighbor coordinates
                    nx, ny = x + i, y + j

                    # Check if neighbor is within bounds and not too close to borders
                    if nx >= margin and nx < final_map.shape[0] - margin and ny >= margin and ny < final_map.shape[1] - margin:
                        final_map[nx, ny] = 1
                        final_map1[nx, ny] = np.nan

    final_map[final_map != 1] = 0
    return final_map, final_map1

def combined_map(flagged_map_1, flagged_map_2, flagged_map_3):
    
    final_final_map1= np.copy(flagged_map_1)
    final_final_map2= np.copy(flagged_map_2)
    final_final_map3= np.copy(flagged_map_3)

    # Convert all nans to boolean True
    nan_map_1 = np.isnan(flagged_map_1)
    nan_map_2 = np.isnan(flagged_map_2)
    nan_map_3 = np.isnan(flagged_map_3)

    # Combine the boolean maps such that if any pixel is flagged in any map, it is flagged in the combined map
    combined_nan_map = np.logical_or(np.logical_or(nan_map_1, nan_map_2), nan_map_3)
    
    # Get the coordinates of True values in the combined_nan_map
    flagged_positions = np.where(combined_nan_map)
    final_flagged_coords = list(zip(flagged_positions[0], flagged_positions[1]))

    # Apply this combined map to each of the final maps
    flagged_map_1[combined_nan_map] = 1
    flagged_map_2[combined_nan_map] = 1
    flagged_map_3[combined_nan_map] = 1

    flagged_map_1[flagged_map_1 != 1] = 0
    flagged_map_2[flagged_map_2 != 1] = 0
    flagged_map_3[flagged_map_3 != 1] = 0

    final_final_map1[combined_nan_map] = np.nan
    final_final_map2[combined_nan_map] = np.nan
    final_final_map3[combined_nan_map] = np.nan

    contour_levels = [1]

    final_final_map1= final_final_map1.flatten()
    final_final_map2= final_final_map2.flatten()
    final_final_map3= final_final_map3.flatten()

    final_final_map1 = [x for x in final_final_map1 if not math.isnan(x)]
    final_final_map2 = [x for x in final_final_map2 if not math.isnan(x)]
    final_final_map3 = [x for x in final_final_map3 if not math.isnan(x)]
    return contour_levels, final_final_map1, final_final_map2, final_final_map3, flagged_map_1, flagged_map_2, flagged_map_3, final_flagged_coords

