import numpy as np
import sys, os
import matplotlib.pyplot as plt
#sys.path.append(os.getcwd()+'/externals/scraps/')
#import scraps as scr
from matplotlib.backends.backend_pdf import PdfPages
#from PyPDF2 import PdfFileMerger
import glob
import pdb
import onrkidpy
from scipy.signal import savgol_filter
from scipy.optimize import curve_fit

def simple_derivative_fits(df, freq, tone_list, s21):

    #set up some preliminary values that we'll need
    n_freq = np.size(freq)
    old_tone_freq = tone_list
    center_ind = np.argwhere(abs(freq - old_tone_freq) == min(abs(freq - old_tone_freq)))[0]

    #smooth the data
    x = s21
    s21 = savgol_filter(s21, 7, 3, mode='mirror')

    #search for local minima
    if s21[center_ind[0]] != min(s21):
       keepgoing = True
       while keepgoing:
          lo_ind = int(max(center_ind-1,0))
          hi_ind = int(min(center_ind+2,n_freq))
          min_ind = np.argwhere(s21[lo_ind:hi_ind] == min(s21[lo_ind:hi_ind]))[0]
          if min_ind[0] == (center_ind[0] - lo_ind):
             keepgoing = False
          else:
             center_ind = lo_ind + min_ind

    f0 = freq[center_ind[0]]
    return f0

# def scraps_fits(bb_freqs, tone_freqs, lo_freqs, freq_span, \
#                 this_freq_data, this_i_data, this_q_data, i_chan, \
#                 pdfFlag = False, path = '', Qc = 0):

#     #set up some preliminary values that we'll need
#     this_df = this_freq_data[1] - this_freq_data[0]
#     n_freq = this_freq_data.size
#     old_tone_freq = tone_freqs[i_chan]
#     this_mag_data = 10. * np.log10(this_i_data**2. + this_q_data**2.)

#     #determine if we have nearby resonators
#     nearby_resonators = np.where(abs(tone_freqs - tone_freqs[i_chan]) < (0.65*freq_span))

#     #this long process is to deal with the case of two nearby resonators
#     if np.size(nearby_resonators) == 2:
#       nearby_tones = tone_freqs[nearby_resonators]
#       our_tone = tone_freqs[i_chan]
#       other_tone = nearby_tones[nearby_tones != our_tone]
#       if our_tone < other_tone:
#         this_index = 1
# 	keepgoing = 1
#         min_diff_from_baseline = 2.
# 	while keepgoing:
# 	  if( ((this_mag_data[0] - this_mag_data[this_index]) < min_diff_from_baseline) | \
# 	    (this_mag_data[this_index] < this_mag_data[this_index-1]) ):
# 	    this_index = this_index + 1
# 	  else:
# 	    this_f0 = this_freq_data[this_index]
# 	    other_f0 = this_f0 + other_tone[0] - our_tone
# 	    mean_freq = np.mean([this_f0,other_f0])
# 	    keepgoing = 0
#           if this_index > (n_freq-1):
#             this_index = 1
#             min_diff_from_baseline = min_diff_from_baseline-0.5
#       else:
#         this_index = n_freq - 2
# 	keepgoing = 1
#         min_diff_from_baseline = 2.
# 	while keepgoing:
# 	  if( ((this_mag_data[n_freq-1] - this_mag_data[this_index]) < min_diff_from_baseline) | \
# 	    (this_mag_data[this_index] < this_mag_data[this_index+1]) ):
# 	    this_index = this_index - 1
# 	  else:
# 	    this_f0 = this_freq_data[this_index]
# 	    other_f0 = this_f0 + other_tone[0] - our_tone
# 	    mean_freq = np.mean([this_f0,other_f0])
# 	    keepgoing = 0
#           if this_index < 1:
#             this_index = n_freq - 2
#             min_diff_from_baseline = min_diff_from_baseline-0.5
#       if this_f0 > other_f0:
#         valid_index = np.where(this_freq_data > mean_freq)
#       else:
#         valid_index = np.where(this_freq_data < mean_freq)
#       this_freq_data = this_freq_data[valid_index]
#       this_i_data = this_i_data[valid_index]
#       this_q_data = this_q_data[valid_index]
#       this_mag_data = this_mag_data[valid_index]

#     #if there are three or more nearby resonators, then let's just do the best we can...
#     if np.size(nearby_resonators) > 2:
#       our_tone = tone_freqs[i_chan]
#       this_index = np.size(this_freq_data) / 2
#       if this_mag_data[this_index] < this_mag_data[this_index-1]:
#         keepgoing = 1
# 	while keepgoing:
# 	  if(this_mag_data[this_index] < this_mag_data[this_index-1]):
# 	    this_index = this_index + 1
# 	  else:
# 	    this_f0 = this_freq_data[this_index]
# 	    keepgoing = 0
#       else:
#         keepgoing = 1
# 	while keepgoing:
# 	  if(this_mag_data[this_index-1] < this_mag_data[this_index]):
# 	    this_index = this_index - 1
# 	  else:
# 	    this_f0 = this_freq_data[this_index]
# 	    keepgoing = 0
#       nearby_tones = tone_freqs[nearby_resonators]
#       our_tone = tone_freqs[i_chan]
#       higher_freq_ind = np.where(nearby_tones > our_tone)
#       if np.size(higher_freq_ind) >= 1:
#         other_f0 = this_f0 + min(nearby_tones[higher_freq_ind]) - our_tone
# 	mean_freq = np.mean([other_f0, our_tone])
# 	valid_index = np.where(this_freq_data < mean_freq)
# 	this_freq_data = this_freq_data[valid_index]
# 	this_i_data = this_i_data[valid_index]
# 	this_q_data = this_q_data[valid_index]
#         this_mag_data = this_mag_data[valid_index]
# 	lower_freq_ind = np.where(nearby_tones < our_tone)
#       if np.size(lower_freq_ind) >= 1:
#         other_f0 = this_f0 + max(nearby_tones[lower_freq_ind]) - our_tone
# 	mean_freq = np.mean([other_f0, our_tone])
# 	valid_index = np.where(this_freq_data > mean_freq)
# 	this_freq_data = this_freq_data[valid_index]
# 	this_i_data = this_i_data[valid_index]
# 	this_q_data = this_q_data[valid_index]
#         this_mag_data = this_mag_data[valid_index]

#     #get the data into the dict required by SCRAPS
#     resonator_data_dict = {'I':this_i_data, \
# 			   'Q':this_q_data, \
# 			   'freq':this_freq_data*1.e6, \
# 			   'name':'RES-'+str(i_chan), \
# 			   'pwr':0., \
# 			   'temp':0.2}

#     #create resonator object and perform fit
#     resonator_object = scr.makeResFromData(resonator_data_dict)
#     resonator_object.load_params(scr.cmplxIQ_params)
#     if Qc == 0:
#       resonator_object.do_lmfit(scr.cmplxIQ_fit)
#     else:
#       resonator_object.do_lmfit(scr.cmplxIQ_fit, qc = Qc, qc_vary = False)

#     #generate a PDF plot if desired
#     if pdfFlag:
#       pdf_file_name = path + '/resonator_fits_' + str(tone_freqs[i_chan]) + '.pdf'
#       with PdfPages(pdf_file_name) as pdf:
#         fig = scr.plotResListData([resonator_object], \
#                                   plot_types = ['LogMag', 'IQ'], \
#                                   num_cols = 2, \
#                                   fig_size = 5, \
#                                   show_colorbar = False, \
#                                   force_square = True, \
#                                   plot_fits = [True]*2, \
#                                   freq_units = 'MHz', \
#                                   plot_kwargs = {'marker':'o','ls':'None'}, \
#                                   fit_kwargs = {'ls':'-','color':'r'})
#         plt.figtext(0.12,0.35,'f0 = '+"{:.4f}".format(resonator_object.lmfit_result.params['f0'].value*1.e-6)+' MHz')
#         plt.figtext(0.12,0.30,'Qi = '+"{:.1f}".format(resonator_object.lmfit_result.params['qi'].value))
#         plt.figtext(0.12,0.25,'Qc = '+"{:.1f}".format(resonator_object.lmfit_result.params['qc'].value))      
#         plt.title('Resonator ' + str(i_chan) + ', f0 = ' + "{:.1f}".format(bb_freqs[i_chan]+1.7e8) + ' Hz')
#         pdf.savefig()
#         plt.close()

#     #do a quick sanity check to make sure it's found a reasonable center
#     min_mag_freq = this_freq_data[np.where(this_mag_data == np.min(this_mag_data))] * 1.e6
#     diff = np.abs(resonator_object.lmfit_result.params['f0'].value - min_mag_freq[0])
#     max_diff = 2.e3
#     if diff > max_diff:
#         resonator_object.lmfit_result.params['f0'].value = min_mag_freq[0]
        
#     return resonator_object

def main(tone_list,filename='',DerivFit=True,quickPlot=False,pdfFlag=False,Qc_array=0,printFlag=False):
    #path, center_freq, pdfFlag = False, quickPlot = False, Qc_array = 0, printFlag = True, FlagBad = False, MaxGoodInd = 0, DerivFit = False):

    #get the lo sweep file, get the filename if needed
    if filename == '':
        yymmdd = onrkidpy.get_yymmdd()
        lo_files = glob.glob('/data/' + yymmdd + '/' + yymmdd + '_LO_Sweep*.npy')
        lo_files.sort(key=os.path.getmtime)
        filename = lo_files[-1]
    lo_data = np.load(filename)
    freq = lo_data[0,:,:]
    s21 = 10. * np.log10(np.abs(lo_data[1,:,:]))

    #get rid of existing pdfs if we're plotting
    if pdfFlag:
      for file in glob.glob(os.path.join(path,'resonator_fits*.pdf')):
        os.remove(file)

    #initialize variables for fitting
    chanmask = onrkidpy.get_chanmask()
    n_chan = np.size(chanmask)
    fit_f0 = np.zeros(n_chan)
    fit_qi = np.zeros(n_chan)
    fit_qc = np.zeros(n_chan)
    difference = np.zeros(n_chan)
    offres_ind = np.argwhere(chanmask == 0)
    fit_f0[offres_ind] = tone_list[offres_ind]

    #get setup if we'll be making a quickplot
    if quickPlot:
        nrows = int(np.min([np.ceil(np.sqrt(np.size(np.where(np.logical_or(chanmask == 1, chanmask == 0))))*18./30.),12]))
        ncols = int(np.min([np.ceil(np.size(np.where(np.logical_or(chanmask == 1, chanmask == 0))) / float(nrows)),18]))
        counter = 1
        max_count = nrows * ncols

    #loop over resonators to perform fit
    df = freq[0,1]-freq[0,0]
    for i_chan in np.argwhere(chanmask == 1):

       #pull in the sweep data for this tone
       i_chan = i_chan[0]
       this_freq_data = freq[i_chan,:]
       this_s21_data = s21[i_chan,:]

       #see if we have a prior on Qc
       if np.size(Qc_array) == 1:
           Qc = 0.
       else:
           Qc = Qc_array[i_chan]

       #call the resonator fitter
       if DerivFit:
          f0 = simple_derivative_fits(df, freq[i_chan,:], tone_list[i_chan], s21[i_chan,:])
          qc = 0.
          qi = 0.
       else:    
         resonator_object = scraps_fits(bb_freqs, tone_freqs, lo_freqs, freq_span, \
                                        this_freq_data, this_i_data, this_q_data, i_chan, \
                                        pdfFlag = pdfFlag, path = path, Qc = Qc)
         f0 = resonator_object.lmfit_result.params['f0'].value/1.e6
         qc = resonator_object.lmfit_result.params['qc'].value
         qi = resonator_object.lmfit_result.params['qi'].value
       #store some of the results
       fit_f0[i_chan] = f0
       fit_qc[i_chan] = qc
       fit_qi[i_chan] = qi
       difference[i_chan] = (fit_f0[i_chan] - tone_list[i_chan]) * 1.e-3

       #make a quick plot if desired
    #    diff_to_flag = 3.
       diff_to_flag = (3./200.) * tone_list * 1e-6
       if quickPlot:
           if np.mod(counter,max_count) == 1:
             fig, axarr = plt.subplots(nrows, ncols, figsize=(30,18))
             #plt.figure(figsize=(30,18))
             counter = 1
           plt.rc('font', size=8)
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].axvline(x=f0, color='r')
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].plot(this_freq_data, this_s21_data)
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_yticks([])
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_xticks([])
           freq_ratio = tone_list[i_chan] / np.max(tone_list)
           span = max(this_freq_data) - min(this_freq_data)
           new_span = span * freq_ratio
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_xlim(np.mean(this_freq_data)-new_span/2., \
                                                                      np.mean(this_freq_data+new_span/2.))
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].legend(["{:d}".format(i_chan)], \
                        fontsize=6, loc = 3, frameon=False, handlelength=0, bbox_to_anchor=(-0.2,-0.15))
        #    pdb.set_trace()
           if np.abs(difference[i_chan]) > diff_to_flag[i_chan]:
               axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_facecolor('yellow')
               if printFlag:
                   print("tone index =", "{:4d}".format(i_chan), \
                         "|| new tone =", "{:9.5f}".format(fit_f0[i_chan]*1.e-6), \
                         "|| old tone =", "{:9.5f}".format(tone_list[i_chan]*1.e-6), \
                         "|| difference (kHz) =", "{:+5.3f}".format(difference[i_chan]))
                   
           counter = counter+1


    if quickPlot:

      #loop over offres tones to plot
      for i_chan in np.argwhere(chanmask == 0):

           #pull in the sweep data for this tone
           i_chan = i_chan[0]
           this_freq_data = freq[i_chan,:]
           this_s21_data = s21[i_chan,:]
           if np.mod(counter,max_count) == 1:
             fig, axarr = plt.subplots(nrows, ncols, figsize=(30,18))
             #plt.figure(figsize=(30,18))
             counter = 1
           plt.rc('font', size=8)
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].plot(this_freq_data, this_s21_data)
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_yticks([])
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_xticks([])
           freq_ratio = tone_list[i_chan] / np.max(tone_list)
           span = max(this_freq_data) - min(this_freq_data)
           new_span = span * freq_ratio
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_xlim(np.mean(this_freq_data)-new_span/2., \
                                                                      np.mean(this_freq_data+new_span/2.))
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].legend(["{:d}".format(i_chan) + ', dS21=' + "{:4.1f}".format(np.max(this_s21_data)-np.min(this_s21_data))], \
                        fontsize=6, loc = 3, frameon=False, handlelength=0, bbox_to_anchor=(-0.2,-0.15))
#           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].legend(["{:5.2f}".format(np.max(this_s21_data**2)-np.min(this_s21_data**2))], \
#                        fontsize=6, loc = 2, frameon=False, handlelength=0)
           axarr[(counter-1)//ncols,np.mod(counter-1,ncols)].set_facecolor('orange')
           counter = counter+1

#         #pull in the sweep data for this tone
#         i_chan = i_chan[0]
#         this_freq_data = (bb_freqs[i_chan] + lo_freqs) * 1.e-6
# 	this_df = this_freq_data[1] - this_freq_data[0]
# 	this_i_data = chan_I[:,i_chan]
# 	this_q_data = chan_Q[:,i_chan]
#         old_tone_freq = tone_freqs[i_chan]
# 	this_mag_data = 10. * np.log10(this_i_data**2. + this_q_data**2.)

#         plt.rc('font', size=8)
#         plt.subplot(nrows, ncols, counter)
#         plt.plot(this_freq_data, this_i_data**2+this_q_data**2)
#         plt.axis('off')
#         plt.title('offres=' + "{:d}".format(i_chan), fontsize=6)
#         counter = counter+1

#     if pdfFlag:
#       files = glob.glob(os.path.join(path,'resonator_fits*.pdf'))
#       merger = PdfFileMerger()
#       for i_file in files:
#           merger.append(open(i_file, 'rb'))
#       with open(os.path.join(path,'resonator_fits.pdf'), 'wb') as fout:
#           merger.write(fout)
#       for i_file in files: 
#           os.remove(i_file)
        

# #     if pdfFlag:
# #       files = glob.glob(os.path.join(path,'resonator_fits*.pdf'))
# #       merger = PdfFileMerger()
# #       for i_file in files:
# #           merger.append(open(i_file, 'rb'))
# #       with open(os.path.join(path,'resonator_fits.pdf'), 'wb') as fout:
# #           merger.write(fout)
# #       for i_file in files: 
# #           os.remove(i_file)

    if quickPlot:
        plt.show(block=False)

    return fit_f0, fit_qi, fit_qc

def hp_filt_func(x, amp, cutoff):
#    return amp * (x / np.sqrt(x**2 + cutoff**2) - 1.)
    vals = amp * (x - cutoff)
    ind = np.ndarray.flatten(np.argwhere(x >= cutoff))
    vals[ind] = 0.
    return vals
#    return amp * (x / np.sqrt(x**2 + cutoff**2) - 1.)

def find_optimal_readout_power(date, device):

    files = glob.glob('/data/' + date + '/' + date + '_attenuator*.npy')
    temp_data = np.load(files[0])
    n_res = np.size(temp_data)
    n_files = np.size(files)
    f0_data = np.zeros((n_files,n_res))
    attenuation = np.zeros(n_files)
    for index, this_file in enumerate(files):
        this_f0 = np.load(this_file)
        f0_data[index,:] = this_f0
        attenuation[index] = float(this_file[-6:-4])

    sorted_data_ind = np.argsort(attenuation)
    attenuation = attenuation[sorted_data_ind]
    f0_data = f0_data[sorted_data_ind,:]
    attenuation_non_linear = np.zeros(n_res)
    for i_res in range(n_res):

        #first let's remove f0 values that are invalid at high power
        this_attenuation = attenuation
        this_df = (f0_data[:,i_res] - f0_data[-1,i_res])/f0_data[-1,i_res]
        this_deriv = this_df - np.roll(this_df,-1)
        this_deriv = this_deriv[:-1]
        bad_atten = np.ndarray.flatten(np.argwhere(this_deriv >= 0))
        valid_bad = np.ndarray.flatten(np.argwhere(bad_atten <= np.size(this_attenuation)/4.))
        bad_atten = bad_atten[valid_bad]
        if np.size(bad_atten) > 0:
          if bad_atten[0] <= 5:
            this_attenuation = this_attenuation[int(np.max(bad_atten)+1):]
            this_df = this_df[int(np.max(bad_atten)+1):]

        popt = curve_fit(hp_filt_func, this_attenuation, this_df, p0 = (1.e-5, 10.))
        attenuation_non_linear[i_res] = popt[0][1]
#         plt.plot(this_attenuation, this_df, 'o')
#         plt.plot(this_attenuation, hp_filt_func(this_attenuation, popt[0][0], popt[0][1]))
#         plt.xlabel('Attenuation (dB)')
#         plt.ylabel('df0 / f0')
#         plt.show()
#         pdb.set_trace()

    bad_ind = np.ndarray.flatten(np.argwhere(np.abs(attenuation_non_linear - \
                                                    np.median(attenuation_non_linear)) / \
                                             np.std(attenuation_non_linear) > 2.5))
    attenuation_non_linear[bad_ind] = np.median(attenuation_non_linear)
    max_readout_power = np.min(attenuation_non_linear) - attenuation_non_linear
    np.save('/home/onrkids/onrkidpy/params/' + device + '_' + date + '_max_readout_power_dB.npy', max_readout_power)
    pdb.set_trace()

    return 0
