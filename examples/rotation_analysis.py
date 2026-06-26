import pdb
import logging
import logging.config

from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from PySide6.QtWidgets import QApplication

from rfsocinterface.analysis.noise_blob import plot_angle_in_blob
from rfsocinterface.core.data import *
from rfsocinterface.core.sweeps import *
from rfsocinterface.core.utils import create_axis_formatter, BAD_RESONANCE_COLOR, mean_histogram, std_histogram
from rfsocinterface.gui.lodiagnostics import DiagnosticsDialog


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)
    # app = QApplication()
    date = '20260617'
    setnum = 1001
    # cdata = ConsolidatedData.from_tod(date, setnum, downsampling_factor=16)
    # cdata = ConsolidatedData.load(date, setnum, mode='r')
    # pdata = cdata.create_processed_data()

    pdata = ProcessedData.load(date, setnum, 'r')

    sweep = pdata.get_lo_sweep(0)
    detector_f = pdata.detector_f()
    data_IQ = pdata.data_IQ[:]
    data_freq_diss = pdata.data_freq_diss[:]
    IQ_to_freq_diss_angle = pdata.IQ_to_freq_diss_angle[:]
    adc_units_to_hz = pdata.adc_units_to_hz[:]

    neg_res = [
        55, 58, 64, 65, 68,
        71, 74, 83, 98, 100,
        101, 103, 113, 130, 139,
        142, 147, 148, 149, 155,
        158, 159, 160, 161, 162,
        163, 164, 165, 166, 167,
        172, 176, 177, 178, 180,
        181, 183, 185, 186, 187,
        190, 191, 197, 199,
    ]
    pos_res = [
        48, 50, 52, 57, 69,
        76, 77, 82, 88, 91,
        93, 95, 96, 104, 109,
        111, 119, 122, 123, 124,
        126, 127, 132, 135, 136,
        138, 145, 146, 150, 152,
        156, 157, 168, 169, 170,
        171, 173, 174, 179, 184,
        188, 193, 194, 195, 196,
        198, 200,
    ]
    good_res = sorted(neg_res + pos_res)
    axis_formatter = create_axis_formatter(3)

    # sweep_file = '/data/20260617/20260617_Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power_LO_Sweep_hour14p0403_high_res.h5'
    # sweep = LoSweepData.load(sweep_file)
    # dial = DiagnosticsDialog(sweep)
    # dial.plot_and_show()
    # dial = DiagnosticsDialog.from_h5(sweep_file)

    # dial.show()
    rotation_angle, sweep_adc_units_to_hz, dIQ_df = sweep.freq_direction()
    rotation_angle = np.rad2deg(rotation_angle)

    mid_ind = sweep.nfreq // 2
    edge_indices = [mid_ind - 5, mid_ind + 5+ 1]
    ind_val = np.arange(edge_indices[0], edge_indices[1])
    freq_val = sweep.freq[:, ind_val] - sweep.detector_f[:, np.newaxis]

    filt_sos_lp = signal.butter(
        2,
        15,
        btype='lowpass',
        fs=pdata.fs,
        output='sos',
        analog=False,
    )
    filt_sos_hp = signal.butter(
        2,
        0.5,
        btype='highpass',
        fs=pdata.fs,
        output='sos',
        analog=False,
    )
    filt_data_IQ = signal.sosfiltfilt(filt_sos_hp, data_IQ)
    filt_data_IQ = signal.sosfiltfilt(filt_sos_lp, filt_data_IQ)

    cut_time = 5
    cut_samples = int(cut_time * pdata.fs)
    cut_data_IQ = filt_data_IQ[..., cut_samples:-cut_samples]
    cut_data_IQ_normalized = cut_data_IQ / pdata.carrier_amplitudes[:, :][..., np.newaxis]

    max_i_samples = np.argmax(np.abs(cut_data_IQ_normalized[0]), axis=-1).flatten()
    max_i = cut_data_IQ_normalized[0, range(pdata.n_tones), max_i_samples]
    max_q_samples = np.argmax(np.abs(cut_data_IQ_normalized[1]), axis=-1).flatten()
    max_q = cut_data_IQ_normalized[1, range(pdata.n_tones), max_q_samples]
    source_cut_sample = np.where(np.abs(max_i) >= np.abs(max_q), max_i_samples, max_q_samples)
    source_sample = source_cut_sample + cut_samples  # Actual sample index of the source crossing

    # for i_res in good_res:
    #     plt.title(f'Resonator {i_res} - Data I')
    #     plt.plot(data_IQ[0, i_res])
    #     plt.axvline(source_sample[i_res], color='red', linestyle='--', label=f'Source Sample = {source_sample[i_res]}')
    #     plt.legend()
    #     plt.figure()
    #     plt.title(f'Resonator {i_res} - Data Q')
    #     plt.plot(data_IQ[1, i_res])
    #     plt.axvline(source_sample[i_res], color='red', linestyle='--', label=f'Source Sample = {source_sample[i_res]}')
    #     plt.legend()
    #     plt.show()
    #     pdb.set_trace()

    with PdfPages('sweep_results.pdf') as pdf:
        for i_res in good_res:
            fig, axes = plt.subplots(1, 3, figsize=(12, 4))
            if i_res in pos_res:
                suffix = '(Positive)'
            else:
                suffix = '(Negative)'
                fig.set_facecolor(BAD_RESONANCE_COLOR)
            fig.suptitle(
                f'LO Sweep for Resonator {i_res} {suffix}\n'
                f'$f_0$ = {sweep.detector_f[i_res] * 1e-6:3f} MHz\n'
                f'IQ-to-Freq/Diss Rotation Angle = {rotation_angle[i_res]:.2f} deg'
            )
            axes[0].set_title('Data I')
            axes[0].plot(sweep.freq[i_res], sweep.data_I[i_res], label='Full Trace')
            axes[0].plot(sweep.freq[i_res, ind_val], sweep.data_I[i_res, ind_val], label='Center Indices')
            handles, labels = axes[0].get_legend_handles_labels()
            label = rf'$\frac{{dI}}{{df}}$ = {dIQ_df[0, i_res]:.3f}'
            extra_text_patch = mpatches.Patch(color="none", label=label)
            handles.append(extra_text_patch)
            labels.append(label)
            axes[0].legend(handles=handles, labels=labels)
            axes[0].xaxis.set_major_formatter(axis_formatter)
            axes[0].set_xlabel('Frequency (MHz)')


            axes[1].set_title('Data Q')
            axes[1].plot(sweep.freq[i_res], sweep.data_Q[i_res], label='Full Trace')
            axes[1].plot(sweep.freq[i_res, ind_val], sweep.data_Q[i_res, ind_val], label='Center Indices')
            handles, labels = axes[1].get_legend_handles_labels()
            label = rf'$\frac{{dQ}}{{df}}$ = {dIQ_df[1, i_res]:.3f}'
            extra_text_patch = mpatches.Patch(color="none", label=label)
            handles.append(extra_text_patch)
            labels.append(label)
            axes[1].legend(handles=handles, labels=labels)
            axes[1].xaxis.set_major_formatter(axis_formatter)
            axes[1].set_xlabel('Frequency (MHz)')

            axes[2].set_title(r'$S_{21}$')
            axes[2].plot(sweep.freq[i_res], sweep.s21[i_res], label='Full Trace')
            axes[2].plot(sweep.freq[i_res, ind_val], sweep.s21[i_res, ind_val], label='Center Indices')
            axes[2].legend()
            axes[2].xaxis.set_major_formatter(axis_formatter)
            axes[2].set_xlabel('Frequency (MHz)')

            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            fig = plot_angle_in_blob(
                data_IQ[:, i_res],
                data_freq_diss[:, i_res],
                IQ_to_freq_diss_angle[i_res],
                adc_units_to_hz[i_res],
                title=f'IQ to Frequency/Dissipation Rotation for Resonator {i_res} ($f = {detector_f[i_res] * 1e-6:.3f}$ MHz)',
                fit_order=1,
                alpha=0.1,
                # sigma=4,
                markersize=1,
                source_crossing_sample=source_sample[i_res],
            )
            if i_res in neg_res:
                fig.set_facecolor(BAD_RESONANCE_COLOR)
            pdf.savefig(fig)
            plt.close(fig)

        n_bins = 15
        fig, axes = plt.subplots(1, 3, figsize=(12, 6))
        fig.suptitle('Histograms')

        axes[0].set_title('dI/df')
        axes[0].set_ylabel('Frequency')
        axes[0].set_xlabel('dI/df (ADC / HZ)')
        axes[0].hist(dIQ_df[0, pos_res], bins=n_bins, alpha=0.5, label='Positive Resonators')
        axes[0].hist(dIQ_df[0, neg_res], bins=n_bins, alpha=0.5, label='Negative Resonators')
        axes[0].legend()

        axes[1].set_title('dQ/df')
        axes[1].set_ylabel('Frequency')
        axes[1].set_xlabel('dQ/df (ADC / HZ)')
        axes[1].hist(dIQ_df[1, pos_res], bins=n_bins, alpha=0.5, label='Positive Resonators')
        axes[1].hist(dIQ_df[1, neg_res], bins=n_bins, alpha=0.5, label='Negative Resonators')
        axes[1].legend()

        axes[2].set_title('IQ-to-Freq/Diss Rotation Angle')
        axes[2].set_ylabel('Frequency')
        axes[2].set_xlabel(r'Angle (deg)')
        axes[2].hist(rotation_angle[pos_res], bins=n_bins, alpha=0.5, label='Positive Resonators')
        axes[2].hist(rotation_angle[neg_res], bins=n_bins, alpha=0.5, label='Negative Resonators')
        axes[2].legend()

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)
    # pdb.set_trace()
    # dial = DiagnosticsDialog(sweep)
    # dial.plot_and_show()
    # dial.plot()

    # app.exec()