import pdb
from rfsocinterface.core.data.storage import ProcessedData
from pathlib import Path
from typing import Literal
import numpy as np
from numpy.polynomial import Polynomial
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy import signal
from matplotlib.backends.backend_pdf import PdfPages
from kidpy3 import RawDataFile

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
        angle: float,
        adc_units_to_Hz: float,
        title: str='',
        fit_order: int=2,
        alpha: float=0.5,
        sigma: float=2.5,
        markersize: float=0.5,
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

    # Compute best fit for IQ data
    iq_mean = np.mean(data_IQ, axis=1, keepdims=True)
    iq_std = np.std(data_IQ, axis=1, keepdims=True)
    iq_inliers_mask = (data_IQ >=  iq_mean - sigma * iq_std) & (data_IQ <= iq_mean + sigma * iq_std)
    iq_inliers_mask = iq_inliers_mask[0] & iq_inliers_mask[1]
    # iq_inliers = np.ones(data_IQ.shape[1], dtype=bool)
    iq_inliers = data_IQ[:, iq_inliers_mask]
    ax.scatter(iq_inliers[0], iq_inliers[1], label='IQ Data in Hz', color='blue', rasterized=True, alpha=alpha, edgecolors=None, s=markersize)
    fit_IQ = Polynomial.fit(iq_inliers[0], iq_inliers[1], fit_order)

    # Compute best fit for freq / diss data
    fd_mean = np.mean(data_freq_diss, axis=1, keepdims=True)
    fd_std = np.std(data_freq_diss, axis=1, keepdims=True)
    fd_inliers_mask = (data_freq_diss >=  fd_mean - sigma * fd_std) & (data_freq_diss<= fd_mean + sigma * fd_std)
    fd_inliers_mask = fd_inliers_mask[0] & fd_inliers_mask[1]
    fd_inliers = data_freq_diss[:, fd_inliers_mask]
    ax.scatter(fd_inliers[0], fd_inliers[1], label='Freq / Diss Data', color='red', rasterized=True, alpha=alpha, edgecolors=None, s=markersize)
    # fd_inliers = np.ones(data_freq_diss.shape[1], dtype=bool)
    fit_fd = Polynomial.fit(fd_inliers[0], fd_inliers[1], fit_order)

    # Plot fits
    min_iq = np.min(iq_inliers, axis=1)
    max_iq = np.max(iq_inliers, axis=1)
    min_fd = np.min(fd_inliers, axis=1)
    max_fd = np.max(fd_inliers, axis=1)
    x_fit = np.linspace(min(min_iq[0], min_fd[0]), max(max_iq[0], max_fd[0]))
    # x_iq = np.linspace(min_iq[0], max_iq[0], 100)
    ax.plot(x_fit, fit_IQ(x_fit), linestyle='--', color='blue', label='IQ fit')
    # x_fd = np.linspace(np.min(data_freq_diss[0]), np.max(data_freq_diss[0]), 100)
    ax.plot(x_fit, fit_fd(x_fit), linestyle='--', color='red', label='freq/diss fit')
 
    # # Plot center point
    # ax.scatter(x0, y0, label='IQ midpoint', color='blue')

    # Determmine direction the data is oriented using the midpoint of the fit
    # i_bar = (min_iq[0] + max_iq[0]) / 2
    i_bar = iq_mean[0, 0]
    q_bar = fit_IQ(i_bar)
    sign_i = np.sign(i_bar)
    sign_q = np.sign(q_bar)
    f_bar = fd_mean[0, 0]
    d_bar = fit_fd(f_bar)
    
    # Compute the angle the IQ data is at relative to the IQ basis
    m_bar = fit_IQ.deriv()(i_bar)
    m_bar_fd = fit_fd.deriv()(f_bar)
    # current_angle = np.atan2(sign_q * np.abs(m_bar), sign_i)
    current_angle = np.atan2(m_bar, 1)
    current_angle_fd = np.atan2(m_bar_fd, 1)
    # print(f'\ti_bar = {i_bar}')
    # print(f'\tm_bar = {m_bar}')
    # print(f'\ttheta = {np.degrees(current_angle)} degrees')

    r = np.ptp(iq_inliers) / 4
    # Plot angle of rotation used for computing freq / diss
    plot_arc(
        ax,
        current_angle,
        current_angle + angle,
        r,
        x0=x0,
        y0=y0,
        color='black',
        label=f'Actual rotation to Freq / Diss from LO sweep ($\\theta = {np.degrees(angle):.2f}^\\circ$)',
    )

    # Plot angle freq/diss data makes with the basis
    r2 = r / 2
    plot_arc(
        ax,
        0,
        current_angle_fd,
        r2,
        x0=x0,
        y0=y0,
        color='xkcd:bright red',
        label=f'Fitted angle of Freq / Diss data ($\\theta = {np.degrees(current_angle_fd):.2f}^\\circ$)',
    )
    # Plot angle IQ data makes with the basis
    r1 = r / 4
    plot_arc(
        ax,
        0,
        current_angle,
        r1,
        x0=x0,
        y0=y0,
        color='xkcd:bright blue',
        label=f'Initial angle based on IQ fit ($\\theta = {np.degrees(current_angle):.2f}^\\circ$)',
    )

    # ax.legend()
    # Shrink current axis by 20%
    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.15, box.width, box.height * 0.9])
    handles, labels = ax.get_legend_handles_labels()
    order = [0, 1, 2, 3, 5, 6, 4]

    # Put a legend to the right of the current axis
    ax.legend(
        handles=(handles[i] for i in order),
        labels=(labels[i] for i in order),
        loc='upper center',
        bbox_to_anchor=(0.5, -0.15),
        ncol=4,
    )
    # fig.tight_layout()

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


