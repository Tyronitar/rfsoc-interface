import numpy as np
import h5py
from onrkidpy import get_yymmdd
import glob
import pdb
import sys
import warnings
warnings.filterwarnings('ignore', message='Casting complex values to real discards the imaginary part')
warnings.filterwarnings('ignore', message='divide by zero encountered in true_divide')
warnings.filterwarnings('ignore', message = 'divide by zero encountered in divide')

sys.path.append("/home/onrkids/readout/host")
import data_handler

def compute_frequency_direction(losweep):

    #Get some needed global values
    delta_f = np.real(losweep[0,0,1] - losweep[0,0,0])
    n_freq = np.size(losweep[0,0,:])
    n_chan = np.size(losweep[0,:,0])
    mid_ind = n_freq // 2

    #we'll fit a polynomial to the I and Q data versus frequency. deriv_length
    #gives the number of samples on either side of the tone frequency to use and
    #fit_order gives the order of the polynomial fit
    fit_order = 3
    deriv_length = 5    

    #perform the fit and then compute the derivative to obtain dI/df and dQ/df
    dI_df = np.zeros(n_chan)
    dQ_df = np.zeros(n_chan)
    edge_indices = [mid_ind-deriv_length, mid_ind+deriv_length+1]
    ind_val = np.arange(edge_indices[0],edge_indices[1])
    for i_chan in range(0,n_chan):
        fit_I = np.polyfit(ind_val, np.real(losweep[1,i_chan,edge_indices[0]:edge_indices[1]]), fit_order)
        fit_I_deriv = np.polyder(fit_I)
        dI_df[i_chan] = np.polyval(fit_I_deriv, mid_ind) / delta_f
        fit_Q = np.polyfit(ind_val, np.imag(losweep[1,i_chan,edge_indices[0]:edge_indices[1]]), fit_order)
        fit_Q_deriv = np.polyder(fit_Q)
        dQ_df[i_chan] = np.polyval(fit_Q_deriv, mid_ind) / delta_f
    return dI_df, dQ_df

def compute_df_per_mK(beam_pol, detector_beam_ampl, detector_f, dfoverf_per_mK):

    valid_index = np.ndarray.flatten(np.argwhere(beam_pol >= 1))
    min_ampl = np.percentile(detector_beam_ampl[valid_index], 10)
    low_ampl_ind = np.argwhere(np.array(detector_beam_ampl[valid_index]) < min_ampl)
    for i in low_ampl_ind:
        detector_beam_ampl[valid_index[i[0]]] = min_ampl
    detector_beam_ampl[valid_index] = detector_beam_ampl[valid_index] / np.median(detector_beam_ampl[valid_index])
    df_per_mK = dfoverf_per_mK * detector_f * detector_beam_ampl
    return df_per_mK

def create_processed_file(date, setnum, azel=True, optcam = False):

    #20230803_rfsoc1_TOD_set1012
    todtemplate = f"/data/{date}/{date}_*_TOD_set{setnum}.h5"
    tele_template = f"/data/{date}/{date}_AZEL_set{setnum}.h5"
    optcam_template = f"/data/{date}/{date}_optcam_set{setnum}.h5"

    if azel:
      azel = h5py.File(tele_template, 'r')
      
    if optcam:
      optcam = h5py.File(optcam_template, 'r')
      
  	# Create processed data file
    pfile = h5py.File(f"/data/{date}/{date}_processed_data_set{setnum}.h5", 'w') # note that this overwrites!
    
    

    

    # print(todlist)
    todlist = glob.glob(todtemplate)

    if len(todlist) == 0:
        print("no TOD files found")
        return
    if azel:
      az_tel = azel['az_tel'][:]
      el_tel = azel['el_tel'][:]
      timestamp_tel = azel['timestamp_tel'][:]
      vis = azel['optical_visibility'][:]
      
      
    if optcam:
      optcam = optcam['optical_image'][:]


    dI_df = np.array([])
    dQ_df = np.array([])
    df_per_mK = np.array([])
    data_f = 0
    data_diss = 0
    data_mK = 0
    chanmask = np.array([], dtype=np.int32)
    detector_pol = np.array([])
    detector_az = 0
    detector_el = 0
    # Iterate over the TOD Files
    for file in todlist:

        #compute the derivatives to obtain frequency direction
        f = data_handler.RawDataFile(file, 'r')
        curr_losweep = f.lo_sweep[:]
        this_dI_df, this_dQ_df = compute_frequency_direction(curr_losweep)
        dI_df = np.concatenate((dI_df, this_dI_df))
        dQ_df = np.concatenate((dQ_df, this_dQ_df))
    
        #compute the calibration factor from dfoverf to mK
        detector_pol = f.detector_pol[:]
        detector_beam_ampl = f.detector_beam_ampl[:]
        dfoverf_per_mK = f.dfoverf_per_mK[:]
        detector_f = f.baseband_freqs[:] + f.lo_freq[:]
        this_df_per_mK = compute_df_per_mK(detector_pol, detector_beam_ampl, detector_f, dfoverf_per_mK)
        df_per_mK = np.concatenate((df_per_mK,this_df_per_mK))

        #create the calibrated datastreams-----------------------------------------------------------
        #first get the I and Q data
        data_I = np.ndarray.astype(f.adc_i[:], np.float64)
        data_Q = np.ndarray.astype(f.adc_q[:], np.float64)
        nsamples = f.n_sample[0]
        ntones = f.n_tones[0]
        valid_tone_index = np.ndarray.flatten(np.argwhere(data_I[:,0] != 0.))
        valid_tone_index = valid_tone_index[:ntones]
        data_I = data_I[valid_tone_index,:]
        data_Q = data_Q[valid_tone_index,:]
        data_I = data_I - np.outer(np.mean(data_I, axis = 1), np.ones(nsamples))
        data_Q = data_Q - np.outer(np.mean(data_Q, axis = 1), np.ones(nsamples))
        
        #pdb.set_trace()

        #now use the derivatives to convert to a frequency shift
        #need to optimally weight the data based on the response
        #in each direction (assuming the noise is identical in I and Q)
        #this will then yield data_f
        this_dI_df = np.array(this_dI_df)
        this_dQ_df = np.array(this_dQ_df)
        eqiv_var_I = np.outer((1. / this_dI_df)**2., np.ones(nsamples))
        eqiv_var_Q = np.outer((1. / this_dQ_df)**2., np.ones(nsamples))
        this_data_f = ( (data_I / np.outer(this_dI_df, np.ones(nsamples)) ) / eqiv_var_I + \
                        (data_Q / np.outer(this_dQ_df, np.ones(nsamples)) ) / eqiv_var_Q ) / \
                      (1./eqiv_var_I + 1./eqiv_var_Q)
        this_data_diss = ( (data_I / np.outer(-this_dQ_df, np.ones(nsamples)) ) / eqiv_var_Q + \
                        (data_Q / np.outer(this_dI_df, np.ones(nsamples)) ) / eqiv_var_I ) / \
                      (1./eqiv_var_I + 1./eqiv_var_Q)
        if np.size(data_f) != 1:
            data_f = np.concatenate((data_f, this_data_f), axis=0)
            data_diss = np.concatenate((data_diss, this_data_diss), axis=0)
        else:
            data_f = np.copy(this_data_f)
            data_diss = np.copy(this_data_diss)
#        del eqiv_var_I, eqiv_var_Q, data_I, data_Q

        #finally, we need to get data_mK
        this_df_per_mK = np.array(this_df_per_mK)
        this_data_mK = np.divide(this_data_f, np.outer(this_df_per_mK, np.ones(nsamples)))
        if np.size(data_mK) != 1:
            data_mK = np.concatenate((data_mK, this_data_mK), axis=0)
        else:
            data_mK = np.copy(this_data_mK)
#        del this_data_f, this_data_mK
#        import matplotlib.pyplot as plt
#        pdb.set_trace()

        #now the telescope data to get coordinates
        time = f.timestamp[:]
        time_0 = time - time[0]
        total_time = np.max(time_0)
        n_samples = np.size(time)
        timestamp_adc = np.arange(0,total_time,total_time/n_samples) + time[0]
        if azel:
            detector_dx_dy_elevation_angle = f.detector_dx_dy_elevation_angle[0]
            this_az_tel = np.interp(timestamp_adc, timestamp_tel, az_tel)
            this_el_tel = np.interp(timestamp_adc, timestamp_tel, el_tel)
            this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_el_tel)
            this_detector_delta_x = f.detector_delta_x[:]
            this_detector_delta_y = f.detector_delta_y[:]
            this_det_az = np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                          np.outer(this_detector_delta_y,np.sin(this_ang)) + \
                          np.outer(np.ones(ntones), this_az_tel)
            this_det_el = np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                          np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                          np.outer(np.ones(ntones), this_el_tel)
        
            #save the az/el information to the file
            if np.size(detector_az) != 1:
                detector_az = np.concatenate((detector_az, this_det_az), axis=0)
            else:
                detector_az = np.copy(this_det_az)
            if np.size(detector_el) != 1:
                detector_el = np.concatenate((detector_el, this_det_el), axis=0)
            else:
                detector_el = np.copy(this_det_el)
        else:
            detector_az = 0.
            detector_el = 0.
            vis=0.

        #also save the chanmask and detector polarization information
        chanmask = np.concatenate((chanmask, f.chanmask[:]))
        no_pol = np.ndarray.flatten(np.argwhere(detector_pol < 1))
        if np.size(no_pol > 0):
            chanmask[no_pol] = -1
#        detector_pol = np.concatenate((detector_pol, f.detector_pol[:]))

#    print(dI_df.shape, dQ_df.shape, df_per_mK.shape, data_f.shape, data_mK.shape)
    pfile.create_dataset("dI_df", data=dI_df)
    pfile.create_dataset("dQ_df", data=dQ_df)
    pfile.create_dataset("df_per_mK", data=df_per_mK)
    pfile.create_dataset("data_f", data=data_f)
    pfile.create_dataset("data_diss", data=data_diss)
    pfile.create_dataset("data_mK", data=data_mK)
    pfile.create_dataset("chanmask", data=chanmask)
    pfile.create_dataset("detector_pol", data=detector_pol)
    pfile.create_dataset("detector_az", data=detector_az)
    pfile.create_dataset("detector_el", data=detector_el)
    pfile.create_dataset("timestamp", data=timestamp_adc)
    pfile.create_dataset("optical_visibility", data=vis)

    # close the hdf file
    pfile.close()


if __name__ == "__main__":
    create_processed_file("20230804", "1008")
