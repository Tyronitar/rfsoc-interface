import h5py
import pdb

from rfsocinterface.core.data import ProcessedData


def save_beammap(date, setnum, filename):
    pdata = ProcessedData.load(date, setnum, 'r')
    with h5py.File(filename, 'w') as f:
        map_group = f.create_group('map')
        pdata.file.copy('map/map_val', map_group)
        pdata.file.copy('map/map_az', map_group)
        pdata.file.copy('map/map_za', map_group)
        pdata.file.copy('beammap', f)
        chanmask = pdata.get_chanmask(0)
        f.create_dataset('chanmask', data=chanmask)
        # map_val = pdata['map/map_val'][:]
        # pdb.set_trace()
        # pmap_val.shape
        # pdata.file.copy('map', f)
        # pdata.file.copy('beammap', f)
        # pdata.file.copy('', f)



if __name__ == '__main__':
    date = '20260617'
    save_beammap(date, 1001, 'tile_2_H_pol_beammap.h5')
    save_beammap(date, 1004, 'tile_2_V_pol_beammap.h5')
    save_beammap(date, 1005, 'tile_3_V_pol_beammap.h5')
    save_beammap(date, 1006, 'tile_3_H_pol_beammap.h5')
