import pdb

import numpy as np

from rfsocinterface.core.params import RFSoCParameters

if __name__ == '__main__':
    tones = np.linspace(15, 250, 50) * 1e6
    tone_powers = np.array([ 4.        ,  6.        ,  0.        , 10.        ,  0.        ,
       10.        , 10.        , 10.        , 10.        , 10.        ,
        0.        ,  2.        ,  6.        ,  1.        , 10.        ,
       10.        , 10.        ,  0.        , 10.        , 10.        ,
        0.        , 10.        , 10.        ,  2.        ,  4.        ,
       10.        ,  8.        , 10.        ,  0.        , 10.        ,
       10.        , 10.        , -4.        , -2.        , -1.        ,
       -4.        , 10.        ,  8.        , 10.        ,  6.        ,
       10.        ,  0.        , -4.        , 10.        ,  1.        ,
        4.98506804, 10.        , 10.        , -2.62230658,  0.        ,
        0.        ,  0.        ,  0.        ,  0.        ,  0.        ,
        0.        ,  0.01039567,  4.        ,  0.        ,  0.        ,
        0.        , 10.        ,  0.        ,  0.        ,  0.        ,
        0.        ,  0.        ,  0.        ,  0.        ,  1.        ,
        0.        , 10.        ,  0.        ,  0.        ,  0.        ,
       10.        ,  0.        ,  0.        ,  0.        ,  0.        ,
        0.        ,  0.        ,  0.        ,  0.        ,  0.        ,
        0.        ,  0.        ,  0.        ,  0.        , 10.        ,
        6.1327495 ,  0.        ,  4.        ,  0.        ,  0.        ,
        0.        ,  0.        ,  0.        ,  0.        , 10.        ])-10
    tone_powers_frac = 10**(tone_powers/10)
    filenames = [
            '/data/params/params_tile_Be260114BL_1000_tones_1.h5',
        ]
    params = RFSoCParameters(filenames[0])

    bb_freqs_onres = params.baseband_freqs[params.onres_ind]
    filenames = [
            '/data/params/params_tile_Be260114BL_1000_tones_1.h5',
        ]
    
    pdb.set_trace()
    f_center = params.f_center
    # update_params_file_format(*filenames)
    params = RFSoCParameters.new_file('Be260114BL_tones_260717', len(bb_freqs_onres), f_center=f_center)
    params.baseband_freqs[:] = bb_freqs_onres
    params.rfin = 15
    params.rfout = 15
    params.add_off_resonance_tones_greedy(
        new_tile_name='Be260114BL_100_tones_260721',
        n_offres=100-len(bb_freqs_onres),
        f_min=170e6,
        f_max=670e6,
        q=1/1000.,
        delta_offres_min=1e6,
        tone_powers_frac = np.ones(100)
       
    )

    pdb.set_trace()


