from __future__ import annotations

import datetime
import logging
import pdb
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait, Future
from multiprocessing import Lock
from typing import Callable

import h5py
import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np
import numpy.typing as npt
import scraps as scr
import tables
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
from numpy.polynomial import Polynomial
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter

import rfsocinterface.analysis.KID_fitting_analysis.fit_mb_params as mb_params
from rfsocinterface.core.losweep import (
    LoSweepData, ResonatorData, PowerSweepData, get_scraps_fit, simple_derivative_fits
)
from rfsocinterface.core.utils import (
    BAD_RFSOC_TONE_START_INDEX, ensure_path, PERMISSIONS_USR_RW, parallel_plot
)

_logger = logging.getLogger(__name__)

NEW_LO_SWEEP_FORMAT_DATE = '20260213'


def generate_full_array_plots(file_list:list):
    
    fig1, axes = plt.subplots(4, 1, figsize=(8, 12))
    fig2, axes2 = plt.subplots(5, 1, figsize=(8, 12))
    fig3,axes3 = plt.subplots(5, 1, figsize=(8, 12))
    full_df_list = []
    for filename in file_list:
        with h5py.File(filename, "r") as f:
            
            fp_temps = f["fp_temps"][:]
            onres_ind = f["onres_ind"][:]
            f0_data = f["f0"][:]
            qi_data = f["qi"][:]
            qc_data = f["qc"][:]
            q_tot_data = f['q_tot'][:]
        df_list = []
        for i_res in onres_ind:
            f0_base = f0_data[0, i_res]
            norm_f0 = (f0_base - 1e8) / (1.6e9 - 1e8)
            norm_f0 = np.clip(norm_f0, 0, 1)
            color = plt.cm.viridis(norm_f0)
            
            df_res = (f0_data[:, i_res]-f0_data[0,i_res])/f0_data[0,i_res]
            df_list.append(df_res)
            axes[0].plot(fp_temps, df_res, color=color)
            axes[0].set(xlabel="Temperature (mK)", ylabel="Δf/f₀")

            axes[1].semilogy(fp_temps, qi_data[:, i_res], color=color)
            axes[1].set(xlabel="Temperature (mK)", ylabel="Qi")
            axes[2].semilogy(fp_temps, qc_data[:, i_res], color=color)

            axes[2].set(xlabel="Temperature (mK)", ylabel="Qc")
            axes[3].semilogy(fp_temps, q_tot_data[:, i_res], color=color)

            axes[3].set(xlabel="Temperature (mK)", ylabel="Q_tot")
            axes3[0].scatter(f0_data[:,i_res], np.log10(qi_data[:, i_res]))
            
            axes3[1].scatter(f0_data[0,i_res], df_res[-1])
            axes3[2].scatter(f0_data[0,i_res], np.log10(qc_data[0, i_res]))


        full_df_list.append(np.array(df_list).T)
    for i_p in range(1,len(fp_temps)):
        df_at_fp_temp = np.array([])
        for f in range(len(full_df_list)):
            df_at_fp_temp = np.append(df_at_fp_temp, full_df_list[f][i_p])
        axes2[i_p-1].hist(df_at_fp_temp, bins = 20)
        axes2[i_p-1].set(xlabel="Δf/f₀", ylabel="Count", title=f"Δf/f₀ distribution at {fp_temps[i_p]}")

    fig1.tight_layout()
    fig2.tight_layout()
    plt.show()

    pdb.set_trace()



class TempSweepDataAnalyzer:
    """Analyses a set of LO sweeps taken at different fridge temperatures."""

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
        self.onres_ind = np.where(self.chanmask == 1)[0]


    @property
    def chanmask(self) -> npt.NDArray:
        return self.sweeps[0].chanmask

    @property
    def combined_sweep_array(self) -> npt.NDArray:
        return np.stack([sweep.data for sweep in self.sweeps], axis=0)

    @property
    def n_tones(self) -> int:
        return 100

    @property
    def n_sweeps(self) -> int:
        return len(self.sweeps)

    @property
    def tile_names(self) -> list[str]:
        return [sweep.tile_name for sweep in self.sweeps]

    def get_fit_f0(self) -> npt.NDArray:
        self.fit_f0 = np.stack([sweep.fit_f0 for sweep in self.sweeps], axis=0)
        return self.fit_f0

    def fit(self):
        for sweep in self.sweeps:
            sweep.fit()
        self.get_fit_f0()

    @ensure_path(1)
    def saveh5(self, fname: Path):
        path = fname.with_suffix('.h5')
        path.touch(PERMISSIONS_USR_RW)
        with tables.File(path, 'w') as fh:
            fh.create_array('/', 'sweeps',          obj=self.combined_sweep_array)
            fh.create_array('/', 'lo_freq',         obj=self.f_center)
            fh.create_array('/', 'baseband_freqs',  obj=self.tone_list - self.f_center)
            fh.create_array('/', 'chanmask',        obj=self.chanmask)
            fh.create_array('/', 'fp_temps',        obj=self.fp_temps)
            fh.create_array('/', 'rfin',            obj=self.rfin)
            fh.create_array('/', 'rfout',           obj=self.rfout)
            fh.create_array('/', 'fit_f0',          obj=self.fit_f0)
            fh.create_array('/', 'max_readout_power', obj=self.max_readout_power)
            fh.root._v_attrs.tile_names = self.tile_names
        _logger.info(f'TempSweepData saved to {fname}')

    @classmethod
    @ensure_path(1)
    def from_h5(cls, fname: Path) -> TempSweepDataAnalyzer:
        with tables.File(fname, 'r') as fh:
            old = (
                datetime.datetime.fromtimestamp(fname.stat().st_mtime)
                < datetime.datetime.strptime(NEW_LO_SWEEP_FORMAT_DATE, '%Y%m%d')
            )
            if old:
                _logger.warning(f'{fname} predates {NEW_LO_SWEEP_FORMAT_DATE}; loading with backwards compatibility.')
                root = fh.root.global_data
            else:
                root = fh.root

            tone_list   = root.baseband_freqs[:]
            f_center    = root.lo_freq[()]
            rfin        = root.rfin[()]
            rfout       = root.rfout[()]
            chanmask    = root.chanmask[:]
            fp_temps    = root.fp_temps[:]
            sweep_data  = root.sweeps[:]
            fit_f0      = root.fit_f0[:]
            max_readout_power = root.max_readout_power[:]
            tile_names  = fh.root._v_attrs.tile_names

            sweeps = []
            for this_fit_f0, arr, tile_name in zip(fit_f0, sweep_data, tile_names):
                sweep = LoSweepData(tone_list, f_center, arr, chanmask, tile_name)
                sweep.fit_f0[:] = this_fit_f0
                sweeps.append(sweep)

        obj = cls(tone_list, f_center, sweeps, fp_temps, rfin, rfout)
        obj.get_fit_f0()
        obj.max_readout_power = max_readout_power
        return obj

    def process_temperature_sweep(
        self,
        stitched_dataset,
        plot: bool = True,
        output_plot_filename: str = "TempSweep.pdf",
        fit_results_h5: str | None = None,
    ):
        """
        Fit resonators across all temperatures, show interactive GUIs for f0
        adjustment, then save results and plots.

        Parameters
        ----------
        stitched_dataset  : dict returned by stitch_full_dataset()
        plot              : whether to append temperature-dependence plots to the PDF
        output_plot_filename : path for the output PDF
        fit_results_h5    : optional path to a previously saved fit_results.h5;
                            if given, those f0/qi/qc values are used as starting
                            points and any resonance not yet fitted is expanded
                            in the GUI
        """
        self.fit()

        sorted_idx     = np.argsort(self.fp_temps)
        self.fp_temps  = self.fp_temps[sorted_idx]
        f0_data        = self.fit_f0[sorted_idx, :]

        n_temps, n_res = f0_data.shape
        q_i_data       = np.zeros_like(f0_data)
        q_c_data       = np.zeros_like(f0_data)
        res_objs       = [[None] * n_res for _ in range(n_temps)]
        redchi_data    = np.zeros_like(f0_data)
        stderr_f0      = np.zeros_like(f0_data)
        stderr_qi      = np.zeros_like(f0_data)
        stderr_qc      = np.zeros_like(f0_data)

        # load previous results if supplied

        figs      = []
        onres_ind = np.where(self.chanmask == 1)[0]

        self.onres_ind = onres_ind
        prev_results = self._load_fit_results_h5(fit_results_h5) if fit_results_h5 else None

        for i_res in onres_ind:
            initial_f0s = self._get_initial_f0s(i_res, stitched_dataset,prev_results, fit_prev_datasets=12)
            fig, f0s    = self._plot_resonator_sweeps(i_res, stitched_dataset, initial_f0s)
            figs.append(fig)
            f0_data[:, i_res] = f0s

            for i_p, f0 in enumerate(f0s):
                tone_idx = np.argmin(
                    np.abs((self.sweeps[i_p].tone_list) - f0)
                )
                try:
                    fit_result = self._fit_single_resonator(
                        tone_idx, i_p, f0_guess=f0, freq_window=f0 * 2e-3
                    )
                    q_i_data[i_p, i_res]    = fit_result['qi'][0]
                    q_c_data[i_p, i_res]    = fit_result['qc'][0]
                    f0_data[i_p, i_res]     = fit_result['f0'][0]
                    redchi_data[i_p, i_res] = fit_result['red_chi'][0]
                    stderr_f0[i_p, i_res]   = fit_result['f0_stderr'][0]
                    stderr_qi[i_p, i_res]   = fit_result['qi_stderr'][0]
                    stderr_qc[i_p, i_res]   = fit_result['qc_stderr'][0]
                    res_objs[i_p][i_res]    = fit_result['fitted_res']
                except Exception as e:
                    _logger.warning(
                        f"Fit failed for resonator {i_res}, temp index {i_p} "
                        f"(T={self.fp_temps[i_p]:.3g}): {e}"
                    )
                    continue
                print(tone_idx)
            if plot:
                figs.append(self._plot_temperature_dependence(
                    i_res,
                    f0_data[:, i_res],
                    q_i_data[:, i_res],
                    q_c_data[:, i_res],
                ))

        fig1,fig2 = self._generate_summary_plots(self.fp_temps, f0_data, q_i_data, q_c_data)
        figs.append(fig1)
        figs.append(fig2)
        pdb.set_trace()
        output_plot_filename = self.sweeps[0].tile_name + output_plot_filename
        with PdfPages(output_plot_filename) as pdf:
            for fig in figs:
                pdf.savefig(fig)
        self._save_fit_results(f0_data, q_i_data, q_c_data, onres_ind,redchi_data=redchi_data, stderr_f0=stderr_f0, stderr_qi=stderr_qi, stderr_qc=stderr_qc, filename=self.sweeps[0].tile_name + "_fit_results.h5")


    def _get_initial_f0s(self, i_res: int, stitched_dataset: dict,   prev_results: dict | None, fit_prev_datasets:int = 1,) -> npt.NDArray:
        """
        Return initial f0 guesses for resonator i_res.
        Uses previous h5 results when available, otherwise runs a quick fit.
        """
        if prev_results is not None and i_res < prev_results["f0"].shape[1]:
            f0s = prev_results["f0"][:, i_res]
            print(f0s)
            if np.any(f0s != 0):
                return f0s
        f0s = np.zeros_like(self.fp_temps)
        for i_p,temp in enumerate(self.fp_temps):
            freq = stitched_dataset["freqs"][i_p][i_res]
            s21  = stitched_dataset["s21"][i_p][i_res]
            
            if fit_prev_datasets > 0:
                
                res_indices = range(
                    max(0, i_res - fit_prev_datasets), i_res
                )
                for r in res_indices:
                    freq = np.append( stitched_dataset["freqs"][i_p][r],freq)
                    s21 = np.append( stitched_dataset["s21"][i_p][r],s21)

            center = freq[np.argmin(s21)]
            f0s[i_p] = center
        return f0s

    def _save_fit_results(
        self,
        f0_data: npt.NDArray,
        q_i_data: npt.NDArray,
        q_c_data: npt.NDArray,
        onres_ind: npt.NDArray,
        redchi_data: npt.NDArray | None = None,
        stderr_f0: npt.NDArray | None = None,
        stderr_qi: npt.NDArray | None = None,
        stderr_qc: npt.NDArray | None = None,
        filename: str = "fit_results.h5",
    ):
        n_temps = len(self.fp_temps)
        n_res   = len(onres_ind)

        load_name  = self.sweeps[0].tile_name
        power_name = "-100dB"

        with h5py.File(filename, "w") as f:
            load_grp = f.create_group(load_name)

            for tt, temp in enumerate(self.fp_temps):
                temp_key  = f"FPtemp_{tt:04d}"
                temp_grp  = load_grp.create_group(temp_key)
                temp_grp.attrs["FPtemp"] = float(temp)

                split_grp = temp_grp.create_group(f"{power_name}/split")

                for rr, i_res in enumerate(onres_ind):
                    res_key  = f"res_{rr:04d}"
                    fit_grp  = split_grp.create_group(f"{res_key}/fit")

                    ds_f0 = fit_grp.create_dataset("f0", data=float(f0_data[tt, i_res]))
                    ds_f0.attrs["stderr"] = float(stderr_f0[tt, i_res])

                    ds_qi = fit_grp.create_dataset("qi", data=float(q_i_data[tt, i_res]))
                    ds_qi.attrs["stderr"] = float(stderr_qi[tt, i_res])

                    ds_qc = fit_grp.create_dataset("qc", data=float(q_c_data[tt, i_res]))
                    ds_qc.attrs["stderr"] = float(stderr_qc[tt, i_res])

                    fit_grp.attrs["redchi"] = float(redchi_data[tt, i_res])
            pdb.set_trace()
        _logger.info(f"Fit results saved to {filename} (extract_dark_data compatible)")

    def _load_fit_results_h5(self, filename: str) -> dict:
        """Load a previously saved fit_results.h5 and return as a dict."""
        with h5py.File(filename, "r") as f:
            load_name = list(f.keys())[0]
            load_grp  = f[load_name]

            temp_keys = sorted(load_grp.keys())
            n_temps   = len(temp_keys)

            # infer resonators from first temperature
            first_temp = load_grp[temp_keys[0]]
            split_grp  = first_temp["-100dB/split"]
            res_keys   = sorted(split_grp.keys())
            n_res      = len(res_keys)
            n_tones    = len(self.tone_list)

            fp_temps = np.zeros(n_temps)
            f0 = np.zeros((n_temps, n_tones))
            qi = np.zeros((n_temps, n_tones))
            qc = np.zeros((n_temps, n_tones))

            for tt, temp_key in enumerate(temp_keys):
                temp_grp = load_grp[temp_key]
                fp_temps[tt] = temp_grp.attrs["FPtemp"]

                split_grp = temp_grp["-100dB/split"]

                for ii, res_key in enumerate(res_keys):
                    fit_grp = split_grp[f"{res_key}/fit"]
                    idx = self.onres_ind[ii]

                    f0[tt, idx] = fit_grp["f0"][()]
                    qi[tt, idx] = fit_grp["qi"][()]
                    qc[tt, idx] = fit_grp["qc"][()]
            return {
                "fp_temps":  fp_temps,
                "onres_ind": self.onres_ind,
                "f0":        f0,
                "qi":        qi,
                "qc":        qc,
            }

    def _fit_single_resonator(
    self,
    i_res: int,
    i_p: int,
    f0_guess: float | None = None,
    let_vary: bool = True,
    plot: bool = False,
    freq_window: float = 0.5e6,
    decimate: int = 1,
    fit_previous_resonators: int = 0,
    ) -> dict:
        sweep     = self.sweeps[i_p]
        resonator = sweep.resonator_data[i_res]
        I         = sweep.data_I[i_res]
        Q         = sweep.data_Q[i_res]
        freq      = resonator.freq
        tone = resonator.tone
        s21 = resonator.s21

        # --- restrict to a window around the resonator ---
        if freq_window is not None:
            center = f0_guess if f0_guess is not None else freq[np.argmin(resonator.s21)]
            mask   = np.abs(freq - center) <= freq_window / 2
            freq   = freq[mask]
            I      = I[mask]
            Q      = Q[mask]
            s21    = resonator.s21[mask]

        if decimate > 1:
            freq = freq[::decimate]
            I    = I[::decimate]
            Q    = Q[::decimate]
            s21  = s21[::decimate]

       
        res_obj = get_scraps_fit(
            I, Q, freq, tone, s21,
            initial_guesses={"f0": {
                "value": f0_guess,
                "vary":  let_vary,
                "min":   f0_guess*(1-1e-4),
                "max":   f0_guess*(1+1e-4),
            }},
        )
        print("Difference in f0", res_obj.lmfit_result['default']['result'].params['f0'].value - f0_guess)

        result = res_obj.lmfit_result['default']['result']
        params = result.params
        redchi = result.redchi
        f0     = params['f0'].value
        f0_stderr = params['f0'].stderr
        qi     = params['qi'].value
        qi_stderr = params['qi'].stderr
        qc     = params['qc'].value
        qc_stderr = params['qc'].stderr
        if plot:
            self._plot_single_fit(i_res, i_p, resonator, I, Q, res_obj, f0, qi, qc, redchi)

        return {
            "f0":         np.array([f0]),
            "f0_stderr":  np.array([f0_stderr]),
            "qi":         np.array([qi]),
            "qi_stderr":  np.array([qi_stderr]),
            "qc":         np.array([qc]),
            "qc_stderr":  np.array([qc_stderr]),
            "q_tot":      np.array([1 / (1/qi + 1/qc)]),
            "red_chi":    np.array([redchi]),
            "fitted_res": res_obj,
        }

    def _plot_single_fit(self, i_res, i_p, resonator, I, Q, res_obj, f0, qi, qc, redchi):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        mag_db = 20 * np.log10(res_obj.resultMag)

        axes[0].plot(resonator.freq, resonator.s21, label="data")
        axes[0].plot(resonator.freq, mag_db, ls="--", label=f"fit  χ²={redchi:.2f}")
        axes[0].axvline(f0, color="gray", alpha=0.6, lw=1, label=f"f0={f0:.6g}")
        axes[0].set(title=f"Res {i_res}, T={self.fp_temps[i_p]:.3g}  |S21|",
                    xlabel="Frequency", ylabel="|S21|")
        axes[0].legend(fontsize=8)

        axes[1].plot(I, Q, label="data")
        axes[1].plot(res_obj.resultI, res_obj.resultQ, ls="--", label="fit")
        axes[1].set(title="IQ", xlabel="I", ylabel="Q")
        axes[1].set_aspect("equal")
        axes[1].legend(fontsize=8)

        fig.suptitle(
            f"Resonator {i_res} | Qi={qi:.3g}  Qc={qc:.3g}  Q_tot={1/(1/qi+1/qc):.3g}",
            fontsize=10,
        )
        fig.tight_layout()
        plt.show()

    def _plot_resonator_sweeps(self, i_res, results, initial_f0s):
        fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
        fig.subplots_adjust(left=0.10, right=0.97, top=0.92, bottom=0.42)

        colors    = plt.cm.Spectral(np.linspace(0, 1, len(results["temps"])))
        f0_values = list(initial_f0s)
        active    = {"idx": None}
        clipboard = {"x": None}

        vlines     = self._draw_resonator_data(ax_mag, ax_phase, i_res, colors, f0_values, results)
        text_boxes = self._add_f0_textboxes(fig, f0_values, vlines, colors, results, active)

        self._add_axes_click(fig, ax_mag, ax_phase, f0_values, vlines, text_boxes, active, clipboard)
        self._add_key_handler(fig, f0_values, vlines, text_boxes, active, clipboard)
        self._add_overlay_controls(fig, ax_mag, ax_phase, i_res, results)

        fig.text(
            0.5, 0.395,
            "Click plot → copies x  |  Click textbox to select  |  Ctrl+V pastes x into selected textbox",
            ha="center", fontsize=9, color="gray",
        )

        fig._resonator_textboxes = text_boxes
        fig._resonator_f0_values = f0_values
        #plt.show()
        plt.close()
        return fig, f0_values

    def _draw_resonator_data(self, ax_mag, ax_phase, i_res, colors, f0_values, results):
        vlines = []
        for i_p, temp in enumerate(f0_values):
            freq  = results["freqs"][i_p][i_res]
            I     = results["I"][i_p][i_res]
            Q     = results["Q"][i_p][i_res]
            s21   = results["s21"][i_p][i_res]
            phase = np.angle(I + 1j * Q, deg=True)

            ax_mag.plot(freq, s21 - np.mean(s21, keepdims=True), color=colors[i_p])
            vl1 = ax_mag.axvline(f0_values[i_p],   color=colors[i_p], alpha=0.9, lw=2.5)
            vl2 = ax_phase.axvline(f0_values[i_p], color=colors[i_p], alpha=0.9, lw=2.5)
            vlines.append((vl1, vl2))

        ax_mag.set(title=f"Resonator {i_res}", ylabel="|S21|")
        ax_phase.set(xlabel="Frequency (Hz)", ylabel="Phase (deg)")
        return vlines

    def _add_f0_textboxes(self, fig, f0_values, vlines, colors, results, active):
        temps      = results["temps"]
        n          = len(temps)
        box_width  = 0.8 / n
        text_boxes = []

        for i_p, (f0, color) in enumerate(zip(f0_values, colors)):
            left = 0.1 + i_p * box_width
            fig.text(
                left + box_width / 2, 0.345,
                f"T={temps[i_p]:.3g}",
                ha="center", va="bottom", fontsize=8, color=color,
            )
            ax_box = fig.add_axes([left, 0.245, box_width * 0.85, 0.06])
            tb = widgets.TextBox(ax_box, "", initial=f"{f0:.6g}")
            ax_box.spines[:].set_edgecolor(color)
            ax_box.spines[:].set_linewidth(2)
            tb.on_submit(self._make_f0_callback(fig, f0_values, vlines, i_p, active, text_boxes))
            text_boxes.append(tb)

        def on_textbox_click(event):
            if event.x is None or event.y is None:
                return
            for idx, tb in enumerate(text_boxes):
                if tb.ax.get_window_extent().contains(event.x, event.y):
                    active["idx"] = idx
                    for j, other_tb in enumerate(text_boxes):
                        other_tb.ax.spines[:].set_linewidth(3.5 if j == idx else 2)
                    fig.canvas.draw_idle()
                    return

        fig._textbox_focus_cid = fig.canvas.mpl_connect("button_press_event", on_textbox_click)
        return text_boxes

    def _make_f0_callback(self, fig, f0_values, vlines, idx, active, text_boxes):
        def on_submit(text):
            try:
                val = float(text)
                f0_values[idx] = val
                vl1, vl2 = vlines[idx]
                vl1.set_xdata([val, val])
                vl2.set_xdata([val, val])
                active["idx"] = None
                for tb in text_boxes:
                    tb.ax.spines[:].set_linewidth(2)
                fig.canvas.draw_idle()
            except ValueError:
                pass
        return on_submit

    def _add_axes_click(self, fig, ax_mag, ax_phase, f0_values, vlines, text_boxes, active, clipboard):
        def on_axes_click(event):
            if event.inaxes not in (ax_mag, ax_phase) or event.xdata is None:
                return
            clipboard["x"] = event.xdata

        fig._axes_click_cid = fig.canvas.mpl_connect("button_press_event", on_axes_click)

    def _add_key_handler(self, fig, f0_values, vlines, text_boxes, active, clipboard):
        """
        Ctrl+V: paste clipboard["x"] into the currently active textbox,
        updating the vline and f0_values entry immediately.
        """
        def on_key_press(event):
            if event.key not in ('ctrl+v', 'control+v'):
                return
            if active["idx"] is None:
                return
            if clipboard["x"] is None:
                return

            idx            = active["idx"]
            val            = clipboard["x"]
            f0_values[idx] = val
            vl1, vl2       = vlines[idx]
            vl1.set_xdata([val, val])
            vl2.set_xdata([val, val])
            text_boxes[idx].set_val(f"{val:.6g}")
            fig.canvas.draw_idle()

        fig._key_press_cid = fig.canvas.mpl_connect("key_press_event", on_key_press)

    def _add_overlay_controls(self, fig, ax_mag, ax_phase, i_res, results):
        freqs   = results["freqs"]
        s21     = results["s21"]
        I_data  = results["I"]
        Q_data  = results["Q"]
        temps   = results["temps"]
        n_res   = len(freqs[0])

        overlay_state = {}
        shown = {"min_res": i_res, "max_res": i_res}

        label_ax = fig.add_axes([0.20, 0.145, 0.60, 0.05])
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

        def draw_overlay(res_idx):
            if res_idx < 0 or res_idx >= n_res or res_idx in overlay_state or res_idx == i_res:
                return
            artists     = []
            line_colors = plt.cm.Spectral(np.linspace(0, 1, len(temps)))
            for i_p in range(len(temps)):
                phase = np.angle(I_data[i_p][res_idx] + 1j * Q_data[i_p][res_idx], deg=True)
                l1, = ax_mag.plot(
                    freqs[i_p][res_idx],
                    s21[i_p][res_idx] - np.mean(s21[i_p][i_res], keepdims=True),
                    color=line_colors[i_p], lw=1, ls="--", alpha=0.7,
                    label=f"res {res_idx}" if i_p == 0 else "_",
                )
                l2, = ax_phase.plot(
                    freqs[i_p][res_idx][0], phase[0],
                    color=line_colors[i_p], lw=1, ls="--", alpha=0.7,
                )
                artists.extend([l1, l2])
            overlay_state[res_idx] = artists
            #ax_mag.legend(fontsize=7, loc="upper right")
            refresh_label()

        def remove_overlay(res_idx):
            if res_idx not in overlay_state:
                return
            for artist in overlay_state.pop(res_idx):
                artist.remove()
            legend = ax_mag.get_legend()
            if legend:
                legend.remove()
            if overlay_state:
                ax_mag.legend(fontsize=7, loc="upper right")
            refresh_label()

        ax_prev_add = fig.add_axes([0.20, 0.055, 0.12, 0.07])
        btn_prev_add = widgets.Button(ax_prev_add, "< add prev", color="0.85", hovercolor="0.70")

        def on_prev_add(event):
            next_res = shown["min_res"] - 1
            draw_overlay(next_res)
            if next_res in overlay_state:
                shown["min_res"] = next_res
            fig.canvas.draw_idle()

        btn_prev_add.on_clicked(on_prev_add)

        ax_prev_rem = fig.add_axes([0.34, 0.055, 0.12, 0.07])
        btn_prev_rem = widgets.Button(ax_prev_rem, "< rem prev", color="0.85", hovercolor="0.70")

        def on_prev_rem(event):
            if not overlay_state:
                return
            prev_overlays = [r for r in overlay_state if r < i_res]
            if not prev_overlays:
                return
            lowest = min(prev_overlays)
            remove_overlay(lowest)
            shown["min_res"] = lowest + 1
            fig.canvas.draw_idle()

        btn_prev_rem.on_clicked(on_prev_rem)

        ax_next_add = fig.add_axes([0.50, 0.055, 0.12, 0.07])
        btn_next_add = widgets.Button(ax_next_add, "add next >", color="0.85", hovercolor="0.70")

        def on_next_add(event):
            next_res = shown["max_res"] + 1
            draw_overlay(next_res)
            if next_res in overlay_state:
                shown["max_res"] = next_res
            fig.canvas.draw_idle()

        btn_next_add.on_clicked(on_next_add)

        ax_next_rem = fig.add_axes([0.64, 0.055, 0.12, 0.07])
        btn_next_rem = widgets.Button(ax_next_rem, "rem next >", color="0.85", hovercolor="0.70")

        def on_next_rem(event):
            if not overlay_state:
                return
            next_overlays = [r for r in overlay_state if r > i_res]
            if not next_overlays:
                return
            highest = max(next_overlays)
            remove_overlay(highest)
            shown["max_res"] = highest - 1
            fig.canvas.draw_idle()

        btn_next_rem.on_clicked(on_next_rem)

        fig._overlay_btn_prev_add = btn_prev_add
        fig._overlay_btn_prev_rem = btn_prev_rem
        fig._overlay_btn_next_add = btn_next_add
        fig._overlay_btn_next_rem = btn_next_rem
        fig._overlay_state        = overlay_state

    def _plot_temperature_dependence(self, i_res, f0, qi, qc, res_objs=None, stitched_dataset=None):
        temps = self.fp_temps
        df    = (f0 - f0[0]) / f0[0]

        fig, axes = plt.subplots(3, 1, figsize=(8, 12))
        fig.suptitle(f"Resonator {i_res} temperature dependence", fontsize=12)

        axes[0].plot(temps, df, 'o-')
        axes[0].set(xlabel="Temperature (mK)", ylabel="Δf/f₀")

        axes[1].plot(temps, qi, 'o-')
        axes[1].set(xlabel="Temperature (mK)", ylabel="Qi")

        axes[2].plot(temps, qc, 'o-')
        axes[2].set(xlabel="Temperature (mK)", ylabel="Qc")
        fig.tight_layout()
        plt.close()
        return fig

    def _generate_summary_plots(self, fp_temps, f0_data, qi_data, qc_data):
        fig1, axes = plt.subplots(3, 1, figsize=(8, 12))
        for i_res in self.onres_ind:
            df_res = (f0_data[:, i_res] - f0_data[0, i_res]) / f0_data[0, i_res]
            axes[0].plot(fp_temps, df_res)
            axes[0].set(xlabel="Temperature (mK)", ylabel="Δf/f₀")
            axes[1].semilogy(fp_temps, qi_data[:, i_res])
            axes[1].set(xlabel="Temperature (mK)", ylabel="Qi")
            axes[2].semilogy(fp_temps, qc_data[:, i_res])
            axes[2].set(xlabel="Temperature (mK)", ylabel="Qc")
            fig1.tight_layout()

        fig2, axes2 = plt.subplots(len(fp_temps), 1, figsize=(8, 12))
        for i_p, temp in enumerate(fp_temps[0:-1]):
            axes2[i_p].hist((f0_data[i_p, self.onres_ind] - f0_data[0, self.onres_ind]) / f0_data[0, self.onres_ind])
            axes2[i_p].set(title=f"Δf/f₀ at {temp}")

        fig2.tight_layout()
        plt.show()
        return fig1, fig2

    def stitch_full_dataset(self) -> dict:
        fp_temps        = self.fp_temps[:]
        sorted_data_ind = np.argsort(fp_temps)
        self.fp_temps   = fp_temps[sorted_data_ind]

        freqs    = []
        full_s21 = []
        full_I   = []
        full_Q   = []

        for i_p in sorted_data_ind:
            sweep_data = self.sweeps[i_p]
            sorted_idx = np.argsort(sweep_data.tone_list + sweep_data.f_center),
            freqs.append(sweep_data.freq[sorted_idx])
            full_s21.append(self._stitch_traces(sweep_data.freq, sweep_data.s21))
            full_I.append(self._stitch_traces(sweep_data.freq, sweep_data.data_I))
            full_Q.append(self._stitch_traces(sweep_data.freq, sweep_data.data_Q))

        return {
            "temps":  self.fp_temps,
            "freqs":  freqs,
            "s21":    full_s21,
            "I":      full_I,
            "Q":      full_Q,
            "sweeps": self.sweeps,
        }

    def _stitch_traces(self, freq_segments, data_segments) -> list:
        n       = len(freq_segments)
        offsets = np.zeros(n)

        for i in range(1, n):
            f_prev, d_prev = freq_segments[i - 1], data_segments[i - 1]
            f_curr, d_curr = freq_segments[i],     data_segments[i]

            f_lo = max(f_prev[0],  f_curr[0])
            f_hi = min(f_prev[-1], f_curr[-1])

            if f_lo >= f_hi:
                offsets[i] = offsets[i - 1]
                continue

            mask_prev = (f_prev >= f_lo) & (f_prev <= f_hi)
            mask_curr = (f_curr >= f_lo) & (f_curr <= f_hi)

            if mask_prev.sum() == 0 or mask_curr.sum() == 0:
                offsets[i] = offsets[i - 1]
                continue

            d_interp   = np.interp(f_curr[mask_curr], f_prev[mask_prev], d_prev[mask_prev])
            offsets[i] = offsets[i - 1] + np.median(d_interp - d_curr[mask_curr])

        return [d + offsets[i] for i, d in enumerate(data_segments)]

    def plot_vna_temp_sweep(self, dataset, expected_resonances_at_base_temp, plot=True):
        temps    = dataset["temps"]
        freqs    = dataset["freqs"]
        full_s21 = dataset["s21"]
        figs     = []

        freq_half_span = 8e6

        for res_freq in expected_resonances_at_base_temp:
            fig, ax = plt.subplots(figsize=(8, 5))
            plotted = False

            for i_p in range(len(freqs)):
                freq = freqs[i_p]
                s21  = full_s21[i_p]
                mask = np.where(
                    (freq > res_freq - freq_half_span) &
                    (freq < res_freq + 0.1 * freq_half_span)
                )
                if not np.any(mask):
                    continue

                plotted = True
                ax.plot(freq[mask], s21[mask] - np.mean(s21[mask]),
                        label=f'{temps[i_p]:.1f} mK')

                peaks = find_peaks(-s21[mask], height=0.02)[0]
                if len(peaks) > 0:
                    ax.axvline(x=freq[mask][peaks[-1]], color='red', ls='--')

            if plotted:
                ax.set(
                    title=f'Resonance around {res_freq * 1e-6:.6f} MHz',
                    xlabel='Frequency (Hz)',
                    ylabel='|S21| (dB)',
                )
                ax.legend()
                ax.grid(True)
                fig.tight_layout()
                if plot:
                    figs.append(fig)
                plt.show()

        return figs


if __name__ == '__main__':
    data_analyzer = TempSweepDataAnalyzer.from_h5(
        '/data/20260515/20260515_Be260114BL_1000_tones_3_Power_Sweep_hour17p1672.h5'
    )
    clean_dataset = data_analyzer.stitch_full_dataset()
    pdb.set_trace()
    data_analyzer.process_temperature_sweep(
        clean_dataset,
        fit_results_h5='Be260114Tr_1000_tones_2_fit_results.h5'
    )