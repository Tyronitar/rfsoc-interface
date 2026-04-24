from __future__ import annotations

from rfsocinterface.core.losweep import LoSweepData, ResonatorData, PowerSweepData, get_scraps_fit
import logging
import pdb
import datetime

from concurrent.futures import Future
from typing import Callable
from multiprocessing import Lock
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait
import rfsocinterface.analysis.KID_fitting_analysis.fit_mb_params as mb_params
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
from scipy.signal import savgol_filter, find_peaks
from scipy.ndimage import gaussian_filter1d
_logger = logging.getLogger(__name__)

import scraps as scr
from scipy.optimize import curve_fit
import h5py
import tables

from rfsocinterface.core.utils import BAD_RFSOC_TONE_START_INDEX, ensure_path, PERMISSIONS_USR_RW, parallel_plot

NEW_LO_SWEEP_FORMAT_DATE = '20260213'  # For backwards compatibility

class TempSweepData:
    def __init__(
        self,
        tone_list: npt.NDArray,
        f_center: float,
        sweeps: list[LoSweepData],
        fp_temps: npt.NDArray,
        rfin: float,
        rfout: float,
    ):
        self.f_center = f_center
        self.tone_list = tone_list
        self.sweeps = sweeps
        self.fp_temps = np.array(fp_temps)
        self.rfin = rfin
        self.rfout = rfout
        self.max_readout_power = np.zeros(self.n_tones)
        self.fit_f0 = np.zeros(self.n_tones)
    
    @property
    def chanmask(self) -> npt.NDArray:
        """The chanmask used during the power sweep."""
        return self.sweeps[0].chanmask
    
    @property
    def combined_sweep_array(self) -> npt.NDArray:
        """The LO sweep data from each lo sweep as one array.

        Resulting array will have shape (N_sweeps, 2, N_tones, N_samples) 
        """
        #pdb.set_trace()
        return np.stack([sweep.data for sweep in self.sweeps], axis=0)
    
    @property
    def n_tones(self) -> int:
        #TODO this is broken
        return 100
    
    @property
    def n_sweeps(self) -> int:
        return len(self.power_levels)
    
    @property
    def tile_names(self) -> list[str]:
        return [sweep.tile_name for sweep in self.sweeps]
    
    def get_fit_f0(self) -> npt.NDArray:
        fit_f0 = np.stack([sweep.fit_f0 for sweep in self.sweeps], axis=0)
        self.fit_f0 = fit_f0
        return fit_f0
    
    def fit(self):
        for sweep in self.sweeps:
            sweep.fit()
        self.get_fit_f0()

    @ensure_path(1)
    def saveh5(self, fname: Path):
        """Save the power sweep to an HDF5 file."""
        path = fname.with_suffix('.h5')
        path.touch(PERMISSIONS_USR_RW)
        with tables.File(path, 'w') as fh:
            fh.create_array('/', 'sweeps', obj=self.combined_sweep_array)
            fh.create_array('/','lo_freq', obj=self.f_center)
            fh.create_array('/','baseband_freqs', obj=self.tone_list - self.f_center)
            fh.create_array('/','chanmask', obj=self.chanmask)
            fh.create_array('/','fp_temps', obj=self.fp_temps)
            fh.create_array('/','rfin', obj=self.rfin)
            fh.create_array('/','rfout', obj=self.rfout)
            fh.create_array('/','fit_f0', obj=self.fit_f0)
            fh.create_array('/','max_readout_power', obj=self.max_readout_power)
            fh.root._v_attrs.tile_names = self.tile_names
        _logger.info(f'PowerSweepData saved to {str(fname)}')
    
    @classmethod
    @ensure_path(1)
    def from_h5(cls, fname: Path) -> PowerSweepData:
        with tables.File(fname, 'r') as fh:
            if datetime.datetime.fromtimestamp(fname.stat().st_mtime) < datetime.datetime.strptime(NEW_LO_SWEEP_FORMAT_DATE, '%Y%m%d'):
                _logger.warning(f'LO sweep file {str(fname)} is from before {NEW_LO_SWEEP_FORMAT_DATE}. Attempting to load with backwards compatibility.')
                tone_list = fh.root.global_data.baseband_freqs[:]
                f_center = fh.root.global_data.lo_freq[()]
                rfin = fh.root.global_data.rfin[()]
                rfout = fh.root.global_data.rfout[()]
                fp_temps = fh.root.global_data.fp_temps[:]
                chanmask = fh.root.global_data.chanmask[:]
                sweep_data = fh.root.global_data.sweeps[:]
                fit_f0 = fh.root.global_data.fit_f0[:]
                max_readout_power = fh.root.global_data.max_readout_power[:]
            else:
                tone_list = fh.root.baseband_freqs[:]
                f_center = fh.root.lo_freq[()]
                rfin = fh.root.rfin[()]
                rfout = fh.root.rfout[()]
                chanmask = fh.root.chanmask[:]
                fp_temps = fh.root.fp_temps[:]
                sweep_data = fh.root.sweeps[:]
                fit_f0 = fh.root.fit_f0[:]
                max_readout_power = fh.root.max_readout_power[:]
                tile_names = fh.root._v_attrs.tile_names


            sweeps = []
            for this_fit_f0, arr, tile_name in zip(fit_f0, sweep_data, tile_names):
            # for arr in sweep_data:
                sweep = LoSweepData(tone_list, f_center, arr, chanmask, tile_name)
                sweep.fit_f0[:] = this_fit_f0
                sweeps.append(sweep)

        temp_sweep = cls(tone_list, f_center, sweeps,fp_temps, rfin, rfout)
        temp_sweep.get_fit_f0()
        temp_sweep.max_readout_power = max_readout_power

        return temp_sweep

    def process_temperature_sweep(self, plot: bool = True, output_plot_filename: str = "TempSweep.pdf"):
        self.fit()

        sorted_idx = np.argsort(self.fp_temps)
        self.fp_temps = self.fp_temps[sorted_idx]
        f0_data = self.fit_f0[sorted_idx, :]

        n_temps, n_res = f0_data.shape
        q_data = np.zeros_like(f0_data)
        q_i_data = np.zeros_like(f0_data)
        q_c_data = np.zeros_like(f0_data)

        figs = []

        onres_ind = np.where(self.chanmask == 1)[0]

        for i_res in onres_ind:
            results = self._fit_single_resonator(i_res)

            f0_data[:, i_res] = results["f0"]
            q_data[:, i_res] = results["q_tot"]
            q_i_data[:, i_res] = results["qi"]
            q_c_data[:, i_res] = results["qc"]

            if plot:
                figs.append(
                    self._plot_resonator_sweeps(i_res, results)
                )

                figs.append(
                    self._plot_temperature_dependence(
                        i_res,
                        f0_data[:, i_res],
                        q_i_data[:, i_res],
                        q_c_data[:, i_res],
                    )
                )
        with PdfPages(output_plot_filename) as pdf:
            for fig in figs:
                pdf.savefig(fig)

    def _fit_single_resonator(self, i_res):
        f0_list, qi_list, qc_list, qtot_list = [], [], [], []

        f0_guess = None
        fit_ires = i_res
        for i_p, temp in enumerate(self.fp_temps):
            sweep = self.sweeps[i_p]
            resonator = sweep.resonator_data[i_res]
            initial_fit = find_peaks(-sweep.s21[i_res], height=0.2)


            Q = sweep.data_Q[fit_ires]
            I = sweep.data_I[fit_ires]





            if i_p == 0:
                res_obj = get_scraps_fit(
                    I, Q,
                    resonator.freq,
                    resonator.tone,
                    resonator.s21,
                    temp=temp
                )
            else:
                freq_range = resonator.freq[-1] - resonator.freq[0]

                res_obj = get_scraps_fit(
                    I, Q,
                    resonator.freq,
                    resonator.tone,
                    resonator.s21,
                    initial_guesses={
                        "f0": {
                            "value": f0_guess,
                            "min": resonator.freq[0],
                            "max": f0_guess + 0.01 * freq_range,
                            "vary": True,
                        }
                    }
                )
            print(res_obj.hasFit)

            params = res_obj.lmfit_result['default']['result'].params

            f0 = params['f0'].value
            qi = params['qi'].value
            qc = params['qc'].value

            f0_guess = f0  # tracking
            print(f0)

            f0_list.append(f0)
            qi_list.append(qi)
            qc_list.append(qc)
            qtot_list.append(1 / (1/qi + 1/qc))

        return {
            "f0": np.array(f0_list),
            "qi": np.array(qi_list),
            "qc": np.array(qc_list),
            "q_tot": np.array(qtot_list),
        }
    
    def _plot_resonator_sweeps(self, i_res, results):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        colors = plt.cm.viridis(np.linspace(0, 1, len(self.fp_temps)))

        for i_p, temp in enumerate(self.fp_temps):
            sweep = self.sweeps[i_p]
            resonator = sweep.resonator_data[i_res]

            I = sweep.data_I[i_res]
            Q = sweep.data_Q[i_res]
            f0 = results["f0"][i_p]

            ax1.plot(resonator.freq, resonator.s21, color=colors[i_p])
            ax1.axvline(f0, color=colors[i_p], alpha=0.5)

            ax2.plot(I, Q, color=colors[i_p])

        ax1.set(title=f"Resonator {i_res} S21", xlabel="Frequency", ylabel="|S21|")
        ax2.set(title="IQ Circle", xlabel="I", ylabel="Q")
        ax2.set_aspect("equal")

        fig.tight_layout()
        return fig
    
    def _plot_temperature_dependence(self, i_res, f0, qi, qc):
        temps = self.fp_temps
        df = (f0 - f0[0]) / f0[0]

        params_fres, params_qi = mb_params.MB_fit(f0, qi, temps)

        fig, axes = plt.subplots(3, 1, figsize=(8, 12))

        # df/f
        axes[0].plot(temps, df, 'o')
        axes[0].set(xlabel="Temperature (mK)", ylabel="Δf/f0")

        # Qi
        axes[1].plot(temps, qi, 'o')
        axes[1].set(xlabel="Temperature", ylabel="Qi")

        # Qc
        axes[2].plot(temps, qc, 'o')
        axes[2].set(xlabel="Temperature", ylabel="Qc")

        fig.tight_layout()
        return fig
    
    def build_full_vna_dataset(self):
        fp_temps = self.fp_temps[:]

        # Sort by temperature
        sorted_data_ind = np.argsort(fp_temps)
        self.fp_temps = fp_temps[sorted_data_ind]

        full_s21 = []
        full_I = []
        full_Q = []
        freqs = []

        for i_p, sweep_data in enumerate(self.sweeps):
            sorted_idx = np.argsort(sweep_data.tone_list + sweep_data.f_center)

            freq = sweep_data.freq[sorted_idx].flatten()
            freqs.append(freq)

            full_I.append(sweep_data.data_I[sorted_idx].flatten())
            full_Q.append(sweep_data.data_Q[sorted_idx].flatten())

            stitched = []
            prev_end = None

            for row in sweep_data.s21[sorted_idx]:
                row_corrected = row.copy()

                if prev_end is not None:
                    offset = prev_end - row_corrected[0]
                    row_corrected += offset

                stitched.append(row_corrected)
                prev_end = row_corrected[-1]

            full_s21.append(np.concatenate(stitched))

        # Return sorted sweeps alongside data for consistency
        sorted_sweeps = [self.sweeps[i] for i in sorted_data_ind]

        return {
            "temps": self.fp_temps,
            "freqs": freqs,
            "s21": full_s21,
            "I": full_I,
            "Q": full_Q,
            "sweeps": sorted_sweeps
        }
    def plot_vna_temp_sweep(self, dataset, expected_resonances_at_base_temp, plot=True):
        temps = dataset["temps"]
        freqs = dataset["freqs"]
        full_s21 = dataset["s21"]

        resonances = []
        figs = []
        freq_half_span = 8e6

        for res_freq in expected_resonances_at_base_temp:
            fig, ax = plt.subplots(figsize=(8, 5))
            plotted = False

            for i_p in range(len(freqs)):
                freq = freqs[i_p]
                s21 = full_s21[i_p]

                mask = np.where(
                    (res_freq - freq_half_span < freq) &
                    (freq < 0.1 * freq_half_span + res_freq)
                )

                if not np.any(mask):
                    continue

                plotted = True

                ax.plot(
                    freq[mask],
                    s21[mask] - np.mean(s21[mask]),
                    label=f'{temps[i_p]:.1f} mK'
                )

                primary_peaks = find_peaks(-s21[mask], height=0.02)[0]

                if len(primary_peaks) > 0:
                    peak_freq = freq[mask][primary_peaks[-1]]
                    ax.axvline(x=peak_freq, color='red', linestyle='--')

            if plotted:
                ax.set_title(f'Resonance around {res_freq * 1e-6:.6f} MHz')
                ax.set_xlabel('Frequency (Hz)')
                ax.set_ylabel('|S21| (dB)')
                ax.legend()
                ax.grid(True)
                fig.tight_layout()

                if plot:
                    figs.append(fig)

            resonances.append(res_freq)

        if plot:
            plt.show()

        return resonances, figs
    
if __name__ == '__main__':
    tile_name = 'Be231102p2_100_tones'
    #old_params = tables.File('/data/params/params_tile_Device_aSi1_Channel2_telescope_275mK.h5', 'r')

    # lo_sweep_files = [
    #     '/data/20260203/20260203_Device_aSi1_Channel2_Power_Sweep_hour15p5464_-3.h5',
    #     '/data/20260203/20260203_Device_aSi1_Channel2_Power_Sweep_hour15p5464_0.h5',
    #     '/data/20260203/20260203_Device_aSi1_Channel2_Power_Sweep_hour15p5464_3.h5',
    #     '/data/20260203/20260203_Device_aSi1_Channel2_Power_Sweep_hour15p5464_6.h5',
    #     '/data/20260203/20260203_Device_aSi1_Channel2_Power_Sweep_hour15p5464_9.h5',
    # ]
    # sweeps = [LoSweepData.from_h5(filename) for filename in lo_sweep_files]
    # sweep_data = PowerSweepData(sweeps[0].tone_list, sweeps[0].f_center, sweeps, np.array([-3, 0, 3, 6, 9]), 17, 13)

    sweep_data = TempSweepData.from_h5('/data/20260422/20260422_Be260114TR_1000_tones_1420LO_260303_Power_Sweep_hour9p7750.h5')
    #sweep_data.fit()
    Be260114Tr_tones_3 = np.array([1180667000, 1189129500, 1190174500,
    1221847000, 1232217000, 1246642000, 1254937000, 1266664500,1268920000, 1296274500, 1321964500,
    1322962000, 1340739500, 1379649500, 1395659500, 1398229500, 1427789500,
    1452124500, 1463652000, 1511963252, 1529370290, 1534427740, 1561959479,
    1570283199,1577083000, 1657808451])
    data_dict = sweep_data.build_full_vna_dataset()