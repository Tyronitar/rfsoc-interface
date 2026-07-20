import pdb

import matplotlib.pyplot as plt
import numpy as np
from kidpy3 import RawDataFile
from scipy.signal import decimate
import h5py


from rfsocinterface.core.data.storage import ProcessedData 


if __name__ == '__main__':
    far_field_date = '20260617'

    # Far-field H-pol
    new_ff_hpol_file = h5py.File('Far_field_tile_2_H_pol_beammap.h5', mode='w')
    ff_hpol = ProcessedData.load(far_field_date, 1001)
    new_ff_hpol_file.attrs['dpix']= ff_hpol['map'].attrs['dpix']
    new_ff_hpol_file.attrs['units']= ff_hpol['map'].attrs['units']
    new_ff_hpol_file.create_dataset('chanmask', data=ff_hpol.chanmask)
    ff_hpol.file.copy('map/map_val', new_ff_hpol_file)
    ff_hpol.file.copy('map/map_az', new_ff_hpol_file)
    ff_hpol.file.copy('map/map_za', new_ff_hpol_file)
    ff_hpol.file.copy('beammap', new_ff_hpol_file)
    new_ff_hpol_file.close()

    # Far-field H-pol
    new_ff_vpol_file = h5py.File('Far_field_tile_2_V_pol_beammap.h5', mode='w')
    ff_vpol = ProcessedData.load(far_field_date, 1004)
    new_ff_vpol_file.attrs['dpix']= ff_vpol['map'].attrs['dpix']
    new_ff_vpol_file.attrs['units']= ff_vpol['map'].attrs['units']
    new_ff_vpol_file.create_dataset('chanmask', data=ff_vpol.chanmask)
    ff_vpol.file.copy('map/map_val', new_ff_vpol_file)
    ff_vpol.file.copy('map/map_az', new_ff_vpol_file)
    ff_vpol.file.copy('map/map_za', new_ff_vpol_file)
    ff_vpol.file.copy('beammap', new_ff_vpol_file)
    new_ff_vpol_file.close()

    near_field_date = '20260710'

    # Near-field set 1005 (H-pol?)
    new_nf_hpol_file = h5py.File('Near_field_tile_2_set1005_beammap.h5', mode='w')
    nf_hpol = ProcessedData.load(near_field_date, 1005)
    new_nf_hpol_file.attrs['dpix']= nf_hpol['map'].attrs['dpix']
    new_nf_hpol_file.attrs['units']= nf_hpol['map'].attrs['units']
    new_nf_hpol_file.create_dataset('chanmask', data=nf_hpol.chanmask)
    nf_hpol.file.copy('map/map_val', new_nf_hpol_file)
    nf_hpol.file.copy('map/map_az', new_nf_hpol_file)
    nf_hpol.file.copy('map/map_za', new_nf_hpol_file)
    nf_hpol.file.copy('beammap', new_nf_hpol_file)
    new_nf_hpol_file.close()

    # Near-field set 1006 (H-pol? + 45 degrees)
    new_nf_vpol_file = h5py.File('Near_field_tile_2_set1006_beammap.h5', mode='w')
    nf_vpol = ProcessedData.load(near_field_date, 1006)
    new_nf_vpol_file.attrs['dpix']= nf_vpol['map'].attrs['dpix']
    new_nf_vpol_file.attrs['units']= nf_vpol['map'].attrs['units']
    new_nf_vpol_file.create_dataset('chanmask', data=nf_vpol.chanmask)
    nf_vpol.file.copy('map/map_val', new_nf_vpol_file)
    nf_vpol.file.copy('map/map_az', new_nf_vpol_file)
    nf_vpol.file.copy('map/map_za', new_nf_vpol_file)
    nf_vpol.file.copy('beammap', new_nf_vpol_file)
    new_nf_vpol_file.close()
