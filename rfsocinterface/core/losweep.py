from __future__ import annotations
import logging
import pdb
import glob

from concurrent.futures import Future

from pathlib import Path
from PySide6.QtWidgets import QProgressDialog

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from numpy.polynomial import Polynomial
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from scipy.signal import savgol_filter
import h5py
import tables

from PySide6.QtWidgets import QApplication
from rfsocinterface.core.utils import BAD_RFSOC_TONE_START_INDEX, ensure_path, PERMISSIONS_USR_RW
from rfsocinterface.core.pool import QThreadJobPool
from rfsocinterface.gui.widgets.progress_bar import QThreadJobProgressDialog
from kidpy3 import capture_packets
from kidpy3.hardware.Valon5009 import Valon5009, SYNTH_A, SYNTH_B
from kidpy3.data_handler import Rfchan
from rfsocinterface.core.utils import get_tod_template


_logger = logging.getLogger(__name__)


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
    center_ind = np.argwhere(abs(freq - old_tone_freq) == min(abs(freq - old_tone_freq)))[0]

    #smooth the data
    x = s21
    s21 = savgol_filter(s21, 7, 3, mode='mirror')

    #search for local minima
    if s21[center_ind[0]] != min(s21):
       keepgoing = True
       while keepgoing:
          lo_ind = int(max(center_ind-1,0))
          hi_ind = int(min(center_ind+2,n_freq))
          min_ind = np.argwhere(s21[lo_ind:hi_ind] == min(s21[lo_ind:hi_ind]))[0]
          if min_ind[0] == (center_ind[0] - lo_ind):
             keepgoing = False
          else:
             center_ind = lo_ind + min_ind

    f0 = freq[center_ind[0]]
    return f0


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
            # ax.ticklabel_format(useOffset=False, style='plain')
            ax.set_ylabel(r'$|S_{21}|$')
            # ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            ax.xaxis.set_major_formatter(FuncFormatter(resonator_plot_formatter))
        # Otherwise, just plot inside the existing axes
        else:
            ax.set_facecolor('white')
            ax.set_yticks([])
            ax.set_xticks([])

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

        if return_fig:
            return fig
        return None

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

    def fit(self, df: float, start: float = None) -> tuple[float, float, float]:
        """Perform a fit to find the resonance frequency."""
        if start is None:
            start = self.tone
        fit_f0 = simple_derivative_fits(df, self.freq, start, self.s21)
        fit_qi = 0.0
        fit_qc = 0.0

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
        self, tone_list: npt.NDArray, f_center: float, sweep_data: npt.NDArray, chanmask: npt.NDArray, 
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
        self.set_diff_to_flag()
    
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
        return np.size(np.where(self.chanmask == 1))

    @property
    def df(self) -> float:
        """The difference between two frequency data points, in Hz."""
        return self.freq[0, 1] - self.freq[0, 0]

    @property
    def onres_ind(self) -> npt.NDArray:
        """The indices of frequencies that are on-resonance."""
        return np.argwhere(self.chanmask == 1)

    @property
    def offres_ind(self) -> npt.NDArray:
        """The indices of frequencies that are off-resonance."""
        return np.argwhere(self.chanmask == 0)

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

    def fit(self, pd: QThreadJobProgressDialog | None=None) -> Future:
        """Perform a fit to determine the resoncance frequencies of each resonator."""
        if pd is None:
            pd = QThreadJobPool(parent=self)
        return pd.map(self._fit_i, np.argwhere(self.chanmask == 1))
        for i_chan in np.argwhere(self.chanmask == 1):
            self._fit_i(i_chan)
    
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


    def plot(self, ncols: int = 18, pd: QThreadJobProgressDialog | None=None) -> tuple[Figure, Future]:
        """Plot the results of fitting the LO sweep.

        Arguments:
            ncols (int): The number of columns to use in the figure. The figure will have
                one inch width for each column.

        Returns:
            (Figure): The generated figure showing the plot for each resonator.
        """
        # Setup for plots
        nrows = int(np.ceil(self.nchan / ncols))

        fig = plt.figure(figsize=(ncols, nrows))
        # fig, subplots = plt.subplots(nrows, ncols, figsize=(ncols, nrows))
        plt.rc('font', size=8)

        # loop over resonators to perform fit
        subplots = []
        for i in range(self.nchan):
            subplot = plt.subplot2grid(
                (nrows, ncols), (i // ncols, np.mod(i, ncols))
            )
            subplots.append(subplot)
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
    
    def freq_direction(self, fit_order: int=3, deriv_length: int=5) -> tuple[npt.NDArray, npt.NDArray]:
        dIQ_df = np.zeros((2, self.nchan))
        mid_ind = self.nfreq // 2
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

        # Q in y direction, I in x direction
        # NOTE: This is the angle (counter-clockwise) from the I-axis to the freq-axis
        # Negative because we're rotating the coordinate axes, not the point
        rotation_angle = -np.atan2(dIQ_df[1, :], dIQ_df[0, :])

        # For a fixed readout tone, a positive shift in the resonance freq appears 
        # as a perceived positive shift in the I/Q data, which thus necessitates the positive sign
        adc_units_to_hz = np.sqrt((dIQ_df[0]) ** 2 + (dIQ_df[1]) ** 2)
        return rotation_angle, adc_units_to_hz


def get_tone_list(filename: str, lo_freq: float = 400) -> npt.NDArray:
    """Get the data from a tone-list and convert to Hz from MHz."""
    flist = np.load(filename)
    return lo_freq * 1.0e6 + flist


class LoSweep:
    """Class for performing an LO Sweep"""

    def __init__(self, valon: Valon5009, chan: Rfchan, freqs: npt.NDArray, f_center: float=400e6):
        """Initialize an LoSweep"""
        self.valon = valon
        self.chan = chan
        self.freqs = freqs  # Hz
        self.f_center = f_center  # Hz
        self._processed = False

    def _get_data(self, N_steps=500, freq_step=0.0, pd: QProgressDialog | None=None):
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
        log = logging.getLogger()
        tone_diff = np.diff(self.freqs)[0] * 1e-6  # MHz
        log.info(f"tone diff={tone_diff}")
        if freq_step > 0:
            flo_step = freq_step
        else:
            flo_step = tone_diff / N_steps

        log.info(f"lo step size={flo_step}")
        flo_start = self.f_center - flo_step * N_steps / 2.0  # 256
        flo_stop = self.f_center + flo_step * N_steps / 2.0  # 256

        flos = np.arange(flo_start, flo_stop, flo_step) # MHz
        if pd is not None:
            pd.setMaximum(len(flos))
            pd.setLabelText('Performing LO Sweep...')
            QApplication.processEvents()
        # flos = np.round(flos * 1e3)*1e-3
        log.info(f"len flos {flos.shape}")
        actual_los = []
        def temp(lofreq):
            # self.set_ValonLO function here
    
            self.valon.set_frequency(SYNTH_B, lofreq)

            # Read values and trash initial read, suspecting linear delay is cause..
            # toss 20 packets in the garbage
            packets = capture_packets(self.chan, 20)

            # Actually use this data
            Naccums = 100
            packets = capture_packets(self.chan, Naccums).T
            I = []
            Q = []
            for packet in packets:
                It = packet[::2]
                Qt = packet[1::2]
                I.append(It)
                Q.append(Qt)
            I = np.array(I)
            Q = np.array(Q)

            Imed = np.median(I, axis=0)
            Qmed = np.median(Q, axis=0)

            Z = Imed + 1j * Qmed
            start_ind = np.min(np.argwhere(Imed != 0.0))
            Z = Z[start_ind : start_ind + len(self.freqs)]


            return Z
        z = []
        for i, lofreq in enumerate(flos):
            if pd is not None:
                pd.setValue(i + 1)
                QApplication.processEvents()
            z.append(temp(lofreq))
        sweep_Z = np.array(z)

        # sweep_Z = np.array([temp(lofreq) for lofreq in flos])
        log.info(f"sweepz.shape={sweep_Z.shape}")

        f = np.zeros([np.size(self.freqs), np.size(flos)])
        log.info(f"shape of f = {f.shape}")
        for itone, ftone in enumerate(self.freqs):
            f[itone, :] = flos * 1.0e6 + ftone  # Convert back to Hz before adding
        #    f = np.array([flos * 1e6 + ftone for ftone in freqs]).flatten()
        sweep_Z_f = sweep_Z.T
        #    sweep_Z_f = sweep_Z.T.flatten()

        ## SAVE f and sweep_Z_f TO LOCAL FILES
        # SHOULD BE ABLE TO SAVE TARG OR VNA
        # WITH TIMESTAMP

        # set the LO back to the original frequency
        self.valon.set_frequency(Valon5009.SYNTH_B, self.f_center)

        return (f, sweep_Z_f)

    def _get_data_at(self, lo_freq: float):
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
        self.valon.set_frequency(SYNTH_B, lo_freq)

        # Read values and trash initial read, suspecting linear delay is cause..
        # toss 20 packets in the garbage
        packets = capture_packets(self.chan, 20)

        # Actually use this data
        Naccums = 100
        packets = capture_packets(self.chan, Naccums)
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
        Z = Z[BAD_RFSOC_TONE_START_INDEX: BAD_RFSOC_TONE_START_INDEX + len(self.freqs)]


        return Z


    def run_sweep(self, chanmask: npt.NDArray, tone_list: npt.NDArray, N_steps=500, freq_step=1e3, pd: QThreadJobProgressDialog | None=None) -> Future[LoSweepData]:
        """Perform a stepped frequency sweep centered at f_center and save result as s21.npy file

        f_center: center frequency for sweep in [MHz], default is 400
        """
        self.tone_list = tone_list

        if np.size(chanmask) == 0:  # Chanmask hasn't been set, so use all ones
            chanmask = np.ones(np.size(tone_list), dtype=int)

        self.chanmask = chanmask
        self._processed = False
        if len(self.freqs) > 1:
            tone_diff = np.diff(self.freqs)[0] * 1e-6  # MHz
        else:
            tone_diff = 0
        _logger.debug(f"tone diff={tone_diff}")
        if freq_step > 0:
            flo_step = freq_step * 1e-6  # MHz
        else:
            flo_step = tone_diff / N_steps

        _logger.debug(f"lo step size={flo_step}")
        flo_start = self.f_center * 1e-6 - flo_step * N_steps / 2.0  # MHz
        flo_stop = self.f_center * 1e-6  + flo_step * N_steps / 2.0  # MHz

        self.flos = np.arange(flo_start, flo_stop, flo_step)  # MHz
        if pd is not None:
            pd.setMaximum(len(self.flos))
        # flos = np.round(flos * 1e3)*1e-3
        _logger.debug(f"len flos {self.flos.shape}")
        if pd is not None:
            future = pd.map(self._get_data_at, self.flos)
        else:
            pool = QThreadJobPool(max_workers=1, parent=self)
            future = pool.map(self._get_data_at, self.flos)
        future.add_done_callback(self._process_sweep_results)
        return future

        # results = self._get_data(
        #     N_steps=N_steps,
        #     freq_step=freq_step,
        #     pd=pd,
        # )
    
    def _process_sweep_results(self, future: Future[npt.NDArray]):
        _logger.info('Processing sweep results')
        if future.cancelled():
            _logger.info('Sweep cancelled. Exiting...')
            return
        sweep_Z = np.array(list(future.result()))

        _logger.debug(f"sweepz.shape={sweep_Z.shape}")

        f = np.zeros([np.size(self.freqs), np.size(self.flos)])
        _logger.debug(f"shape of f = {f.shape}")
        for itone, ftone in enumerate(self.freqs):
            f[itone, :] = self.flos * 1e6 + ftone
        #    f = np.array([flos * 1e6 + ftone for ftone in freqs]).flatten()
        sweep_Z_f = sweep_Z.T
        #    sweep_Z_f = sweep_Z.T.flatten()

        ## SAVE f and sweep_Z_f TO LOCAL FILES
        # SHOULD BE ABLE TO SAVE TARG OR VNA
        # WITH TIMESTAMP

        # set the LO back to the original frequency
        self.valon.set_frequency(self.chan.chan_number, self.f_center * 1e-6)

        self.data = LoSweepData(self.tone_list, self.f_center, np.array((f, sweep_Z_f)), self.chanmask)
        self._processed = True
        _logger.info('Finished processing sweep results')


class ManualLoSweepData(LoSweepData):
    def __init__(
            self,
            date: str,
            min_setnum: int,
            max_setnum: int,
            f_center: float=400e6,
    ):
        n_setnum = max_setnum - min_setnum + 1
        n_tones: float
        data: npt.NDArray
        flos: npt.NDArray
        baseband_freqs: npt.NDArray
        chanmask: npt.NDArray
        for i_setnum, setnum in enumerate(range(min_setnum, max_setnum + 1)):
            tod_template = get_tod_template(date, setnum)
            todlist = glob.glob(tod_template)
            if len(todlist) == 0:
                raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")
            with tables.open_file(todlist[0], 'r') as f:
                global_data = f.root.global_data
                time_ordered_data = f.root.time_ordered_data
                # Initialize arrays if needed
                if i_setnum == 0:
                    n_tones = f.root.dimension.n_tones[0]
                    flos = np.zeros(n_setnum)
                    baseband_freqs = global_data.baseband_freqs[:]
                    data = np.zeros(2, n_tones, n_setnum, dtype=complex)
                    chanmask = f.root.global_data.chanmask[:]
                # Append to the data 
                flos[i_setnum] = global_data.lo_freq[:]
                data_I = time_ordered_data.adc_i[BAD_RFSOC_TONE_START_INDEX:BAD_RFSOC_TONE_START_INDEX + n_tones]
                data_Q = time_ordered_data.adc_q[BAD_RFSOC_TONE_START_INDEX:BAD_RFSOC_TONE_START_INDEX + n_tones]
                z = np.median(data_I, axis=-1) + 1j * np.median(data_Q, axis=-1)
                data[1, :, i_setnum] = z
        # Determine the list of frequencies
        for i_tone, tone in enumerate(baseband_freqs):
            data[0, i_tone, :] = flos + tone
        super().__init__(baseband_freqs, f_center, data, chanmask)



if __name__ == '__main__':
    import pdb

    data = LoSweepData.from_h5('/data/20250409/20250409_rfsoc2_LO_Sweep_hour16p6986.h5')
    pdb.set_trace()