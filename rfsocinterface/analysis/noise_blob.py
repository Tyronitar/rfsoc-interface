import pdb
from rfsocinterface.core.data import ProcessedData
from pathlib import Path
from typing import Literal
import numpy as np
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


