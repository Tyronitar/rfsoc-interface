from typing import Literal
import time
import logging
from pathlib import Path

import h5py
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.figure import Figure
from scipy import signal

from rfsocinterface.core.data.routines import DataRoutine, register_routine
from rfsocinterface.core.data.storage import ProcessedData
from rfsocinterface.core.data.utils import DEFAULT_MAP_DPIX, N_POLARIZATION, OPTCAM_HEIGHT_PIXELS, OPTCAM_OFFSET_AZ_PIX, OPTCAM_OFFSET_ZA_PIX, OPTCAM_PIX_SIZE_DEGREES, OPTCAM_WIDTH_PIXELS, get_channel_group_name
from rfsocinterface.core.utils import GAUSSIAN_SIGMA, PERMISSIONS_ALL_FULL, add_colorbar_outside, argclosest, gaussian_filter, PathLike, convert_path, ensure_path

_logger = logging.getLogger(__name__)

def plot_map(
        map: npt.NDArray,
        map_x: npt.NDArray,
        map_y: npt.NDArray,
        extent: tuple[float, float, float, float],
        max_abs: float=None,
        flagged_map: npt.NDArray=None,
        contour_levels: npt.NDArray=None,
        cb_shrink: float=0.95,
        cb_label: str='Signal (mK)',
        cmap: str='Greys_r',
        title: str='',
        add_x_label: bool=True,
) -> Figure:
    xlim = min(map_x),max(map_x)
    ylim = max(map_y),min(map_y)

    if max_abs is None:
        max_abs = np.nanmax(np.abs(map))

    fig = plt.figure()
    plt.imshow(
        np.flip(np.transpose(map[::-1]),1),
        aspect='equal',
        extent=extent,
        vmin=-max_abs,
        vmax=max_abs,
        cmap=cmap,
    )
    cb = plt.colorbar(shrink=cb_shrink)
    cb.set_label(cb_label, rotation=270, labelpad=15)
    if flagged_map:
        plt.contour(
            np.flip(np.flip(np.transpose(flagged_map[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )
    plt.title(title)
    if add_x_label:
        plt.xlabel('Azimuth (degrees)')
    plt.ylabel('ZA (degrees)')
    plt.xlim(xlim), plt.ylim(ylim)

    return fig


def get_scaled_optical_image(
        dpix: float,
        optical_image: npt.NDArray,
        map_az: npt.NDArray,
        map_za: npt.NDArray,
        optcam_pix_size_degrees: float=OPTCAM_PIX_SIZE_DEGREES,
        optcam_offset_az_pix: float=OPTCAM_OFFSET_AZ_PIX,
        optcam_offset_za_pix: float=OPTCAM_OFFSET_ZA_PIX,
        optcam_height_pixels: int=OPTCAM_HEIGHT_PIXELS,
        optcam_width_pixels: int=OPTCAM_WIDTH_PIXELS,
) -> npt.NDArray:
    opt_npix_per_tel_npix = dpix / optcam_pix_size_degrees
    opt_npix_az = int(map_az.size * opt_npix_per_tel_npix / 2) * 2
    opt_npix_za = int(map_za.size * opt_npix_per_tel_npix / 2) * 2
    opt_center_az = int(optcam_width_pixels / 2) + optcam_offset_az_pix
    opt_center_za = int(optcam_height_pixels / 2) + optcam_offset_za_pix
    az_range = slice(
        opt_center_az - int(opt_npix_az / 2),
        opt_center_az + int(opt_npix_az / 2),
    )
    za_range = slice(
        opt_center_za - int(opt_npix_za / 2),
        opt_center_za + int(opt_npix_za / 2),
    )
    return optical_image[za_range, az_range]


def get_extent(map_az: npt.NDArray, map_za: npt.NDArray, dpix: float=DEFAULT_MAP_DPIX) -> tuple[float, float, float, float]:
    return (
        min(map_az)-dpix /2.,
        max(map_az)+dpix /2,
        max(map_za)+dpix /2.,
        min(map_za)-dpix /2.
    )


def get_map_size(
    detector_az: h5py.Dataset,
    detector_za: h5py.Dataset,
    az_trim: float,
    za_trim: float,
    dpix: float=DEFAULT_MAP_DPIX,
    beam_map_mode: bool=False,
) -> tuple[int, int, npt.NDArray, npt.NDArray]:

    max_az = np.max(detector_az) - az_trim
    min_az = np.min(detector_az) + az_trim
    max_za = np.max(detector_za) - za_trim
    min_za = np.min(detector_za) + za_trim
    n_pix_x = int(np.ceil((max_az - min_az) / dpix))
    n_pix_y = int(np.ceil((max_za - min_za) / dpix))
    map_x = np.arange(n_pix_x) * dpix + min_az + dpix / 2.
    map_y = np.arange(n_pix_y) * dpix + min_za + dpix / 2.
    if not beam_map_mode:
        map_y += 0.1  # 0.1 accounts for assymmetry in array

    return n_pix_x, n_pix_y, map_x, map_y


@register_routine
class BinTODIntoMap(DataRoutine):
    name = 'BinTODIntoMap'
    version = '1.0.0'

    produces = {
        '/map/netd',
        '/map/hits_map',
        '/map/sum_map',
        '/map/map_az',
        '/map/map_za',
        '/map/good_samples',
    }

    def __init__(
            self,
            dataset: Literal['data_mK', 'data_freq']='data_mK',
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            med_netd_cut_threshold: float=3.,
            beam_map_mode: bool=False,
            dpix: int=DEFAULT_MAP_DPIX,
    ):
        if dataset not in ('data_mK', 'data_freq'):
            raise ValueError(f'{self.name}: Unable to use dataset {dataset}; choose "data_mK" or "data_freq".')
        if beam_map_mode:
            az_trim = 0.
            za_trim = 0.

        super().__init__(
            dataset=dataset,
            hp_filter_freq=hp_filter_freq,
            lp_filter_freq=lp_filter_freq,
            az_trim=az_trim,
            za_trim=za_trim,
            med_netd_cut_threshold=med_netd_cut_threshold,
            beam_map_mode=beam_map_mode,
            dpix=dpix,
        )

    def inputs(self, pdata: ProcessedData):
        dsets = []
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        for i_chan in range(pdata.n_chan):
            dsets.append(f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}')
        return dsets


    def _initialize_map_arrays(
        self,
        pdata: ProcessedData,
        n_maps: int,
        n_pix_x: int,
        n_pix_y: int,
        dpix: float,
    ):
        if pdata.has('map', exact_match=True):
            _logger.warning(f'{self.name}: Map group already exists in the file; overwriting datasets.')
            del pdata['map']
        map_group = pdata.create_group('map')
        map_group.create_dataset('map_az', shape=(n_pix_x,), dtype=np.float64)
        map_group.create_dataset('map_za', shape=(n_pix_y,), dtype=np.float64)
        map_group.create_dataset('sum_map', shape=(n_maps, n_pix_x, n_pix_y), chunks=(1, n_pix_x, n_pix_y), dtype=np.float64)
        map_group.create_dataset('hits_map', shape=(n_maps, n_pix_x, n_pix_y), chunks=(1, n_pix_x, n_pix_y), dtype=np.float64)
        map_group.create_dataset('netd', shape=(pdata.n_tones,), dtype=np.float64)
        map_group.attrs['dpix'] = dpix
        # TODO: fix this last part
        good_samples = map_group.create_dataset('good_samples', (pdata.n_chan,), dtype=h5py.vlen_dtype(np.uint32))
        for i_chan in range(pdata.n_chan):
            interpolated_samples = pdata.get_from_channel(i_chan, 'time_ordered_data/interpolated_samples')
            good_samples[i_chan] = np.setdiff1d(np.arange(pdata.n_samples), interpolated_samples)

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        dpix = self.params['dpix']
        beam_map_mode = self.params['beam_map_mode']
        n_pix_x, n_pix_y, map_az, map_za = get_map_size(
            pdata.detector_az,
            pdata.detector_za,
            self.params['az_trim'],
            self.params['za_trim'],
            dpix,
            beam_map_mode=beam_map_mode,
        )
        n_maps = N_POLARIZATION if not beam_map_mode else self.n_tones
        self._initialize_map_arrays(pdata, n_maps, n_pix_x, n_pix_y, dpix)
        pdata['map/map_az'][:] = map_az
        pdata['map/map_za'][:] = map_za
        detector_az = pdata.detector_az
        detector_za = pdata.detector_za

        match self.params['dataset']:
            case 'data_mK':
                data = pdata.data_mK[:]
            case 'data_freq':
                data = pdata.data_freq_diss[0]

        sum_map = pdata['map/sum_map'][:]
        hits_map = pdata['map/hits_map'][:]
        netd = pdata['map/netd'][:]

        chanmask = pdata.chanmask[:]
        bad_tones = [
            1, 3, 223, 278, 299,
            303, 10, 69, 192, 820,
            263, 483, 172, 574, 426,
            569, 297, 167, 15, 717,
            487, 842, 453, 13, 719,
            92, 571, 630, 84, 220,
            364, 516, 74, 726, 292,
            519, 812, 302, 683, 537,
            294, 534, 256, 661, 529,
            737, 54, 782, 567, 103,
            330, 133, 809, 460, 589,
            387, 538, 213, 120, 79,
            783, 612, 121, 117, 749
        ]
        chanmask[bad_tones] = -1

        # Compute NETD values
        _logger.info(f'{self.name}: Computing netd...')
        wind = signal.get_window('hamming', pdata.n_samples)
        hp_filter_freq = self.params['hp_filter_freq']
        lp_filter_freq = self.params['lp_filter_freq']
        for i_tone in np.where(chanmask == 1)[0]:
            this_freq, this_psd = signal.periodogram(data[i_tone, :], pdata.fs, window=wind)
            valid_freq = np.where((this_freq > hp_filter_freq) & (this_freq < lp_filter_freq))
            netd[i_tone] = np.sqrt(np.median(this_psd[valid_freq]))
        _logger.info(f'{self.name}: Done computing netd')

        # Get rid of tones with bad weights
        med_netd_cut_threshold = self.params['med_netd_cut_threshold']
        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        chanmask[good_idx] = np.where(good_netd > med_netd_cut_threshold * np.nanmedian(good_netd), -1, chanmask[good_idx])

        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, chanmask[good_idx])
        chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, chanmask[good_idx])

        netd[chanmask != 1] = 0

        if beam_map_mode:
            tones_to_map = np.argwhere(pdata.chanmask != 0).flatten()
        else:
            tones_to_map = np.argwhere(chanmask == 1).flatten()

        # Create map
        _logger.info('BinTODIntoMap: Creating map...')
        for n_loop, i_tone in enumerate(tones_to_map):
            if n_loop == np.size(tones_to_map) // 2:
                _logger.info(f'{self.name}: Halfway done creating map...')
            if beam_map_mode:
                map_idx = i_tone
                weight = 1.
            else:
                map_idx = pdata.detector_pol[i_tone] - 1  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1./ netd[i_tone] ** 2.

            this_detector_az = detector_az[i_tone]
            this_detector_za = detector_za[i_tone]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_tone])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/dpix))
            y_ind = y_ind.astype('int64')

            #eliminate samples outside the map
            i_chan = pdata.get_channel_index_from_tone_index(i_tone)
            good_samples = pdata['map/good_samples'][i_chan][:]
            # good_samples = np.arange(pdata.n_samples)  # TODO: Update this after fixing good_samples
            valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
                np.logical_and(x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x), \
                np.logical_and(y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y))))
            good_samples = good_samples[valid_index]

            #loop over samples to create sum and hits maps
            for time_sample in good_samples:
                sum_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += this_clean_data[time_sample] * weight
                hits_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += 1. * weight
        pdata.set_chanmask(chanmask)
        pdata['map/hits_map'][:] = hits_map
        pdata['map/sum_map'][:] = sum_map
        pdata['map/netd'][:] = netd
        _logger.info(f'{self.name}: Done creating map.')

        return list(self.produces) + ['/vdsets/chanmask']


@register_routine
class PlotMap(DataRoutine):
    name = 'PlotMap'
    version = '1.0.0'

    requires = {
        '/map/map_az',
        '/map/map_za',
        '/map/netd',
        '/map/sum_map',
        '/map/hits_map',
    }

    produces = {
        '/map/plotting/map',
        '/map/plotting/total_map',
        '/map/plotting/flagged_map_1',
        '/map/plotting/flagged_map_2',
        '/map/plotting/flagged_total_map',
        '/map/plotting/contour_levels',
    }

    @ensure_path('savefile')
    def __init__(
            self,
            gaussian_sigma: float=GAUSSIAN_SIGMA,
            valid_covariance_threshold: float=0.5,
            cb_shrink: float=0.95,
            max_abs_threshold: float=0.75,
            save_plot: bool=True,
            savefile: Path=None,
            show: bool=False,
            overwrite: bool=True,
    ):
        super().__init__(
            gaussian_sigma=gaussian_sigma,
            valid_covariance_threshold=valid_covariance_threshold,
            cb_shrink=cb_shrink,
            max_abs_threshold=max_abs_threshold,
            save_plot=save_plot,
            savefile=savefile,
            show=show,
            overwrite=overwrite,
        )

    def inputs(self, pdata: ProcessedData):
        return list(self.requires)

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        reset_arrays = self._intialize_arrays(pdata)
        if reset_arrays:
            self._get_combined_map(pdata)
        self.plot(pdata)

        if reset_arrays:
            return list(self.produces)
        return []

    def _intialize_arrays(self, pdata: ProcessedData) -> bool:
        if pdata.has('map/plotting', exact_match=True):
            if not self.params['overwrite']:
                # Specified not to overwrite existing plotting datasets, so just
                # plot the data without recomputing the maps.
                return False
            _logger.info('Plotting group already exists in the file; overwriting datasets.')
            del pdata['map/plotting']
        sum_map = pdata['map/sum_map']
        hits_map = pdata['map/hits_map']
        mapp = pdata.create_dataset(
            '/map/plotting/map',
            shape=sum_map.shape,
            dtype=np.float64,
        )
        total_map = pdata.create_dataset(
            '/map/plotting/total_map',
            shape=sum_map.shape[1:],
            dtype=np.float64,
        )
        with np.errstate(divide='ignore', invalid='ignore'):
            mapp[:] = sum_map[:] / hits_map[:]
            total_map[:] = np.sum(sum_map, axis=0) / np.sum(hits_map, axis=0)
        return True

    def _get_combined_map(self, pdata: ProcessedData) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
        sigma = self.params['gaussian_sigma']
        map = pdata['map/plotting/map']
        total_map = pdata['map/plotting/total_map']
        flagged_map_1 = gaussian_filter(map[0], sigma)
        flagged_map_2 = gaussian_filter(map[1], sigma)
        flagged_map_3 = gaussian_filter(total_map, sigma)

        # Convert all nans to boolean True
        nan_map_1 = np.isnan(flagged_map_1)
        nan_map_2 = np.isnan(flagged_map_2)
        nan_map_3 = np.isnan(flagged_map_3)

        # Combine the boolean maps such that if any pixel is flagged in any map, it is flagged in the combined map
        combined_nan_map = np.logical_or(np.logical_or(nan_map_1, nan_map_2), nan_map_3)

        # Get the coordinates of True values in the combined_nan_map
        flagged_positions = np.where(combined_nan_map)
        final_flagged_coords = list(zip(flagged_positions[0], flagged_positions[1]))

        # Apply this combined map to each of the final maps
        flagged_map_1[combined_nan_map] = 1
        flagged_map_2[combined_nan_map] = 1
        flagged_map_3[combined_nan_map] = 1

        flagged_map_1[flagged_map_1 != 1] = 0
        flagged_map_2[flagged_map_2 != 1] = 0
        flagged_map_3[flagged_map_3 != 1] = 0

        flagged_map_1[combined_nan_map] = np.nan
        flagged_map_2[combined_nan_map] = np.nan
        flagged_map_3[combined_nan_map] = np.nan

        contour_levels = [1]

        # flagged_map_1= flagged_map_1.flatten()
        # flagged_map_2= flagged_map_2.flatten()
        # flagged_map_3= flagged_map_3.flatten()

        # flagged_map_1 = [x for x in flagged_map_1 if not np.isnan(x)]
        # flagged_map_2 = [x for x in flagged_map_2 if not np.isnan(x)]
        # flagged_map_3 = [x for x in flagged_map_3 if not np.isnan(x)]

        pdata.create_dataset('/map/plotting/flagged_map_1', data=flagged_map_1)
        pdata.create_dataset('/map/plotting/flagged_map_2', data=flagged_map_2)
        pdata.create_dataset('/map/plotting/flagged_total_map', data=flagged_map_3)
        pdata.create_dataset('/map/plotting/contour_levels', data=contour_levels)

    def plot(self, pdata: ProcessedData):
        hits_map = pdata['map/hits_map']
        mapp = pdata['map/plotting/map'][:]
        total_map = pdata['map/plotting/total_map'][:]
        flagged_map_1_filt = pdata['map/plotting/flagged_map_1'][:]
        flagged_map_2_filt = pdata['map/plotting/flagged_map_2'][:]
        flagged_map_tot_filt = pdata['map/plotting/flagged_total_map'][:]
        contour_levels = pdata['map/plotting/contour_levels']
        dpix = pdata['map'].attrs['dpix']

        map_az = pdata['map/map_az']
        map_za = pdata['map/map_za']
        extent = get_extent(map_az, map_za, dpix)

        valid_cov_1 = np.argwhere(hits_map[0] > 0.5 * np.median(hits_map[0]))
        map_goodcov_1 = np.zeros(np.size(valid_cov_1[:,0]))
        for i_cov in np.arange(np.size(valid_cov_1[:,0])):
            map_goodcov_1[i_cov] = mapp[0, valid_cov_1[i_cov,0],valid_cov_1[i_cov,1]]
        valid_cov_2 = np.argwhere(hits_map[1] > 0.5 * np.median(hits_map[1]))
        map_goodcov_2 = np.zeros(np.size(valid_cov_2[:,0]))
        for i_cov in np.arange(np.size(valid_cov_2[:,0])):
            map_goodcov_2[i_cov] = mapp[1, valid_cov_2[i_cov,0],valid_cov_2[i_cov,1]]

        netd = pdata['map/netd']
        netd_1 = netd[pdata.detector_pol == 1]
        netd_2 = netd[pdata.detector_pol == 2]
        valid_netd_1 = np.argwhere(netd_1 > 0)
        valid_netd_2 = np.argwhere(netd_2 > 0)

        cb_shrink = self.params['cb_shrink']
        max_abs_threshold = self.params['max_abs_threshold']
        this_xlim = min(map_az), max(map_az)
        this_ylim = max(map_za), min(map_za)
        max_abs = np.max(np.abs(np.append(map_goodcov_1, map_goodcov_2))) * max_abs_threshold
        med_netd_1 = 1./np.sqrt(np.sum(1./netd_1[valid_netd_1]**2)/np.size(valid_netd_1))
        med_netd_2 = 1./np.sqrt(np.sum(1./netd_2[valid_netd_2]**2)/np.size(valid_netd_2))

        t0 = time.asctime(time.localtime(pdata.timestamp[0]-7500))
        vis = pdata.optical_visibility[()]

        # TODO: Make figure size change based on the size of the map
        # aspect_ratio = (this_ylim[0] - this_ylim[1]) / (this_xlim[1] - this_xlim[0])
        # fig_height = 7.5
        # fig_width = fig_height / aspect_ratio
        fig, axes = plt.subplots(4, 1, figsize=(15, 7.5), sharex=True)
        fig.suptitle(
            f'{pdata.file_stub}\nLocal Time = {t0}, Optical Visibility = {vis} meters\n'
            f'NETD V-Pol (30Hz) = {med_netd_1:.1f} mK, NETD H-Pol (30Hz) = {med_netd_2:.1f} mK'
        )
        for ax in axes:
            ax.set_ylabel('ZA (degrees)')
            ax.set_xlim(this_xlim)
            ax.set_ylim(this_ylim)

        # Vertical polarization
        im = axes[0].imshow(
            np.flip(np.transpose(mapp[0][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Blues_r',
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[0])
        cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)
        axes[0].contour(
            np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Horizontal polarization
        im = axes[1].imshow(
            np.flip(np.transpose(mapp[1][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Reds_r'
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[1])
        cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)
        axes[1].contour(
            np.flip(np.flip(np.transpose(flagged_map_2_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='black',
        )

        # Total signal
        im = axes[2].imshow(
            np.flip(np.transpose(total_map[::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Greys_r'
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[2])
        cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
        axes[2].contour(
            np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Optical Image
        optical_image = get_scaled_optical_image(dpix, pdata.optical_image, map_az, map_za)
        opt_vmax = 255.
        opt_vmin = -255  # NOTE: Shouldn't this be 0?
        im = axes[3].imshow(
            optical_image,
            extent=extent,
            aspect='equal',
            vmin=opt_vmin,
            vmax=opt_vmax,
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[3])
        cb.set_label('Optical Signal (rgb)', rotation=270, labelpad=15)
        axes[3].set_xlabel('Azimuth (degrees)')

        fig.subplots_adjust(wspace=0, hspace=0)

        if self.params['save_plot']:
            if self.params['savefile'] is None:
                # TODO: Move this to some global getter function
                self.params['savefile'] = pdata.folder / f'{pdata.file_stub}_Source_Finder_Image.png'
            if not self.params['savefile'].exists():
                self.params['savefile'].touch(PERMISSIONS_ALL_FULL)
            fig.savefig(self.params['savefile'], bbox_inches='tight')
        if self.params['show']:
            plt.show()

        plt.close(fig)


@ensure_path('savefile')
def animate_video(
    total_map: npt.NDArray,
    optical_video: npt.NDArray,
    interval_ms: float,
    extent: tuple[int, ...],
    repeat_delay_ms: float=2000,
    show: bool=False,
    savefile: Path=None,
) -> tuple[Figure, animation.FuncAnimation]:
    smoothed_map = np.transpose(total_map[..., ::-1], (0, 2, 1))
    # gaussian = np.ones((1,3,3)) / 16
    # gaussian[0, 1, 1] = 0.25
    # smoothed_map = signal.convolve(smoothed_map, gaussian)
    max_abs = 0.75 * np.max(np.abs(smoothed_map))
    vmax = max_abs
    vmin = -max_abs

    fig, axes = plt.subplots(2, 1, figsize=(5, 10), sharex=True)
    im_mm = axes[0].imshow(smoothed_map[0], vmin=vmin, vmax=vmax, animated=True, cmap='Greys_r', extent=extent, aspect='equal')
    im_opt = axes[1].imshow(optical_video[0], animated=True, extent=extent, aspect='equal')
    fig.subplots_adjust(wspace=0, hspace=0)
    add_colorbar_outside(im_mm, axes[0], 'right')

    def animation_func(i: int):
        im_mm.set_array(smoothed_map[i])
        im_opt.set_array(optical_video[i])

    an = animation.FuncAnimation(
        fig,
        animation_func,
        frames=total_map.shape[0],
        interval=interval_ms,
        repeat_delay=repeat_delay_ms,
    )
    if savefile is not None:
        an.save(savefile)
    if show:
        plt.show()
    return fig, an


@register_routine
class MakeVideo(DataRoutine):
    name = 'MakeVideo'
    version = '1.0.0'

    produces = {
        '/video/netd',
        '/video/hits_map',
        '/video/sum_map',
        '/video/map_az',
        '/video/map_za',
        '/video/cropped_optical_video',
        '/video/good_samples',
    }

    @ensure_path('savefile')
    def __init__(
            self,
            dataset: Literal['data_mK', 'data_freq']='data_mK',
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            med_netd_cut_threshold: float=3.,
            beam_map_mode: bool=False,
            dpix: int=DEFAULT_MAP_DPIX,
            block_size_s: float=1,
            plot: bool=True,
            savefile: Path=None,
            show: bool=False,
    ):
        if dataset not in ('data_mK', 'data_freq'):
            raise ValueError(f'Unable to use dataset {dataset} for BinTODIntoMap; choose "data_mK" or "data_freq".')
        if beam_map_mode:
            az_trim = 0.
            za_trim = 0.

        super().__init__(
            dataset=dataset,
            hp_filter_freq=hp_filter_freq,
            lp_filter_freq=lp_filter_freq,
            az_trim=az_trim,
            za_trim=za_trim,
            med_netd_cut_threshold=med_netd_cut_threshold,
            beam_map_mode=beam_map_mode,
            dpix=dpix,
            block_size_s=block_size_s,
            plot=plot,
            show=show,
            savefile=savefile,
        )

    def inputs(self, pdata: ProcessedData):
        dsets = []
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        for i_chan in range(pdata.n_chan):
            dsets.append(f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}')
        # dsets.append('/global_data/optical_video')
        # dsets.append('/global_data/optical_timestamp')
        return dsets

    def _initialize_map_arrays(
        self,
        pdata: ProcessedData,
        n_blocks: int,
        n_maps: int,
        n_pix_x: int,
        n_pix_y: int,
        optical_video_shape: tuple[int, ...],
        dpix: float,
        block_size_s: float,
    ):
        if pdata.has('video', exact_match=True):
            _logger.warning(f'{self.name}: Video group already exists in the file; overwriting datasets.')
            del pdata['video']
        video_group = pdata.create_group('video')
        video_group.create_dataset('map_az', shape=(n_pix_x,), dtype=np.float64)
        video_group.create_dataset('map_za', shape=(n_pix_y,), dtype=np.float64)
        video_group.create_dataset('netd', shape=(pdata.n_tones,), dtype=np.float64)
        video_group.create_dataset('sum_map', shape=(n_blocks, n_maps, n_pix_x, n_pix_y), chunks=(1, 1, n_pix_x, n_pix_y), dtype=np.float64)
        video_group.create_dataset('hits_map', shape=(n_blocks, n_maps, n_pix_x, n_pix_y), chunks=(1, 1, n_pix_x, n_pix_y), dtype=np.float64)
        video_group.create_dataset('cropped_optical_video', shape=(n_blocks, *optical_video_shape), chunks=(1, *optical_video_shape), dtype=np.int8)
        video_group.attrs['dpix'] = dpix
        video_group.attrs['block_size_s'] = block_size_s
        good_samples = video_group.create_dataset('good_samples', (pdata.n_chan,), dtype=h5py.vlen_dtype(np.uint32))
        for i_chan in range(pdata.n_chan):
            interpolated_samples = pdata.get_from_channel(i_chan, 'time_ordered_data/interpolated_samples')
            good_samples[i_chan] = np.setdiff1d(np.arange(pdata.n_samples), interpolated_samples)

    def run(self, pdata: ProcessedData, inputs: list[str]=None):
        dpix = self.params['dpix']
        beam_map_mode = self.params['beam_map_mode']
        block_size_s = self.params['block_size_s']
        blocks = np.arange(0, pdata.n_samples, int(pdata.fs * block_size_s))
        n_blocks = blocks.size - 1
        n_pix_x, n_pix_y, map_az, map_za = get_map_size(
            pdata.detector_az,
            pdata.detector_za,
            self.params['az_trim'],
            self.params['za_trim'],
            dpix,
            beam_map_mode=beam_map_mode,
        )
        n_maps = N_POLARIZATION if not beam_map_mode else self.n_tones

        # Determine optical video dimenmsions before intiializing arryas
        if np.size(pdata.optical_image) == 0:
            optical_image_shape = (0, 0, 0)
        else:
            scaled_optical_image = get_scaled_optical_image(dpix, pdata.optical_image[:], map_az, map_za)
            optical_image_shape = scaled_optical_image.shape

        self._initialize_map_arrays(pdata, n_blocks, n_maps, n_pix_x, n_pix_y, optical_image_shape, dpix, block_size_s)
        pdata['video/map_az'][:] = map_az
        pdata['video/map_za'][:] = map_za
        detector_az = pdata.detector_az
        detector_za = pdata.detector_za
        optical_video = pdata['video/cropped_optical_video']

        match self.params['dataset']:
            case 'data_mK':
                data = pdata.data_mK[:]
            case 'data_freq':
                data = pdata.data_freq_diss[0]

        sum_map = pdata['video/sum_map'][:]
        hits_map = pdata['video/hits_map'][:]
        netd = pdata['video/netd'][:]

        chanmask = pdata.chanmask[:]
        bad_tones = [
            1, 3, 223, 278, 299,
            303, 10, 69, 192, 820,
            263, 483, 172, 574, 426,
            569, 297, 167, 15, 717,
            487, 842, 453, 13, 719,
            92, 571, 630, 84, 220,
            364, 516, 74, 726, 292,
            519, 812, 302, 683, 537,
            294, 534, 256, 661, 529,
            737, 54, 782, 567, 103,
            330, 133, 809, 460, 589,
            387, 538, 213, 120, 79,
            783, 612, 121, 117, 749
        ]
        chanmask[bad_tones] = -1

        # Compute NETD values
        _logger.info(f'{self.name}: Computing netd...')
        wind = signal.get_window('hamming', pdata.n_samples)
        hp_filter_freq = self.params['hp_filter_freq']
        lp_filter_freq = self.params['lp_filter_freq']
        for i_tone in np.where(chanmask == 1)[0]:
            this_freq, this_psd = signal.periodogram(data[i_tone, :], pdata.fs, window=wind)
            valid_freq = np.where((this_freq > hp_filter_freq) & (this_freq < lp_filter_freq))
            netd[i_tone] = np.sqrt(np.median(this_psd[valid_freq]))
        _logger.info(f'{self.name}: Done computing netd')

        # Get rid of tones with bad weights
        med_netd_cut_threshold = self.params['med_netd_cut_threshold']
        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        chanmask[good_idx] = np.where(good_netd > med_netd_cut_threshold * np.nanmedian(good_netd), -1, chanmask[good_idx])

        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, chanmask[good_idx])
        chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, chanmask[good_idx])

        netd[chanmask != 1] = 0

        if beam_map_mode:
            tones_to_map = np.argwhere(pdata.chanmask != 0).flatten()
        else:
            tones_to_map = np.argwhere(chanmask == 1).flatten()

        # Create map
        _logger.info(f'{self.name}: Creating map...')
        for n_loop, i_tone in enumerate(tones_to_map):
            if n_loop == np.size(tones_to_map) // 2:
                _logger.info(f'{self.name}: Halfway done creating map...')
            if beam_map_mode:
                map_idx = i_tone
                weight = 1.
            else:
                map_idx = pdata.detector_pol[i_tone] - 1  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1./ netd[i_tone] ** 2.

            this_detector_az = detector_az[i_tone]
            this_detector_za = detector_za[i_tone]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_tone])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/dpix))
            y_ind = y_ind.astype('int64')

            #eliminate samples outside the map
            i_chan = pdata.get_channel_index_from_tone_index(i_tone)
            good_samples = pdata['video/good_samples'][i_chan][:]
            valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
                np.logical_and(x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x), \
                np.logical_and(y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y))))
            good_samples = good_samples[valid_index]

            #loop over samples to create sum and hits maps
            for i_block, block_end in enumerate(blocks[1:]):
                block_slice = slice(blocks[i_block], block_end)
                for time_sample in good_samples[block_slice]:
                    sum_map[i_block, map_idx, x_ind[time_sample],y_ind[time_sample]] += this_clean_data[time_sample] * weight
                    hits_map[i_block, map_idx, x_ind[time_sample],y_ind[time_sample]] += 1. * weight
        pdata.set_chanmask(chanmask)
        pdata['video/hits_map'][:] = hits_map
        pdata['video/sum_map'][:] = sum_map
        pdata['video/netd'][:] = netd
        _logger.info(f'{self.name}: Done creating maps.')

        # Optical Video processing
        if pdata.has('/global_data/optical_video', exact_match=True):
            optical_timestamp = pdata['global_data/optical_timestamp'][:]
            full_optical_video = pdata['global_data/optical_video']
            full_scaled_video = get_scaled_optical_image(dpix, full_optical_video, map_az, map_za)
            video_timestamp = np.zeros(n_blocks)
            for i_block, block_end in enumerate(blocks[1:]):
                block_slice = slice(blocks[i_block], block_end)
                timestamp_block = pdata.timestamp[block_slice]
                this_timestamp = np.mean(timestamp_block)
                video_timestamp[i_block] = this_timestamp
                closest_optical_frame = argclosest(optical_timestamp, this_timestamp)
                optical_video[i_block] = full_scaled_video[..., closest_optical_frame]
        else:
            optical_video[:] = np.repeat(scaled_optical_image[np.newaxis], n_blocks, axis=0)

        # TODO: Scale optical video to increase exposure

        # Animation
        with np.errstate(divide='ignore', invalid='ignore'):
            total_map = np.nansum(sum_map[:] / hits_map[:], axis=1)
        if self.params['plot']:
            _logger.info(f'{self.name}: Creating animation...')
            if self.params['savefile'] is None:
                self.params['savefile'] = str(pdata.folder / f'{pdata.file_stub}_Map_Animation.gif')
            animate_video(
                total_map,
                optical_video[:],
                1000 * block_size_s,
                get_extent(map_az, map_za, dpix),
                show=self.params['show'],
                savefile=self.params['savefile'],
            )
        return list(self.produces)