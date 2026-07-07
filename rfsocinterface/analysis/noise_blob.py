import pdb
from rfsocinterface.core.data.storage import ProcessedData
from pathlib import Path
from typing import Literal
import numpy as np
from numpy.polynomial import Polynomial
import numpy.typing as npt
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.figure import Figure
import scipy
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from rfsocinterface.core.utils import DEFAULT_DATA_DIRECTORY


def plot_complex_datastreams_scatter_plot(
    pd: ProcessedData,
    chanmask: npt.NDArray,
    filename: str,
    basis: str='fd',
) -> list[Figure]:
    """Make a noise blob.
    
    Plots 
    Arguments:
        data: Data to plot (2 x N_tones x N_samples).
        chanmask: (N_tones)
    """
    figs = []
    if basis.lower() == 'fd':
        data = pd.data_freq_diss
        xlabel = 'Frequency (Hz)'
        ylabel = 'Dissipation (Hz)'
    else:
        data = pd.data_IQ
        xlabel = 'I (ADC Units)'
        ylabel = 'Q (ADC Units)'

    with PdfPages(filename) as pdf:
        for i_res in np.argwhere(chanmask == 1).flatten():
            fig = plt.figure(figsize=(9, 6))
            ax = plt.subplot()
            ax.scatter(data[0, i_res], data[1, i_res])
            ax.set_aspect('equal')

            ax.set_xlabel(xlabel, fontsize=16)
            ax.set_ylabel(ylabel, fontsize=16)
                
            ax.tick_params(labelsize=14)
            ax.set_title(f'Resonator {i_res}', fontsize=16)
            figs.append(fig)
            pdf.savefig(fig)
            plt.close(fig)
    return figs

def line_and_circle_intersection_points(m,b,x0,y0,r):
    x_list = []
    y_list = []

    c1 = 1 + m ** 2
    c2 = - 2.0 * x0 + 2 * m * ( b - y0 )
    c3 = x0 ** 2 + ( b - y0 ) ** 2 - r ** 2

    # solve the quadratic equation:

    delta = c2 ** 2 - 4.0 * c1 * c3

    x1 = ( - c2 + np.sqrt(delta) ) / ( 2.0 * c1 )
    x2 = ( - c2 - np.sqrt(delta) ) / ( 2.0 * c1 )

    x_list.append(x1)
    x_list.append(x2)

    y1 = m * x1 + b
    y2 = m * x2 + b

    y_list.append(y1)
    y_list.append(y2)

    return x_list, y_list

def plot_arc(
        ax: plt.Axes,
        theta_start: float,
        theta_end: float,
        r: float,
        x0: float=0,
        y0: float=0,
        **kwargs,
):
    color = kwargs.get('color', 'black')
    angle = theta_end - theta_start
    theta = np.linspace(theta_start, theta_end, 100)
    x = r * np.cos(theta) + x0
    y = r * np.sin(theta) + x0
    arc = ax.plot(x, y, **kwargs)

    # Add lines on ends of angle
    rs = np.linspace(0, r * 3, 10)
    xs = rs * np.cos(theta_start) + x0
    ys = rs * np.sin(theta_start) + x0
    plt.plot(xs, ys, color=color)
    xs = rs * np.cos(theta_end) + x0
    ys = rs * np.sin(theta_end) + x0
    plt.plot(xs, ys, color=color)


    # Add text showing the angle in degrees
    mid_angle = angle / 2
    mid_angle_x = (1.2 * r) * np.cos(theta_start + mid_angle) + x0
    mid_angle_y = (1.2 * r) * np.sin(theta_start + mid_angle) + y0
    ax.annotate(f'{np.degrees(angle):.2f}', xy=(mid_angle_x, mid_angle_y), color=color)

    # Add arrow showing direction of rotation
    ax.annotate(
        '',
        xy=(mid_angle_x, mid_angle_y),
        arrowprops=dict(arrowstyle='->', color=color),
        size=10,
        color=color,
    )



def plot_angle_in_blob(
        data_IQ: npt.NDArray,
        data_freq_diss: npt.NDArray,
        IQ_to_freq_diss_angle: float,
        adc_units_to_Hz: float,
        title: str='',
        fit_order: int=2,
        alpha: float=0.5,
        sigma: float=2.5,
        markersize: float=0.5,
        source_crossing_sample: int=None,
    ) -> Figure:
    """Plot the IQ noise blob and the rotation angle used to convert to freq/diss.
    
    Expects angle in radians.
    """
    fig = plt.figure(figsize=(12, 5))
    fig.set_dpi(300)
    ax = fig.subplots()
    ax.grid(True)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Dissipation(Hz)')

    ax.axhline(0, color='dimgray')
    ax.axvline(0, color='dimgray')

    n_samples = data_IQ.shape[1]
    data_IQ = data_IQ[:] / adc_units_to_Hz
    data_freq_diss = data_freq_diss[:] 
    # x0, y0 = np.median(data_IQ, axis=1)
    x0 = y0 = 0
    # x0 = y0 = 0

    # Identify inliers for IQ data and scatter plot
    iq_mean = np.mean(data_IQ, axis=1, keepdims=True)
    iq_std = np.std(data_IQ, axis=1, keepdims=True)
    iq_inliers_mask = (data_IQ >=  iq_mean - sigma * iq_std) & (data_IQ <= iq_mean + sigma * iq_std)
    iq_inliers_mask = iq_inliers_mask[0] & iq_inliers_mask[1]
    # iq_inliers = np.ones(data_IQ.shape[1], dtype=bool)
    iq_inliers = data_IQ[:, iq_inliers_mask]
    ax.scatter(iq_inliers[0], iq_inliers[1], label='IQ Data in Hz', color='blue', rasterized=True, alpha=alpha, edgecolors=None, s=markersize)

    # Identify inliers for freq / diss data and scatter plot
    fd_mean = np.mean(data_freq_diss, axis=1, keepdims=True)
    fd_std = np.std(data_freq_diss, axis=1, keepdims=True)
    fd_inliers_mask = (data_freq_diss >=  fd_mean - sigma * fd_std) & (data_freq_diss<= fd_mean + sigma * fd_std)
    fd_inliers_mask = fd_inliers_mask[0] & fd_inliers_mask[1]
    fd_inliers = data_freq_diss[:, fd_inliers_mask]
    ax.scatter(fd_inliers[0], fd_inliers[1], label='Freq / Diss Data', color='red', rasterized=True, alpha=alpha, edgecolors=None, s=markersize)
    # fd_inliers = np.ones(data_freq_diss.shape[1], dtype=bool)

    # Compute best fit for IQ and freq / diss data
    min_iq = np.min(iq_inliers, axis=1)
    max_iq = np.max(iq_inliers, axis=1)
    min_fd = np.min(fd_inliers, axis=1)
    max_fd = np.max(fd_inliers, axis=1)
    min_x = min(min_iq[0], min_fd[0])
    max_x = max(max_iq[0], max_fd[0])
    min_y = min(min_iq[1], min_fd[1])
    max_y = max(max_iq[1], max_fd[1])
    med_plot_dim = abs(min(max_x, max_y)) / 2
    med_plot_dim_iq = abs(np.min(max_iq)) / 2
    med_plot_dim_fd = abs(np.min(max_fd)) / 2

    # Scale vectors in plot by largest dimension / 2
    iq_ptp = np.ptp(iq_inliers, axis=1)
    fd_ptp = np.ptp(fd_inliers, axis=1)
    vector_scaling_factor = max(*iq_ptp, *fd_ptp) / 2

    iq_color = 'blue'
    # iq_color = 'cyan'

    fd_color = 'red'
    # fd_color = 'darkorange'

    if source_crossing_sample is None:
        # Do PCA analysis to determine the directions of the datasets
        iq_pca = PCA(n_components=2)
        iq_pca.fit(data_IQ.T)
        fd_pca = PCA(n_components=2)
        fd_pca.fit(data_freq_diss.T)

        scaled_iq_vec = iq_pca.components_[0] * vector_scaling_factor
        iq_angle = np.atan2(scaled_iq_vec[1], scaled_iq_vec[0])
        iq_vec_label = 'IQ principal component vector'
        iq_angle_label = f'IQ angle based on PCA ($\\theta = {np.degrees(iq_angle):.2f}^\\circ$)'

        scaled_fd_vec = fd_pca.components_[0] * vector_scaling_factor
        fd_angle = np.atan2(scaled_fd_vec[1], scaled_fd_vec[0])
        fd_vec_label = 'FD principal component vector'
        fd_angle_label = f'Freq / Diss angle based on PCA ($\\theta = {np.degrees(fd_angle):.2f}^\\circ$)'
    else:
        # USe the source crossing values to compute the direction
        source_iq = data_IQ[:, source_crossing_sample]
        source_fd = data_freq_diss[:, source_crossing_sample]

        scaled_iq_vec = source_iq / np.linalg.norm(source_iq) * vector_scaling_factor
        iq_angle = np.atan2(source_iq[1], source_iq[0])
        iq_vec_label = 'IQ vector at source crossing'
        iq_angle_label = f'IQ angle implied by source crossing \n($\\theta = {np.rad2deg(iq_angle):.2f}^\\circ$)'

        scaled_fd_vec = source_fd / np.linalg.norm(source_fd) * vector_scaling_factor
        fd_angle = np.atan2(source_fd[1], source_fd[0])
        fd_vec_label = 'Freq / Diss vector at source crossing'
        fd_angle_label = f'Freq / Diss angle implied by source crossing \n($\\theta = {np.rad2deg(fd_angle):.2f}^\\circ$)'

    # Plot the vectors
    iq_vec_plot = ax.quiver(0, 0, scaled_iq_vec[0], scaled_iq_vec[1], scale_units='xy', scale=1, linestyle=':', color=iq_color, label=iq_vec_label)
    iq_vec_plot.set_path_effects([
        path_effects.withStroke(linewidth=1, foreground='black')
    ])
    fd_vec_plot = ax.quiver(0, 0, scaled_fd_vec[0], scaled_fd_vec[1], scale_units='xy', scale=1, linestyle=':', color=fd_color, label=fd_vec_label)
    fd_vec_plot.set_path_effects([
        path_effects.withStroke(linewidth=1, foreground='black')
    ])

    # r = np.ptp(iq_inliers) / 4
    r = med_plot_dim * 1.5
    # Plot angle of rotation used for computing freq / diss
    plot_arc(
        ax,
        iq_angle,
        iq_angle + IQ_to_freq_diss_angle,
        r,
        x0=x0,
        y0=y0,
        color='black',
        label=f'Actual rotation used to create Freq / Diss data \n($\\theta = {np.rad2deg(IQ_to_freq_diss_angle):.2f}^\\circ$)',
    )

    # Plot angle freq/diss data makes with the basis
    r2 = r * 2 / 3
    plot_arc(
        ax,
        0,
        fd_angle,
        r2,
        x0=x0,
        y0=y0,
        color=fd_color,
        label=fd_angle_label,
    )
    # Plot angle IQ data makes with the basis
    r1 = r / 3
    plot_arc(
        ax,
        0,
        iq_angle,
        r1,
        x0=x0,
        y0=y0,
        color=iq_color,
        label=iq_angle_label,
    )

    # ax.legend()
    # Shrink current axis by 20%
    box = ax.get_position()
    handles, labels = ax.get_legend_handles_labels()
    order = [0, 1, 2, 3, 6, 5, 4]
    ax.set_position([box.x0, box.y0 + box.height * 0.25, box.width, box.height * 0.8])

    # Put a legend to the right of the current axis
    ax.legend(
        handles=(handles[i] for i in order),
        labels=(labels[i] for i in order),
        loc='upper center',
        bbox_to_anchor=(0.5, -0.15),
        ncol=4,
        fontsize=8,
    )

    return fig


if __name__ == '__main__':
    date = '20250916'
    setnum = 1017
    basis='fd'
    output_file = f'{DEFAULT_DATA_DIRECTORY}/{date}/{date}_set{setnum}_noise_blob_{basis}.pdf'
    ds_factor = 4

    pd = ProcessedData.from_tod(
        date,
        setnum,
        do_electronics_noise_removal=True,
        ds_factor=ds_factor,
    )
    raw_data = RawDataFile('/data/20250916/20250916_Be231102p2_100_tones_TOD_set1017.h5', 'r')

    figs = plot_complex_datastreams_scatter_plot(
        pd,
        pd.chanmask[:],
        output_file,
        basis=basis,
    )
    for i_res in np.argwhere(pd.chanmask[:] == 1).flatten():
        print(f'Resonator {i_res}: {np.degrees(pd.IQ_to_freq_diss_angle[i_res])}')

    # for i_res in [53, 54, 56]:
    #     sweep = raw_data.lo_sweep[1, i_res, :]
    #     sweep_i = np.real(sweep)
    #     sweep_q = np.imag(sweep)
    #     plt.figure()
    #     plt.title(f'LO Sweep for Resonator {i_res}')
    #     plt.plot(sweep_i, label='data_I')
    #     plt.plot(sweep_q, label='data_Q')
    #     plt.annotate(f'$\\theta$ LO sweep = {np.degrees(pd.IQ_to_freq_diss_angle[i_res]):.03} degrees', (0, 0))
    #     plt.legend()
    # plt.show()
    pd.close()


