from zipfile import Path
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.sweeps import LoSweep, LoSweepData, PowerSweep
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3.data_handler import RawDataFile
from kidpy3 import capture
from kidpy3.udp2 import get_last_lo

import json
import time
import numpy as np
import h5py
import pdb


settings = Settings()
settings.load_settings()
rfsoc = RFSOCWrapper(settings['rfsocs'][0])
chan = 1
tile_name='Be260114BL_100_tones_260721'
tone_file = get_filename(file_type='tonelist', tile_name = tile_name, mkdir=True).with_suffix('.h5')
rfsoc.load_params_file(1,'/data/params/params_tile_' + tile_name  + ".h5", upload_tones = False, set_freq = False, set_atten = False)

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

def run_Lo_sweep(rfsoc, step = 5e3, span = 200e3, tone_shift = 0, filename_suffix = None):
    print(step,span)
    sweep_file = (get_filename(file_type='lo',tile_name = tile_name, mkdir=True, filename_suffix=filename_suffix)).with_suffix('.h5')
    sweep = LoSweep(
        rfsoc = rfsoc,
        chan = 1,
        savefile = sweep_file,
        tone_shift=tone_shift,
        freq_step=step,
        full_span=span,
        filename_suffix=filename_suffix
    )
    sweep_data = sweep.run_sweep()
    sweep_data.save()
    return sweep_file

   
def run_noise_data_collection(rfsoc,tile_name, set_tone_list = False):
    save_location = get_filename(file_type='tod',tile_name=tile_name, mkdir=True).with_suffix('.h5')
    start_streaming(rfsoc,duration=1, save_location=save_location, chan=1)
    
if __name__ == '__main__':
    run_noise_data_collection(rfsoc, tile_name=tile_name)

