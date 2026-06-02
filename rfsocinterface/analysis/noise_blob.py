import pdb
from rfsocinterface.core.data.storage import ProcessedData
from pathlib import Path
from typing import Literal
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import fig
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




