import time 

from kidpy3 import capture, RawDataFile
import numpy as np
import pdb

from rfsocinterface.core.rfsoc import RFSoCWrapper
from rfsocinterface.core.settings import Settings
from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW


def collect_data(duration: int):
    start = time.time()
    stop = start + duration
    counter = 0
    while time.time() < stop:
        time.sleep(1.e-2)
        counter += 1
        if counter % 1000 == 0:
            print('Collected data for {:.2f} seconds'.format(time.time() - start))


if __name__ == '__main__':
    settings = Settings()
    settings.load_settings()
    rfsoc_settings = settings['rfsocs'][0]  # Just take the first one for testing
    rfsoc = RFSoCWrapper(rfsoc_settings)
    rfchan = rfsoc.get_channel(1)
    save_location = get_filename(file_type='tod', chan_name=rfchan.tile_name, mkdir=True).with_suffix('.h5')
    print(save_location)
    rfchan.raw_filename = str(save_location)

    capture([rfchan], collect_data, 30 * 60)

    # fname = '/data/20260520/20260520_100_tone_uniform_202050829_TOD_set1002.h5'
    # f = RawDataFile(fname, 'r')
    # pkt_idx = f.pkt_idx[:] 

    # missed_ind = np.argwhere(np.diff(pkt_idx) != 1)[0]
    # pdb.set_trace()