from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


from rfsocinterface.core.data import ProcessedData
from rfsocinterface.analysis.compute_noise_psd import compute_noise_psd, XLIM
from rfsocinterface.core.utils import ordinal

TICK_SIZE = 20
AXES_LABEL_SIZE = 22
TITLE_SIZE = 26
LEGEND_SIZE = 22

def plot_psd(
        ax: plt.Axes,
        color: str,
        label: str,
        freq: npt.NDArray,
        psd: npt.NDArray,
        min_percentile: float=16,
        max_percentile: float=84,
        flat_spectrum: bool=True,
) -> list[Figure]:

    # cutoff = 250  # Number of data points to cut off at the end
    # psd = psd[:, :, :-cutoff]
    # freq = freq[:-cutoff]

    psd_med = np.median(psd, axis=1)

    match color.lower():
        case 'b':
            med_color = 'b'
            fill_color = 'cyan'
        case 'r':
            med_color = 'r'
            fill_color = 'lightcoral'
        case 'g':
            med_color = 'g'
            fill_color = 'lightgreen'
        case 'black':
            med_color = 'k'
            fill_color = 'lightgrey'
        # case 30:
        #     med_color = 'g'
        #     fill_color = 'lightgreen'


    plot_data_med = 10 * np.log10(psd_med)

    psd_min = psd_med[:]
    psd_max = psd_med[:]

    if psd.shape[1] > 1:
        psd_min = np.percentile(psd, min_percentile, axis=1)
        psd_max = np.percentile(psd, max_percentile, axis=1)

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_max = 10 * np.log10(psd_max)

    xdata = freq
    ydata_min = np.mean(plot_data_min, axis=0)
    ydata_med = np.mean(plot_data_med, axis=0)
    ydata_max = np.mean(plot_data_max, axis=0)
    

    if flat_spectrum:
        flat_spectrum_idx = np.where((xdata > 10) & (xdata < 50))
        flat_spectrum_noise = np.median(ydata_med[flat_spectrum_idx])
        ax.plot(xdata, ydata_med, color=med_color, label=rf'{label} ({flat_spectrum_noise:.1f} dBc Hz$^{{-1}}$)')
        plt.axhline(flat_spectrum_noise, color=med_color, linestyle='dashed')
    else:
        ax.plot(xdata, ydata_med, color=med_color, label=label)

    ax.fill_between(
        xdata,
        ydata_min,
        ydata_max,
        facecolor=fill_color,
        alpha=0.5,
    )



if __name__ == "__main__":
    # loopback = 'IF'
    loopback = 'Digital'
    if loopback == 'IF':
        set1000 = 1018
        set100 = 1021
        set10 = 1024
        set30 = 1026
    else:
        set1000 = 1028
        set100 = 1029
        set10 = 1031
        set30 = 1033    

    # Make Raw Spectrum Plot
    data_1000 = ProcessedData.from_tod(
        '20250829',
        set1000,
        do_electronics_noise_removal=False,
    )
    input_data_1000 = data_1000.data_gain_phase / data_1000.carrier_amplitude_norm()
    _, freq_1000, psd_1000 = compute_noise_psd(
        input_data_1000,
        data_1000.timestamp,
        chanmask=data_1000.chanmask[:],
        nominal_block_length=10,
        cut_time=10,
    )

    ylim = (-110, -70)
    with PdfPages(f'raw_psd_plots_{loopback}.pdf') as pdf:
        fig = plt.figure(figsize=(9, 6))
        ax = plt.subplot()
        ax.set_xscale('log')
        ax.set_yscale('linear')
        ax.set_xlim(*XLIM)
        ax.set_ylim(*ylim)
        ax.set_xlabel('Frequency (Hz)', fontsize=AXES_LABEL_SIZE)
        ax.set_ylabel(r'Noise PSD ($\text{dBc Hz}^{-1})$', fontsize=AXES_LABEL_SIZE)
        ax.tick_params(labelsize=TICK_SIZE)

        plot_psd(ax, 'black', 'Raw Spectrum', freq_1000, psd_1000, flat_spectrum=False)


        data_1000.close()

        data_1000 = ProcessedData.from_tod(
            '20250829',
            set1000,
            do_electronics_noise_removal=True,
        )
        input_data_1000 = data_1000.data_gain_phase / data_1000.carrier_amplitude_norm()
        _, freq_1000, psd_1000 = compute_noise_psd(
            input_data_1000,
            data_1000.timestamp,
            chanmask=data_1000.chanmask[:],
            nominal_block_length=10,
            cut_time=10,
        )

        plot_psd(ax, 'b', 'Clean Spectrum', freq_1000, psd_1000, flat_spectrum=False)

        ax.legend(fontsize=LEGEND_SIZE, loc='upper right')
        ax.text(1.4 * XLIM[0], ylim[0] + 2, f'{loopback} Loopback', fontsize=TITLE_SIZE)

        plt.tight_layout()

        pdf.savefig(fig)


    # Make Cleaned Spectrum Plots
    data_100 = ProcessedData.from_file('20250829', set100, mode='r')
    input_data_100 = data_100.data_gain_phase / data_100.carrier_amplitude_norm()
    _, freq_100, psd_100 = compute_noise_psd(
        input_data_100,
        data_100.timestamp,
        chanmask=data_100.chanmask[:],
        nominal_block_length=10,
        cut_time=10,
    )

    data_10 = ProcessedData.from_file('20250829', set10, mode='r')
    input_data_10 = data_10.data_gain_phase / data_10.carrier_amplitude_norm()
    _, freq_10, psd_10 = compute_noise_psd(
        input_data_10,
        data_10.timestamp,
        chanmask=data_10.chanmask[:],
        nominal_block_length=10,
        cut_time=10,
    )

    data_30 = ProcessedData.from_file('20250829', set30, mode='r')
    input_data_30 = data_30.data_gain_phase / data_30.carrier_amplitude_norm()
    _, freq_30, psd_30 = compute_noise_psd(
        input_data_30,
        data_30.timestamp,
        chanmask=data_30.chanmask[:],
        nominal_block_length=10,
        cut_time=10,
    )

    ylim = (-135, -80)
    with PdfPages(f'psd_plots_{loopback}.pdf') as pdf:
        fig = plt.figure(figsize=(9, 6))
        ax = plt.subplot()
        ax.set_xscale('log')
        ax.set_yscale('linear')
        ax.set_xlim(*XLIM)
        ax.set_ylim(*ylim)
        ax.set_xlabel('Frequency (Hz)', fontsize=AXES_LABEL_SIZE)
        ax.set_ylabel(r'Noise PSD ($\text{dBc Hz}^{-1})$', fontsize=AXES_LABEL_SIZE)
        ax.tick_params(labelsize=TICK_SIZE)


        plot_psd(ax, 'b', '1000 Tones', freq_1000, psd_1000)
        plot_psd(ax, 'g', '10 Tones', freq_10, psd_10)
        plot_psd(ax, 'r', '100 Tones', freq_100, psd_100)
        handles, labels = plt.gca().get_legend_handles_labels()
        order = [0,2,1]
        ax.legend([handles[idx] for idx in order],[labels[idx] for idx in order], fontsize=LEGEND_SIZE, loc='upper right')

        # ax.legend(fontsize=LEGEND_SIZE, loc='upper right')

        ax.text(1.4 * XLIM[0], ylim[0] + 2, f'{loopback} Loopback', fontsize=TITLE_SIZE)

        plt.tight_layout()

        pdf.savefig(fig)
    # plt.show()

    data_1000.close()
    data_100.close()
    data_10.close()
    data_30.close()

   

