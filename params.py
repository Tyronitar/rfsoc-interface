from pathlib import Path
import pdb

import numpy as np
import tables

from rfsocinterface.core.data.data import initialize_params_file, update_params_file, DATA_DIRECTORY, DEFAULT_PARAMS_DIRECTORY
from rfsocinterface.core.rfsoc import RFSOCWrapper



if __name__ == "__main__":
    tile_name = 'ten_tone_uniform_20250806'
    lo_freq = 4e8
    baseband_freqs = np.linspace(10, 210, 10) * 1e6
    
    #needs to be the same length as baseband
    detdx = None
    detdy = None
    chanmask = None  #needs to be the same length as baseband_freqs, with 1 for the tones we keep and 0 the tones we remove
    det_beam_ampl = None
    det_pol = None
    tone_powers = None
    df_overf_per_mK = None


    initialize_params_file(tile_name, baseband_freqs, lo_freq, DEFAULT_PARAMS_DIRECTORY)
    update_params_file(
        tile_name,
        params_dir=DEFAULT_PARAMS_DIRECTORY,
        detector_delta_dx=detdx,
        detector_delta_dy=detdy,
        chanmask=chanmask,
        detector_beam_ampl=det_beam_ampl,
        detector_pol=det_pol,
        tone_powers=tone_powers,
        dfoverf_per_mK=df_overf_per_mK
    )
