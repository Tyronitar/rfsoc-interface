from zipfile import Path
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.losweep import LoSweep, LoSweepData, PowerSweep, TempSweepData
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3 import capture

import json
import time
import numpy as np
import h5py
import pdb


settings = Settings()
settings.load_settings()
rfsoc = RFSOCWrapper(settings['rfsocs'][0])
chan = 1
chan_name='Be260114BL_1000_tones_3'
tone_file = get_filename(file_type='tonelist', chan_name=chan_name)
rfsoc.load_params_file(1,'/data/params/params_tile_' + chan_name  + ".h5")

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
def run_Lo_sweep(rfsoc, chan_name, step = 5e3, span = 200e3, tone_shift = 0):
    print(step,span)
    sweep_file = get_filename(file_type='lo', chan_name=chan_name, mkdir=True).with_suffix('.h5')
    sweep = LoSweep(
        rfsoc,
        1,
        sweep_file,
        tone_shift=tone_shift,
        freq_step=step,
        full_span=span,
    )
    save_location = get_filename(file_type='lo', chan_name=chan_name, mkdir=True).with_suffix('.h5')
    savefile = save_location.with_stem(f'{save_location.stem}')
    sweep_data = sweep.run_sweep()
    sweep_data.saveh5(savefile)
    return savefile
def run_power_sweep(rfsoc, chan_name, power_levels):
    #sweep_file = f'power_sweep.h5'
    save_location = get_filename(file_type='power', chan_name=chan_name, mkdir=True).with_suffix('.h5')
    sweep = PowerSweep(
        rfsoc,
        1,
        save_location,
        power_levels=power_levels,
        tone_shift=0,
        freq_step=0.5e3,
        full_span=200e3,
    )
    savefile = save_location.with_stem(f'{save_location.stem}_high_res')
    sweep_data = sweep.run_sweep()
    sweep_data.fit()
    freq_dir, _ = sweep_data.freq_direction()
    print(freq_dir-last_fit_freq_dir)
    last_fit_freq_dir = freq_dir
    sweep_data.saveh5(savefile)
    return save_location
   
def run_noise_data_collection(rfsoc, chan_name, set_tone_list = False):
    save_location = get_filename(file_type='tod', chan_name=chan_name, mkdir=True).with_suffix('.h5')
    start_streaming(rfsoc,duration=102, save_location=save_location, chan=1)
    


def save_temp_sweeps(LoSweepDataPath:list[str], fp_temps:np.ndarray):
    sweeps  = []
    for path in LoSweepDataPath:
        sweep_data = LoSweepData.from_h5(path)
        sweeps.append(sweep_data)
    temp_sweep = TempSweepData(sweep_data.tone_list, sweep_data.f_center, sweeps,fp_temps,rfsoc.get_rfin(chan), rfsoc.get_rfout(chan) )
    save_location = get_filename(file_type='power', chan_name=chan_name, mkdir=True).with_suffix('.h5')
    savefile = save_location.with_stem(f'{save_location.stem}_high_res')
    temp_sweep.saveh5(save_location)

    return savefile
if __name__ == '__main__':
    save_temp_sweeps(['/data/20260514/20260514_Uniform_test_1000_tones_260303_LO_Sweep_hour17p3139.h5'], [242])