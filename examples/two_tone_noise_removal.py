import numpy as np
import scipy.signal as sig
import matplotlib.pyplot as plt
def to_gain_phase(z):
    """Complex IQ -> (gain, unwrapped phase in rad)."""
    return np.abs(z), np.unwrap(np.angle(z))


def dbc_psd(x, fs, carrier=1.0, nperseg=None):
    """Welch PSD in dBc/Hz (DC bin dropped for log axes). welch detrends the mean."""
    nperseg = nperseg or len(x) // 10
    f, S = sig.welch(x / carrier, fs=fs, window='hann', nperseg=nperseg)
    return f[1:], 10 * np.log10(S[1:])


def plot_gain_phase_psd(axes, z, fs, carrier, nperseg, label=None, **kw):
    """Plot gain (axes[0]) and phase (axes[1]) dBc/Hz PSDs of complex IQ data z."""
    g, p = to_gain_phase(z)
    for ax, x, c, name in zip(axes, (g, p), (carrier, 1.0), ('Gain', 'Phase')):
        f, S = dbc_psd(x, fs, c, nperseg)
        ax.semilogx(f, S, label=f'{label}: {name}' if label else None, **kw)


def noise_removal_two_tone(I_on, Q_on, I_off, Q_off, fs, lp_freq,
                           nperseg=None, return_coeffs=False, plot=True):
    z_on = np.asarray(I_on) + 1j * np.asarray(Q_on)
    z_off = np.asarray(I_off) + 1j * np.asarray(Q_off)

    gain_on, phase_on = to_gain_phase(z_on)
    data = np.array([gain_on - gain_on.mean(), phase_on - phase_on.mean()])
    gain_off, phase_off = to_gain_phase(z_off)
    template = np.array([gain_off - gain_off.mean(), phase_off - phase_off.mean()])

    N = data.shape[-1]
    nperseg = nperseg or N//10
    freqs_full = np.fft.rfftfreq(N, 1 / fs)

    clean = np.zeros_like(data)
    H_coarse = []
    for r in range(2):                                  # 0 = gain, 1 = phase
        f_coarse, Pxx = sig.welch(template[r], fs=fs, window='hann', nperseg=nperseg)
        _, Pxy = sig.csd(template[r], data[r], fs=fs, window='hann', nperseg=nperseg)
        H = Pxy / Pxx                                   # data ≈ H * template
        H_coarse.append(H)

        # interpolate onto the full rfft grid, zero above the cutoff
        H_full = (np.interp(freqs_full, f_coarse, H.real)
                  + 1j * np.interp(freqs_full, f_coarse, H.imag))
        H_full[freqs_full > lp_freq] = 0
        clean[r] = data[r] - np.fft.irfft(H_full * np.fft.rfft(template[r]), n=N)

    # gain/phase -> IQ, restoring the on-res operating point
    z_out = (clean[0] + gain_on.mean()) * np.exp(1j * (clean[1] + phase_on.mean()))

    if plot:
        fig, ax = plt.subplots(figsize=(12, 4.5))
        plot_gain_phase_psd((ax, ax), z_on, fs, gain_on.mean(), nperseg=nperseg, label='Before', alpha=0.5)
        plot_gain_phase_psd((ax, ax), z_out, fs, gain_on.mean(), nperseg=nperseg, label='After')
        ax.axvline(lp_freq, color='k', ls=':', alpha=0.4, label='lp_freq')
        ax.set(xlabel='Frequency [Hz]', ylabel='Noise [dBc/Hz]', ylim=(-110, -40))
        ax.grid(True, which='both', alpha=0.3)
        ax.legend()
        fig.tight_layout()
        plt.show()

    if return_coeffs:
        return z_out.real, z_out.imag, f_coarse, np.array(H_coarse)
    return z_out.real, z_out.imag
def lowpass(x, fs, cutoff, order=4):
    """Zero-phase Butterworth lowpass (mean removed first to avoid edge transients)."""
    sos = sig.butter(order, cutoff, btype='low', fs=fs, output='sos')
    return sig.sosfiltfilt(sos, x - x.mean())


def _scan_setup(n_tones, on_tone, tones, tone_freqs, freq_label, abs_diff, fmt):
    """Shared bookkeeping: which tones, their separations, labels, order and colors."""
    tones = [t for t in range(n_tones) if t != on_tone] if tones is None else list(tones)
    signed = tone_freqs is not None and not abs_diff

    if tone_freqs is None:
        values = np.asarray(tones, dtype=float)
        labels = [f'Tone {t}' for t in tones]
        x_label = 'Template tone index'
        legend_title = 'Template tone'
    else:
        tone_freqs = np.asarray(tone_freqs, dtype=float)
        values = tone_freqs[tones] - tone_freqs[on_tone]
        if abs_diff:
            values = np.abs(values)
        labels = [f'{fmt.format(v)} {freq_label}' for v in values]
        prefix = 'Template - tone' if signed else '|Template - tone'
        suffix = '' if signed else '|'
        x_label = f'{prefix} {on_tone}{suffix} frequency [{freq_label}]'
        legend_title = 'Template - on tone' if signed else '|Template - on tone|'

    order = np.argsort(values)                    # legend / line order
    dist = np.abs(values - (0 if tone_freqs is not None else values.min()))
    zrank = np.empty(len(tones))                  # nearest tones drawn on top
    zrank[np.argsort(-dist)] = np.arange(len(tones))

    cmap = plt.get_cmap('coolwarm' if signed else 'viridis')
    color_of = np.empty((len(tones), 4))          # color for each entry of `tones`
    color_of[order] = cmap(np.linspace(0, 1, len(tones)))

    return dict(tones=tones, values=values, labels=labels, x_label=x_label,
                legend_title=legend_title, order=order, zrank=zrank, color_of=color_of)


def plot_template_scan(dataIQ, fs, lp_freq, nperseg=None,
                       tones=None, on_tone=0, ylim=(-110, -40),
                       tone_freqs=None, freq_label='Hz', abs_diff=False,
                       legend_ncol=1, fmt='{:+.3g}'):
    """
    Plot gain/phase PSD (dBc/Hz) of tone `on_tone` before cleaning and after
    cleaning with each other tone as the template. Each cleaned curve is labeled
    in the legend with its frequency difference from the on tone.

    dataIQ:       (2, n_tones, n_samples), axis 0 = [I, Q]
    tone_freqs:   optional (n_tones,) tone frequencies; without it, legend shows tone index
    freq_label:   units for the legend entries, e.g. 'MHz'
    abs_diff:     label with |difference| instead of the signed difference
    legend_ncol:  number of legend columns (raise this for many tones)
    fmt:          number format for the difference, e.g. '{:+.3g}' or '{:.2f}'
    """
    dataIQ = np.asarray(dataIQ)
    s = _scan_setup(dataIQ.shape[1], on_tone, tones, tone_freqs, freq_label, abs_diff, fmt)

    z_on = dataIQ[0, on_tone] + 1j * dataIQ[1, on_tone]
    carrier = np.abs(z_on).mean()

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharex=True, sharey=True)
    plot_gain_phase_psd(axes, z_on, fs, carrier, nperseg, color='k', lw=2, zorder=100)
    axes[0].plot([], [], 'k', lw=2, label=f'Tone {on_tone} (uncleaned)')   # legend entry

    for i in s['order']:
        t = s['tones'][i]
        I_c, Q_c = noise_removal_two_tone(z_on.real, z_on.imag, dataIQ[0, t], dataIQ[1, t],
                                          fs, lp_freq, nperseg=nperseg, plot=False)
        plot_gain_phase_psd(axes, I_c + 1j * Q_c, fs, carrier, nperseg,
                            color=s['color_of'][i], alpha=0.7, lw=1, zorder=s['zrank'][i])
        axes[0].plot([], [], color=s['color_of'][i], lw=1.5, label=s['labels'][i])

    for ax, title in zip(axes, ('Gain', 'Phase')):
        ax.axvline(lp_freq, color='k', ls=':', alpha=0.4)
        ax.set_title(f'{title}: tone {on_tone} cleaned with each tone')
        ax.set_xlabel('Frequency [Hz]')
        ax.grid(True, which='both', alpha=0.3)
        if ylim is not None:
            ax.set_ylim(ylim)
    axes[0].set_ylabel('Noise [dBc/Hz]')

    # reserve the right-hand strip of the figure for the legend
    handles, leg_labels = axes[0].get_legend_handles_labels()
    right = 0.80 if legend_ncol == 1 else min(0.80, 0.9 - 0.08 * legend_ncol)
    fig.tight_layout(rect=(0, 0, right, 1))
    fig.legend(handles, leg_labels, loc='center left', bbox_to_anchor=(right, 0.5),
               ncol=legend_ncol, title=s['legend_title'], fontsize='small', frameon=True)
    plt.show()


def plot_template_correlation(dataIQ, fs, tones=None, on_tone=0,
                              tone_freqs=None, freq_label='Hz', abs_diff=False,
                              fmt='{:+.3g}', lowpass_freq=None):
    """
    Plot the correlation coefficient between the gain/phase time streams of
    `on_tone` and each other tone versus frequency separation.

    dataIQ:        (2, n_tones, n_samples), axis 0 = [I, Q]
    tone_freqs:    optional (n_tones,) tone frequencies; without it, x axis is tone index
    lowpass_freq:  if given, lowpass the time streams at this cutoff (Hz, below
                   Nyquist) before correlating. None = unfiltered.

    Returns dict with tones, separation and gain/phase correlations
    (in the same order as `tones`).
    """
    dataIQ = np.asarray(dataIQ)
    if lowpass_freq is not None and lowpass_freq >= fs / 2:
        raise ValueError(f'lowpass_freq ({lowpass_freq} Hz) must be below Nyquist ({fs/2} Hz)')
    s = _scan_setup(dataIQ.shape[1], on_tone, tones, tone_freqs, freq_label, abs_diff, fmt)

    def gain_phase(t):
        g, p = to_gain_phase(dataIQ[0, t] + 1j * dataIQ[1, t])
        if lowpass_freq is not None:
            g, p = lowpass(g, fs, lowpass_freq), lowpass(p, fs, lowpass_freq)
        return g, p

    g_on, p_on = gain_phase(on_tone)
    corr = np.array([[np.corrcoef(g_on, g)[0, 1], np.corrcoef(p_on, p)[0, 1]]
                     for g, p in map(gain_phase, s['tones'])])      # (n_templates, 2)

    filt_note = 'unfiltered' if lowpass_freq is None else f'lowpassed at {lowpass_freq:g} Hz'
    fig, axes = plt.subplots(1, 2, figsize=(15, 4), sharex=True, sharey=True)
    for ax, c, name in zip(axes, corr.T, ('Gain', 'Phase')):
        ax.semilogx(s['values'][s['order']], c[s['order']], '-', color='gray', lw=0.8, alpha=0.5)
        ax.scatter(s['values'], c, c=s['color_of'], s=30, zorder=3)
        ax.axhline(0, color='k', lw=0.8, alpha=0.5)
        ax.set_title(f'{name}: correlation of tone {on_tone} with each tone ({filt_note})')
        ax.set_xlabel(s['x_label'])
        ax.set_ylim(-1.05, 1.05)
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel('Correlation coefficient')
    fig.tight_layout()
    plt.show()

    return {'tones': np.array(s['tones']), 'separation': s['values'],
            'corr_gain': corr[:, 0], 'corr_phase': corr[:, 1]}