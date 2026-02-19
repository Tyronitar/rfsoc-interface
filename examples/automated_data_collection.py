from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.losweep import LoSweep, LoSweepData
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3 import capture

import json

def start_streaming(self):
    # TODO: Do this in another thread
    chans = self.get_selected_channels(self.channel_comboBox)
    rfchans = []


    duration = get_num_value(self.duration_lineEdit, int, use_placeholder_text=True)

    save_location = get_filename(file_type='tod', chan_name=rfchans[0].tile_name, mkdir=True).with_suffix('.h5')
    rfchan = rfsoc.get_channel(chan)
    rfchans.append(rfchan)
    rfchan.raw_filename = str(save_location)


    save_path.touch(PERMISSIONS_USR_RW, exist_ok=True)

    date = save_location.stem[:8]
    setnum = int(save_location.stem[-4:])
    _logger.debug(f'Streaming {duration} seconds of data for chans: {[chan.tile_name for chan in rfchans]}')
    capture(rfchans, time.sleep, duration)


if __name__ == "__main__":
    settings = Settings()
    settings.load_settings()

    rfsoc = RFSOCWrapper(settings['rfsocs'][0])

    for i in range(10):
        sweep_file = f'sweep_{i}.h5'
        sweep = LoSweep(
            rfsoc,
            1,
            sweep_file,
            0,
            1e3,
            100e3,
        )
        sweep_data = sweep.run_sweep()
        sweep_data.fit()
        sweep_data.saveh5(sweep_file)

        start_streaming(...)

    
        rfsoc.set_atten()




