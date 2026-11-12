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
        chanmask = pdata.chanmask
        f.create_dataset('chanmask', data=chanmask)
        # map_val = pdata['map/map_val'][:]
        # pdb.set_trace()
        # pmap_val.shape
        # pdata.file.copy('map', f)
        # pdata.file.copy('beammap', f)
        # pdata.file.copy('', f)



if __name__ == '__main__':
    # date = '20260617'
    # save_beammap(date, 1001, 'tile_2_H_pol_beammap.h5')
    # save_beammap(date, 1004, 'tile_2_V_pol_beammap.h5')
    # save_beammap(date, 1005, 'tile_3_V_pol_beammap.h5')
    # save_beammap(date, 1006, 'tile_3_H_pol_beammap.h5')
    # save_beammap(date, 1001, 'tile_2_H_pol_beammap_0p02.h5')
    # save_beammap(date, 1004, 'tile_2_V_pol_beammap_0p02.h5')
    # save_beammap(date, 1005, 'tile_3_V_pol_beammap_0p02.h5')
    # save_beammap(date, 1006, 'tile_3_H_pol_beammap_0p02.h5')

    # date = '20261023'
    # save_beammap(date, 1016, 'tile_4_H_pol_beammap.h5')
    # save_beammap(date, 1017, 'tile_4_hillside_beammap.h5')
    # save_beammap(date, 1018, 'tile_4_V_pol_beammap.h5')

    # date = '20261028'
    # save_beammap(date, 1007, '20261028_set1007_tile2_V_pol.h5')
    # save_beammap(date, 1008, '20261028_set1008_tile2_no_source.h5')
    # save_beammap(date, 1009, '20261028_set1009_tile2_H_pol.h5')
    # save_beammap(date, 1007, '20261028_set1007_tile2_V_pol_0p02.h5')
    # save_beammap(date, 1008, '20261028_set1008_tile2_no_source_0p02.h5')
    # save_beammap(date, 1009, '20261028_set1009_tile2_H_pol_0p02.h5')
    # save_beammap(date, 1007, '20261028_set1007_tile2_V_pol_OLD.h5')
    # save_beammap(date, 1009, '20261028_set1009_tile2_H_pol_OLD.h5')

    date = '20261105'
    # save_beammap(date, 1001, '20261105_set1001_tile3_H_pol_v1.h5')
    # save_beammap(date, 1002, '20261105_set1002_tile3_source_off.h5')
    # save_beammap(date, 1003, '20261105_set1003_tile3_V_pol_v1.h5')
    # save_beammap(date, 1004, '20261105_set1004_tile3_H_pol_v2.h5')
    # save_beammap(date, 1005, '20261105_set1005_tile3_V_pol_v2.h5')
    save_beammap(date, 1001, '20261105_set1001_tile3_H_pol_v1_clean.h5')
    save_beammap(date, 1002, '20261105_set1002_tile3_source_off_clean.h5')
    save_beammap(date, 1003, '20261105_set1003_tile3_V_pol_v1_clean.h5')
    save_beammap(date, 1004, '20261105_set1004_tile3_H_pol_v2_clean.h5')
    save_beammap(date, 1005, '20261105_set1005_tile3_V_pol_v2_clean.h5')

