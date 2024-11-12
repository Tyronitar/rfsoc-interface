from __future__ import annotations
from typing import Callable, Iterable
import logging

from pathlib import Path
from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import QProgressDialog

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.figure import Figure
import h5py

from onr_fit_lo_sweeps import simple_derivative_fits
from onrkidpy import get_chanmask
from PySide6.QtWidgets import QApplication
from rfsocinterface.utils import ensure_path, Job
import valon5009
import time
import udpcap


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
        ax.set_xlim(
            np.mean(self.freq * 1e-6) - new_span / 2.0,
            np.mean(self.freq * 1e-6 + new_span / 2.0),
        )

        # Add a label showing the resonator number
        if self.is_onres:
            ax.legend(
                [f'{self.idx:d}'],
                fontsize=6,
                loc=3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                bbox_to_anchor=(0.01, 0.02),
                alignment='center',
                edgecolor='black',
                # bbox_to_anchor=(-0.2,-0.15)
            )
            if self.flagged:
                ax.set_facecolor('yellow')
        else:
            ax.legend(
                [
                    f'{self.idx:d}'
                    + ', dS21='
                    + f'{np.max(self.s21) - np.min(self.s21):4.1f}'
                ],
                fontsize=6,
                loc=3,
                frameon=False,
                framealpha=0,
                handlelength=0,
                bbox_to_anchor=(0.01, 0.02),
                alignment='center',
                edgecolor='black',
            )
            ax.set_facecolor('orange')

        if return_fig:
            return fig
        return None

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

    def __init__(
        self, tone_list: npt.NDArray, sweep_data: tuple[npt.NDArray, npt.NDArray], chanmask: npt.NDArray, 
    ) -> None:
        """Initialize a LoSweepData object."""
        self.data = sweep_data
        self.tone_list = tone_list
        self.freq = np.real(self.data[0, :, :])
        self.s21 = np.real(10.0 * np.log10(np.abs(self.data[1, :, :])))
        self.chanmask = chanmask
        self.resonator_data = [ResonatorData(self, i) for i in range(self.nchan)]

        self.fit_f0 = np.zeros(self.nchan)
        self.fit_qi = np.zeros(self.nchan)
        self.fit_qc = np.zeros(self.nchan)
        self.fit_f0[self.offres_ind] = tone_list[self.offres_ind]
        self.diff_to_flag = (3.0 / 200.0) * self.tone_list * 1e-6
    
    @classmethod
    @ensure_path(1, 2, 3)
    def from_file(cls, tone_file: Path, sweep_file: Path, chanmask_file: Path, lo_freq: float=400) -> LoSweepData:
        """Create a LoSweepData object from a sweep file."""
        tone_list = get_tone_list(tone_file, lo_freq=lo_freq)
        data = np.load(sweep_file)
        chanmask = get_chanmask(chanmask_file)
        return cls(tone_list, data, chanmask)

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
        return np.argwhere(np.abs(self.difference) > self.diff_to_flag)

    def fit(self, do_print=False, signal: SignalInstance | None=None):
        """Perform a fit to determine the resoncance frequencies of each resonator."""
        if signal:
            signal.emit(len(self.chanmask == 1) - 1)
        for i_chan in np.argwhere(self.chanmask == 1):
            # pull in the sweep data for this tone
            i: int = i_chan[0]
            resonator = self.resonator_data[i]

            # call the resonator fitter
            f0, qc, qi = resonator.fit(self.df)
            self.fit_f0[i] = f0
            self.fit_qc[i] = qc
            self.fit_qi[i] = qi

            diff = resonator.difference
            if np.abs(diff) > self.diff_to_flag[i]:
                resonator.flagged = True
                if do_print:
                    print(
                        'tone index =',
                        f'{i:4d}',
                        '|| new tone =',
                        f'{self.fit_f0[i] * 1.0e-6:9.5f}',
                        '|| old tone =',
                        f'{self.tone_list[i] * 1.0e-6:9.5f}',
                        '|| difference (kHz) =',
                        f'{diff:+5.3f}',
                    )
            if signal:
                signal.emit(0)
                # job.updateProgress.emit()
                # QApplication.processEvents()
        
    
    def plot(self, ncols: int = 18, signal: SignalInstance=None) -> Figure:
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
        plt.rc('font', size=8)

        # loop over resonators to perform fit
        if signal:
            signal.emit(len(self.resonator_data) - 1)
        for counter, resonator in enumerate(self.resonator_data):
            subplot = plt.subplot2grid(
                (nrows, ncols), (counter // ncols, np.mod(counter, ncols))
            )
            resonator.plot(subplot)
            if signal:
                signal.emit(0)

        plt.tight_layout()
        return fig
    
    @ensure_path(1)
    def savenp(self, fname: Path):
        path = fname.with_suffix('.npy')
        np.save(path, self.data)

    @ensure_path(1)
    def saveh5(self, fname: Path):
        """Save the LO Sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        with h5py.File(path, 'w') as fh:
            fh.create_dataset('global_data/lo_sweep', data=self.data)
            # fh.create_dataset('global_data/s21', data=self.s21)
            # fh.create_dataset('global_data/freq', data=self.freq)
            fh.create_dataset('global_data/baseband_freqs', data=self.tone_list)
            fh.create_dataset('global_data/chanmask', data=self.chanmask)
            fh.create_dataset('global_data/fit_f0', data=self.fit_f0)
            fh.create_dataset('global_data/fit_qi', data=self.fit_qi)
            fh.create_dataset('global_data/fit_qc', data=self.fit_qc)



def get_tone_list(filename: str, lo_freq: float = 400) -> npt.NDArray:
    """Get the data from a tone-list and convert to Hz from MHz."""
    flist = np.load(filename)
    return lo_freq * 1.0e6 + flist


class LoSweep:
    """Class for performing an LO Sweep"""

    def __init__(self, valon: valon5009.Synthesizer, udp: udpcap.udpcap, freqs: npt.NDArray, f_center: float=400.0):
        """Initialize an LoSweep"""
        self.valon = valon
        self._udp = udp
        self.freqs = freqs
        self.f_center = f_center

    def _get_data(self, N_steps=500, freq_step=0.0, signal: SignalInstance | None=None):
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
        tone_diff = np.diff(self.freqs)[0] / 1e6  # MHz
        log.info(f"tone diff={tone_diff}")
        if freq_step > 0:
            flo_step = freq_step
        else:
            flo_step = tone_diff / N_steps

        log.info(f"lo step size={flo_step}")
        flo_start = self.f_center - flo_step * N_steps / 2.0  # 256
        flo_stop = self.f_center + flo_step * N_steps / 2.0  # 256

        flos = np.arange(flo_start, flo_stop, flo_step) #+1e-6
        if signal is not None:
            signal.emit(len(flos))
        # flos = np.round(flos * 1e3)*1e-3
        log.info(f"len flos {flos.shape}")
        self._udp.bindSocket()
        actual_los = []
        def temp(lofreq):
            # self.set_ValonLO function here
    
            # print(lofreq)
            self.valon.set_frequency(valon5009.SYNTH_B, lofreq)
            # Read values and trash initial read, suspecting linear delay is cause..
            Naccums = 100
            I, Q = [], []
            for i in range(20):  # toss 10 packets in the garbage
                self._udp.parse_packet()

            for i in range(Naccums):
                # d = udp.parse_packet()
                d = self._udp.parse_packet()
                It = d[::2]
                Qt = d[1::2]
                I.append(It)
                Q.append(Qt)
            I = np.array(I)
            Q = np.array(Q)
            Imed = np.median(I, axis=0)
            Qmed = np.median(Q, axis=0)

            Z = Imed + 1j * Qmed
            start_ind = np.min(np.argwhere(Imed != 0.0))
            Z = Z[start_ind : start_ind + len(self.freqs)]

            print(".", end="")

            return Z
        z = []
        for i, lofreq in enumerate(flos):
            if signal is not None:
                signal.emit(0)
            z.append(temp(lofreq))
        sweep_Z = np.array(z)

        # sweep_Z = np.array([temp(lofreq) for lofreq in flos])
        log.info(f"sweepz.shape={sweep_Z.shape}")

        f = np.zeros([np.size(self.freqs), np.size(flos)])
        log.info(f"shape of f = {f.shape}")
        for itone, ftone in enumerate(self.freqs):
            f[itone, :] = flos * 1.0e6 + ftone
        #    f = np.array([flos * 1e6 + ftone for ftone in freqs]).flatten()
        sweep_Z_f = sweep_Z.T
        #    sweep_Z_f = sweep_Z.T.flatten()
        self._udp.release()
        ## SAVE f and sweep_Z_f TO LOCAL FILES
        # SHOULD BE ABLE TO SAVE TARG OR VNA
        # WITH TIMESTAMP

        # set the LO back to the original frequency
        self.valon.set_frequency(valon5009.SYNTH_B, self.f_center)

        return (f, sweep_Z_f)

    def run_sweep(self, chanmask_file: Path, tone_list: npt.NDArray, N_steps=500, freq_step=1.0, signal: SignalInstance | None=None):
        """Perform a stepped frequency sweep centered at f_center and save result as s21.npy file

        f_center: center frequency for sweep in [MHz], default is 400
        """
        #    print(freqs)
        results = self._get_data(
            N_steps=N_steps,
            freq_step=freq_step,
            signal=signal,
        )
        chanmask = get_chanmask(chanmask_file)
        return LoSweepData(tone_list, np.array(results), chanmask)
        print("LO Sweep s21 file saved.")
