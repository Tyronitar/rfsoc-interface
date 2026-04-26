from __future__ import annotations

from rfsocinterface.core.losweep import LoSweepData, ResonatorData, PowerSweepData, get_scraps_fit, simple_derivative_fits
import logging
import pdb
import datetime
import matplotlib.widgets as widgets

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

class TempSweepDataAnalyzer:
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

    def process_temperature_sweep(self,stitched_dataset, plot: bool = True, output_plot_filename: str = "TempSweep.pdf"):
        self.fit()

        sorted_idx = np.argsort(self.fp_temps)
        self.fp_temps = self.fp_temps[sorted_idx]
        f0_data = self.fit_f0[sorted_idx, :]

        n_temps, n_res = f0_data.shape
        q_data = np.zeros_like(f0_data)
        q_i_data = np.zeros_like(f0_data)
        q_c_data = np.zeros_like(f0_data)
        res_objs = [[None for _ in range(n_res)] for _ in range(n_temps)]

        figs = []

        onres_ind = np.where(self.chanmask == 1)[0]

        for i_res in onres_ind:
            initial_f0s = np.zeros_like(self.fp_temps)
            for i_p in range(len(self.fp_temps)):
                initial_result = self._fit_single_resonator(i_res, i_p, let_vary=True)
                initial_f0s[i_p] = initial_result['f0'][0]


            fig, f0s = self._plot_resonator_sweeps(i_res, stitched_dataset,initial_f0s)
            figs.append(
                fig
            ) 
            f0_data[:, i_res] = f0s
            

            for i_p in range(len(f0s)):
                tone_idx = np.argmin(abs((self.sweeps[i_p].f_center + self.sweeps[i_p].tone_list)-f0s[i_p])) 
                print(tone_idx)               
                fit_result = self._fit_single_resonator(tone_idx, i_p, plot = False)
                q_i_data[i_p,i_res] = fit_result['qi'][0]
                q_c_data[i_p,i_res] = fit_result['qc'][0]
                res_objs[i_p][i_res] = fit_result['fitted_res']


            if plot:
                figs.append(
                    self._plot_temperature_dependence(
                        i_res,
                        f0_data[:, i_res],
                        q_i_data[:, i_res],
                        q_c_data[:, i_res],
                    )
                )
        self._save_fit_results(f0_data, q_i_data, q_c_data, onres_ind)
        pdb.set_trace()
        with PdfPages(output_plot_filename) as pdf:
            for fig in figs:
                pdf.savefig(fig)

    def _save_fit_results(self, f0_data, q_i_data, q_c_data, onres_ind,
                      filename: str = "fit_results.h5"):

        q_tot_data = np.zeros_like(f0_data)
        mask = (q_i_data != 0) & (q_c_data != 0)
        q_tot_data[mask] = 1.0 / (1.0 / q_i_data[mask] + 1.0 / q_c_data[mask])

        with h5py.File(filename, "w") as f:
            f.create_dataset("fp_temps",  data=self.fp_temps)
            f.create_dataset("onres_ind", data=onres_ind)
            f.create_dataset("f0",        data=f0_data)
            f.create_dataset("qi",        data=q_i_data)
            f.create_dataset("qc",        data=q_c_data)
            f.create_dataset("q_tot",     data=q_tot_data)

            # store shape metadata as attributes for convenience
            f.attrs["n_temps"] = f0_data.shape[0]
            f.attrs["n_res"]   = f0_data.shape[1]
            f.attrs["n_onres"] = len(onres_ind)

        print(f"Fit results saved to {filename}")
    def _fit_single_resonator(self, i_res, i_p, f0_guess=None, let_vary=True, plot=False):
        sweep     = self.sweeps[i_p]
        resonator = sweep.resonator_data[i_res]
        I         = sweep.data_I[i_res]
        Q         = sweep.data_Q[i_res]

        if f0_guess is not None:
            res_obj = get_scraps_fit(
                I, Q,
                resonator.freq, resonator.tone, resonator.s21,
                initial_guesses={
                    "f0": {
                        "value": f0_guess,
                        "vary":  let_vary,
                        "min":   f0_guess * 0.98,
                        "max":   f0_guess * 1.02,
                    }
                },
            )
        else:
            res_obj = get_scraps_fit(
                I, Q,
                resonator.freq, resonator.tone, resonator.s21,
                initial_guesses={"f0": {"value": None}},
            )

        result = res_obj.lmfit_result['default']['result']
        params = result.params
        redchi = result.redchi

        f0 = params['f0'].value
        qi = params['qi'].value
        qc = params['qc'].value

        if plot:
            fig, axes = plt.subplots(1, 2, figsize=(12, 4))

            axes[0].plot(resonator.freq, resonator.s21, label="data")
            mag_db = 20*np.log10(res_obj.resultMag)
            axes[0].plot(resonator.freq, mag_db, ls="--", label=f"fit  χ²={redchi:.2f}")
            axes[0].axvline(f0, color="gray", alpha=0.6, lw=1, label=f"f0={f0:.6g}")
            axes[0].set(title=f"Res {i_res}, T={self.fp_temps[i_p]:.3g}  |S21|",
                        xlabel="Frequency", ylabel="|S21|")
            axes[0].legend(fontsize=8)

            I_fit, Q_fit = res_obj.resultI, res_obj.resultQ   # adjust attr name if needed
            axes[1].plot(I, Q, label="data")
            axes[1].plot(I_fit, Q_fit, ls="--", label="fit")
            axes[1].set(title="IQ", xlabel="I", ylabel="Q")
            axes[1].set_aspect("equal")
            axes[1].legend(fontsize=8)

            fig.suptitle(f"Resonator {i_res} | Qi={qi:.3g}  Qc={qc:.3g}  Q_tot={1/(1/qi+1/qc):.3g}",
                        fontsize=10)
            fig.tight_layout()
            plt.show()

        return {
            "f0":       np.array([f0]),
            "qi":       np.array([qi]),
            "qc":       np.array([qc]),
            "q_tot":    np.array([1 / (1/qi + 1/qc)]),
            "red_chi":  np.array([redchi]),
            "fitted_res": res_obj,
        }
    
    def _plot_resonator_sweeps(self, i_res, results, inital_f0s):
        fig, ax1 = plt.subplots(1, 1, figsize=(8, 5))
        fig.subplots_adjust(left=0.10, right=0.97, top=0.92, bottom=0.42)

        colors = plt.cm.tab10(np.linspace(0, 1, len(results["temps"])))

        f0_values = inital_f0s
        vlines = self._draw_resonator_data(ax1, i_res, colors, f0_values, results)
        text_boxes = self._add_f0_textboxes(fig, f0_values, vlines, colors, results)
        self._add_overlay_controls(fig, ax1, i_res, results)

        fig.text(0.5, 0.375,
                "Edit f₀ values below — press Enter to update the marker",
                ha="center", fontsize=9, color="gray")

        fig._resonator_textboxes = text_boxes
        fig._resonator_f0_values = f0_values
        plt.show()
        return fig, f0_values
    def _add_f0_textboxes(self, fig, f0_values, vlines, colors, results):
        temps = results["temps"]
        n = len(temps)
        box_width = 0.8 / n
        text_boxes = []

        for i_p, (f0, color) in enumerate(zip(f0_values, colors)):
            left = 0.1 + i_p * box_width
            fig.text(
                left + box_width / 2, 0.33,
                f"T={temps[i_p]:.3g}",
                ha="center", va="bottom", fontsize=8, color=color,
            )
            ax_box = fig.add_axes([left, 0.23, box_width * 0.85, 0.06])
            tb = widgets.TextBox(ax_box, "", initial=f"{f0:.6g}")
            ax_box.spines[:].set_edgecolor(color)
            ax_box.spines[:].set_linewidth(2)
            tb.on_submit(self._make_f0_callback(fig, f0_values, vlines, i_p))
            text_boxes.append(tb)

        return text_boxes

    def _draw_resonator_data(self, ax1, i_res, colors, f0_values, results):
        vlines = []
        for i_p, temp in enumerate(results["temps"]):
            ax1.plot(results["freqs"][i_p][i_res], results["s21"][i_p][ i_res], color=colors[i_p])
            vl = ax1.axvline(f0_values[i_p], color=colors[i_p], alpha=0.9, lw=2.5)
            vlines.append(vl)

        ax1.set(title=f"Resonator {i_res} S21", xlabel="Frequency", ylabel="|S21|")
        return vlines


    def _add_overlay_controls(self, fig, ax1, i_res, results):
        if i_res <= 0:
            return

        freqs = results["freqs"]
        s21   = results["s21"]
        temps = results["temps"]

        overlay_state = {}
        shown = {"min_res": i_res}

        label_ax = fig.add_axes([0.25, 0.13, 0.50, 0.05])
        label_ax.axis("off")
        label_text = label_ax.text(
            0.5, 0.5, "no overlays",
            ha="center", va="center", fontsize=9, color="gray",
            transform=label_ax.transAxes,
        )

        def refresh_label():
            label_text.set_text(
                "no overlays" if not overlay_state
                else "showing: " + ", ".join(f"res {r}" for r in sorted(overlay_state))
            )
            fig.canvas.draw_idle()

        ax_add = fig.add_axes([0.38, 0.04, 0.10, 0.07])
        btn_add = widgets.Button(ax_add, "+ add", color="0.85", hovercolor="0.70")

        def on_add(event):
            next_res = shown["min_res"] - 1
            if next_res < 0 or next_res in overlay_state:
                return
            artists = []
            line_colors = plt.cm.tab10(np.linspace(0, 1, len(temps)))
            for i_p in range(len(temps)):
                l1, = ax1.plot(
                    freqs[i_p][ next_res], s21[i_p][ next_res],
                    color=line_colors[i_p], lw=1, ls="--", alpha=0.7,
                    label=f"res {next_res}" if i_p == 0 else "_",
                )
                artists.append(l1)
            overlay_state[next_res] = artists
            shown["min_res"] = next_res
            ax1.legend(fontsize=8)
            refresh_label()

        btn_add.on_clicked(on_add)

        ax_rem = fig.add_axes([0.50, 0.04, 0.10, 0.07])
        btn_rem = widgets.Button(ax_rem, "- remove", color="0.85", hovercolor="0.70")

        def on_remove(event):
            if not overlay_state:
                return
            lowest = min(overlay_state)
            for artist in overlay_state.pop(lowest):
                artist.remove()
            shown["min_res"] = lowest + 1
            legend = ax1.get_legend()
            if legend:
                legend.remove()
            if overlay_state:
                ax1.legend(fontsize=8)
            refresh_label()

        btn_rem.on_clicked(on_remove)

        fig._overlay_btn_add = btn_add
        fig._overlay_btn_rem = btn_rem
        fig._overlay_state   = overlay_state
    def _make_f0_callback(self, fig, f0_values, vlines, idx):
        """Return a submit callback that updates f0_values[idx] and its vline."""
        def on_submit(text):
            try:
                val = float(text)
                f0_values[idx] = val
                vlines[idx].set_xdata([val, val])
                fig.canvas.draw_idle()
            except ValueError:
                pass
        return on_submit


    def _add_prev_resonator_button(self, fig, ax1, ax2, i_res, prev_colors):
        """Add a toggle button that overlays/removes the i_res-1 traces."""
        if i_res <= 0:
            return

        ax_btn = fig.add_axes([0.38, 0.08, 0.24, 0.07])
        btn = widgets.Button(
            ax_btn, f"Show resonator {i_res - 1}",
            color="0.85", hovercolor="0.70",
        )

        state = {"active": False, "artists": []}

        def on_click(event):
            if not state["active"]:
                self._show_prev_resonator(fig, ax1, ax2, i_res, prev_colors, state)
                btn.label.set_text(f"Hide resonator {i_res - 1}")
            else:
                self._hide_prev_resonator(fig, ax1, state)
                btn.label.set_text(f"Show resonator {i_res - 1}")
            state["active"] = not state["active"]
            fig.canvas.draw_idle()

        btn.on_clicked(on_click)
        fig._resonator_btn = btn


    def _show_prev_resonator(self, fig, ax1, ax2, i_res, prev_colors, state):
        """Draw i_res-1 traces as dashed overlays and record the artists."""
        for i_p in range(len(self.fp_temps)):
            sweep = self.sweeps[i_p]
            resonator_prev = sweep.resonator_data[i_res - 1]

            l1, = ax1.plot(
                resonator_prev.freq, resonator_prev.s21,
                color=prev_colors[i_p], lw=1, ls="--", alpha=0.7,
                label=f"res {i_res - 1}" if i_p == 0 else "_",
            )
            l2, = ax2.plot(
                sweep.data_I[i_res - 1], sweep.data_Q[i_res - 1],
                color=prev_colors[i_p], lw=1, ls="--", alpha=0.7,
            )
            state["artists"].extend([l1, l2])

        ax1.legend(fontsize=8)


    def _hide_prev_resonator(self, fig, ax1, state):
        """Remove all i_res-1 overlay artists."""
        for artist in state["artists"]:
            artist.remove()
        state["artists"].clear()
        legend = ax1.get_legend()
        if legend:
            legend.remove()
    
    def _plot_temperature_dependence(self, i_res, f0, qi, qc, res_objs = None, stiched_dataset = None):
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

        plt.show()
        fig.tight_layout()
        

        
        
        return fig
    
    def stitch_full_dataset(self):
        fp_temps = self.fp_temps[:]
        sorted_data_ind = np.argsort(fp_temps)
        self.fp_temps = fp_temps[sorted_data_ind]

        full_s21 = []
        full_I = []
        full_Q = []
        freqs = []

        for i_p in sorted_data_ind:
            sweep_data = self.sweeps[i_p]
            sorted_idx = np.argsort(sweep_data.tone_list + sweep_data.f_center)

            freqs.append(sweep_data.freq[sorted_idx])

            # stitch each quantity using overlapping frequency regions
            full_s21.append(self._stitch_traces(sweep_data.freq, sweep_data.s21))
            full_I.append(self._stitch_traces(sweep_data.freq, sweep_data.data_I))
            full_Q.append(self._stitch_traces(sweep_data.freq, sweep_data.data_Q))
        return {
            "temps": self.fp_temps,
            "freqs": freqs,
            "s21": full_s21,
            "I": full_I,
            "Q": full_Q,
            "sweeps": self.sweeps
        }

    def _stitch_traces(self, freq_segments, data_segments):
        n = len(freq_segments)
        offsets = np.zeros(n)

        for i in range(1, n):
            f_prev, d_prev = freq_segments[i - 1], data_segments[i - 1]
            f_curr, d_curr = freq_segments[i],     data_segments[i]

            f_overlap_lo = max(f_prev[0],  f_curr[0])
            f_overlap_hi = min(f_prev[-1], f_curr[-1])

            if f_overlap_lo >= f_overlap_hi:
                offsets[i] = offsets[i - 1]
                continue

            mask_prev = (f_prev >= f_overlap_lo) & (f_prev <= f_overlap_hi)
            mask_curr = (f_curr >= f_overlap_lo) & (f_curr <= f_overlap_hi)

            if mask_prev.sum() == 0 or mask_curr.sum() == 0:
                offsets[i] = offsets[i - 1]
                continue

            d_prev_interp = np.interp(f_curr[mask_curr], f_prev[mask_prev], d_prev[mask_prev])
            local_offset  = np.median(d_prev_interp - d_curr[mask_curr])
            offsets[i]    = offsets[i - 1] + local_offset

        # apply offsets
        corrected_segments = [d + offsets[i] for i, d in enumerate(data_segments)]
        return corrected_segments  
                

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

    data_analyzer = TempSweepDataAnalyzer.from_h5('/data/20260424/20260424_Be260114Tr_1000_tones_3_Power_Sweep_hour11p0422.h5')
    #sweep_data.fit()
    Be260114Tr_tones_3 = np.array([1180667000, 1189129500, 1190174500,
    1221847000, 1232217000, 1246642000, 1254937000, 1266664500,1268920000, 1296274500, 1321964500,
    1322962000, 1340739500, 1379649500, 1395659500, 1398229500, 1427789500,
    1452124500, 1463652000, 1511963252, 1529370290, 1534427740, 1561959479,
    1570283199,1577083000, 1657808451])
    clean_dataset = data_analyzer.stitch_full_dataset()
    data_analyzer.process_temperature_sweep(clean_dataset)
