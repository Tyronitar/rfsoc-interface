from rfsocinterface.core.data import ProcessedData, MapData
import numpy as np
from numpy.polynomial import Polynomial
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
from scipy import signal
import pdb

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
    ) -> Figure:
    """Plot the IQ noise blob and the rotation angle used to convert to freq/diss.
    
    Expects angle in radians.
    """
    fig = plt.figure(figsize=(9, 5))
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
    x0, y0 = np.median(data_IQ, axis=1)
    min_iq = np.min(data_IQ, axis=1)
    max_iq = np.max(data_IQ, axis=1)
    # x0 = y0 = 0
    ax.scatter(data_IQ[0], data_IQ[1], label='IQ Data in Hz', color='lightskyblue', rasterized=True)
    ax.scatter(data_freq_diss[0], data_freq_diss[1], label='Freq / Diss Data', color='pink', rasterized=True)

    # Compute best fit for IQ data
    # iq_mean = np.mean(data_IQ, axis=1, keepdims=True)
    # iq_std = np.std(data_IQ, axis=1, keepdims=True)
    # iq_inliers = (data_IQ >=  iq_mean - 2 * iq_std) & (data_IQ <= iq_mean + 2 * iq_std)
    # iq_inliers = iq_inliers[0] & iq_inliers[1]
    iq_inliers = np.ones(data_IQ.shape[1], dtype=bool)
    fit_IQ = Polynomial.fit(data_IQ[0, iq_inliers], data_IQ[1, iq_inliers], fit_order)

    # Compute best fit for freq / diss data
    # fd_mean = np.mean(data_freq_diss, axis=1, keepdims=True)
    # fd_std = np.std(data_freq_diss, axis=1, keepdims=True)
    # fd_inliers = (data_freq_diss >=  fd_mean - 2 * fd_std) & (data_freq_diss<= fd_mean + 2 * fd_std)
    # fd_inliers = fd_inliers[0] & fd_inliers[1]
    iq_inliers = np.ones(data_freq_diss.shape[1], dtype=bool)
    fit_fd = Polynomial.fit(data_freq_diss[0], data_freq_diss[1], fit_order)

    # Plot fits
    x_iq = np.linspace(min_iq[0], max_iq[0], 100)
    ax.plot(x_iq, fit_IQ(x_iq), linestyle='--', color='blue', label='IQ fit')
    x_fd = np.linspace(np.min(data_freq_diss[0]), np.max(data_freq_diss[0]), 100)
    ax.plot(x_fd, fit_fd(x_fd), linestyle='--', color='red', label='freq/diss fit')
 
    # # Plot center point
    # ax.scatter(x0, y0, label='IQ midpoint', color='blue')

    # Determmine direction the data is oriented using the midpoint of the fit
    i_bar = (min_iq[0] + max_iq[0]) / 2
    q_bar = fit_IQ(i_bar)
    sign_i = np.sign(i_bar)
    sign_q = np.sign(q_bar)
    
    # Compute the angle the IQ data is at relative to the IQ basis
    m_bar = fit_IQ.deriv()(i_bar)
    current_angle = np.atan2(sign_q * np.abs(m_bar), sign_i)
    print(f'\ti_bar = {i_bar}')
    print(f'\tm_bar = {m_bar}')
    print(f'\ttheta = {np.degrees(current_angle)} degrees')

    # Plot angle of rotation used for computing freq / diss
    r = np.ptp(data_IQ) / 8
    plot_arc(
        ax,
        current_angle,
        current_angle + angle,
        r,
        x0=x0,
        y0=y0,
        color='black',
        label='Actual rotation to Freq / Diss',
    )
    # Plot angle IQ data makes with the basis
    r1 = np.ptp(data_IQ) / 16
    plot_arc(
        ax,
        0,
        current_angle,
        r1,
        x0=x0,
        y0=y0,
        color='xkcd:bright blue',
        label='Initial angle based on IQ fit',
    )

    ax.legend()
    fig.tight_layout()

    return fig



if __name__ == '__main__':
    date = '20250912'
    setnum = 1014
    data = MapData.from_file(date, setnum, 'r')
    with PdfPages(f'{date}_{setnum}_IQ_rotation_quadratic.pdf') as pdf:
        for i_res in range(data.n_tones):
        # for i_res in range(10):
            print(f'Resonator {i_res}:')
            fig = plot_angle_in_blob(
                data.data_IQ[:, i_res],
                data.data_freq_diss[:, i_res],
                data.IQ_to_freq_diss_angle[i_res],
                data.adc_units_to_hz[i_res],
                title=f'IQ to Frequency/Dissipation Rotation for Resonator {i_res}'
            )
            pdf.savefig(fig)
            plt.close(fig)

    # plt.show()
    data.close()

    # quad_sum = np.sqrt(data.data_I[:] ** 2 + data.data_Q[:] ** 2)
    # source_peak_idx = np.argmax(quad_sum, axis=1)

    # peak_I = data.data_I[np.arange(data.n_tones, dtype=int), source_peak_idx]
    # peak_Q = data.data_Q[np.arange(data.n_tones, dtype=int), source_peak_idx]

    # angle = -np.atan2(peak_Q, peak_I)

    # plt.figure()
    # plt.scatter(data.IQ_to_freq_diss_angle[:], angle)
    # one_to_one = np.arange(-4, 4) 
    # plt.plot(one_to_one, one_to_one, linestyle='--', color='red')
    # plt.plot(one_to_one, one_to_one + np.pi / 2, linestyle='--', color='green')
    # plt.figure()
    # diff = data.IQ_to_freq_diss_angle[:] - angle

    # too_large_indices = np.where(diff > np.pi)
    # too_small_indices = np.where(diff < -np.pi)
    # diff[too_large_indices] -= 2 * np.pi
    # diff[too_small_indices] += 2 * np.pi

    # plt.hist(diff)

    # plt.figure()
    # plt.scatter(np.arange(data.n_tones), diff)

    # plt.show()
    # pdb.set_trace()
