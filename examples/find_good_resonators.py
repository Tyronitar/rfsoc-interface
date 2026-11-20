import pdb

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from rfsocinterface.core.data import (
    ProcessedData
)
from rfsocinterface.core.params import RFSoCParameters

if __name__ == '__main__':
    date = '20260617'

    setnum_vs = (1004, 1005)
    setnum_hs = (1001, 1006)
    tile_names = (
        'Device_aSi1_Channel2_telescope_275mK_20260804',
        'Device_aSi2_Channel3_telescope_275mK_20260804',
    )
    colors = (
        'blue',
        'orange'
    )

    focal_center = np.array([5.978, 88.748])

    bands = np.linspace(0, 1.5, 5)
    max_dist = 1.5

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))

    ax.scatter(0, 0, marker='+', color='r')

    for band in bands[1:]:
        circle = Circle(
            (0, 0),
            radius=band,
            edgecolor='black',
            facecolor='none',
            linewidth=1,
            linestyle='--'
        )
        ax.add_patch(circle)

    for i_tile in range(2):
        pdata_h = ProcessedData.load(date, setnum_hs[i_tile], mode='r')
        pdata_v = ProcessedData.load(date, setnum_vs[i_tile], mode='r')
        params = RFSoCParameters.load(tile_names[i_tile])
        n_tones = params.n_tones
        onres_ind = params.onres_ind

        detector_pol = params.detector_pol[:]
        hpol = np.argwhere(detector_pol == 1).flatten()
        vpol = np.argwhere(detector_pol == 2).flatten()
        dx = params.detector_delta_x[:]
        dy = params.detector_delta_y[:]

        ampl_h = pdata_h['beammap/amplitude'][:]
        ampl_v = pdata_v['beammap/amplitude'][:]
        rel_ampl_v = (ampl_v - ampl_v.min()) / ampl_v.max()
        rel_ampl_h = (ampl_h - ampl_h.min()) / ampl_h.max()

        choices = [
            np.zeros(n_tones),
            ampl_v,
            ampl_h,
        ]
        ampl = np.choose(detector_pol, [np.zeros(n_tones), ampl_v, ampl_h])
        ampl_mean = np.mean(ampl[onres_ind])
        ampl_std = np.std(ampl[onres_ind])


        good_ampl = np.argwhere(
            (ampl >= ampl_mean)
            & (ampl > 0)
        ).flatten()


        diff = np.column_stack([dx, dy])
        pos = focal_center - diff
        diff = focal_center - pos

        dist = np.sqrt(dx ** 2 + dy ** 2)
        in_dist = np.argwhere(dist <= max_dist).flatten()

        good_ind = np.intersect1d(onres_ind, np.intersect1d(good_ampl, in_dist))
        low_ampl = np.intersect1d(onres_ind, np.setdiff1d(in_dist, good_ampl))
        good_h = np.intersect1d(good_ind, hpol)
        good_v = np.intersect1d(good_ind, vpol)


        sorted_dist = np.argsort(dist)
        sorted_dist_h = sorted_dist[np.isin(sorted_dist, good_h)]
        sorted_dist_v = sorted_dist[np.isin(sorted_dist, good_v)]

        # Plot Non-close beam centers
        ax.scatter(-dx[low_ampl], -dy[low_ampl], facecolors='none', edgecolors=colors[i_tile], marker='o', s=10)
        ax.scatter(-dx[good_ind], -dy[good_ind], c=colors[i_tile], marker='o', s=10)

        for i_res in sorted_dist_h[:5]:
            ax.text(
                -dx[i_res] + 0.01, -dy[i_res] - 0.01,
                f'{i_res} H',
                fontsize='small',
                horizontalalignment='left',
            )

        for i_res in sorted_dist_v[:5]:
            ax.text(
                -dx[i_res] - 0.01, -dy[i_res] - 0.01,
                f'{i_res} V',
                fontsize='small',
                horizontalalignment='right',
            )

    ax.invert_yaxis()
    ax.set_aspect('equal')
    plt.show()
    pdb.set_trace()



