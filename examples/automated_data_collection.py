from zipfile import Path
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.losweep import LoSweep, LoSweepData
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3 import capture

import json
import time
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

    rfsoc = RFSOCWrapper(settings['rfsocs'][0])

    for i in range(1):
        sweep_file = f'sweep_{i}.h5'
        sweep = LoSweep(
            rfsoc,
            1,
            sweep_file,
            0,
            1e3,
            100e3,
        )
        save_location = get_filename(file_type='lo', chan_name='Be231102p2', mkdir=True).with_suffix('.h5')

        sweep_data = sweep.run_sweep()
        sweep_data.fit()
        sweep_data.saveh5(save_location)
        save_location = get_filename(file_type='tod', chan_name='Be231102p2', mkdir=True).with_suffix('.h5')

        start_streaming(rfsoc,duration=10, save_location=save_location, chan=1)

    




