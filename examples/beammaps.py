import pdb
import logging
import logging.config

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.offsetbox import AnchoredText

from rfsocinterface.core.data import (
    ProcessedData,
    Pipeline,
    CleanTOD,
    RemoveElectronicsNoise,
    HighPassFilter,
    LowPassFilter,
    BinTODIntoMap,
    PlotMap,
    BinTODIntoVideo,
    AnimateVideo,
    get_extent,
)
from rfsocinterface.analysis import (
    ComputeNoisePSD,
    PlotPSD,
    PsdBasis,
    AnalyzeBeamMap,
    PlotBeamMap,
    CheckFocus,
)
from rfsocinterface.core.utils import (
    BAD_RESONANCE_COLOR,
    OFF_RESONANCE_COLOR,
    elide_text,
)
from rfsocinterface.core.params import RFSoCParameters, DEFAULT_DFOVERF_PER_MK
from rfsocinterface.core.sweeps import LoSweepData


def flag_non_signal(
        pdata: ProcessedData,
        movement_threshold: float=1e-4,
        lower_bound_az: float=4.525,
        upper_bound_az: float=9.475,
        plot: bool = False,
        save_changes: bool = True,
    ):
    tel_az = pdata.get_telescope_az(0)[:]
    tel_za = pdata.get_telescope_za(0)[:]
    map_signal_mask = pdata.get_map_signal_mask(0)
    if not save_changes:
        # Load a copy of the mask to avoid modifying the original dataset
        map_signal_mask = map_signal_mask[:]  
    sample_idx = np.arange(tel_az.size)

    # First, flag samples during move to initial position

    d_za = np.diff(tel_za)
    diff_sample_idx = np.arange(d_za.size)

    # Telescope moves in AZ then ZA at the start

    # Find when first AZ dither stops, i.e.
    # when the telescope first starts moving in ZA 
    # AKA first time that ZA changes (i.e. d_za > 0)
    za_dither_start_idx = np.nanargmax(np.abs(d_za) >= movement_threshold)  # Finds first `True`

    # Find when the telescope gets to the intial position
    # i.e. first ZA dither stops
    # AKA first time that ZA stops changing after ZA dither starts (i.e. diff == 0)
    initial_pos_idx = np.nanargmax(
        (np.abs(d_za) < movement_threshold)
        & (diff_sample_idx > za_dither_start_idx)  # Only look after ZA dither starts
    )

    # NOTE: Porbably need to deal with off-by-one errors since using np.diff

    # Ignore samples during the move to the initial position
    map_signal_mask[:initial_pos_idx] = False


    # Flag samples that are outside of [5, 9] AZ
    outside_samples = np.argwhere((tel_az < lower_bound_az) | (tel_az > upper_bound_az)).flatten()
    map_signal_mask[outside_samples] = False

    # Flag samples where the position is unknown
    nan_idx = np.argwhere(
        np.isnan(tel_az) |
        np.isnan(tel_za)
    ).flatten()
    map_signal_mask[nan_idx] = False

    if plot:
        map_signal_mask = map_signal_mask[:]
        plt.title(f'Signal Mask - {pdata.file_stub}')
        plt.scatter(
            tel_az[map_signal_mask],
            tel_za[map_signal_mask],
            c=sample_idx[map_signal_mask] / sample_idx.size,
            cmap='viridis',
            label='Good Samples',
        )
        plt.scatter(
            tel_az[:initial_pos_idx],
            tel_za[:initial_pos_idx],
            c='r',
            label='Intial move'
        )
        plt.scatter(
            tel_az[outside_samples],
            tel_za[outside_samples],
            c='gray',
            label='Outside bounds'
        )
        plt.axvline(lower_bound_az, color='red', linestyle='--')
        plt.axvline(upper_bound_az, color='red', linestyle='--')
        plt.gca().invert_yaxis()
        plt.legend()
        plt.show()

def plot_signal_mask(
    map_signal_mask: npt.NDArray,
    tel_az: npt.NDArray,
    tel_za: npt.NDArray,
    title: str,
):
    sample_idx = np.arange(tel_az.size)
    plt.title(title)
    plt.scatter(
        tel_az[map_signal_mask],
        tel_za[map_signal_mask],
        c=sample_idx[map_signal_mask] / sample_idx.size,
        cmap='viridis',
        label='Good Samples',
    )
    plt.scatter(
        tel_az[~map_signal_mask],
        tel_za[~map_signal_mask],
        c='gray',
        label='Non-signal Samples'
    )
    plt.gca().invert_yaxis()
    plt.legend()
    plt.show()


def plot_single_beammap(
    pdata: ProcessedData,
    i_tone_absolute: int,
    zoom_half_width: float | None = None,
):
    """Plot the beammap results for a single resonator.

    The left panel shows the full map with the fitted beam center marked. The
    right panel shows a zoomed-in view around the beam with no markers, and the
    zoomed region is outlined on the full map.

    Args:
        pdata: Processed data containing the ``map`` and ``beammap`` groups.
        i_tone_absolute: Absolute tone index to plot.
        zoom_half_width: Half-width of the zoomed region in degrees. Defaults
            to 1.5x the larger fitted FWHM.
    """
    az_center = pdata['beammap/az_center'][:]
    za_center = pdata['beammap/za_center'][:]
    amplitude = pdata['beammap/amplitude'][:]
    snr = pdata['beammap/snr'][:]
    chisq = pdata['beammap/chisq'][:]
    fwhm_az = pdata['beammap/fwhm_az'][:]
    fwhm_za = pdata['beammap/fwhm_za'][:]
    map_val = pdata['map/map_val'][:]
    map_az = pdata['map/map_az'][:]
    map_za = pdata['map/map_za'][:]
    dpix = pdata['map'].attrs['dpix']
    units = pdata['map'].attrs.get('units', 'mK')
    extent = get_extent(map_az, map_za, dpix=dpix)
    chanmask = pdata.chanmask
    detector_f = pdata.detector_f()

    fig, (ax, ax_zoom) = plt.subplots(1, 2, figsize=(12, 5.5))

    data_to_plot = map_val[i_tone_absolute]
    data_to_plot -= np.nanmedian(data_to_plot)
    data_to_plot /= np.nanmax(data_to_plot)
    # data_to_plot = 10 * np.log10(np.abs(data_to_plot))

    imshow_kwargs = {
        'extent': extent,
        'aspect': 'equal',
        'cmap': 'jet',
        # 'interpolation': 'bilinear',
    }

    # All map data
    im = ax.imshow(data_to_plot, **imshow_kwargs)

    # Zoomed-in map data (same color scale so the colorbar applies to both)
    ax_zoom.imshow(data_to_plot, norm=im.norm, **imshow_kwargs)

    # Color bar (shared, to the right of the zoomed panel)
    divider = make_axes_locatable(ax_zoom)
    cax = divider.append_axes('right', size='5%', pad=0.05)
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(f'Normalized signal ({units})', rotation=270, labelpad=15)

    # Center of bright source (full map only, so it doesn't hide the beam)
    ax.plot(
        az_center[i_tone_absolute],
        za_center[i_tone_absolute],
        marker='+',
        color='white',
        markersize=10,
        mew=2,
    )

    # Determine zoom window around the beam. Fall back to the brightest pixel
    # and/or a fraction of the map if the fit failed.
    x0 = az_center[i_tone_absolute]
    y0 = za_center[i_tone_absolute]
    if not (np.isfinite(x0) and np.isfinite(y0)):
        i_za, i_az = np.unravel_index(np.nanargmax(data_to_plot), data_to_plot.shape)
        x0 = map_az[i_az]
        y0 = map_za[i_za]
    if zoom_half_width is None:
        fwhm = np.nanmax([fwhm_az[i_tone_absolute], fwhm_za[i_tone_absolute]])
        if np.isfinite(fwhm) and fwhm > 0:
            zoom_half_width = max(2 * fwhm, 0.25)
        else:
            zoom_half_width = 0.1 * min(np.ptp(map_az), np.ptp(map_za))
    zoom_half_width = max(zoom_half_width, 2 * dpix)

    # Keep the same axis orientation as the full map (extent may be inverted)
    x_dir = np.sign(extent[1] - extent[0]) or 1
    y_dir = np.sign(extent[3] - extent[2]) or 1
    ax_zoom.set_xlim(x0 - x_dir * zoom_half_width, x0 + x_dir * zoom_half_width)
    ax_zoom.set_ylim(y0 - y_dir * zoom_half_width, y0 + y_dir * zoom_half_width)

    # Stats
    show_stats = chanmask[i_tone_absolute] != 0
    if show_stats:
        bbox_pad = 0.3
        t = AnchoredText(
            f'Amplitude = {amplitude[i_tone_absolute] * 1e5:2f}    '
            f'chisq = {chisq[i_tone_absolute]:.3f}    '
            f'snr = {snr[i_tone_absolute]:.3f}\n'
            f'fwhm_az = {fwhm_az[i_tone_absolute]:.2f}    '
            f'fwhm_za = {fwhm_za[i_tone_absolute]:.2f}\n'
            f'az_center = {az_center[i_tone_absolute]:.2f}    '
            f'za_center = {za_center[i_tone_absolute]:.2f}',
            loc='lower center',
            bbox_to_anchor=(0.5, 0.01),
            bbox_transform=fig.transFigure,
            pad=bbox_pad,
            borderpad=0,
            prop={
                # color='white',
                'horizontalalignment': 'center',
            },
        )
        # t.patch.set_alpha(0.25)
        # t.patch.set_color('black')
        fig.add_artist(t)

    i_chan, i_tone_relative = pdata.get_relative_tone_index(i_tone_absolute)
    if pdata.n_chan > 1:
        # Spefcify the tile name if there are multiple channels
        tile_name = pdata.get_tile_name(i_chan)
        title = (
            f'{elide_text(tile_name, max_len=30)} - Tone {i_tone_relative}\n'
            f'($f_0$={detector_f[i_tone_absolute] * 1e-6:.3f} MHz)'
        )
    else:
        title = (
            f'Tone {i_tone_relative} '
            f'($f_0$={detector_f[i_tone_absolute] * 1e-6:.3f} MHz)'
        )

    # Indicate in plot title and face color if off-resonance / bad tone
    if chanmask[i_tone_absolute] != 1:
        if chanmask[i_tone_absolute] == 0:
            title += ' (Off-resonance)'
            facecolor = OFF_RESONANCE_COLOR
        else:
            title += ' (Bad Resonance)'
            facecolor = BAD_RESONANCE_COLOR
        fig.set_facecolor(facecolor)

    for a in (ax, ax_zoom):
        a.set_xlabel('X Position (deg)')
        a.set_ylabel('Y Position (deg)')
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title('Full map')
    ax_zoom.set_title('Beam (zoomed)')
    fig.suptitle(title)
    # fig.set_dpi(300)

    # Leave room at the bottom for the stats box
    fig.tight_layout(rect=(0, 0.14 if show_stats else 0, 1, 1))

    # Outline the zoomed region on the full map. The connector lines are
    # hidden since they cross the zoomed panel's tick labels.
    indicator = ax.indicate_inset_zoom(ax_zoom, edgecolor='white', alpha=0.9)
    for connector in indicator.connectors:
        connector.set_visible(False)

    plt.show()
    pdb.set_trace()


if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 15
    hp_filter_freq = 0.03

    ds_factor = 16

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']
    # dataset = 'data_mK'
    # datasets = ['.*/data_mK']

    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=True,
        dataset=dataset,
        az_trim=0,
        za_trim=0,
        dpix=0.02,
        r0=0.0,
    )
    analyze_beammap = AnalyzeBeamMap()
    plot_beammap = PlotBeamMap(dpi=100)

    pipeline = Pipeline([
        # hp_filter,
        # lp_filter,
        # clean_tod,
        bin_tod_to_map,
        analyze_beammap,
        plot_beammap,
    ])

    date = '20260617'
    setnum = 1001

    # tod_file = '/data/20261028/20261028_Device_aSi1_Channel2_telescope_275mK_20260804_TOD_set1001.h5'
    # tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260804'
    # with RFSoCParameters.load(tile_name, 'r') as params:
    #     params.append_to_TOD(tod_file)
    # sweep = LoSweepData.load_most_recent(tile_name)
    # if sweep is not None:
    #     sweep.append_to_TOD(tod_file)

    # pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata, _ = pipeline.from_consolidated_data(date, setnum)
    for setnum in [1001, 1004, 1005, 1006]:
        pdata = ProcessedData.load(date, setnum)
        pipeline.run(pdata)
        pdata.close()

    # pdb.set_trace()
    # bin_tod_to_map.apply(pdata)
    # analyze_beammap.apply(pdata)
    # plot_single_beammap(
    #     pdata,
    #     112,
    # )
    # plot_beammap.apply(pdata)
    # pdb.set_trace()
    # plot_signal_mask(
    #     pdata.get_map_signal_mask(0)[:],
    #     pdata.get_telescope_az(0)[:],
    #     pdata.get_telescope_za(0)[:],
    #     f'Signal Mask - {pdata.file_stub}',
    # )
    # pdata.get_map_signal_mask(0)[:] = True
    # flag_non_signal(
    #     pdata,
    #     plot=True,
    #     lower_bound_az=2.525,
    #     upper_bound_az=7.475,
    # )
    # pipeline.run(pdata)
    # try:
    #     map_signal_mask = pdata.get_map_signal_mask(0)
    # except KeyError:
    #     map_signal_mask = make_signal_dset(pdata)

    # date = '20261023'
    # for setnum in [1016, 1017, 1018]:
    # for setnum in [1017]:
    #     pdata = ProcessedData.load(date, setnum)
    #     pdata.setnum = setnum
    #     flag_non_signal(pdata, movement_threshold=1e-4)
    #     # pdb.set_trace()
    #     bin_tod_to_map.apply(pdata)
    #     analyze_beammap.apply(pdata)
    #     plot_beammap.apply(pdata)
    #     pdata.close()




