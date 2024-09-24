from __future__ import annotations
from pathlib import Path

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from onr_fit_lo_sweeps import simple_derivative_fits
from onrkidpy import get_chanmask

from rfsocinterface.utils import ensure_path

class ResonatorData:
    """Class for accessing and plotting the data of a single resonator.

    All of the data for this resonator comes directly from the provided LoSweepData
    object.
    
    Attributes:
        data (LoSweepData): The LO sweep to reference the data of.
        idx (int): The index of this resonator within the LO sweep.
        flagged (bool): Whether this resonator has been flagged for follow up.
    """

    def __init__(self, data: LoSweepData, idx: int):
        """Initialize a ResonatorData object."""
        self.data = data
        self.idx = idx
        self.flagged = False
    
    def plot(self, ax: plt.Axes | None=None, animated: bool=False) -> Figure | None:
        """Plot the results of the LO sweep fitting for this resonator.
        
        Arguments:
            ax (plt.Axes | None): The axes to place the plot in. If None, this method
                will create a new figure. Defaults to None.
            animated (bool): Whether to make the vertical line animated. Defaults to
                False.
        
        Returns:
            (Figure | None): The newly created figure. Will only return something if
                no axes was provided.
        """
        return_fig = False
        # If not axes provided, create a new figure
        if ax is None:
            fig = plt.figure(figsize=(8, 5))
            ax = plt.subplot()
            return_fig = True
            ax.set_title(f'Transmission Magnitude near Resonator #{self.idx}')
            ax.set_xlabel('Frequency (MHz)')
            ax.ticklabel_format(useOffset=False, style='plain')
            ax.set_ylabel(r'$|S_{21}|$')
        # Otherwise, just plot inside the existing axes
        else:
            ax.set_facecolor('white')
            ax.set_yticks([])
            ax.set_xticks([])

        ax.plot(self.freq * 1e-6, self.s21)
        ax.axvline(x=self.fit_f0 * 1e-6, color='r', animated=animated)

        # Scale the span of the plot based on the frequency ratio
        new_span = self.span * 1e-6 * self.freq_ratio
        ax.set_xlim(np.mean(self.freq * 1e-6)-new_span/2., np.mean(self.freq * 1e-6+new_span/2.))

        # Add a label showing the resonator number
        if self.is_onres:
            ax.legend(
                ["{:d}".format(self.idx)],
                fontsize=6,
                loc = 3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                bbox_to_anchor=(0.01,0.02),
                alignment='center',
                edgecolor='black',
                # bbox_to_anchor=(-0.2,-0.15)
            )
            if self.flagged:
                ax.set_facecolor('yellow')
        else:
            ax.legend(
                ["{:d}".format(self.idx) + ', dS21=' + "{:4.1f}".format(np.max(self.s21)-np.min(self.s21))],
                fontsize=6,
                loc = 3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                bbox_to_anchor=(0.01,0.02),
                alignment='center',
                edgecolor='black',
            )
            ax.set_facecolor('orange')
        
        if return_fig:
            return fig

    @property
    def tone(self) -> float:
        """float: The original tone for this resonator from the tone list, in Hz."""
        return self.data.tone_list[self.idx]
    
    @property
    def freq(self) -> npt.NDArray:
        """npt.NDArray: The frequency window of this resonator, in Hz."""
        return self.data.freq[self.idx, :]

    @property
    def s21(self) -> npt.NDArray:
        """npt.NDArray: The absolute value of $$S_{21}$$."""
        return self.data.s21[self.idx, :]

    @property
    def difference(self) -> float:
        """float: The difference in the fitted value and the original tone, in KHz."""
        return (self.data.fit_f0[self.idx] - self.data.tone_list[self.idx]) * 1e-3
    
    @property
    def is_onres(self) -> bool:
        """bool: Whether this resonator is on-resonance."""
        return self.data.chanmask[self.idx] == 1
    
    @property
    def freq_ratio(self) -> float:
        """float: The ratio of the original tone and the maximum tone in the sweep."""
        return self.tone / self.data.tone_list.max()
    
    @property
    def fit_f0(self) -> float:
        """float: The fitted value for the resonance frequency."""
        return self.data.fit_f0[self.idx]
    
    @fit_f0.setter
    def fit_f0(self, val: float):
        self.data.fit_f0[self.idx] = val
        self.flagged = np.abs(self.difference) > self.data.diff_to_flag[self.idx]
    
    @property
    def fit_qi(self) -> float:
        """float: The qi factor for the fitted resonance."""
        return self.data.fit_qi[self.idx]

    @fit_qi.setter
    def fit_qi(self, val: float):
        self.data.fit_qi[self.idx] = val
    
    @property
    def fit_qc(self) -> float:
        """float: The qc factor for the fitted resonance."""
        return self.data.fit_qc[self.idx]

    @fit_qc.setter
    def fit_qc(self, val: float):
        self.data.fit_qc[self.idx] = val
    
    @property
    def span(self) -> float:
        """float: The span of the frequency window for the resonator."""
        return np.ptp(self.freq)
    
    def fit(self, df: float) -> tuple[float, float, float]:
        """Perform a fit to find the resonance frequency."""
        fit_f0 = simple_derivative_fits(df, self.freq, self.tone, self.s21)
        fit_qi = 0.
        fit_qc = 0.

        return fit_f0, fit_qi, fit_qc
    
class LoSweepData:
    """Class for storing and plotting the data from an entire LO sweep.

    This class contains the data from an LO sweep. It also provides methods for fitting
    the data to determine new resonance frequencies, and plotting the results.
    
    Attributes:
        data (npt.NDArray): The data from the LO sweep.
        tone_list (npt.NDArray): The tone for each resonator.
        freq (npt.NDArray): The full frequency sprectrum of the sweep.
        s21 (npt.NDArray): The vlaue of S_{21} at all frequencies in `freq`.
        chanmask (npt.NDarray): A mask to determine which frequencies are on-resonance.
        resonator_data (list[ResonatorData]): List of the data for each resonator.
        fit_f0 (npt.NDArray): The fitted resonance frequencies for each resonator.
        fit_qi (npt.NDArray): The qi factor of the fitted resonance frequency for each
            resonator.
        fit_qc (npt.NDArray): The qc factor of the fitted resonance frequency for each
            resonator.
        diff_to_flag (npt.NDArray): The mimimum difference in tone and fitted frequency
            to flag for further inspection.
    """

    @ensure_path(2, 3)
    def __init__(self, tone_list: npt.NDArray, sweep_file: Path, chanmask_file: Path) -> None:
        """Initialize a LoSweepData object."""
        self.data = np.load(sweep_file)
        self.tone_list = tone_list
        self.freq = self.data[0, :, :]
        self.s21 = 10. * np.log10(np.abs(self.data[1, :, :]))
        self.chanmask = get_chanmask(chanmask_file)
        self.resonator_data = [ResonatorData(self, i) for i in range(self.nchan)]

        self.fit_f0 = np.zeros(self.nchan)
        self.fit_qi = np.zeros(self.nchan)
        self.fit_qc = np.zeros(self.nchan)
        self.fit_f0[self.offres_ind] = tone_list[self.offres_ind]
        self.diff_to_flag = (3./200.) * self.tone_list * 1e-6
    
    @property
    def difference(self) -> npt.NDArray:
        """The difference of the fitted frequencies and the provided tones."""
        return (self.fit_f0 - self.tone_list) * 1e-3

    @property
    def nchan(self) -> int:
        """The number of resonators."""
        return np.size(self.chanmask)
    
    @property
    def df(self) -> float:
        """The difference between two frequency data points."""
        return self.freq[0, 1] - self.freq[0, 0]
    
    @property
    def offres_ind(self) -> npt.NDArray:
        """The indices of frequencies that are off-resonance."""
        return np.argwhere(self.chanmask == 0)
    
    @property
    def flagged(self) -> npt.NDArray:
        """The indices of the resonators which are flagged."""
        return np.argwhere(self.difference > self.diff_to_flag)
    
    def fit(self, do_print=False):
        """Perform a fit to determine the resoncance frequencies of each resonator."""

        for i_chan in np.argwhere(self.chanmask == 1):
            # pull in the sweep data for this tone
            i_chan = i_chan[0]
            resonator = self.resonator_data[i_chan]

            # call the resonator fitter
            f0, qc, qi = resonator.fit(self.df)
            self.fit_f0[i_chan] = f0
            self.fit_qc[i_chan] = qc
            self.fit_qi[i_chan] = qi

            diff = resonator.difference
            if np.abs(diff) > self.diff_to_flag[i_chan]:
                resonator.flagged = True
                if do_print:
                    print("tone index =", "{:4d}".format(i_chan), \
                            "|| new tone =", "{:9.5f}".format(self.fit_f0[i_chan]*1.e-6), \
                            "|| old tone =", "{:9.5f}".format(self.tone_list[i_chan]*1.e-6), \
                            "|| difference (kHz) =", "{:+5.3f}".format(diff))

    def plot(self, ncols: int=18) -> Figure:
        """Plot the results of fitting the LO sweep.
        
        Arguments:
            ncols (int): The number of columns to use in the figure. The figure will have
                one inch width for each column.
        
        Returns:
            (Figure): The generated figure showing the plot for each resonator.
        """
        # Setup for plots 
        nrows = int(np.ceil(self.nchan/ ncols))

        fig = plt.figure(figsize=(ncols, nrows))
        plt.rc('font', size=8)
        counter = 0

        #loop over resonators to perform fit
        for resonator in self.resonator_data:
            subplot = plt.subplot2grid((nrows, ncols), (counter // ncols, np.mod(counter, ncols)))
            resonator.plot(subplot)
            counter += 1

        plt.tight_layout()
        return fig

def get_tone_list(filename: str, lo_freq: float=400):
    """Get the data from a tone-list and convert to Hz from MHz."""
    flist = np.load(filename)
    tones = lo_freq * 1.0e6 + flist
    return tones
