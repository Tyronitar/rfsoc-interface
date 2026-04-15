from pathlib import Path
from typing import Literal
import shutil

from datetime import datetime

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
import pdb
import h5py


from rfsocinterface.core.data import ProcessedData, ProcessedDataLN, ProcessedDataL0, ProcessedDataL1, ComputeNoisePSD, PsdBasis
from rfsocinterface.analysis.psd import compute_noise_psd, XLIM
from rfsocinterface.core.utils import ordinal

TICK_SIZE = 20
AXES_LABEL_SIZE = 22
TITLE_SIZE = 26
LEGEND_SIZE = 20
LEGEND_LABEL_SPACING = 0.15

def plot_psd(
        ax: plt.Axes,
        color: str,
        label: str,
        freq: npt.NDArray,
        psd: npt.NDArray,
        min_percentile: float=16,
        max_percentile: float=84,
        flat_spectrum: bool=True,
        flat_spectrum_search_bounds: tuple=(10, 50),
) -> list[Figure]:

    # cutoff = 250  # Number of data points to cut off at the end
    # psd = psd[:, :, :-cutoff]
    # freq = freq[:-cutoff]

    # for i_tone in range(psd.shape[1]):
    #     ax.plot(freq[:], np.mean(10 * np.log10(psd[:, i_tone]), axis=0))
    # return

    psd_med = np.median(psd, axis=1)

    match color.lower():
        case 'b' | 'blue;':
            med_color = 'b'
            fill_color = 'cyan'
        case 'r' | 'red':
            med_color = 'r'
            fill_color = 'lightcoral'
        case 'g' | 'green':
            med_color = 'g'
            fill_color = 'lightgreen'
        case 'k' | 'black':
            med_color = 'k'
            fill_color = 'lightgrey'
        case 'o' | 'orange':
            med_color = 'darkorange'
            fill_color = 'bisque'
        case 'gold':
            med_color = 'gold'
            fill_color = 'khaki'
        case 'turquoise' | 'teal':
            med_color = 'teal'
            fill_color = 'turquoise'
        case 'purple':
            med_color = 'purple'
            fill_color = 'violet'
        # case 31:
        #     med_color = 'g'
        #     fill_color = 'lightgreen'


    plot_data_med = 10 * np.log10(psd_med)

    psd_min = psd_med[:]
    psd_max = psd_med[:]

    if psd.shape[1] > 1:
        psd_min = np.percentile(psd, min_percentile, axis=1)
        psd_max = np.percentile(psd, max_percentile, axis=1)

    # means = np.mean(np.mean(psd, axis=0), axis=-1)
    # idx = np.argsort(means)
    # pdb.set_trace()

    plot_data_min = 10 * np.log10(psd_min)
    plot_data_max = 10 * np.log10(psd_max)

    xdata = freq[:]
    ydata_min = np.mean(plot_data_min, axis=0)
    ydata_med = np.mean(plot_data_med, axis=0)
    ydata_max = np.mean(plot_data_max, axis=0)


    if flat_spectrum:
        flat_spectrum_idx = np.where((xdata > flat_spectrum_search_bounds[0]) & (xdata < flat_spectrum_search_bounds[1]))
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
    date = '20260415'
    setnum = 1014

    data_l0 = ProcessedDataL0.from_tod(
            date,
            setnum,
        )
    data_l1 = ProcessedDataL1.from_level0(
        data_l0,
        do_electronics_noise_removal=True,
        block_length=110,
    )
    psd_routine = ComputeNoisePSD(
        PsdBasis.GAIN_PHASE,
        cut_time=2,
    )
    data_l2 = ProcessedDataLN.from_previous_level(data_l1)
    psd_routine(data_l2)
    freq = data_l2.get_node_value('freq', '/psd')[:]
    psd = data_l2.get_node_value('psd_gain_phase', '/psd')[:]

    plt.plot(freq, 10 * np.log10(np.median(psd[0], axis=0)))
    plt.show()

    pdb.set_trace()



    in_lab = False

    use_cached_onres = True
    use_cached_offres = True
    use_cached_if = True

    if in_lab:
        #
        # Lab
        #

        if_data = h5py.File('/data/20250829/20250829_processed_data_set1021.h5', 'r')
        carrier_amp = if_data['detector_0/data/carrier_amplitudes'][:]
        carrier_norm = np.mean(np.abs(carrier_amp[0] + 1j*carrier_amp[1]), axis=0)
        in_data = if_data['detector_0/data/data_gain_phase'][:] / carrier_norm
        _, freq_if, psd_if = compute_noise_psd(
            in_data,
            if_data['detector_0/data/timestamp'][:],
            if_data['detector_0/global_data/chanmask'][:],
            nominal_block_length=10,
            cut_time=10
        )

        if_date = '20260319'
        onres_date = '20260319'
        onres_setnum = 1023
        offres_date = '20260319'
        offres_setnum = 1023
    else:
        #
        # Telescope
        #

        if_date = '20260325'
        
        # IF Loopback for reference
        if_setnum = 1006
        if use_cached_if:
            print(f'Using cached IF Loopback data from {if_date}_set{if_setnum}')
            data_l2 = ProcessedDataLN.from_file(if_date, if_setnum, level=2)
        else:
            data_l0 = ProcessedDataL0.from_tod(if_date, if_setnum)
            data_l1 = ProcessedDataL1.from_level0(
                data_l0,
                do_electronics_noise_removal=True,
                block_length=110,
            )
            data_l2 = ProcessedDataLN.from_previous_level(data_l1)
            psd_routine = ComputeNoisePSD(
                PsdBasis.GAIN_PHASE,
                cut_time=2,
                # tone_indices='onres',
            )
            psd_routine(data_l2)
        freq_if = data_l2.get_node_value('freq', '/psd')[:]
        psd_if = data_l2.get_node_value('psd_gain_phase', '/psd')[:]

        data_l2.close()
        # data_l1.close()
        # data_l0.close()

        onres_date = '20260413'
        onres_setnum = 1004
        # onres_date = '20260325'
        # onres_setnum = 1002
        offres_date = '20260325'
        offres_setnum = 1005

    # Now process the data for on-resonance PSD
    if use_cached_onres:
        print(f'Using cached on-resonance data from {onres_date}_set{onres_setnum}')
        data_l2 = ProcessedDataLN.from_file(onres_date, onres_setnum, level=2)
    else:
        data_l0 = ProcessedDataL0.from_tod(
            onres_date,
            onres_setnum,
        )
        data_l1 = ProcessedDataL1.from_level0(
            data_l0,
            do_electronics_noise_removal=True,
            block_length=110,
        )
        psd_routine = ComputeNoisePSD(
            PsdBasis.FREQ_DISS,
            cut_time=2,
            tone_indices='onres',
        )
        data_l2 = ProcessedDataLN.from_previous_level(data_l1)
        psd_routine(data_l2)
    freq_onres = data_l2.get_node_value('freq', '/psd')[:]
    psd_onres = data_l2.get_node_value('psd_freq_diss', '/psd')[:]

    # Convert back to dBc/Hz
    # Multiply psd by resonance freq to get Hz
    # Multiply by adc/Hz to get to adc units
    # divide by carrier amplitude squared to get to dBc
    f = data_l2.baseband_freqs[data_l2.onres_ind] + data_l2.lo_freq
    psd_adc = psd_onres * (f[np.newaxis, :, np.newaxis] * data_l2.adc_units_to_hz[data_l2.onres_ind][np.newaxis, :, np.newaxis]) ** 2
    psd_onres = psd_adc / (data_l2.carrier_amplitude_norm() ** 2)

    data_l2.close()
    if not use_cached_onres:
        data_l1.close()
        data_l0.close()

    # Off-resonance only
    if use_cached_offres:
        print(f'Using cached off-resonance data from {offres_date}_set{offres_setnum}')
        data_l2 = ProcessedDataLN.from_file(offres_date, offres_setnum, level=2)
    else:
        data_l0 = ProcessedDataL0.from_tod(
            offres_date,
            offres_setnum,
        )
        if not in_lab:
            data_l0.chanmask[:] = data_l0.chanmask[:] * 0
        data_l1 = ProcessedDataL1.from_level0(
            data_l0,
            do_electronics_noise_removal=True,
            block_length=110,
            only_use_offres_indices=True,
        )

        data_l2 = ProcessedDataLN.from_previous_level(data_l1)
        psd_routine = ComputeNoisePSD(
            PsdBasis.GAIN_PHASE,
            cut_time=2,
            tone_indices='offres'
        )
        psd_routine(data_l2)
    freq_offres = data_l2.get_node_value('freq', '/psd')[:]
    psd_offres = data_l2.get_node_value('psd_gain_phase', '/psd')[:]

    data_l2.close()
    if not use_cached_offres:
        data_l1.close()
        data_l0.close()

    # save_name = f'noise_plot_{date}set{setnum}.pdf'
    date = datetime.now().strftime('%Y%m%d')
    if in_lab:
        save_name = f'noise_plot_{date}_lab.pdf'
    else:
        save_name = f'noise_plot_{date}_telescope.pdf'
 

    with PdfPages(save_name) as pdf:
        fig = plt.figure(figsize=(9, 6))
        ax = plt.subplot()
        ax.set_xscale('log')
        ax.set_yscale('linear')
        ax.set_xlim(*XLIM)
        ylim = (-116, -75) if in_lab else (-108, -68)
        ax.set_ylim(*ylim)
        ax.set_xlabel('Frequency (Hz)', fontsize=AXES_LABEL_SIZE)
        ax.set_ylabel(r'Noise PSD ($\text{dBc Hz}^{-1})$', fontsize=AXES_LABEL_SIZE)
        ax.tick_params(labelsize=TICK_SIZE)

        # # Plot IF loopback for reference
        plot_psd(ax, 'red', 'IF Loopback', freq_if, psd_if, flat_spectrum=True)
        
        # plot_psd(ax, 'purple', 'KID - Dark in Lab', freq_onres, psd_onres, flat_spectrum=True, flat_spectrum_search_bounds=(150, 250))
        label_prefix = '' if in_lab else 'On Sky '
        plot_psd(ax, 'purple', f'{label_prefix}Freq', freq_onres, psd_onres[np.newaxis, 0], flat_spectrum=True, flat_spectrum_search_bounds=(150, 250))
        plot_psd(ax, 'orange', f'{label_prefix}Diss', freq_onres, psd_onres[np.newaxis, 1], flat_spectrum=True, flat_spectrum_search_bounds=(150, 250))

        plot_psd(ax, 'turquoise', 'Off Resonance', freq_offres, psd_offres, flat_spectrum=True)

        ylim = ax.get_ylim()
        # ax.text(1.4 * XLIM[0], ylim[0] + 2, f'100 Tones', fontsize=TITLE_SIZE)
        text = '100 Tones' if in_lab else 'SKIPR: 869 Tones'
        ax.text(1.4 * XLIM[0], ylim[0] + 2, text, fontsize=TITLE_SIZE)
        ax.legend(fontsize=LEGEND_SIZE, loc='upper right')
        order = [0, 3, 1, 2]
        handles, labels = ax.get_legend_handles_labels()
        reordered_handles = [handles[i] for i in order]
        reordered_labels = [labels[i] for i in order]
        ax.legend(reordered_handles, reordered_labels, loc='upper right', fontsize=LEGEND_SIZE, labelspacing=LEGEND_LABEL_SPACING)
        fig.tight_layout()
        pdf.savefig()
    plt.show()


    # _, freq_1000, psd_1000 = compute_noise_psd(
    #     input_data_1000,
    #     data_1000.timestamp,
    #     chanmask=data_1000.chanmask[:],
    #     nominal_block_length=10,
    #     cut_time=10,
    # )