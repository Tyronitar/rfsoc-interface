from __future__ import annotations
import logging
import pdb

from concurrent.futures import Future
from typing import Callable
from multiprocessing import Lock
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait

from pathlib import Path
from PySide6.QtWidgets import QProgressDialog

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.gridspec import GridSpec
from scipy.signal import savgol_filter, find_peaks
# import scraps as scr
import h5py

from PySide6.QtWidgets import QApplication
from rfsocinterface.core.utils import BAD_RFSOC_TONE_START_INDEX, ensure_path, PERMISSIONS_USR_RW, parallel_plot
from rfsocinterface.core.pool import QThreadJobPool
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.widgets.progress_bar import QThreadJobProgressDialog
from kidpy3 import capture_packets
from kidpy3.hardware.Valon5009 import Valon5009, SYNTH_B
from kidpy3.data_handler import Rfchan
# from kidpy3.measure import ResonatorFinder


_logger = logging.getLogger(__name__)

DEFAULT_NCOLS = 10


def resonator_plot_formatter(x: float, pos: int) -> str:
    """Format the x-axis labels for the resonator plot, converting to MHz.

    Arguments:
        x (float): The x value to format.
        pos (int): The position of the tick.

    Returns:
        str: The formatted string for the x-axis label.
    """
    return f'{x * 1e-6:.3f}'

def simple_derivative_fits(df: npt.NDArray, freq: npt.NDArray, tone_list: npt.NDArray, s21: npt.NDArray):

    #set up some preliminary values that we'll need
    n_freq = np.size(freq)
    old_tone_freq = tone_list
    center_ind = np.argwhere(abs(freq - old_tone_freq) == min(abs(freq - old_tone_freq))).flatten()[0]

    #smooth the data
    x = s21
    s21 = savgol_filter(s21, 7, 3, mode='mirror')

    #search for local minima
    if s21[center_ind] != min(s21):
       keepgoing = True
       while keepgoing:
            lo_ind = int(max(center_ind-1,0))
            hi_ind = int(min(center_ind+2,n_freq))
            # min_ind = np.argwhere(s21[lo_ind:hi_ind] == min(s21[lo_ind:hi_ind])).flatten()[0]
            min_ind = np.argmin(s21[lo_ind:hi_ind])
            if min_ind == (center_ind - lo_ind):
                keepgoing = False
            else:
                center_ind = lo_ind + min_ind

   
    peaks = find_peaks(-s21, prominence=2)
    if len(peaks[0]) != 0:
        prominances = peaks[1]['prominences']
        highest_prom_index = np.argmax(prominances)
        #print(freq[peaks[0][highest_prom_index]])
        f0 = freq[peaks[0][highest_prom_index]]
    else:
        f0 = freq[center_ind]
    
    return f0

def fit_resonance(df: npt.NDArray, freq: npt.NDArray, tone_list: npt.NDArray, s21: npt.NDArray):

       
    fit_f0 = simple_derivative_fits(df, freq, tone_list, s21)
    fit_qi = 0.0
    fit_qc = 0.0
    return fit_f0, fit_qc, fit_qi

def get_scraps_fit(I: npt.NDArray,Q:np.NDarray, freq: npt.NDArray, tone_list: npt.NDArray, s21: npt.NDArray, power: npt.NDArray = None, temp:npt.NDArray = None):
    data_dict = {'I': I, 'Q': Q, 'freq': freq, 'name': "resonance", 'pwr': power, 'temp': temp}
    res_obj = scr.makeResFromData(data_dict)
    res_obj.load_params(scr.hanger_params)
    res_obj.do_lmfit(scr.hanger_fit)
    return res_obj
def create_resonator_mini_plot(
        fig: Figure,
        ax: plt.Axes,
        idx: int,
        freq: npt.NDArray,
        s21: npt.NDArray,
        fit_f0: float,
        onres: bool,
        flagged: bool,
):
    ax.set_facecolor('white')
    ax.set_yticks([])
    ax.set_xticks([])
    ax.plot(freq, s21)
    ax.axvline(x=fit_f0, color='r')

    # Scale the span of the plot based on the frequency ratio
    xlim = (freq.min(), freq.max())
    ax.set_xlim(*xlim)

    # Add a label showing the resonator number
    if onres:
        ax.legend(
            [f'{idx:d}'],
            fontsize=8,
            loc=3,
            frameon=False,
            framealpha=0,
            handlelength=0,
            alignment='center',
            edgecolor='black',
        )
        if flagged:
            ax.set_facecolor('yellow')
    else:
        ax.legend(
            [f'{idx:d}, dS21={np.ptp(s21):4.1f}'],
            fontsize=8,
            loc=3,
            frameon=False,
            framealpha=0,
            handlelength=0,
            alignment='center',
            edgecolor='black',
            )
        ax.set_facecolor('orange')
def create_IQCircle_mini_plot(
        fig: Figure,
        ax: plt.Axes,
        idx: int,
        I: npt.NDArray,
        Q: npt.NDArray,
        freq: np.ndarray,
        tone_freq: float,
        freq_direction: float,
        onres: bool,
        flagged: bool,
):
    ax.set_facecolor('white')
    ax.set_yticks([])
    ax.set_xticks([])
    color = np.arange(len(I))
    ax.scatter(I, Q, c = color, s = 0.1, cmap='viridis')
    ax.set_aspect('equal')
    f0_ind = np.argmin(np.abs(freq-tone_freq))
    #ax.plot(I[f0_ind], Q[f0_ind], color = 'red', marker = '*')
    length = 0.005
    ax.quiver(I[f0_ind], Q[f0_ind], length*np.cos(-freq_direction), length*np.sin(-freq_direction), scale = 0.01, width = 0.05)
    

    # Add a label showing the resonator number
    if onres:
        ax.legend(
            [f'{idx:d}'],
            fontsize=8,
            loc=3,
            frameon=False,
            framealpha=0,
            handlelength=0,
            alignment='center',
            edgecolor='black',
        )
        if flagged:
            ax.set_facecolor('yellow')
    #else:
        #ax.legend(
        #    [f'{idx:d}, dS21={np.ptp(s21):4.1f}'],
        #    fontsize=8,
        #    loc=3,
        #    frameon=False,
        #    framealpha=0,
        #    handlelength=0,
        #   alignment='center',
        #    edgecolor='black',
        #    )
        #ax.set_facecolor('orange')


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

    def plot(self, ax: plt.Axes | None = None, animated: bool = False) -> Figure | None:
        """Plot the results of the LO sweep fitting for this resonator.

        Arguments:
            ax (plt.Axes | None): The axes to place the plot in. If None, this method
                will create a new figure. Defaults to None.fit_f0
            animated (bool): Whether to make the vertical line animated. Defaults to
                False.

        Returns:
            (Figure | None): The newly created figure. Will only return something if
                no axes was provided.
        """
        return_fig = False
        # If axes is provided, make the mini plot inside
        if ax is not None:
            create_IQCircle_mini_plot(
                None,
                ax,
                self.idx,
                self.freq,
                self.s21,
                self.tone,
                self.is_onres,
                self.flagged,
            )
            return

        # If axes not provided, create a new figure
        fig = plt.figure(figsize=(8, 5))
        ax = plt.subplot()
        ax.set_title(f'Transmission Magnitude near Resonator #{self.idx}')
        ax.set_xlabel('Frequency (MHz)')
        ax.set_ylabel(r'$|S_{21}|$')
        ax.xaxis.set_major_formatter(FuncFormatter(resonator_plot_formatter))

        ax.plot(self.freq, self.s21)
        ax.axvline(x=self.fit_f0, color='r', animated=animated)

        # Scale the span of the plot based on the frequency ratio
        ax.set_xlim(self.freq.min(), self.freq.max())

        # Add a label showing the resonator number
        if self.is_onres:
            ax.legend(
                [f'{self.idx:d}'],
                fontsize=6,
                loc=3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                alignment='center',
                edgecolor='black',
            )
            if self.flagged:
                ax.set_facecolor('yellow')
        else:
            ax.legend(
                [f'{self.idx:d}, dS21={np.ptp(self.s21):4.1f}'],
                fontsize=6,
                loc=3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                alignment='center',
                edgecolor='black',
            )
            ax.set_facecolor('orange')

        return fig

    @property
    def baseband_tone(self) -> float:
        """float: The tone for this resonator relative to the f center, in Hz."""
        return self.data.tone_list[self.idx] - self.data.f_center

    @property
    def tone(self) -> float:
        """float: The absolute tone for this resonator, in Hz."""
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
        """float: The difference in the fitted value and the original tone, in Hz."""
        return self.data.fit_f0[self.idx] - self.data.tone_list[self.idx]

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
        """float: The fitted value for the resonance frequency, in Hz."""
        return self.data.fit_f0[self.idx]

    @fit_f0.setter
    def fit_f0(self, val: float):
        self.data.fit_f0[self.idx] = val
        self.flagged = np.abs(self.difference) > self.data.diff_to_flag[self.idx]

    @property
    def fit_qi(self) -> float:
        """float: The qi factor for the fitted resonance, in Hz."""
        return self.data.fit_qi[self.idx]

    @fit_qi.setter
    def fit_qi(self, val: float):
        self.data.fit_qi[self.idx] = val

    @property
    def fit_qc(self) -> float:
        """float: The qc factor for the fitted resonance, in Hz."""
        return self.data.fit_qc[self.idx]

    @fit_qc.setter
    def fit_qc(self, val: float):
        self.data.fit_qc[self.idx] = val

    @property
    def span(self) -> float:
        """float: The span of the frequency window for the resonator, in Hz."""
        return np.ptp(self.freq)

    def fit(self, df: float, start: float = None, callback: Callable | None=None) -> tuple[float, float, float]:
        """Perform a fit to find the resonance frequency."""
        if start is None:
            start = self.tone

        return fit_resonance(df, self.freq, self.tone, self.s21)


class LoSweepData:
    """Class for storing and plotting the data from an entire LO sweep.

    This class contains the data from an LO sweep. It also provides methods for fitting
    the data to determine new resonance frequencies, and plotting the results.

    Attributes:
        data (npt.NDArray): The data from the LO sweep.
        tone_list (npt.NDArray): The tone for each resonator, in Hz.
        freq (npt.NDArray): The full frequency sprectrum of the sweep, in Hz.
        s21 (npt.NDArray): The value of S_{21} at all frequencies in `freq`.
        chanmask (npt.NDarray): A mask to determine which frequencies are on-resonance.
        resonator_data (list[ResonatorData]): List of the data for each resonator.
        fit_f0 (npt.NDArray): The fitted resonance frequencies for each resonator, in Hz.
        fit_qi (npt.NDArray): The qi factor of the fitted resonance frequency for each
            resonator, in Hz.
        fit_qc (npt.NDArray): The qc factor of the fitted resonance frequency for each
            resonator, in Hz.
        diff_to_flag (npt.NDArray): The mimimum difference in tone and fitted frequency
            to flag for further inspection, in Hz.
    """

    def __init__(
        self,
        tone_list: npt.NDArray,
        f_center: float,
        sweep_data: npt.NDArray,
        chanmask: npt.NDArray, 
        diff_to_flag: float=3e3,
        scraps_fit: bool = False,
    ) -> None:
        """Initialize a LoSweepData object."""
        self.data = sweep_data
        self.f_center = f_center  # Center frequency of the sweep in Hz
        self.tone_list = tone_list[:] + f_center  # Frequencies in Hz
        self.freq = np.real(self.data[0, :, :])
        self.s21 = np.real(10.0 * np.log10(np.abs(self.data[1, :, :])))
        self.chanmask = chanmask
        self.resonator_data = [ResonatorData(self, i) for i in range(self.nchan)]
        self.fit_f0 = self.tone_list.copy()
        self.fit_qi = np.zeros(self.nchan)
        self.fit_qc = np.zeros(self.nchan)
        self.fit_f0[self.offres_ind] = self.tone_list[self.offres_ind]
        self.set_diff_to_flag(val=diff_to_flag)
        self._fitted = False
        self._plotted = False
        self._fit_cancelled = False
        self._plot_cancelled = False
    
    def set_diff_to_flag(self, val: float=3e3):
        """Set the flagging threshold.
        
        Arguments:
            val (float): The minimumum difference to flag in Hz. (defaults to 3000.0)
        """
        # self.diff_to_flag = (val * 1e3 / 2e8) * self.tone_list
        self.diff_to_flag = np.abs(val / self.f_center * self.tone_list)
    
    @classmethod
    @ensure_path(1, 2, 3)
    def from_file(cls, tone_file: Path, sweep_file: Path, chanmask_file: Path, lo_freq: float=400) -> LoSweepData:
        """Create a LoSweepData object from a sweep file."""
        tone_list = get_tone_list(tone_file, lo_freq=lo_freq)
        data = np.load(sweep_file)
        chanmask = get_chanmask(chanmask_file)
        return cls(tone_list, lo_freq, data, chanmask)

    @classmethod
    @ensure_path(1)
    def from_h5(cls, path: Path) -> LoSweepData:
        """Create a LoSweepData object from a sweep file."""
        path = path.with_suffix('.h5')
        with h5py.File(path, 'r') as f:
            tone_list = f['global_data/baseband_freqs'][:]
            data = f['global_data/lo_sweep'][:]
            chanmask = f['global_data/chanmask'][:]
            fit_f0 = f['global_data/fit_f0'][:]
            fit_qi = f['global_data/fit_qi'][:]
            fit_qc = f['global_data/fit_qc'][:]
            f_center = f['global_data/lo_freq'][()]
        sweep = cls(tone_list, f_center, data, chanmask)
        sweep.fit_f0 = fit_f0
        sweep.fit_qi = fit_qi
        sweep.fit_qc = fit_qc
        _logger.debug(f'Loaded LO sweep data from {str(path)}')
        return sweep

    @property
    def difference(self) -> npt.NDArray:
        """The absolute difference of the fitted frequencies and the provided tones, in Hz."""
        return np.abs(self.fit_f0 - self.tone_list)

    @property
    def nchan(self) -> int:
        """The number of resonators."""
        return np.size(self.chanmask)

    @property
    def nfreq(self) -> int:
        """The number of frequencies."""
        return np.size(self.freq[0, :])

    @property
    def ngoodchan(self) -> int:
        """The number of good resonators."""
        return np.size(self.onres_ind)

    @property
    def df(self) -> float:
        """The difference between two frequency data points, in Hz."""
        return self.freq[0, 1] - self.freq[0, 0]

    @property
    def onres_ind(self) -> npt.NDArray:
        """The indices of frequencies that are on-resonance."""
        return np.argwhere(self.chanmask == 1).flatten()

    @property
    def offres_ind(self) -> npt.NDArray:
        """The indices of frequencies that are off-resonance."""
        return np.argwhere(self.chanmask == 0).flatten()

    @property
    def data_I(self) -> npt.NDArray:
        """The real part of the data."""
        return np.real(self.data[1, ...])

    @property
    def data_Q(self) -> npt.NDArray:
        """The imaginary part of the data."""
        return np.imag(self.data[1, ...])

    @property
    def flagged(self) -> npt.NDArray:
        """The indices of the resonators which are flagged."""
        return np.argwhere(np.abs(self.difference) > self.diff_to_flag)
    
    @property
    def new_tone_list(self) -> npt.NDArray:
        """The new base band frequencies, based on the fit"""
        return self.fit_f0 - self.f_center
    
    def cancel_fit(self):
        self._fit_cancelled = True

    def cancel_plot(self):
        self._plot_cancelled = True

    def fit(self, callback: Callable | None=None, max_workers: int=4, scraps_fit: bool =False) -> None:
        """Perform a fit to determine the resoncance frequencies of each resonator."""
        self._fitted = False
        self._fit_cancelled = False
        _logger.debug('Fitting LO sweep results...')
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            if scraps_fit:
                res = executor.map(
                    get_scraps_fit,
                    self.data_I[self.onres_ind, :],
                    self.data_Q[self.onres_ind, :],
                    self.freq[self.onres_ind, :],
                    self.tone_list[self.onres_ind],
                    self.s21[self.onres_ind, :],
                )
                for i_res, res_obj in zip(self.onres_ind, res):
                    
                    self.fit_f0[i_res] = res_obj.lmfit_result['default']['result'].params['f0'].value
                    self.fit_qi[i_res] = res_obj.lmfit_result['default']['result'].params['qi'].value
                    self.fit_qc[i_res] = res_obj.lmfit_result['default']['result'].params['qc'].value
                    if self._fit_cancelled:
                        return
                    if callback is not None:
                        callback()
                self._fitted = True
                return
            res = executor.map(
                fit_resonance,
                (self.df for _ in range(self.ngoodchan)),
                self.freq[self.onres_ind, :],
                self.tone_list[self.onres_ind],
                self.s21[self.onres_ind, :],
            )
            for i_res, (fit_f0, fit_qi, fit_qc) in zip(self.onres_ind, res):
                if self._fit_cancelled:
                    return
                # i_res = self.onres_ind[i]
                self.fit_f0[i_res] = fit_f0
                self.fit_qi[i_res] = fit_qi
                self.fit_qc[i_res] = fit_qc
                if callback is not None:
                    callback()
            
        self._fitted = True

    def _fit_i(self, i_chan):
            # pull in the sweep data for this tone
            i = i_chan[0]
            resonator = self.resonator_data[i]

            # call the resonator fitter
            f0, qc, qi = resonator.fit(self.df)
            self.fit_f0[i] = f0
            self.fit_qc[i] = qc
            self.fit_qi[i] = qi

            diff = resonator.difference
            if np.abs(diff) > self.diff_to_flag[i]:
                resonator.flagged = True
                string = ' || '.join([
                    f'tone index = {i:4d}',
                    f'new tone = {self.fit_f0[i] * 1.0e-6:9.5f} MHz',
                    f'old tone = {self.tone_list[i] * 1.0e-6:9.5f} MHz',
                    f'difference (kHz) = {diff * 1e-3:+5.3f}',
                ])
                _logger.info(string)
            self.tone_list = f0


    def plot(self, ncols: int=DEFAULT_NCOLS, callback: Callable | None=None, fig: Figure=None, plot_IQ_Circle: bool = False) -> Figure:
        """Plot the results of fitting the LO sweep.

        Arguments:
            ncols (int): The number of columns to use in the figure. The figure will have
                one inch width for each column.

        Returns:
            (Figure): The generated figure showing the plot for each resonator.
        """
        self._plotted = False
        self._plot_cancelled = False

        # Setup for plots
        nchan = self.nchan
        # nchan = 50
        if fig is None:
            nrows = int(np.ceil(nchan / ncols))
            fig = plt.figure(figsize=(ncols, nrows), dpi=100)
            for i in range(1, nchan + 1):
                fig.add_subplot(nrows, ncols, i, frame_on=False, xticks=[], yticks=[], aspect='equal')
        axes = fig.axes
        # plt.rc('font', size=8)
        # for i in range(nchan, np.size(axes)):
        #     np.ravel(axes)[i].set_axis_off()

        # Make this wrapper so `parallel_plot` can be canceled
        def callback_wrapper():
            if self._plot_cancelled:
                raise InterruptedError('Plotting Cancelled')
            if callback is not None:
                callback()

        try:
            if plot_IQ_Circle:
                parallel_plot(
                    fig,
                    axes,
                    create_IQCircle_mini_plot,
                    np.arange(nchan),
                    self.data_I[:nchan],
                    self.data_Q[:nchan],
                    self.freq[:nchan],
                    self.tone_list[:nchan],
                    self.freq_direction()[0],
                    np.isin(np.arange(nchan), self.onres_ind[:nchan]),
                    np.isin(np.arange(nchan), self.flagged[:nchan]),
                    callback=callback_wrapper,
                )
            else:
                parallel_plot(
                    fig,
                    axes,
                    create_resonator_mini_plot,
                    np.arange(nchan),
                    self.freq[:nchan],
                    self.s21[:nchan],
                    self.fit_f0[:nchan],
                    np.isin(np.arange(nchan), self.onres_ind[:nchan]),
                    np.isin(np.arange(nchan), self.flagged[:nchan]),
                    callback=callback_wrapper,
                )
        except InterruptedError:
            return
        
        self._plotted = True
        return fig

    def _fit_i(self, i_chan):
        if pd is None:
            pd = QThreadJobPool(parent=self)
        return fig, pd.map(ResonatorData.plot, self.resonator_data, subplots)
    
    @ensure_path(1)
    def savenp(self, fname: Path):
        path = fname.with_suffix('.npy')
        path.touch(PERMISSIONS_USR_RW, exist_ok=True)
        np.save(path, self.data)
    
    @ensure_path(1)
    def save_new_tone_list(self, fname: Path):
        path = fname.with_suffix('.npy')
        path.touch(PERMISSIONS_USR_RW, exist_ok=True)
        np.save(fname, self.new_tone_list)
        _logger.debug(f'LoSweepData saved new tone list to {str(fname)}')

    @ensure_path(1)
    def saveh5(self, fname: Path):
        """Save the LO Sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        path.touch(PERMISSIONS_USR_RW)
        with h5py.File(path, 'w') as fh:
            fh.create_dataset('global_data/lo_sweep', data=self.data)
            fh.create_dataset('global_data/lo_freq', data=self.f_center)
            fh.create_dataset('global_data/baseband_freqs', data=self.tone_list - self.f_center)
            fh.create_dataset('global_data/chanmask', data=self.chanmask)
            fh.create_dataset('global_data/fit_f0', data=self.fit_f0)
            fh.create_dataset('global_data/fit_qi', data=self.fit_qi)
            fh.create_dataset('global_data/fit_qc', data=self.fit_qc)
        _logger.info(f'LoSweepData saved to {str(fname)}')

    def freq_direction(self, fit_order: int=3, deriv_length: int=5) -> tuple[npt.NDArray, npt.NDArray]:
        dIQ_df = np.zeros((2, self.nchan))
        mid_ind = np.argmin(abs(self.tone_list[:,np.newaxis] - self.freq[0, :]))
        edge_indices = [mid_ind - deriv_length, mid_ind + deriv_length + 1]
        ind_val = np.arange(edge_indices[0], edge_indices[1])
        freq_val = self.freq[:, ind_val] - self.tone_list[:, np.newaxis]

        for i_chan in range(0, self.nchan):
            fit_I = Polynomial.fit(freq_val[i_chan], self.data_I[i_chan, edge_indices[0]:edge_indices[1]], fit_order)
            fit_I_deriv = fit_I.deriv()
            dIQ_df[0, i_chan] = fit_I_deriv(freq_val[i_chan, deriv_length])
            fit_Q = Polynomial.fit(freq_val[i_chan], self.data_Q[i_chan, edge_indices[0]:edge_indices[1]], fit_order)
            fit_Q_deriv = fit_Q.deriv()
            dIQ_df[1, i_chan] = fit_Q_deriv(freq_val[i_chan, deriv_length])
            if self.chanmask[i_chan] == 0:
                dIQ_df[:, i_chan] = [1,0]#Make sure off resonances tones are not scaled or rotated. 
        # Q in y direction, I in x direction
        # NOTE: This is the angle (counter-clockwise) from the I-axis to the freq-axis
        # Negative because we're rotating the coordinate axes, not the point
        rotation_angle = -np.atan2(dIQ_df[1, :], dIQ_df[0, :])

        # For a fixed readout tone, a positive shift in the resonance freq appears 
        # as a perceived positive shift in the I/Q data, which thus necessitates the positive sign
        adc_units_to_hz = np.sqrt((dIQ_df[0]) ** 2 + (dIQ_df[1]) ** 2)
        with np.printoptions(threshold=20):
            _logger.debug(f'Computed frequency direction:\n\ttheta = {rotation_angle}\n\tadc_units_to_hz = {adc_units_to_hz}')
        return rotation_angle, adc_units_to_hz
    
    def find_resonances(self) -> tuple[npt.NDArray, npt.NDArray]:
        rf = ResonatorFinder(self.data, self.f_center, self.df)
        res_freq, res_depth = rf.find_resonators()
        return res_freq, res_depth


def get_tone_list(filename: str, lo_freq: float = 400) -> npt.NDArray:
    """Get the data from a tone-list and convert to Hz from MHz."""
    flist = np.load(filename)
    return lo_freq * 1.0e6 + flist


class LoSweep:
    """Class for performing an LO Sweep"""

    def __init__(
            self,
            rfsoc: RFSOCWrapper,
            chan: int,
            savefile: Path,
            tone_shift: float,
            freq_step: float,
            full_span: float,
            diff_to_flag: float=3e3,
    ):
        """Initialize an LoSweep"""
        _logger.info(f'Initializing LO Sweep with {rfsoc.get_channel_name(chan)}...')

        self.rfsoc = rfsoc
        self.chan = chan
        self.valon = rfsoc.get_valon(chan)
        self.savefile = savefile
        self.tone_shift = tone_shift
        self.freq_step = freq_step
        self.full_span = full_span
        self.f_center = rfsoc.get_channel(chan).lo_freq
        self.diff_to_flag = diff_to_flag
        self._data = None

        rfsoc.set_frequency(chan, self.f_center)
        if tone_shift != 0:
            _logger.debug(f'Tone shift != 0. Computing new tones...')
            self.f_center = rfsoc.get_frequency(chan)  # Hz
            curr_tone_list, curr_amp_list = rfsoc.get_tone_list(chan)
            new_tones = np.ndarray.tolist(
                curr_tone_list
                + float(tone_shift)
                * (curr_tone_list + self.f_center)
                / self.f_center
            )
            _logger.debug(f'LoConfigWidget calling `set_tone_list` for RFSoC {rfsoc.name} channel {chan}')
            _logger.info(
                "Waiting for the RFSOC to finish writing the updated frequency list"
            )
            rfsoc.set_tone_list(chan, new_tones, curr_amp_list.tolist())

        self.rfchan = rfsoc.get_channel(chan)
        self.tone_list = rfsoc.get_tone_list(chan)[0]


        self._processed = False
        self._cancel = False
    
    @property
    def n_steps(self) -> int:
        """Number of steps in the LO sweep."""
        return self.full_span // self.freq_step
    
    def cancel(self):
        """Cancel the LO sweep."""
        self._cancel = True
    
    @property
    def data(self) -> LoSweepData:
        if self._data is None:
            raise RuntimeWarning('Attempting to access nonexistant data of an LO sweep. Has the sweep been run yet?')
        return self._data

    def _get_data_at(self, lo_freq: float) -> npt.NDArray:
        """
        Actually perform an LO Sweep using valon 5009's and save the data

        :param loSource:
            Valon 5009 Device Object instance
        :type loSource: valon5009.Synthesizer
        :param f_center:
            Center frequency of upconverted tones
        :param freqs: List of Baseband Frequencies returned from rfsocInterface.py's writeWaveform()
        :type freqs: List

        :param udp: udp data capture utility. This is our bread and butter for taking data from ethernet
        :type udp: udpcap.udpcap object instance

        :param N_steps: Number of steps with which to do the sweep.
        :type N_steps: Int

        Credit: Dr. Adrian Sinclair (adriankaisinclair@gmail.com)
        """
        self.rfsoc.set_frequency(self.chan, lo_freq)

        # Read values and trash initial read, suspecting linear delay is cause..
        # toss 20 packets in the garbage
        packets = capture_packets(self.rfchan, 20)

        # Actually use this data
        Naccums = 100
        packets = capture_packets(self.rfchan, Naccums)
        I = []
        Q = []
        # for packet in packets:
        for i in range(packets.shape[1]):
            packet = packets[:, i]
            It = packet[::2]
            Qt = packet[1::2]
            I.append(It)
            Q.append(Qt)
        I = np.array(I)
        Q = np.array(Q)

        Imed = np.median(I, axis=0)
        Qmed = np.median(Q, axis=0)

        Z = Imed + 1j * Qmed
        Z = Z[BAD_RFSOC_TONE_START_INDEX: BAD_RFSOC_TONE_START_INDEX + len(self.tone_list)]

        return Z


    def run_sweep(self, callback: Callable | None=None) -> LoSweepData | None:
        """Perform a stepped frequency sweep centered at f_center and save result as s21.npy file"""
        _logger.info('Performing final setup before LO sweep...')
        # Final setup before sweep
        chanmask = self.rfchan.chanmask

        if np.size(chanmask) == 0:  # Chanmask hasn't been set, so use all ones
            chanmask = np.ones(np.size(self.tone_list), dtype=int)

        self._processed = False
        flo_step = self.freq_step

        flo_start = self.f_center - flo_step * self.n_steps / 2.0
        flo_stop = self.f_center  + flo_step * self.n_steps / 2.0

        self.flos = np.arange(flo_start, flo_stop + flo_step, flo_step)

        # Perform LO Sweep
        _logger.info('Starting LO sweep...')
        _logger.debug(f'Starting LO sweep from {flo_start:.6f} MHz to {flo_stop:.6f} MHz in {self.n_steps} steps')
        z = np.zeros((np.size(self.flos), np.size(self.tone_list)), dtype=complex)
        for i, flo in enumerate(self.flos):
            if self._cancel:
                z = None
                break
            z[i, :] = self._get_data_at(flo)
            if callback is not None:
                callback()

        # Process LO sweep
        if z is None:
            _logger.info('Sweep cancelled. Exiting...')
            data = None
        else:
            _logger.info('Processing sweep results')
            f = np.zeros([np.size(self.tone_list), np.size(self.flos)])

            for itone, ftone in enumerate(self.tone_list):
                f[itone, :] = self.flos + ftone
            sweep_data = np.array((f, z.T))
            _logger.debug(f'Shape of LO sweep data: {sweep_data.shape}')

            data = LoSweepData(self.tone_list, self.f_center, sweep_data, chanmask, diff_to_flag=self.diff_to_flag)
            self._processed = True
            _logger.info('Finished processing sweep results')
            data.saveh5(self.savefile)

        # Set the LO back to the original frequency
        self.rfsoc.set_frequency(self.chan, self.f_center)
        self._data = data
        return data

class PowerSweep_data:
    """Class for performing a power sweep"""

    def __init__(
            self,
            sweeps: list[LoSweepData],
            output_attenuations: list[float]=None,
            input_attenuations: list[float]=None,
    ):
        """Initialize an PowerSweep_data"""
        sorted_indices = np.argsort(output_attenuations)
        self.sweeps = np.array([sweeps[i] for i in sorted_indices])
        for sweep in self.sweeps:
            sweep.fit() 
        self.input_attenuations = np.array([input_attenuations[i] for i in sorted_indices])
        self.output_attenuations = np.array([output_attenuations[i] for i in sorted_indices])
    def plot_f0_vs_output_power(self):
        """Plot f0 vs output attenuation for all active resonators."""

        # Find active resonators
        resonator_indices =np.where(self.sweeps[0].chanmask == 1)[0]
        if len(self.output_attenuations) != len(self.sweeps):
            raise ValueError("output_attenuations must have the same length as sweeps")

        # Collect f0 values: shape = (num_sweeps, num_resonators)
        f0_list = []
        qi_list = []
        qc_list = []

        for sweep in self.sweeps:
            f0_list.append([sweep.fit_f0[i] for i in resonator_indices])
            qi_list.append( [sweep.fit_qi[i] for i in resonator_indices])
            qc_list.append( [sweep.fit_qc[i] for i in resonator_indices])

        f0_list = np.array(f0_list)

        qi_list = np.array(qi_list)
        qc_list = np.array(qc_list)
        qr_list = (qi_list * qc_list) / (qi_list + qc_list)
       
        plot_list = [0,1]
        bad_resonances = [29,39,50,51,52,97,98,99]
        for i, resonator_index in enumerate(resonator_indices):
            if ~np.isin(resonator_index, bad_resonances):
                
                x = (f0_list[:, i]-f0_list[-1, i])/f0_list[-1, i]
                d_pwr = self.get_power_at_device(f0_list[:, i], -self.output_attenuations)
                y = qr_list[:, i]*x
                
                plt.plot(
                    d_pwr,
                    y,
                    marker='o',
                    label=f"Resonator {resonator_index}"
                )
                crossings = np.where(np.diff(np.sign(y - 0.1)))[0]
                print(crossings)
                
        plt.xlabel('Output Attenuation (dB)')
        plt.ylabel(r'Nonlinearity Factor (a)')
        plt.title(r'Nonlinearity Factor (a) vs Output Attenuation')
        plt.grid(True)
        #plt.legend(loc='lower right', fontsize='small', ncol=1)
        plt.tight_layout()
        plt.show()
    def get_power_at_device(self, freq:float, rf_out:float, mini_c_out:float = -4.5, output_tone_power:float = -20.4):
        dev_pwr = output_tone_power + rf_out + mini_c_out + self.get_atten_inside_cryo(freq)
        return dev_pwr
    def get_atten_inside_cryo(self, freq):
        return -8.75e-10*freq-41.5




if __name__ == '__main__':
    import pdb

    # Lab Testing
    # data = LoSweepData.from_h5('/data/20251204/20251204_Be231102p2_LO_Sweep_hour17p0742.h5')
    # data = LoSweepData.from_h5('/data/20251204/20251204_Be231102p2_LO_Sweep_hour17p4989.h5')
    # data = LoSweepData.from_h5('/data/20251204/20251204_Be231102p2_LO_Sweep_hour17p1558.h5')
    # data = LoSweepData.from_h5('/data/20251204/20251204_100_tone_uniform_202050829_LO_Sweep_hour16p4036.h5')
    # data = LoSweepData.from_h5('/data/20250814/20250814_thousand_tone_uniform_300MHz_LO_Sweep_hour15p7650.h5')

    class Incrementer:
        def __init__(self):
            self.val = 0
            self.lock = Lock()

        def __call__(self):
            self.val += 1
            #print(f'LO Sweep progress: {self.val}', flush=True)
    inc = Incrementer()
    def callback():
        with inc.lock:
            inc()
    # # import timeit
    # fit = data.fit(callback=callback)
    # # time = timeit.timeit('fit = data.fit(callback=callback)', globals=globals(), number=10)
    # # print(time)
    # # print([f for f in fit])
    # pdb.set_trace()
    # i_res = 10
    # plt.figure()
    # plt.title('IQ Circle')
    # plt.plot(data.data_I[i_res], data.data_Q[i_res])
    # plt.xlabel('Data I')
    # plt.ylabel('Data Q')
    # plt.figure()
    # plt.title('S21')
    # plt.plot(data.freq[i_res], data.s21[i_res])
    # plt.xlabel('Frequency (Hz)')
    # plt.ylabel('S21')
    # plt.show()
    # pdb.set_trace()
    # Power Sweep Testing
    files = list(Path('/data/20260126_power_sweep/').glob('*.h5'))
    print(files)
    sweeps = []
    output_attenuations = []
    input_attenuations = []
    for file in files:
        sweep = LoSweepData.from_h5(file)
        sweeps.append(sweep)
        name = file.stem
        parts = name.split('_')
        output_attenuations.append(int(parts[-1]))
        input_attenuations.append(int(parts[-3]))
    psweep = PowerSweep_data(sweeps, output_attenuations=output_attenuations, input_attenuations=input_attenuations)
    psweep.plot_f0_vs_output_power()


    # Telescope Testing
    # # data = LoSweepData.from_h5('/data/20251208/20251208_Device_aSi1_Channel2_blind_LO_Sweep_hour13p4400_blind.h5')
    # # data = LoSweepData.from_h5('/data/20251208/20251208_Device_aSi1_Channel3_blind_LO_Sweep_hour14p2292_blind.h5')
    #data = LoSweepData.from_h5('/data/20260126/20260126_Be231102p2_100_tones_LO_Sweep_hour17p4189_high_res.h5')
    #data.fit(callback=callback)
    #fig = data.plot(callback=callback, plot_IQ_Circle=False)
    #plt.tight_layout()
    #plt.show()
    #fig = data.plot(callback=callback, plot_IQ_Circle=True)
    #plt.tight_layout()
    #plt.show()
    #pdb.set_trace()
    #sfreq, z = data.data

    # # NOTE: This is reversed for channel 2 only
    # sfreq = sfreq[::-1]

    # s21_sqrd = z.real ** 2 + z.imag ** 2
    # s21_pow = 10 * np.log10(s21_sqrd)
    # for i in range(data.nchan):
    #     plt.plot(sfreq[i] / 1e6, s21_pow[i])
    # plt.xticks(fontsize=16)
    # plt.yticks(fontsize=16)
    # plt.xlabel("Frequency (MHz)", fontsize=18)
    # plt.ylabel("dB", fontsize=18)
    # plt.legend(["S21 of resonator sweep"], fontsize=18)
    # plt.show()

    # finder = ResonatorFinder(
    #     (sfreq, z),
    #     data.f_center,
    #     1e3,
    # )
    # freqs = finder.find_resonators()
    # pdb.set_trace()