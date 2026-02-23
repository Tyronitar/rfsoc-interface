from zipfile import Path
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.losweep import LoSweep, LoSweepData
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3 import capture

import json
import time
import numpy as np
def start_streaming(rfsoc, duration:int = 100, save_location:Path = None, chan: int = 0):
    # TODO: Do this in another thread
    rfchans = []


   

    rfchan = rfsoc.get_channel(chan)
    rfchans.append(rfchan)
    rfchan.raw_filename = str(save_location)


    save_location.touch(PERMISSIONS_USR_RW, exist_ok=True)

    date = save_location.stem[:8]
    setnum = int(save_location.stem[-4:])
    #_logger.debug(f'Streaming {duration} seconds of data for chans: {[chan.tile_name for chan in rfchans]}')
    capture(rfchans, time.sleep, duration)


if __name__ == "__main__":
    settings = Settings()
    settings.load_settings()
    n_tones = 100
    rfsoc = RFSOCWrapper(settings['rfsocs'][0])
    chan = 1
    last_fit_f0 = np.zeros(n_tones)
    for i in range(1):
        sweep_file = f'sweep_{i}.h5'
        sweep = LoSweep(
            rfsoc,
            1,
            sweep_file,
            0,
            1e3,
            300e3,
        )
        save_location = get_filename(file_type='lo', chan_name='Be231102p2_100_tones', mkdir=True).with_suffix('.h5')
        savefile = save_location.with_stem(f'{save_location.stem}_high_res')
        sweep_data = sweep.run_sweep()
        sweep_data.fit()
        print(sweep_data.fit_f0-last_fit_f0)
        last_fit_f0 = sweep_data.fit_f0.copy()
        sweep_data.saveh5(savefile)
        save_location = get_filename(file_type='tod', chan_name='Be231102p2_100_tones', mkdir=True).with_suffix('.h5')
          
        #tone_file = get_filename(file_type='tonelist', chan_name=rfsoc.get_channel_name(chan))
        #sweep_data.save_new_tone_list(tone_file)
        #_, curr_amp_list = rfsoc.get_tone_list(chan)
        #rfsoc.set_tone_list(chan, sweep_data.new_tone_list, amplitudes=curr_amp_list)
        start_streaming(rfsoc,duration=100, save_location=save_location, chan=1)

    




