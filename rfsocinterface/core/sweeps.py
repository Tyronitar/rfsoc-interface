from __future__ import annotations
import logging
import pdb
import datetime

from concurrent.futures import Future
from typing import Callable, Generic, TypeVar
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
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from scipy.signal import savgol_filter
from scipy.optimize import curve_fit
import h5py

from PySide6.QtWidgets import QApplication
from rfsocinterface.core.utils import (
    ensure_path,
    convert_path,
    PERMISSIONS_USR_RW,
    parallel_plot,
    mHz_axis_formatter,
    mHz_coordinate_formatter,
    get_sweep_filename,
    get_params_file_template,
    ON_RESONANCE_COLOR,
    OFF_RESONANCE_COLOR,
    BAD_RESONANCE_COLOR,
    FLAGGED_RESONANCE_COLOR,
)
from rfsocinterface.core.pool import QThreadJobPool
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.params import initialize_params_file, update_params_file
from kidpy3 import capture_packets
from kidpy3.hardware.Valon5009 import Valon5009, SYNTH_B
from kidpy3.data_handler import Rfchan
from kidpy3.measure import ResonatorFinder


_logger = logging.getLogger(__name__)

DEFAULT_NCOLS = 10
POWER_SWEEP_FRACTIONAL_FREQ_SHIFT = 1e-5
POWER_SWEEP_NOMINAL_NON_LINEAR_POWER_DB = 0

NEW_LO_SWEEP_FORMAT_DATE = '20260213'  # For backwards compatibility

CompositeSweepDataType = TypeVar('CompositeSweepDataType', bound='CompositeSweepData')


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

    f0 = freq[center_ind]
    return f0


def create_resonator_mini_plot(
        fig: Figure,
        ax: plt.Axes,
        idx: int,
        freq: npt.NDArray,
        s21: npt.NDArray,
        fit_f0: float,
        chanmask: int,
        flagged: bool,
):
    ax.set_box_aspect(1.0)
    ax.set_facecolor(ON_RESONANCE_COLOR)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.plot(freq, s21)
    ax.axvline(x=fit_f0, color='r')

    ax.set_xlim(freq.min(), freq.max())

    # Add a label showing the resonator number
    ax.legend(
        [f'{idx:d}'],
        fontsize=8,
        loc=3,
        frameon=False,
        framealpha=0,
        handlelength=0,
        alignment='center',
        edgecolor='black',
    )    # Add a label showing the resonator number
    if chanmask == 1:
        if flagged:
            ax.set_facecolor(FLAGGED_RESONANCE_COLOR)
    elif chanmask == 0:
        ax.set_facecolor(OFF_RESONANCE_COLOR)
    else:
        ax.set_facecolor(BAD_RESONANCE_COLOR)




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

    def plot(self, fig: Figure=None, ax: plt.Axes | None = None, animated: bool = False) -> Figure | None:
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
        # If axes is provided, make the mini plot inside
        if ax is not None:
            create_resonator_mini_plot(
                None,
                ax,
                self.idx,
                self.freq,
                self.s21,
                self.fit_f0,
                self.chanmask,
                self.flagged,
            )
            return

        # If axes not provided, create a new figure
        if fig is None:
            fig = plt.figure(figsize=(8, 5))
        ax = fig.add_subplot()
        ax.set_title(f'Transmission Magnitude near Resonator #{self.idx}')
        ax.set_xlabel('Frequency (MHz)')
        ax.set_ylabel(r'$|S_{21}|$')
        ax.xaxis.set_major_formatter(FuncFormatter(mHz_axis_formatter))
        ax.format_coord = mHz_coordinate_formatter

        ax.plot(self.freq, self.s21)
        ax.axvline(x=self.fit_f0, color='r', animated=animated)

        ax.set_xlim(self.freq.min(), self.freq.max())

        ax.legend(
            [f'{self.idx:d}'],
            fontsize=6,
            loc=3,
            frameon=False,
            framealpha=0,
            handlelength=0,
            alignment='center',
            edgecolor='black',
        )    # Add a label showing the resonator number
        if self.chanmask == 1:
            if self.flagged:
                ax.set_facecolor(FLAGGED_RESONANCE_COLOR)
        elif self.chanmask == 0:
            ax.set_facecolor(OFF_RESONANCE_COLOR)
        else:
            ax.set_facecolor(BAD_RESONANCE_COLOR)

        return fig

    @property
    def baseband_tone(self) -> float:
        """float: The tone for this resonator relative to the f center, in Hz."""
        return self.data.detector_f[self.idx] - self.data.f_center

    @property
    def tone(self) -> float:
        """float: The absolute tone for this resonator, in Hz."""
        return self.data.detector_f[self.idx]

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
        return self.data.fit_f0[self.idx] - self.data.detector_f[self.idx]

    @property
    def is_onres(self) -> bool:
        """bool: Whether this resonator is on-resonance."""
        return self.data.chanmask[self.idx] == 1

    @property
    def freq_ratio(self) -> float:
        """float: The ratio of the original tone and the maximum tone in the sweep."""
        return self.tone / self.data.detector_f.max()

    @property
    def chanmask(self) -> int:
        """The chanmask value for this resonator"""
        return self.data.chanmask[self.idx]
    
    @chanmask.setter
    def chanmask(self, val: int):
        self.data.chanmask[self.idx] = val

    @property
    def fit_f0(self) -> float:
        """float: The fitted value for the resonance frequency, in Hz."""
        return self.data.fit_f0[self.idx]

    @fit_f0.setter
    def fit_f0(self, val: float):
        self.data.fit_f0[self.idx] = val
    
    @property
    def flagged(self) -> bool:
        return np.abs(self.difference) > self.data.diff_to_flag[self.idx]

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
        fit_f0 = simple_derivative_fits(df, self.freq, start, self.s21)
        fit_qi = 0.0
        fit_qc = 0.0

        if callback is not None:
            callback()
        return fit_f0, fit_qi, fit_qc


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
        baseband_freqs: npt.NDArray,
        f_center: float,
        sweep_data: npt.NDArray,
        chanmask: npt.NDArray, 
        tile_name: str,
        diff_to_flag: float=3e3,
        filename: str=None,
    ) -> None:
        """Initialize a LoSweepData object."""
        self.data = sweep_data
        self.f_center = f_center  # Center frequency of the sweep in Hz
        self.detector_f = baseband_freqs[:] + f_center  # Frequencies in Hz
        self.freq = np.real(self.data[0, :, :])
        self.s21 = np.real(10.0 * np.log10(np.abs(self.data[1, :, :])))
        self.chanmask = chanmask
        self.resonator_data = [ResonatorData(self, i) for i in range(self.n_tones)]
        self.tile_name = tile_name
        self.filename = convert_path(filename)

        self.fit_f0 = self.detector_f.copy()
        self.fit_qi = np.zeros(self.n_tones)
        self.fit_qc = np.zeros(self.n_tones)
        self.set_diff_to_flag(val=diff_to_flag)
        self._fitted = False
        self._plotted = False
        self._fit_canceled = False
        self._plot_canceled = False
    
    def set_diff_to_flag(self, val: float=3e3):
        """Set the flagging threshold.
        
        Arguments:
            val (float): The minimumum difference to flag in Hz. (defaults to 3000.0)
        """
        # self.diff_to_flag = (val * 1e3 / 2e8) * self.tone_list
        self.diff_to_flag = np.abs(val / self.f_center * self.detector_f)

    @ensure_path(1)
    def savenp(self, fname: Path):
        path = fname.with_suffix('.npy')
        path.touch(PERMISSIONS_USR_RW, exist_ok=True)
        np.save(path, self.data)
    
    @ensure_path(1)
    def save_new_tone_list(self, fname: Path):
        path = fname.with_suffix('.npy')
        path.touch(PERMISSIONS_USR_RW, exist_ok=True)
        np.save(fname, self.new_baseband_freqs)
        _logger.debug(f'LoSweepData saved new tone list to {str(fname)}')

    def save(self):
        """Save the LO Sweep to the current HDF5 file."""
        if self.filename is None:
            raise RuntimeWarning('No filename specified for this sweep. Use `save_as` to specify a filename.')
        self.save_as(self.filename)

    @ensure_path(1)
    def save_as(self, fname: Path):
        """Save the LO Sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        path.touch(PERMISSIONS_USR_RW)
        with h5py.File(path, 'w') as fh:
            fh.attrs['f_center'] = self.f_center
            fh.attrs['tile_name'] = self.tile_name
            fh.create_dataset('/global_data/lo_sweep', data=self.data, dtype=np.complex128)
            fh.create_dataset('/global_data/baseband_freqs', data=np.real(self.detector_f - self.f_center), dtype=np.float64)
            fh.create_dataset('/global_data/chanmask', data=self.chanmask, dtype=np.int8)
            fh.create_dataset('/global_data/fit_f0', data=self.fit_f0, dtype=np.float64)
            fh.create_dataset('/global_data/fit_qi', data=self.fit_qi, dtype=np.float64)
            fh.create_dataset('/global_data/fit_qc', data=self.fit_qc, dtype=np.float64)
        _logger.info(f'LoSweepData saved to {str(fname)}')
    
    @classmethod
    @ensure_path(1)
    def load(cls, path: Path) -> LoSweepData:
        """Load an LO sweep from an HDF5 file."""
        path = path.with_suffix('.h5')
        with h5py.File(path, 'r') as f:
            if datetime.datetime.fromtimestamp(path.stat().st_mtime) < datetime.datetime.strptime(NEW_LO_SWEEP_FORMAT_DATE, '%Y%m%d'):
                _logger.warning(f'LO sweep file {str(path)} is from before {NEW_LO_SWEEP_FORMAT_DATE}. Attempting to load with backwards compatibility.')
                tone_list = f['global_data/baseband_freqs'][:]
                data = f['global_data/lo_sweep'][:]
                chanmask = f['global_data/chanmask'][:]
                fit_f0 = f['global_data/fit_f0'][:]
                fit_qi = f['global_data/fit_qi'][:]
                fit_qc = f['global_data/fit_qc'][:]
                f_center = f['global_data/lo_freq'][()]
                tile_name = ''
            else:
                tone_list = f['global_data/baseband_freqs'][:]
                data = f['global_data/lo_sweep'][:]
                chanmask = f['global_data/chanmask'][:]
                fit_f0 = f['global_data/fit_f0'][:]
                fit_qi = f['global_data/fit_qi'][:]
                fit_qc = f['global_data/fit_qc'][:]
                f_center = f.attrs['f_center']
                tile_name = f.attrs['tile_name']

        sweep = cls(tone_list, f_center, data, chanmask, tile_name, filename=path)
        sweep.fit_f0 = fit_f0
        sweep.fit_qi = fit_qi
        sweep.fit_qc = fit_qc
        _logger.debug(f'Loaded LO sweep data from {str(path)}')
        return sweep

    @property
    def difference(self) -> npt.NDArray:
        """The absolute difference of the fitted frequencies and the provided tones, in Hz."""
        return np.abs(self.fit_f0 - self.detector_f)

    @property
    def n_tones(self) -> int:
        """The number of resonators."""
        return np.size(self.chanmask)

    @property
    def nfreq(self) -> int:
        """The number of frequency points in the sweep."""
        return np.size(self.freq[0, :])

    @property
    def n_good_tones(self) -> int:
        """The number of good resonators."""
        return np.size(self.onres_ind)
    
    @property
    def n_fits(self) -> int:
        """The number of fits to perform."""
        return self.n_good_tones

    @property
    def n_plots(self) -> int:
        """The number of plots to generate."""
        return self.n_tones

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
    def new_baseband_freqs(self) -> npt.NDArray:
        """The new base band frequencies, based on the fit"""
        return self.fit_f0 - self.f_center
    
    @property
    def baseband_freqs(self) -> npt.NDArray:
        """The baseband frequencies used during the LO sweep."""
        return self.detector_f - self.f_center
    
    def cancel_fit(self):
        self._fit_canceled = True

    def cancel_plot(self):
        self._plot_canceled = True

    def fit(self, callback: Callable | None=None, max_workers: int=4):
        """Perform a fit to determine the resoncance frequencies of each resonator."""
        self._fitted = False
        self._fit_canceled = False
        _logger.debug('Fitting LO sweep results...')
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            res = executor.map(
                simple_derivative_fits,
                (self.df for _ in range(self.n_good_tones)),
                self.freq[self.onres_ind, :],
                self.detector_f[self.onres_ind],
                self.s21[self.onres_ind, :],
            )
            for i, f0 in enumerate(res):
                if self._fit_canceled:
                    return
                i_res = self.onres_ind[i]
                self.fit_f0[i_res] = f0
                self.fit_qc[i_res] = 0.0
                self.fit_qi[i_res] = 0.0
                if callback is not None:
                    callback()
            
        self._fitted = True

    def plot(self, ncols: int=DEFAULT_NCOLS, callback: Callable | None=None, fig: Figure=None) -> Figure:
        """Plot the results of fitting the LO sweep.

        Arguments:
            ncols (int): The number of columns to use in the figure. The figure will have
                one inch width for each column.

        Returns:
            (Figure): The generated figure showing the plot for each resonator.
        """
        self._plotted = False
        self._plot_canceled = False

        # Setup for plots
        if fig is None:
            nrows = int(np.ceil(self.n_tones / ncols))
            fig = plt.figure(figsize=(ncols, nrows), dpi=100)
            for i in range(1, self.n_tones + 1):
                fig.add_subplot(nrows, ncols, i, aspect='equal', xticks=[], yticks=[])
        axes = fig.axes

        # Make this wrapper so `parallel_plot` can be canceled
        def callback_wrapper():
            if self._plot_canceled:
                raise InterruptedError('Plotting Canceled')
            if callback is not None:
                callback()

        try:
            parallel_plot(
                fig,
                axes,
                create_resonator_mini_plot,
                np.arange(self.n_tones),
                self.freq[:self.n_tones],
                self.s21[:self.n_tones],
                self.fit_f0[:self.n_tones],
                self.chanmask,
                np.isin(np.arange(self.n_tones), self.flagged[:self.n_tones]),
                callback=callback_wrapper,
            )
        except InterruptedError:
            return
        
        self._plotted = True
        return fig

    def freq_direction(self, fit_order: int=3, deriv_length: int=5) -> tuple[npt.NDArray, npt.NDArray]:
        dIQ_df = np.zeros((2, self.n_tones))
        mid_ind = self.nfreq // 2
        edge_indices = [mid_ind - deriv_length, mid_ind + deriv_length + 1]
        ind_val = np.arange(edge_indices[0], edge_indices[1])
        freq_val = self.freq[:, ind_val] - self.detector_f[:, np.newaxis]

        for i_tone in range(0, self.n_tones):
            fit_I = Polynomial.fit(freq_val[i_tone], self.data_I[i_tone, edge_indices[0]:edge_indices[1]], fit_order)
            fit_I_deriv = fit_I.deriv()
            dIQ_df[0, i_tone] = fit_I_deriv(freq_val[i_tone, deriv_length])
            fit_Q = Polynomial.fit(freq_val[i_tone], self.data_Q[i_tone, edge_indices[0]:edge_indices[1]], fit_order)
            fit_Q_deriv = fit_Q.deriv()
            dIQ_df[1, i_tone] = fit_Q_deriv(freq_val[i_tone, deriv_length])

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
    
    def plot_full_trace(self, fig: Figure=None, callback: Callable=None) -> Figure | None:
        # Only return if we're creating a new figure
        if fig is None:
            fig, ax = plt.subplots(figsize=(10, 6))

        if len(fig.axes) == 0:
            ax = fig.add_subplot()
        else:
            ax = fig.axes[0]

        ax.set_xlabel('Frequency (MHz)')
        ax.set_ylabel(r'$|S_{21}|$')
        ax.xaxis.set_major_formatter(FuncFormatter(mHz_axis_formatter))
        ax.format_coord = mHz_coordinate_formatter

        for i_tone in range(self.n_tones):
            if self._plot_canceled:
                return
            ax.plot(self.freq[i_tone], self.s21[i_tone], color='blue')
            if callback is not None:
                callback()
        
        return fig
    
    def reset_stop_signals(self):
        self._fit_canceled = False
        self._fitted = False
        self._plot_canceled = False
        self._plotted = False
    
    def plot_blind_sweep(self, f0: npt.NDArray, fig: Figure=None, callback: Callable=None) -> Figure:
        self.reset_stop_signals()
        self.plot_full_trace(fig=fig, callback=callback)
        if self._plot_canceled:
            return
        ax = fig.axes[0]
        for resonance in f0:
            ax.axvline(resonance, linestyle='-', color='red')

        custom_lines = [
            Line2D([0], [0], color='blue', linestyle='-'),
            Line2D([0], [0], color='red', linestyle='-'),
        ]

        custom_labels = [r'$S_{21}$', 'New Resonances']
        fig.legend(
            custom_lines,
            custom_labels,
            loc='lower center',
            bbox_to_anchor=(0.5, 0.0),
            bbox_transform=fig.transFigure,
            ncol=2,
        )
        fig.tight_layout(rect=[0, 0.05, 1, 1])
        
        self._plotted = True
        return fig
    
    def find_resonances(
        self,
        min_resonance_depth_dB: float=0.2,
        spacing_threshold_Hz: float=3e3,
        min_samples_per_resonance: float=2,
        max_noise_fluctuation_dB: float=0.05,
        baseline_percentile: float=50,
    ) -> tuple[npt.NDArray, npt.NDArray]:
        rf = ResonatorFinder(self.data, self.f_center, self.df)
        res_freq, res_depth = rf.find_resonators(
            min_resonance_depth_dB=min_resonance_depth_dB,
            spacing_threshold_Hz=spacing_threshold_Hz,
            min_samples_per_resonance=min_samples_per_resonance,
            max_noise_fluctuation_dB=max_noise_fluctuation_dB,
            baseline_percentile=baseline_percentile,
        )
        return res_freq , res_depth
    
    def plot_new_resonances(
        self,
        f0: npt.NDArray,
        old_f0: npt.NDArray | None=None,
        nrows: int=4,
        ncols: int=3,
        tile_name: str='blind_sweep',
        savefile: str=None,
        callback: Callable=None
    ):
        self.reset_stop_signals()
        if savefile is None:
            savefile = f'{tile_name}_new_tones.pdf'
        with PdfPages(savefile) as pdf:
            custom_lines = [
                Line2D([0], [0], color='blue', linestyle='-'),
                Line2D([0], [0], color='red', linestyle='-'),
            ]
            custom_labels = [r'$S_{21}$', 'New Resonances']
            if old_f0 is not None:
                custom_lines.append(Line2D([0], [0], color='green', linestyle='--'))
                custom_labels.append('Old Resonances')
            group_size = nrows * ncols
            stop = self.n_tones
            group_starts = np.arange(0, stop + group_size, group_size, dtype=int)
            for start_idx, end_idx in zip(group_starts, group_starts[1:]):
                fig, axes = plt.subplots(nrows, ncols, figsize=(nrows * 4, ncols * 4))
                for i, i_tone in enumerate(range(start_idx, min(end_idx, stop))):
                    if self._plot_canceled:
                        plt.close(fig)
                        return
                    ax = np.ravel(axes)[i]
                    ax.set_title(f'Tone {i_tone + 1}')
                    this_freq = self.freq[i_tone]
                    ax.plot(this_freq, self.s21[i_tone], color='blue')
                    this_f0 = f0[(this_freq.min() <= f0) & (f0 <= this_freq.max())]
                    for resonance in this_f0:
                        ax.axvline(resonance, linestyle='-', color='red')
                    if old_f0 is not None:
                        this_old_f0 = old_f0[(this_freq.min() <= old_f0) & (old_f0 <= this_freq.max())]
                        for resonance in this_old_f0:
                            ax.axvline(resonance, linestyle='--', color='green')
                    ax.set_xlabel('Frequency (MHz)')
                    ax.set_ylabel(r'$|S_{21}|$')
                    ax.xaxis.set_major_formatter(FuncFormatter(mHz_axis_formatter))
                    ax.format_coord = mHz_coordinate_formatter
                    if callback is not None:
                        callback()
                fig.legend(
                    custom_lines,
                    custom_labels,
                    loc='lower center',
                    bbox_to_anchor=(0.5, 0.0),
                    bbox_transform=fig.transFigure,
                    ncol=3 if old_f0 is not None else 2,
                )
                fig.tight_layout(rect=[0, 0.05, 1, 1])
                pdf.savefig(fig)
                # plt.show()
                plt.close(fig)
                # pdb.set_trace()
        self._plotted = True

    def generate_new_params_file(self, tile_name: str, old_params: h5py.File | None=None, plot: bool=False):
        f0, depths = self.find_resonances()
        if plot:
            old_f0 = None
            if old_params is not None:
                old_f0 = old_params['baseband_freqs'][:] + old_params['lo_freq'][()]
            self.plot_new_resonances(f0, old_f0, tile_name=tile_name)
            
        initialize_params_file(
            tile_name,
            f0 - self.f_center,
            self.f_center,
        )


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

        self.tone_list = rfsoc.get_tone_list(chan)[0]

        # Set up LO frequencies for sweep
        n_steps = self.full_span // self.freq_step + 1
        flo_step = self.freq_step

        flo_start = self.f_center - flo_step * n_steps / 2.0
        flo_stop = self.f_center  + flo_step * n_steps / 2.0

        self.flos = np.arange(flo_start, flo_stop + flo_step, flo_step)


        self._processed = False
        self._canceled = False
    
    @property
    def tile_name(self) -> str:
        return self.rfsoc.get_channel_name(self.chan)

    @property
    def n_steps(self) -> int:
        """Number of steps in the LO sweep."""
        return self.flos.size
    
    def cancel(self):
        """Cancel the LO sweep."""
        self._canceled = True
    
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
        packets = self.rfsoc.capture_packets(self.chan, 20)

        # Actually use this data
        # TODO: Can reduce Naccums to speed up LO sweep
        Naccums = 100
        packets = self.rfsoc.capture_packets(self.chan, Naccums)
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
        Z = Z[:len(self.tone_list)]

        return Z


    def run_sweep(self, callback: Callable | None=None, save: bool=True) -> LoSweepData | None:
        """Perform a stepped frequency sweep centered at f_center and save result as s21.npy file"""
        _logger.info('Performing final setup before LO sweep...')
        # Final setup before sweep
        chanmask = self.rfsoc.get_chanmask(self.chan)

        if np.size(chanmask) == 0:  # Chanmask hasn't been set, so use all ones
            chanmask = np.ones(np.size(self.tone_list), dtype=int)

        self._processed = False

        flo_start = self.flos[0]
        flo_stop = self.flos[-1]

        # Perform LO Sweep
        _logger.info('Starting LO sweep...')
        _logger.debug(f'Starting LO sweep from {flo_start:.6f} MHz to {flo_stop:.6f} MHz in {self.n_steps} steps')
        z = np.zeros((np.size(self.flos), np.size(self.tone_list)), dtype=complex)
        for i, flo in enumerate(self.flos):
            if self._canceled:
                z = None
                break
            z[i, :] = self._get_data_at(flo)
            if callback is not None:
                callback()

        # Process LO sweep
        if z is None:
            _logger.info('Sweep canceled. Exiting...')
            data = None
        else:
            _logger.info('Processing sweep results')
            f = np.zeros([np.size(self.tone_list), np.size(self.flos)])

            for itone, ftone in enumerate(self.tone_list):
                f[itone, :] = self.flos + ftone
            sweep_data = np.array((f, z.T))
            _logger.debug(f'Shape of LO sweep data: {sweep_data.shape}')

            data = LoSweepData(self.tone_list, self.f_center, sweep_data, chanmask, self.rfsoc.get_channel_name(self.chan), diff_to_flag=self.diff_to_flag, filename=self.savefile)
            if save:
                data.save()

        # Set the LO back to the original frequency
        self.rfsoc.set_frequency(self.chan, self.f_center)
        self._data = data

        if z is not None:
            self._processed = True
            _logger.info('Finished processing sweep results')
        return data


class CompositeSweep(Generic[CompositeSweepDataType]):
    """Class for a sweep consisting of multiple LO sweeps."""
    sweep_type = ''

    def __init__(
        self,
        rfsoc: RFSOCWrapper,
        chan: int,
        tone_shift: float,
        freq_step: float,
        full_span: float,
        savefile: Path=None,
        filename_suffix: str='',
        mkdir: bool=False,
        **kwargs,
    ):
        self.rfsoc = rfsoc
        self.chan = chan
        if savefile is None:
            savefile = get_sweep_filename(
                sweep_type=self.sweep_type,
                chan_name=self.tile_name,
                suffix=filename_suffix,
                mkdir=mkdir,
            )
        self.savefile = savefile

        self.tone_shift = tone_shift
        self.freq_step = freq_step
        self.full_span = full_span

        self.bb_freqs = rfsoc.get_tone_list(chan)[0]
        self.f_center = rfsoc.get_frequency(chan)

        self.params = kwargs

        self._data = []
        self._sweeps = []
        self._processed = False
        self._canceled = False

    @property
    def tile_name(self) -> str:
        return self.rfsoc.get_channel_name(self.chan)
    
    @property
    def rfchan(self) -> Rfchan:
        return self.rfsoc.get_channel(self.chan)

    @property
    def data(self) -> CompositeSweepDataType:
        if self._data is None:
            raise RuntimeWarning(f'Attempting to access nonexistant data of a {self.sweep_type} sweep. Has the sweep been run yet?')
        return self._data

    @property
    def n_sweeps(self) -> int:
        """Number of sweeps this sweep is comprised of."""
        return len(self._sweeps)

    @property
    def n_steps(self) -> int:
        """Total number of steps in the sweep."""
        return sum(sweep.n_steps for sweep in self._sweeps)

    def cancel(self):
        """Cancel the sweep."""
        self._canceled = True
        for sweep in self._sweeps:
            sweep.cancel()
    
    def _setup_sweeps(self):
        raise NotImplementedError
    
    def _between_sweep_callback(self, i_sweep: int, sweep: LoSweep):
        raise NotImplementedError
    
    def _end_sweeps_callback(self):
        raise NotImplementedError
    
    def save_sweeps(self, data: list[LoSweepData]):
        raise NotImplementedError
    
    def run_sweep(self, callback: Callable | None=None) -> ...:
        data = []
        try:
            for i_sweep, sweep in enumerate(self._sweeps):
                if self._canceled:
                    data = None
                    break
                self._between_sweep_callback(i_sweep, sweep)

                this_sweep_data = sweep.run_sweep(callback=callback, save=False)
                if self._canceled:
                    data = None
                    break
                data.append(this_sweep_data)

            if data is None:
                _logger.info('Sweep canceled. Exiting...')
                self._data = None
            else:
                self.save_sweeps(data)
        except Exception:
            _logger.exception('Exception encountered during sweep. Canceling...')
            self._data = None
            self.cancel()
            return
        finally:
            # Make sure the cleanup is always run afterwards
            self._end_sweeps_callback()
        
        self._processed = True

class CompositeSweepData:
    sweep_type = ''

    def __init__(
        self,
        bb_freqs: npt.NDArray,
        f_center: float,
        sweeps: list[LoSweepData],
        filename: Path | None = None,
    ):
        self.filename = convert_path(filename)

        self.f_center = f_center
        self.bb_freqs = bb_freqs
        self.sweeps = sweeps
        self._fit_f0 = np.zeros(self.n_tones)

        # Signals for fitting and plotting 
        self._fitted = False
        self._plotted = False
        self._fit_canceled = False
        self._plot_canceled = False

    def reset_stop_signals(self):
        self._fit_canceled = False
        self._fitted = False
        self._plot_canceled = False
        self._plotted = False
    

    @property
    def chanmask(self) -> npt.NDArray:
        """The chanmask used during the sweep."""
        return self.sweeps[0].chanmask
    
    @property
    def onres_ind(self) -> npt.NDArray:
        return np.argwhere(self.chanmask == 1).flatten()

    @property
    def offres_ind(self) -> npt.NDArray:
        return np.argwhere(self.chanmask == 0).flatten()
    
    @property
    def combined_sweep_array(self) -> npt.NDArray:
        """The LO sweep data from each LO sweep as one array.

        Resulting array will have shape (N_sweeps, 2, N_tones, N_samples) 
        """
        return np.stack([sweep.data for sweep in self.sweeps], axis=0)
    
    @property
    def n_tones(self) -> int:
        return self.sweeps[0].n_tones
    
    @property
    def n_sweeps(self) -> int:
        return len(self.sweeps)
    
    @property
    def tile_names(self) -> list[str]:
        return [sweep.tile_name for sweep in self.sweeps]
    
    @property
    def detector_f(self) -> npt.NDArray:
        return self.bb_freqs + self.f_center
    
    def fit_f0(self, callback: Callable=None):
        """Fit f0 for each sweep in this sweep."""
        with ThreadPoolExecutor() as executor:
            executor.map(LoSweepData.fit, self.sweeps, [callback] * len(self.sweeps))
        self.get_fit_f0()

    def get_fit_f0(self) -> npt.NDArray:
        fit_f0 = np.stack([sweep.fit_f0 for sweep in self.sweeps], axis=0)
        self._fit_f0 = fit_f0
        return fit_f0

    @property
    def n_fits(self) -> int:
        """The number of fits to perform for each sweep."""
        return sum(sweep.n_fits for sweep in self.sweeps)

    def fit(self, callback: Callable=None):
        """Fit each sweep in this sweep."""
        raise NotImplementedError

    def cancel_fit(self):
        """Cancel the fit for each sweep in this sweep."""
        for sweep in self.sweeps:
            sweep.cancel_fit()
        self._fit_canceled = True
    
    @property
    def n_plots(self) -> int:
        """The number of plots to generate."""
        raise NotImplementedError

    def plot(self, callback: Callable=None):
        """Plot the results of the sweep."""
        raise NotImplementedError
    
    def cancel_plot(self):
        """Cancel the plotting for each sweep in this sweep."""
        for sweep in self.sweeps:
            sweep.cancel_plot()
        self._plot_canceled = True
    
    def save(self):
        """Save the sweep to the current HDF5 file."""
        if self.filename is None:
            raise RuntimeWarning('No filename specified for this sweep. Use `save_as` to specify a filename.')
        self.save_as(self.savefile)

    @ensure_path(1)
    def save_as(self, fname: Path):
        """Save the sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        path.touch(PERMISSIONS_USR_RW)
        with h5py.File(path, 'w') as fh:
            fh.attrs['f_center'] = self.f_center
            fh.attrs['tile_names'] = self.tile_names
            fh.create_dataset('sweeps', data=self.combined_sweep_array, dtype=np.complex128)
            fh.create_dataset('baseband_freqs', data=self.bb_freqs, dtype=np.float64)
            fh.create_dataset('chanmask', data=self.chanmask, dtype=np.int8)
            fh.create_dataset('fit_f0', data=self._fit_f0, dtype=np.float64)

    @classmethod
    @ensure_path(1)
    def load(cls, fname: Path) -> CompositeSweepData:
        """Load a sweep from an HDF5 file."""
        raise NotImplementedError


def power_sweep_fit_function(x: npt.NDArray, amp: float, cutoff: float):
    vals = amp * (cutoff - x)
    vals[x <= cutoff] = 0
    return vals


class PowerSweepData(CompositeSweepData):
    def __init__(
        self,
        bb_freqs: npt.NDArray,
        f_center: float,
        sweeps: list[LoSweepData],
        power_levels: npt.NDArray,
        rfin: float,
        rfout: float,
        filename: Path | None = None,
    ):
        super().__init__(
            bb_freqs=bb_freqs,
            f_center=f_center,
            sweeps=sweeps,
            filename=filename,
        )
        self.power_levels = np.array(power_levels)
        self.rfin = rfin
        self.rfout = rfout
        self.max_readout_power = np.zeros(self.n_tones)
        self._onres_power_levels = None
        self._onres_df = None
        self._onres_popt = None

    @ensure_path(1)
    def save_as(self, fname: Path):
        """Save the power sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        super().save_as(path)
        with h5py.File(path, 'a') as fh:
            fh.attrs['rfin'] = self.rfin
            fh.attrs['rfout'] = self.rfout
            fh.create_dataset('power_levels', data=self.power_levels, dtype=np.float64)
            fh.create_dataset('max_readout_power', data=self.max_readout_power, dtype=np.float64)
        _logger.info(f'PowerSweepData saved to {str(fname)}')
    
    @classmethod
    @ensure_path(1)
    def load(cls, fname: Path) -> PowerSweepData:
        with h5py.File(fname, 'r') as fh:
            f_center = fh.attrs['f_center']
            tile_names = fh.attrs['tile_names']
            sweep_data = fh['sweeps'][:]
            bb_freqs = fh['baseband_freqs'][:]
            chanmask = fh['chanmask'][:]
            fit_f0 = fh['fit_f0'][:]

            # Fields specific to power sweeps
            rfin = fh.attrs['rfin']
            rfout = fh.attrs['rfout']
            power_levels = fh['power_levels'][:]
            max_readout_power = fh['max_readout_power'][:]

        sweeps = []
        for this_fit_f0, arr, tile_name in zip(fit_f0, sweep_data, tile_names):
            sweep = LoSweepData(bb_freqs, f_center, arr, chanmask, tile_name)
            sweep.fit_f0[:] = this_fit_f0
            sweeps.append(sweep)

        power_sweep = cls(bb_freqs, f_center, sweeps, power_levels, rfin, rfout, filename=fname)
        power_sweep.get_fit_f0()
        power_sweep.max_readout_power = max_readout_power

        return power_sweep

    @property
    def n_fits(self) -> int:
        """The number of fits to perform for the power sweep."""
        return super().n_fits + self.onres_ind.size
    
    def fit(self, callback: Callable=None):
        """Fit the power sweep data to determine the optimal readout power for each resonator."""
        super().fit_f0(callback=callback)  # Must find f0 first
        self.find_optimal_readout_power(callback=callback)

    def find_optimal_readout_power(
        self,
        baseline_percentage: float=0.33,
        bad_power_cutoff_percentile: float=0.75,
        max_power_deviation_from_median_dB: float=5,
        callback: Callable=None,
    ):
        self._fitted = False
        self._fit_canceled = False

        onres_power_levels = []
        onres_df = []
        onres_popt = np.zeros((len(self.onres_ind), 2))

        f0_data = self._fit_f0[:]
        power_levels = self.power_levels[:]

        sorted_data_ind = np.argsort(power_levels)
        power_levels = power_levels[sorted_data_ind]
        f0_data = f0_data[sorted_data_ind, :]
        power_level_non_linear = np.zeros(self.n_tones)
        non_linear_slope = np.zeros(self.n_tones)

        for i_onres, i_res in enumerate(self.onres_ind):
            if self._fit_canceled:
                return

            # First let's remove f0 values that are invalid at high power
            this_power_level = power_levels[:]
            this_df = (f0_data[:, i_res] - f0_data[0, i_res]) / f0_data[0, i_res]
            median_baseline = np.median(this_df[:int(self.n_sweeps * baseline_percentage)])
            this_df -= median_baseline
            this_deriv = np.diff(this_df)
            
            # Only look at the f0 values at the highest 25% of powers
            bad_power_indices = np.argwhere(this_deriv > 0).flatten()
            valid_bad = np.argwhere(bad_power_indices >= bad_power_cutoff_percentile * self.n_sweeps).flatten()
            bad_power_indices = bad_power_indices[valid_bad]

            if np.size(bad_power_indices) > 0:
                stop_index = np.min(bad_power_indices)
                this_power_level = this_power_level[:stop_index]
                this_df = this_df[:stop_index]
            
            nominal_non_linear_db = np.median(this_power_level)
            
            try:
                popt, _ = curve_fit(
                    power_sweep_fit_function,
                    this_power_level,
                    this_df,
                    p0=(
                        POWER_SWEEP_FRACTIONAL_FREQ_SHIFT,
                        nominal_non_linear_db,
                    ),
                )
                non_linear_slope[i_res] = popt[0]
                power_level_non_linear[i_res] = popt[1]
            except RuntimeError as e:
                print(f'Encountered exception during fit; using default value for resonator {i_res}')
                print(e)
                non_linear_slope[i_res] = POWER_SWEEP_FRACTIONAL_FREQ_SHIFT
                power_level_non_linear[i_res] = POWER_SWEEP_NOMINAL_NON_LINEAR_POWER_DB
            
            onres_power_levels.append(this_power_level)
            onres_df.append(this_df)
            onres_popt[i_onres] = popt

            if callback is not None:
                callback()

        med = np.median(power_level_non_linear)
        bad_ind = np.argwhere(np.abs(power_level_non_linear - med) > max_power_deviation_from_median_dB).flatten()
        power_level_non_linear[bad_ind] = med

        power_level_non_linear[self.offres_ind] = med  # Set off-resonance to median
        negative_ind = np.argwhere(non_linear_slope < 0).flatten()
        power_level_non_linear[negative_ind] = med

        max_readout_power = power_level_non_linear - np.max(power_level_non_linear)

        self.max_readout_power = max_readout_power
        self._onres_power_levels = np.array(onres_power_levels, dtype=object)
        self._onres_df = np.array(onres_df, dtype=object)
        self._onres_popt = onres_popt
        self.fitted = True

        return max_readout_power

    @property
    def n_plots(self) -> int:
        """The number of plots to make for the power sweep.
        
        Number of on-resonance tones + 1 for the summary histogram.
        """
        return self.onres_ind.size + 1

    def plot(self, callback: Callable=None):
        """Plot the power sweep data."""
        self.plot_optimal_readout_powers(callback=callback)
    
    def plot_optimal_readout_powers(
        self, 
        pdf_filename: str=None,
        nrows: int=4,
        ncols: int=3,
        callback: Callable=None,
    ):
        self._plotted = False
        self._plot_canceled = False
        if pdf_filename is None:
            pdf_filename = f'{self.tile_names[0]}_optimal_readout_powers.pdf'

        pdf = PdfPages(pdf_filename)
        page_size = nrows * ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(nrows * 4, ncols * 4))
        custom_lines = [
            Line2D([0], [0], color='orange', linestyle='-'),
            Line2D([0], [0], color='blue', linestyle='-'),
            Line2D([0], [0], color='red', linestyle='-'),
        ]
        custom_labels = ['df', 'Fit', 'Max Readout Power']

        i_plot = 0

        for i_onres, i_res in enumerate(self.onres_ind):
            if self._plot_canceled:
                plt.close(fig)
                pdf.close()
                return
            # Start a new page if needed
            if i_plot >= page_size:
                # Save the current figure 
                fig.legend(
                    custom_lines,
                    custom_labels,
                    loc='lower center',
                    bbox_to_anchor=(0.5, 0.0),
                    bbox_transform=fig.transFigure,
                    ncol=3,
                )
                fig.tight_layout(rect=[0, 0.05, 1, 1])
                pdf.savefig(fig)
                plt.close(fig)

                # Start a new figure
                fig, axes = plt.subplots(nrows, ncols, figsize=(nrows * 4, ncols * 4))
                i_plot = 0
            
            this_power_level = self._onres_power_levels[i_onres]
            this_df = self._onres_df[i_onres]
            popt = self._onres_popt[i_onres]
            max_power_level = self.max_readout_power[i_res]

            ax = np.ravel(axes)[i_plot]
            ax.set_title(rf'Tone {i_res} ($f_0$ = {self.detector_f[i_res]})')
            ax.scatter(this_power_level, this_df, c='orange', marker='x')
            ax.plot(this_power_level, power_sweep_fit_function(this_power_level, popt[0], popt[1]), color='blue')
            ax.axvline(max_power_level, color='red')
            ax.set_xlabel('Power Level (dB)')
            ax.set_ylabel('df0 / f0')
            i_plot += 1

            if callback is not None:
                callback()

        # Save the last page 
        fig.legend(
            custom_lines,
            custom_labels,
            loc='lower center',
            bbox_to_anchor=(0.5, 0.0),
            bbox_transform=fig.transFigure,
            ncol=3,
        )
        fig.tight_layout(rect=[0, 0.05, 1, 1])
        pdf.savefig(fig)
        plt.close(fig)

        if self._plot_canceled:
            plt.close(fig)
            pdf.close()
            return

        # Histogram
        counts, bins = np.histogram(self.max_readout_power, bins=60, range=(-10, 10))
        plt.figure()
        plt.title('Optimal Readout Power Distribution')
        plt.xlabel(f'Optimal Readout Power (dB relative to nominal RFIN/RFOUT of {self.rfin:.2f}/{self.rfout:.2f} dB)')
        plt.ylabel('Frequency')
        plt.stairs(counts, bins, fill=True)
        pdf.savefig()
        plt.close()
        pdf.close()

        if callback is not None:
            callback()

        self._plotted = True

class PowerSweep(CompositeSweep[PowerSweepData]):
    sweep_type = 'Power'

    def __init__(
        self,
        rfsoc: RFSOCWrapper,
        chan: int,
        tone_shift: float,
        freq_step: float,
        full_span: float,
        power_levels: npt.NDArray,
        savefile: Path=None,
        filename_suffix: str='',
        mkdir: bool=False,
        **kwargs,
    ):
        """Initialize a PowerSweep
        
        Arguments: 
            power_levels (npt.NDArray): Power at the resonator relative to the nominal
                rfout and rfin values, in dB.
        """
        super().__init__(
            rfsoc,
            chan,
            tone_shift,
            freq_step,
            full_span,
            savefile=savefile,
            filename_suffix=filename_suffix,
            mkdir=mkdir,
        )

        self.power_levels = power_levels
        self.starting_rfin = self.rfsoc.get_rfin(self.chan)
        self.starting_rfout = self.rfsoc.get_rfout(self.chan)

        self._setup_sweeps()
    
    def _setup_sweeps(self):
        self.rfins = []
        self.rfouts = []
        for power_level in self.power_levels:
            this_rfout = self.starting_rfout - power_level
            this_rfin = self.starting_rfin + power_level
            if this_rfin < 0 or this_rfin > 31.75 or this_rfout < 0 or this_rfout > 31.75:
                raise ValueError(f'All power levels must be in range [0, 31.75].')
            self.rfins.append(this_rfin)
            self.rfouts.append(this_rfout)
            this_savefile = self.savefile.with_stem(f'{self.savefile.stem}_{power_level:+f}dB'.replace('.', '_'))
            sweep = LoSweep(
                self.rfsoc, self.chan, this_savefile, self.tone_shift,
                self.freq_step, self.full_span,
            )
            self._sweeps.append(sweep)
    
    def _between_sweep_callback(self, i_sweep: int, sweep: LoSweep):
        # Set the appropriate power level for this sweep
        self.rfsoc.set_rfin(self.chan, self.rfins[i_sweep])
        self.rfsoc.set_rfout(self.chan, self.rfouts[i_sweep])
    
    def _end_sweeps_callback(self):
        # Reset to original power level
        self.rfsoc.set_rfin(self.chan, self.starting_rfin)
        self.rfsoc.set_rfout(self.chan, self.starting_rfout)
    
    def save_sweeps(self, data: list[LoSweepData]):
        self._data = PowerSweepData(
            self.bb_freqs,
            self.f_center,
            data,
            self.power_levels,
            self.starting_rfin,
            self.starting_rfout,
        )
        self._data.save_as(self.savefile)
    


if __name__ == '__main__':
    import pdb
    from rfsocinterface.core.params import initialize_params_file, update_params_file

    # sweep_file = '/data/20260513/20260513_Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour15p0019.h5'
    # tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260513_with_offres_and_max_power'
    sweep_file = '/data/20260515/20260515_Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour11p7350.h5'
    tile_name = 'Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power'

    sweep = PowerSweepData.load(sweep_file)
    sweep.fit()  # Fit resonances if they haven't yet
    sweep.save_as(sweep_file)
    sweep.find_optimal_readout_power(bad_power_cutoff_percentile=0.5, pdf_filename=f'max_power_{tile_name}.pdf')
    sweep.save_as(sweep_file)

    pdb.set_trace()
    # NOTE: This will overwrite everything that isn't tone_powers with defaults
    # TODO: Create a "copy_params_file" function
    params_file = get_params_file_template(tile_name)
    if Path(params_file).exists():
        update_params_file(params_file, tone_powers=sweep.max_readout_power)
    else:
        initialize_params_file(tile_name, sweep.bb_freqs, lo_freq=sweep.f_center)
        update_params_file(tile_name, tone_powers=sweep.max_readout_power)


