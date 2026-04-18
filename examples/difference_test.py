import pdb

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import tables
from rfsocinterface.core.data import MapData
from rfsocinterface.core.data.map import plot_map


def diff(date: str, setnum_up: int, setnum_down: int) -> Figure:
    print(f'running diff for {setnum_up} and {setnum_down}')
    data_mirror_up = MapData.from_file(date, setnum_up)
    data_mirror_down = MapData.from_file(date, setnum_down)
    with tables.File(f'{date}_set{setnum_up}_map_data.h5', 'w') as fh:
        fh.create_array('/', 'map_vpol', obj=data_mirror_up.map[0])
        fh.create_array('/', 'map_hpol', obj=data_mirror_up.map[1])
        fh.create_array('/', 'map_total_intensity', obj=data_mirror_up.total_map)
    with tables.File(f'{date}_set{setnum_down}_map_data.h5', 'w') as fh:
        fh.create_array('/', 'map_vpol', obj=data_mirror_down.map[0])
        fh.create_array('/', 'map_hpol', obj=data_mirror_down.map[1])
        fh.create_array('/', 'map_total_intensity', obj=data_mirror_down.total_map)
    za_shift=0
    map_down_shifted = np.roll(data_mirror_down.total_map[:], za_shift, axis=1)
    diff_map = data_mirror_up.total_map[:] - map_down_shifted


    f = plot_map(
        diff_map[:, :],
        data_mirror_up.map_az[:],
        data_mirror_up.map_za[:],
        extent=data_mirror_up.extent(),
        title=f'Difference Between set{setnum_up} and set{setnum_down}',
    )
    data_mirror_up.close()
    data_mirror_down.close()
    return f

if __name__ == '__main__':
    date = '20251212'
    # f1 = diff(date, 1007, 1008)
    f2 = diff(date, 1009, 1010)
    f2.savefig('difference.png')

    plt.show()

