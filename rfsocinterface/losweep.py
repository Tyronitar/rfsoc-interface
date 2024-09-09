from __future__ import annotations
import os
from pathlib import Path

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from onr_fit_lo_sweeps import simple_derivative_fits
from onrkidpy import get_chanmask

SUBPLOT_SIZE = 2/3

class ResonatorData:

    def __init__(self, data: LoSweep, idx: int):
        self.data = data
        self.idx = idx
        self.flagged = False
    
    def plot(self, ax: plt.Axes | None=None) -> Figure | None:
        return_fig = False
        if ax is None:
            fig = plt.figure(figsize=(8, 5))
            ax = plt.subplot()
            return_fig = True
            ax.set_title(f'Transmission Magnitude of Resonator #{self.idx}')
            ax.set_xlabel('Frequency (MHz)')
            ax.set_ylabel(r'$|S_{21}|$')
        else:
            ax.set_yticks([])
            ax.set_xticks([])

        ax.plot(self.freq, self.s21)
        ax.axvline(x=self.fit_f0, color='r')

        new_span = self.span * self.freq_ratio
        ax.set_xlim(np.mean(self.freq)-new_span/2., np.mean(self.freq+new_span/2.))
        if self.is_onres:
            ax.legend(
                ["{:d}".format(self.idx)],
                fontsize=6,
                loc = 3,
                frameon=False,
                handlelength=0,
                bbox_to_anchor=(-0.2,-0.15)
            )
            if self.flagged:
                ax.set_facecolor('yellow')
        else:
            ax.legend(
                ["{:d}".format(self.idx) + ', dS21=' + "{:4.1f}".format(np.max(self.s21)-np.min(self.s21))],
                fontsize=6,
                loc = 3,
                frameon=False,
                handlelength=0,
                bbox_to_anchor=(-0.2,-0.15)
            )
            ax.set_facecolor('orange')
        
        if return_fig:
            return fig

    @property
    def tone(self) -> float:
        return self.data.tone_list[self.idx]
    
    @property
    def freq(self) -> npt.NDArray:
        return self.data.freq[self.idx, :]

    @property
    def s21(self) -> npt.NDArray:
        return self.data.s21[self.idx, :]

    @property
    def difference(self) -> float:
        return (self.data.fit_f0[self.idx] - self.data.tone_list[self.idx]) * 1e-3
    
    @property
    def is_onres(self) -> bool:
        return self.data.chanmask[self.idx] == 1
    
    @property
    def freq_ratio(self) -> float:
        return self.tone / self.data.tone_list.max()
    
    @property
    def fit_f0(self) -> float:
        return self.data.fit_f0[self.idx]
    
    @property
    def fit_qi(self) -> float:
        return self.data.fit_qi[self.idx]
    
    @property
    def fit_qc(self) -> float:
        return self.data.fit_qc[self.idx]
    
    @property
    def span(self) -> float:
        return np.ptp(self.freq)
    
    def fit(self, df: float) -> tuple[float, float, float]:
        fit_f0 = simple_derivative_fits(df, self.freq, self.tone, self.s21)
        fit_qi = 0.
        fit_qc = 0.

        return fit_f0, fit_qi, fit_qc
    
class LoSweep:
    def __init__(self, tone_list: npt.NDArray, sweep_file: str, chanmask_file: str) -> None:
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
        return (self.fit_f0 - self.tone_list) * 1e-3

    @property
    def nchan(self) -> int:
        return np.size(self.chanmask)
    
    @property
    def offres_ind(self) -> npt.NDArray:
        return np.argwhere(self.chanmask == 0)
    
    @property
    def flagged(self) -> npt.NDArray:
        return np.argwhere(self.difference > self.diff_to_flag)
    
    def fit(self, do_print=False):
        df = self.freq[0, 1] - self.freq[0, 0]

        for i_chan in np.argwhere(self.chanmask == 1):
            # pull in the sweep data for this tone
            i_chan = i_chan[0]
            resonator = self.resonator_data[i_chan]

            # call the resonator fitter
            f0, qc, qi = resonator.fit(df)
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

    def plot(self, fig_width: float=18):
        # Setup for plots 
        ncols = fig_width
        nrows = int(np.ceil(self.nchan/ ncols))
        print(nrows, ncols)

        fig = plt.figure(figsize=(fig_width, nrows))
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
    flist = np.load(filename)
    tones = lo_freq * 1.0e6 + flist
    return tones

def fit_lo_sweep(
    tone_list: npt.NDArray,
    sweep_file: str,
    chanmask_file: str,
    Qc_array=0,
    do_print=False,
):
    #path, center_freq, pdfFlag = False, quickPlot = False, Qc_array = 0, printFlag = True, FlagBad = False, MaxGoodInd = 0, DerivFit = False):

    lo_data = np.load(sweep_file)
    freq = lo_data[0,:,:]
    s21 = 10. * np.log10(np.abs(lo_data[1,:,:]))

    #initialize variables for fitting
    chanmask = get_chanmask(chanmask_file)
    n_chan = np.size(chanmask)
    fit_f0 = np.zeros(n_chan)
    fit_qi = np.zeros(n_chan)
    fit_qc = np.zeros(n_chan)
    difference = np.zeros(n_chan)
    offres_ind = np.argwhere(chanmask == 0)
    fit_f0[offres_ind] = tone_list[offres_ind]

    # Setup for plots if we'll be making a quickplot
    nrows = int(np.min([np.ceil(np.sqrt(np.size(np.where(np.logical_or(chanmask == 1, chanmask == 0))))*18./30.),12]))
    ncols = int(np.min([np.ceil(np.size(np.where(np.logical_or(chanmask == 1, chanmask == 0))) / float(nrows)),18]))
    total_rows = int(np.ceil(n_chan / ncols))
    counter = 0

    diff_to_flag = (3./200.) * tone_list * 1e-6

    # loop over resonators to perform fit
    df = freq[0,1]-freq[0,0]
    for i_chan in np.argwhere(chanmask == 1):
        # pull in the sweep data for this tone
        i_chan = i_chan[0]

        # call the resonator fitter
        f0 = simple_derivative_fits(df, freq[i_chan,:], tone_list[i_chan], s21[i_chan,:])
        qc = 0.
        qi = 0.

        #store some of the results
        fit_f0[i_chan] = f0
        fit_qc[i_chan] = qc
        fit_qi[i_chan] = qi
        difference[i_chan] = (fit_f0[i_chan] - tone_list[i_chan]) * 1.e-3

        if np.abs(difference[i_chan]) > diff_to_flag[i_chan]:
            if do_print:
                print("tone index =", "{:4d}".format(i_chan), \
                        "|| new tone =", "{:9.5f}".format(fit_f0[i_chan]*1.e-6), \
                        "|| old tone =", "{:9.5f}".format(tone_list[i_chan]*1.e-6), \
                        "|| difference (kHz) =", "{:+5.3f}".format(difference[i_chan]))
                

    return fit_f0, fit_qi, fit_qc

def plot_lo_fit(
    tone_list: npt.NDArray,
    sweep_file: str,
    chanmask_file: str,
    fit_f0: npt.NDArray,
    fig_width: float=18,
):
    lo_data = np.load(sweep_file)
    freq = lo_data[0,:,:]
    s21 = 10. * np.log10(np.abs(lo_data[1,:,:]))

    #initialize variables for fitting
    chanmask = get_chanmask(chanmask_file)
    n_chan = np.size(chanmask)
    difference = np.zeros(n_chan)

    # Setup for plots 
    ncols = fig_width
    nrows = int(np.ceil(n_chan / ncols))
    print(nrows, ncols)

    fig = plt.figure(figsize=(fig_width, nrows))
    plt.rc('font', size=8)
    counter = 0

    # make plot 
    diff_to_flag = (3./200.) * tone_list * 1e-6

    #loop over resonators to perform fit
    for i_chan in np.arange(n_chan):
        if chanmask[i_chan] == 1:
            #pull in the sweep data for this tone
            this_freq_data = freq[i_chan,:]
            this_s21_data = s21[i_chan,:]

            difference[i_chan] = (fit_f0[i_chan] - tone_list[i_chan]) * 1.e-3

            subplot = plt.subplot2grid((nrows, ncols), (counter // ncols, np.mod(counter, ncols)))
            subplot.axvline(x=fit_f0[i_chan], color='r')
            subplot.plot(this_freq_data, this_s21_data)
            subplot.set_yticks([])
            subplot.set_xticks([])

            freq_ratio = tone_list[i_chan] / np.max(tone_list)
            span = max(this_freq_data) - min(this_freq_data)
            new_span = span * freq_ratio
            subplot.set_xlim(np.mean(this_freq_data)-new_span/2., \
                                                                        np.mean(this_freq_data+new_span/2.))
            subplot.legend(["{:d}".format(i_chan)], \
                        fontsize=6, loc = 3, frameon=False, handlelength=0, bbox_to_anchor=(-0.2,-0.15))

            if np.abs(difference[i_chan]) > diff_to_flag[i_chan]:
                subplot.set_facecolor('yellow')

        # loop over off-res tones to plot
        else:

            # pull in the sweep data for this tone
            this_freq_data = freq[i_chan,:]
            this_s21_data = s21[i_chan,:]

            subplot = plt.subplot2grid((nrows, ncols), (counter // ncols, np.mod(counter, ncols)))
            subplot.plot(this_freq_data, this_s21_data)
            subplot.set_yticks([])
            subplot.set_xticks([])
            freq_ratio = tone_list[i_chan] / np.max(tone_list)
            span = max(this_freq_data) - min(this_freq_data)
            new_span = span * freq_ratio
            subplot.set_xlim(np.mean(this_freq_data)-new_span/2., \
                                                                        np.mean(this_freq_data+new_span/2.))
            subplot.legend(["{:d}".format(i_chan) + ', dS21=' + "{:4.1f}".format(np.max(this_s21_data)-np.min(this_s21_data))], \
                        fontsize=6, loc = 3, frameon=False, handlelength=0, bbox_to_anchor=(-0.2,-0.15))
            subplot.set_facecolor('orange')
        counter += 1

    flagged = np.argwhere(np.abs(difference) > diff_to_flag)
    plt.tight_layout()
    return fig, flagged


if __name__ == '__main__':
    # fit the resonances from a sweep
    sweep = LoSweep(
        get_tone_list('Default_tone_list.npy'),
        '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
        chanmask_file='chanmask.npy',
    )
    sweep.fit(do_print=True)

    fig = sweep.plot()
    plt.show()
    # fit_f0, fit_qi, fit_qc = fit_lo_sweep(
    #     get_tone_list('Default_tone_list.npy'),
    #     '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
    #     chanmask_file='chanmask.npy',
    #     do_print=True,
    # )

    # plot_lo_fit(
    #     get_tone_list('Default_tone_list.npy'),
    #     '20240822_rfsoc2_LO_Sweep_hour16p3294.npy',
    #     'chanmask.npy',
    #     fit_f0,
    # )

