from pathlib import Path
import pdb

import numpy as np
import tables

from rfsocinterface.core.data.data import initialize_params_file, update_params_file, DATA_DIRECTORY, DEFAULT_PARAMS_DIRECTORY
from rfsocinterface.core.rfsoc import RFSOCWrapper

Be231102p2_tones = np.array([213078506, 214801178, 247405640, 255826241, 256855576, 260115494,
       263857108, 265547813, 269670205, 270298250, 272671603, 274710449,
       276383775, 278960930, 308519951, 312882861, 313150099, 314004392,
       314391462, 318555194, 322412444, 323717312, 326364689, 328323325,
       328705367, 335793390, 340651152, 368175878, 373470266, 375799889,
       375951626, 377837022, 384075676, 386531740, 386868808, 387216094,
       393636830, 397181500, 401249603, 404139304, 409101781, 417625771])

Be231102p2_LO_freq = 300e6


if __name__ == "__main__":
    tile_name = 'Device_aSi1_Channel2'
    baseband_freqs =  np.load('/home/onrkids/readout/host/params/Default_tone_list.npy')
    lo_freq = 4e8

    #needs to be the same length as baseband
    detdx = np.load('/home/onrkids/readout/host/params/detector_delta_x_tile2.npy')
    detdy = np.load('/home/onrkids/readout/host/params/detector_delta_y_tile2.npy')
    chanmask = np.load('/home/onrkids/onrkidpy/params/chanmask.npy')  #needs to be the same length as baseband_freqs, with 1 for the tones we keep and 0 the tones we remove
    det_beam_ampl = np.load('/home/onrkids/readout/host/params/detector_beam_ampl_tile2.npy')
    det_pol = np.load('/home/onrkids/readout/host/params/detector_pol_tile2.npy')
    tone_powers = np.load('/home/onrkids/onrkidpy/params/Device_aSi1_Channel2_max_readout_power_dB.npy')
    df_overf_per_mK = np.load('/home/onrkids/readout/host/params/dfoverf_per_mK_tile2.npy')


    initialize_params_file(tile_name, baseband_freqs, lo_freq, DEFAULT_PARAMS_DIRECTORY)
    update_params_file(
        tile_name,
        params_dir=DEFAULT_PARAMS_DIRECTORY,
        detector_delta_x=detdx,
        detector_delta_y=detdy,
        chanmask=chanmask,
        detector_beam_ampl=det_beam_ampl,
        detector_pol=det_pol,
        tone_powers=tone_powers,
        dfoverf_per_mK=df_overf_per_mK
    )
