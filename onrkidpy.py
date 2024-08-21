import numpy as np
import os
import pdb
from datetime import date
from datetime import datetime
import glob
import matplotlib.pyplot as plt

def get_yymmdd():

    #get today's date string
    yy = "{}".format(date.today().year)
    mm = "{}".format(date.today().month)
    if date.today().month < 10:
        mm = '0' + mm
    dd = "{}".format(date.today().day)
    if date.today().day < 10:
        dd = '0' + dd
    yymmdd = yy + mm + dd
    return yymmdd

def get_chanmask(chanmask_file=''):

    if chanmask_file=='':
        chanmask_file = '/home/onrkids/onrkidpy/params/chanmask.npy'
    chanmask = np.load(chanmask_file)
    return chanmask

def get_filename(type='LO', chan_name="", attenuation=0.):

    #see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = '/data/' + yymmdd 
    check_date_folder = glob.glob('/data/' + yymmdd + '/')
    if np.size(check_date_folder) == 0:
        os.makedirs(date_folder)
    if chan_name != "":
        chan_name = chan_name+'_'
    date_folder = date_folder + '/' + yymmdd + '_'

    #provide the name of the file
    if type == 'LO' or type == "TONELIST":
        hour_str = float(datetime.now().strftime("%H")) + float(datetime.now().strftime("%M"))/60. + \
            float(datetime.now().strftime("%S"))/3600.
        if hour_str < 10:
            hour_str = 'hour0' + '{0:.4f}'.format(hour_str)
        else:
            hour_str = 'hour' + '{0:.4f}'.format(hour_str)
        hour_str = hour_str.replace('.','p')
        if type == 'LO':
            savefile = date_folder + chan_name + 'LO_Sweep_' + hour_str
        if type == 'TONELIST':
            savefile = date_folder + chan_name +  'tone_list_' + hour_str
            
    if type == 'TOD' or type == 'AZEL':
        this_dir_files = glob.glob(date_folder + '*TOD_set' + '*')
        if np.size(this_dir_files) == 0:
            setnum = '1001'
        else:
            this_dir_files.sort()
            if type == 'TOD':
                offset = 1
            else:
                offset = 0
            setnum = "{}".format(int(this_dir_files[-1][-7:-3])+offset)
    if type == 'TOD':
        savefile = date_folder + chan_name + 'TOD_set' + setnum
    if type == 'AZEL':
        savefile = date_folder + chan_name +  'AZEL_set' + setnum

    if type == 'attenuator':
        savefile = date_folder + chan_name + 'attenuator' + '{0:02d}'.format(int(attenuation))

    return savefile

def plot_lo_sweep(filename=''):

    #get the filename if needed
    if filename == '':
        yymmdd = get_yymmdd()
        lo_files = glob.glob('/data/' + yymmdd + '/LO_Sweep*.npy')
        lo_files.sort(key=os.path.getmtime)
        filename = lo_files[-1]

    lo_data = np.load(filename)
    freq = lo_data[0,:,:]
    s21 = 10. * np.log10(np.abs(lo_data[1,:,:]))
    for i_tone in range(np.size(freq[:,0])):
       plt.plot(freq[i_tone,:], s21[i_tone,:])
    plt.show()
    pdb.set_trace()
