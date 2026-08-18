"""Data processing code for generating maps."""

import logging
import time
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Literal

import av
import h5py
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib import animation
from matplotlib.figure import Figure
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import signal
from scipy.spatial.distance import cdist

from rfsocinterface.core.data.routines import (
    DataRoutine,
    RoutineResult,
    register_routine,
)
from rfsocinterface.core.data.storage import ProcessedData
from rfsocinterface.core.data.utils import (
    DEFAULT_MAP_DPIX,
    N_POLARIZATION,
    OPTCAM_HEIGHT_PIXELS,
    OPTCAM_OFFSET_AZ_PIX,
    OPTCAM_OFFSET_ZA_PIX,
    OPTCAM_PIX_SIZE_DEGREES,
    OPTCAM_WIDTH_PIXELS,
    get_channel_group_name,
)
from rfsocinterface.core.utils import (
    GAUSSIAN_SIGMA,
    PERMISSIONS_ALL_FULL,
    add_colorbar_outside,
    argclosest,
    ensure_path,
    gaussian_filter,
)

_logger = logging.getLogger(__name__)


def plot_map(
    map_data: npt.NDArray,
    map_x: npt.NDArray,
    map_y: npt.NDArray,
    ax: plt.Axes | None = None,
    extent: tuple[float, float, float, float] | None = None,
    max_abs: float | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    flagged_map: npt.NDArray = None,
    contour_levels: npt.NDArray = None,
    cb_label: str = 'Signal (mK)',
    cmap: str = 'Greys_r',
    title: str = '',
    add_x_label: bool = True,
    dpix: float | None = DEFAULT_MAP_DPIX,
) -> Figure | None:
    """Create a plot for a map."""
    xlim = min(map_x), max(map_x)
    ylim = max(map_y), min(map_y)
    if extent is None:
        extent = get_extent(map_x, map_y, dpix=dpix)

    if max_abs is None:
        max_abs = np.nanmax(np.abs(map_data))

    fig = None
    if ax is None:
        fig = plt.figure()
        ax = plt.gca()
    im = ax.imshow(
        np.flip(np.transpose(map_data[::-1]), 1),
        aspect='equal',
        extent=extent,
        vmin=vmin if vmin is not None else -max_abs,
        vmax=vmax if vmax is not None else max_abs,
        cmap=cmap,
    )
    # Color bar
    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='5%', pad=0.05)
    cb = plt.colorbar(im, cax=cax)
    cb.set_label(cb_label, rotation=270, labelpad=15)

    # cb = plt.colorbar(im, shrink=cb_shrink)
    # cb.set_label(cb_label, rotation=270, labelpad=15)
    if flagged_map:
        ax.contour(
            np.flip(np.flip(np.transpose(flagged_map[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )
    ax.set_title(title)
    if add_x_label:
        ax.set_xlabel('Azimuth (degrees)')
    ax.set_ylabel('ZA (degrees)')
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    return fig


def get_scaled_optical_image(
    dpix: float,
    optical_image: npt.NDArray,
    map_az: npt.NDArray,
    map_za: npt.NDArray,
    optcam_pix_size_degrees: float = OPTCAM_PIX_SIZE_DEGREES,
    optcam_offset_az_pix: float = OPTCAM_OFFSET_AZ_PIX,
    optcam_offset_za_pix: float = OPTCAM_OFFSET_ZA_PIX,
    optcam_height_pixels: int = OPTCAM_HEIGHT_PIXELS,
    optcam_width_pixels: int = OPTCAM_WIDTH_PIXELS,
) -> npt.NDArray:
    """Scale the optical image to match the pixel scale of the map."""
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


def get_extent(
    map_az: npt.NDArray, map_za: npt.NDArray, dpix: float = DEFAULT_MAP_DPIX
) -> tuple[float, float, float, float]:
    """Get the extent of the map for plotting."""
    return (
        min(map_az) - dpix / 2.0,
        max(map_az) + dpix / 2,
        max(map_za) + dpix / 2.0,
        min(map_za) - dpix / 2.0,
    )


def get_map_size(
    detector_az: h5py.Dataset,
    detector_za: h5py.Dataset,
    az_trim: float,
    za_trim: float,
    dpix: float = DEFAULT_MAP_DPIX,
    beam_map_mode: bool = False,
) -> tuple[int, int, npt.NDArray, npt.NDArray]:
    """Determine map size based on detector positions and desired pixel size."""
    max_az = np.nanmax(detector_az) - az_trim
    min_az = np.nanmin(detector_az) + az_trim
    max_za = np.nanmax(detector_za) - za_trim
    min_za = np.nanmin(detector_za) + za_trim
    n_pix_x = int(np.ceil((max_az - min_az) / dpix))
    n_pix_y = int(np.ceil((max_za - min_za) / dpix))
    map_x = np.arange(n_pix_x) * dpix + min_az + dpix / 2.0
    map_y = np.arange(n_pix_y) * dpix + min_za + dpix / 2.0
    if not beam_map_mode:
        map_y += 0.1  # 0.1 accounts for assymmetry in array

    return n_pix_x, n_pix_y, map_x, map_y


def compute_map_kernel(
    r0: float = 0.15,
    dpix: float = DEFAULT_MAP_DPIX,
    sigma: float = 0.087 / 2.3,
) -> npt.NDArray:
    """Compute a Gaussian kernel for smoothing the map.

    Arguemnts:
        r0 (float, optional): The radius of the kernel in degrees. Defaults to 0.15
            degrees.
        dpix (float, optional): The pixel size of the map in degrees. Defaults to 0.03
            degrees.
        sigma (float, optional): The standard deviation of the Gaussian kernel in
            degrees. Defaults to 0.087/2.3 degrees.
    """
    kernel_pos = np.arange(-r0, r0 + dpix, dpix)
    if 0 not in kernel_pos:
        kernel_pos = np.insert(kernel_pos, np.searchsorted(kernel_pos, 0), 0)
    kernel_size = kernel_pos.size
    pos = np.array(np.meshgrid(kernel_pos, kernel_pos)).T.reshape(-1, 2)
    distances = cdist(pos, np.atleast_2d([0, 0]), 'sqeuclidean').reshape(
        kernel_size, kernel_size
    )
    kernel = np.exp(-np.pow(distances / (2 * sigma**2), 2))
    kernel[distances > r0] = 0
    return kernel


@register_routine
class BinTODIntoMap(DataRoutine):
    """Bin time-ordered data into a map based on telescope pointing information.

    Creates the following items in the HDF5 file:
    - /map: group containing the map datasets.
    - /map/map_az: 1D array of azimuth values for the map pixels.
    - /map/map_za: 1D array of zenith angle values for the map pixels.
    - /map/netd: 1D array of length n_tones containing the NETD values for each tone.
    - /map/sum_map: 3D array of shape (n_maps, n_pix_x, n_pix_y) containing the sum
        of the data values for each pixel.
    - /map/hits_map: 3D array of shape (n_maps, n_pix_x, n_pix_y) containing the
        number of hits for each pixel.
    - /map/map_val: 3D array of shape (n_maps, n_pix_x, n_pix_y) containing
        the binned map values (i.e. sum_map / hits_map).
    - /map/total_map: 2D array of shape (n_pix_x, n_pix_y) containing
        the total map values (sum over all maps).
    - /map/good_samples: 2D variable length array of length n_chan containing the
        indices of the good samples for each channel.

    """

    name = 'BinTODIntoMap'
    version = '2.2.0'

    produces: ClassVar[set] = {
        '/map/',
        '/map/netd',
        '/map/hits_map',
        '/map/sum_map',
        '/map/map_val',
        '/map/total_map',
        '/map/map_az',
        '/map/map_za',
        '/map/good_samples',
    }

    def __init__(
        self,
        dataset: Literal['data_mK', 'data_freq'] = 'data_mK',
        hp_filter_freq: float = 0.5,
        lp_filter_freq: float = 10.0,
        med_netd_cut_threshold: float = 3.0,
        az_trim: float = 2.3,
        za_trim: float = 0.2,
        beam_map_mode: bool = False,
        dpix: int = DEFAULT_MAP_DPIX,
        r0: float = 0.15,
        sigma: float = 0.087 / 2.3,
    ):
        """Initialize the BinTODIntoMap routine.

        Arguments:
            dataset (str, optional): The name of the dataset to clean. Must be either
                'data_mK' or 'data_freq'. Defaults to 'data_mK'.
            hp_filter_freq (float, optional): The cutoff frequency for the high-pass
                filter applied to the data when computing NETD values.
            lp_filter_freq (float, optional): The cutoff frequency for the low-pass
                filter applied to the data when computing NETD values.
            med_netd_cut_threshold (float, optional): The threshold for cutting tones
                based on their NETD values.
            az_trim (float, optional): The amount to trim from the edges of the map in
                the azimuth direction, in degrees. Defaults to 2.3 degrees.
            za_trim (float, optional): The amount to trim from the edges of the map in
                the zenith angle direction, in degrees. Defaults to 0.2 degrees.
            beam_map_mode (bool, optional): Whether to create a beam map instead of a
                polarization map.
            dpix (float, optional): The pixel size of the map in degrees. Defaults to
                0.03 degrees.
            r0 (float, optional): The radius of the kernel used for smoothing the map,
                in degrees. Defaults to 0.15 degrees.
            sigma (float, optional): The standard deviation of the Gaussian kernel used
                for smoothing the map, in degrees. Defaults to 0.087/2.3 degrees, which
                corresponds to a FWHM of 0.087 degrees (the approximate beam size of
                SKIPR).
        """
        if dataset not in ('data_mK', 'data_freq'):
            msg = (
                f'{self.name}: Unable to use dataset {dataset}; choose "data_mK" or '
                '"data_freq".'
            )
            _logger.error(msg)
            raise ValueError(msg)
        if beam_map_mode:
            az_trim = 0.0
            za_trim = 0.0

        super().__init__(
            dataset=dataset,
            hp_filter_freq=hp_filter_freq,
            lp_filter_freq=lp_filter_freq,
            med_netd_cut_threshold=med_netd_cut_threshold,
            az_trim=az_trim,
            za_trim=za_trim,
            beam_map_mode=beam_map_mode,
            dpix=dpix,
            r0=r0,
            sigma=sigma,
        )

    @typing.override
    def _inputs(self, pdata: ProcessedData):
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        return [
            f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}'
            for i_chan in range(pdata.n_chan)
        ]

    def _initialize_map_arrays(
        self,
        pdata: ProcessedData,
        n_maps: int,
        n_pix_x: int,
        n_pix_y: int,
        dpix: float,
    ):
        """Initialize the map arrays in the ProcessedData object.

        Overwrites existing "map" group if it already exists.
        """
        if pdata.has('map', exact_match=True):
            _logger.warning(
                f'{self.name}: Map group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['map']
        map_group = pdata.create_group('map')
        map_group.create_dataset('map_az', shape=(n_pix_x,), dtype=np.float64)
        map_group.create_dataset('map_za', shape=(n_pix_y,), dtype=np.float64)
        map_group.create_dataset(
            'sum_map',
            shape=(n_maps, n_pix_x, n_pix_y),
            chunks=(1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        map_group.create_dataset(
            'hits_map',
            shape=(n_maps, n_pix_x, n_pix_y),
            chunks=(1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        map_group.create_dataset(
            'map_val',
            shape=(n_maps, n_pix_x, n_pix_y),
            chunks=(1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        map_group.create_dataset(
            'total_map',
            shape=(n_pix_x, n_pix_y),
            chunks=(n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        map_group.create_dataset('netd', shape=(pdata.n_tones,), dtype=np.float64)
        map_group.attrs['dpix'] = dpix
        map_group.attrs['units'] = (
            'mK' if self.params['dataset'] == 'data_mK' else 'df/f'
        )
        good_samples = map_group.create_dataset(
            'good_samples', (pdata.n_chan,), dtype=h5py.vlen_dtype(np.uint32)
        )
        for i_chan in range(pdata.n_chan):
            interpolated_samples = pdata.get_from_channel(
                i_chan, 'time_ordered_data/interpolated_samples'
            )
            good_samples[i_chan] = np.setdiff1d(
                np.arange(pdata.n_samples), interpolated_samples
            )

    @typing.override
    def _run(self, pdata: ProcessedData, inputs: list[str]):
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
        n_maps = N_POLARIZATION if not beam_map_mode else pdata.n_tones
        self._initialize_map_arrays(pdata, n_maps, n_pix_x, n_pix_y, dpix)
        pdata['map/map_az'][:] = map_az
        pdata['map/map_za'][:] = map_za
        detector_az = pdata.detector_az
        detector_za = pdata.detector_za

        match self.params['dataset']:
            case 'data_mK':
                data = pdata.data_mK[:]
            case 'data_freq':  # df / f
                data = pdata.data_freq_diss[0] / pdata.detector_f()[:, np.newaxis]

        sum_map = pdata['map/sum_map'][:]
        hits_map = pdata['map/hits_map'][:]
        netd = pdata['map/netd'][:]

        chanmask = pdata.chanmask[:]

        # Compute NETD values
        _logger.info(f'{self.name}: Computing netd...')
        wind = signal.get_window('hamming', pdata.n_samples)
        hp_filter_freq = self.params['hp_filter_freq']
        lp_filter_freq = self.params['lp_filter_freq']
        for i_tone in np.where(chanmask == 1)[0]:
            this_freq, this_psd = signal.periodogram(
                data[i_tone, :], pdata.fs, window=wind
            )
            valid_freq = np.where(
                (this_freq > hp_filter_freq) & (this_freq < lp_filter_freq)
            )
            netd[i_tone] = np.sqrt(np.median(this_psd[valid_freq]))
        _logger.info(f'{self.name}: Done computing netd')

        # Get rid of tones with bad weights
        if not beam_map_mode:
            med_netd_cut_threshold = self.params['med_netd_cut_threshold']
            good_idx = np.argwhere(chanmask == 1).flatten()
            good_netd = netd[good_idx]
            chanmask[good_idx] = np.where(
                good_netd > med_netd_cut_threshold * np.nanmedian(good_netd),
                -1,
                chanmask[good_idx],
            )

            good_idx = np.argwhere(chanmask == 1).flatten()
            good_netd = netd[good_idx]
            netd_med = np.median(np.log10(good_netd))
            netd_std = np.std(np.log10(good_netd))
            chanmask[good_idx] = np.where(
                good_netd > 10 ** (netd_med + netd_std * 2), -1, chanmask[good_idx]
            )
            chanmask[good_idx] = np.where(
                good_netd < 10 ** (netd_med - netd_std * 2), -1, chanmask[good_idx]
            )

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
                weight = 1.0
            else:
                map_idx = (
                    pdata.detector_pol[i_tone] - 1
                )  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1.0 / netd[i_tone] ** 2.0

            this_detector_az = detector_az[i_tone]
            this_detector_za = detector_za[i_tone]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_tone])

            # Get this detector's positions, need to account for rotation in EL based on
            # beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az - map_az[0]) / dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za - map_za[0]) / dpix))
            y_ind = y_ind.astype('int64')

            # eliminate samples outside the map
            i_chan = pdata.get_channel_index_from_tone_index(i_tone)
            good_samples = pdata['map/good_samples'][i_chan][:]
            valid_index = np.ndarray.flatten(
                np.argwhere(
                    np.logical_and(
                        np.logical_and(
                            x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x
                        ),
                        np.logical_and(
                            y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y
                        ),
                    )
                )
            )
            good_samples = good_samples[valid_index]

            # #loop over samples to create sum and hits maps
            for time_sample in good_samples:
                sum_map[map_idx, x_ind[time_sample], y_ind[time_sample]] += (
                    this_clean_data[time_sample] * weight
                )
                hits_map[map_idx, x_ind[time_sample], y_ind[time_sample]] += (
                    1.0 * weight
                )

        # Create kernel and convolve with map to get more accurate values for pixels
        # with few hits.
        kernel = compute_map_kernel(
            r0=self.params['r0'], dpix=dpix, sigma=self.params['sigma']
        )
        for map_idx in range(n_maps):
            sum_map[map_idx] = signal.convolve2d(sum_map[map_idx], kernel, mode='same')
            hits_map[map_idx] = signal.convolve2d(
                hits_map[map_idx], kernel, mode='same'
            )

        if not beam_map_mode:
            pdata.set_chanmask(chanmask)
        pdata['map/hits_map'][:] = hits_map
        pdata['map/sum_map'][:] = sum_map
        with np.errstate(divide='ignore', invalid='ignore'):
            pdata['map/map_val'][:] = sum_map / hits_map
            pdata['map/total_map'][:] = np.sum(sum_map, axis=0) / np.sum(
                hits_map, axis=0
            )
        pdata['map/netd'][:] = netd
        _logger.info(f'{self.name}: Done creating map.')

        return RoutineResult(
            modified={'input': ('/vdsets/tones',)},
            created={'input': self.produces},
        )


@register_routine
class PlotMap(DataRoutine):
    """Plot the map created by BinTODIntoMap.

    Creates the following items in the HDF5 file:
    - /map/plotting: group containing the plotting datasets.
    - /map/plotting/flagged_map_1: 2D array of shape (n_pix_x, n_pix_y) containing
        the flagged pixels based on the first map (e.g. polarization 1).
    - /map/plotting/flagged_map_2: 2D array of shape (n_pix_x, n_pix_y) containing
        the flagged pixels based on the second map (e.g. polarization 2).
    - /map/plotting/flagged_total_map: 2D array of shape (n_pix_x, n_pix_y)
        containing the flagged pixels based on the total map
    - /map/plotting/contour_levels: 1D array containing the contour levels used for
        plotting the flagged pixels.
    """

    name = 'PlotMap'
    version = '2.2.0'

    requires: ClassVar[set] = {
        '/map',
        '/map/map_az',
        '/map/map_za',
        '/map/netd',
        '/map/hits_map',
        '/map/map_val',
        '/map/total_map',
    }

    produces: ClassVar[set] = {
        '/map/plotting',
        '/map/plotting/flagged_map_1',
        '/map/plotting/flagged_map_2',
        '/map/plotting/flagged_total_map',
        '/map/plotting/contour_levels',
    }

    @ensure_path('savefile')
    def __init__(
        self,
        gaussian_sigma: float = GAUSSIAN_SIGMA,
        valid_covariance_threshold: float = 0.5,
        cb_shrink: float = 0.95,
        max_abs_threshold: float = 0.75,
        save_plot: bool = True,
        savefile: Path | None = None,
        show: bool = False,
        keep_figure_open: bool = False,
        overwrite: bool = True,
    ):
        """Initialize the PlotMap routine.

        Arguments:
            gaussian_sigma (float, optional): The standard deviation of the Gaussian
                kernel for for determining flagged pixels. Defaults to GAUSSIAN_SIGMA.
            valid_covariance_threshold (float, optional): The threshold for determining
                whether a pixel is flagged based on the covariance of the maps. Defaults
                to 0.5.
            cb_shrink (float, optional): The shrink factor for the colorbar in the plot.
                Defaults to 0.95.
            max_abs_threshold (float, optional): The maximum absolute value multiplier
                for the color scale in the plot. Defaults to 0.75.
            save_plot (bool, optional): Whether to save the plot as a PNG file. Defaults
                to True.
            savefile (Path, optional): The path to save the plot PNG file. If None, the
                plot will be saved in the same directory as the HDF5 file. Defaults to
                None.
            show (bool, optional): Whether to display the plot. Defaults to False.
            keep_figure_open (bool, optional): Whether to keep the figure open after
                plotting. Defaults to False.
            overwrite (bool, optional): Whether to overwrite existing plotting datasets
                in the HDF5 file. Defaults to True.
        """
        super().__init__(
            gaussian_sigma=gaussian_sigma,
            valid_covariance_threshold=valid_covariance_threshold,
            cb_shrink=cb_shrink,
            max_abs_threshold=max_abs_threshold,
            save_plot=save_plot,
            savefile=savefile,
            show=show,
            keep_figure_open=keep_figure_open,
            overwrite=overwrite,
        )

    @typing.override
    def _inputs(self, pdata: ProcessedData):
        return self.requires

    @typing.override
    def _run(self, pdata: ProcessedData, inputs: list[str]):
        reset_arrays = self._intialize_arrays(pdata)
        if reset_arrays:
            self._get_combined_map(pdata)
        fig = self._plot(pdata)

        created = {'input': self.produces} if reset_arrays else {}
        values = {'input': fig} if fig is not None else {}
        return RoutineResult(
            created=created,
            value=values,
        )

    def _intialize_arrays(self, pdata: ProcessedData) -> bool:
        """Initialize the plotting datasets in the ProcessedData object.

        If the plotting datasets already exist and overwrite is set to False,
        this function will return False and not modify the existing datasets.
        If overwrite is True, it will delete the existing plotting group and
        create new datasets. If the plotting datasets do not already exist,
        it will create them and return True.

        Returns:
            (bool): Whether new plotting datasets were created (True) or existing
                datasets were used (False).
        """
        if pdata.has('map/plotting', exact_match=True):
            if not self.params['overwrite']:
                # Specified not to overwrite existing plotting datasets, so just
                # plot the data without recomputing the maps.
                return False
            _logger.info(
                'Plotting group already exists in the file; overwriting datasets.'
            )
            del pdata['map/plotting']
        pdata['map'].create_group('plotting')
        return True

    def _get_combined_map(
        self, pdata: ProcessedData
    ) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
        """Get the combined map of flagged pixels."""
        sigma = self.params['gaussian_sigma']
        map_val = pdata['map/map_val']
        total_map = pdata['map/total_map']
        flagged_map_1 = gaussian_filter(map_val[0], sigma)
        flagged_map_2 = gaussian_filter(map_val[1], sigma)
        flagged_map_3 = gaussian_filter(total_map, sigma)

        # Convert all nans to boolean True
        nan_map_1 = np.isnan(flagged_map_1)
        nan_map_2 = np.isnan(flagged_map_2)
        nan_map_3 = np.isnan(flagged_map_3)

        # Combine the boolean maps such that if any pixel is flagged in any map, it is
        # flagged in the combined map
        combined_nan_map = np.logical_or(np.logical_or(nan_map_1, nan_map_2), nan_map_3)

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

    def _plot(self, pdata: ProcessedData) -> Figure | None:
        """Plot the maps using matplotlib.

        Plot will have 4 subplots: V-Pol map, H-Pol map, total map, and the optical
        image.
        """
        hits_map = pdata['map/hits_map']
        map_val = pdata['map/map_val'][:]
        total_map = pdata['map/total_map'][:]
        flagged_map_1_filt = pdata['map/plotting/flagged_map_1'][:]
        flagged_map_2_filt = pdata['map/plotting/flagged_map_2'][:]
        flagged_map_tot_filt = pdata['map/plotting/flagged_total_map'][:]
        contour_levels = pdata['map/plotting/contour_levels']
        dpix = pdata['map'].attrs['dpix']
        units = pdata['map'].attrs.get('units', 'mK')

        map_az = pdata['map/map_az']
        map_za = pdata['map/map_za']
        extent = get_extent(map_az, map_za, dpix)

        valid_cov_1 = np.argwhere(hits_map[0] > 0.5 * np.median(hits_map[0]))
        map_goodcov_1 = np.zeros(np.size(valid_cov_1[:, 0]))
        for i_cov in np.arange(np.size(valid_cov_1[:, 0])):
            map_goodcov_1[i_cov] = map_val[
                0, valid_cov_1[i_cov, 0], valid_cov_1[i_cov, 1]
            ]
        valid_cov_2 = np.argwhere(hits_map[1] > 0.5 * np.median(hits_map[1]))
        map_goodcov_2 = np.zeros(np.size(valid_cov_2[:, 0]))
        for i_cov in np.arange(np.size(valid_cov_2[:, 0])):
            map_goodcov_2[i_cov] = map_val[
                1, valid_cov_2[i_cov, 0], valid_cov_2[i_cov, 1]
            ]

        netd = pdata['map/netd']
        netd_1 = netd[pdata.pol_ind_1]
        netd_2 = netd[pdata.pol_ind_2]
        valid_netd_1 = np.argwhere(netd_1 > 0)
        valid_netd_2 = np.argwhere(netd_2 > 0)

        cb_shrink = self.params['cb_shrink']
        max_abs_threshold = self.params['max_abs_threshold']
        this_xlim = min(map_az), max(map_az)
        this_ylim = max(map_za), min(map_za)
        max_abs = (
            np.max(np.abs(np.append(map_goodcov_1, map_goodcov_2))) * max_abs_threshold
        )
        med_netd_1 = 1.0 / np.sqrt(
            np.sum(1.0 / netd_1[valid_netd_1] ** 2) / np.size(valid_netd_1)
        )
        med_netd_2 = 1.0 / np.sqrt(
            np.sum(1.0 / netd_2[valid_netd_2] ** 2) / np.size(valid_netd_2)
        )

        t0 = time.asctime(time.localtime(pdata.timestamp[0] - 7500))
        vis = pdata.optical_visibility[()]

        # TODO: Make figure size change based on the size of the map
        # aspect_ratio = (this_ylim[0] - this_ylim[1]) / (this_xlim[1] - this_xlim[0])
        # fig_height = 7.5
        # fig_width = fig_height / aspect_ratio
        fig, axes = plt.subplots(4, 1, figsize=(15, 7.5), sharex=True)
        fig.suptitle(
            f'{pdata.file_stub}\nLocal Time = {t0}, Optical Visibility = {vis} meters\n'
            f'NETD V-Pol (30Hz) = {med_netd_1:.1f} {units},'
            f' NETD H-Pol (30Hz) = {med_netd_2:.1f} {units}'
        )
        for ax in axes:
            ax.set_ylabel('ZA (degrees)')
            ax.set_xlim(this_xlim)
            ax.set_ylim(this_ylim)

        # Vertical polarization
        im = axes[0].imshow(
            np.flip(np.transpose(map_val[0][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Blues_r',
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[0])
        cb.set_label(f'V-Pol Signal ({units})', rotation=270, labelpad=15)
        axes[0].contour(
            np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Horizontal polarization
        im = axes[1].imshow(
            np.flip(np.transpose(map_val[1][::-1]), 1),
            extent=extent,
            aspect='equal',
            vmin=-max_abs,
            vmax=max_abs,
            cmap='Reds_r',
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[1])
        cb.set_label(f'H-Pol Signal ({units})', rotation=270, labelpad=15)
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
            cmap='Greys_r',
        )
        cb = fig.colorbar(im, shrink=cb_shrink, ax=axes[2])
        cb.set_label(f'Total Signal ({units})', rotation=270, labelpad=15)
        axes[2].contour(
            np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0),
            levels=contour_levels,
            extent=extent,
            colors='red',
        )

        # Optical Image
        optical_image = get_scaled_optical_image(
            dpix, pdata.optical_image, map_az, map_za
        )
        opt_vmax = 255.0
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
                self.params['savefile'] = (
                    pdata.folder / f'{pdata.file_stub}_Source_Finder_Image.png'
                )
            if not self.params['savefile'].exists():
                self.paramsp['savefile'].parent.mkdir(
                    mode=PERMISSIONS_ALL_FULL, parents=True, exist_ok=True
                )
                self.params['savefile'].touch(PERMISSIONS_ALL_FULL)
            fig.savefig(self.params['savefile'], bbox_inches='tight')
        if self.params['show']:
            plt.show()

        if not self.params['keep_figure_open']:
            plt.close(fig)
        return fig


@ensure_path('savefile')
def animate_video(
    total_map: npt.NDArray,
    optical_video: npt.NDArray,
    interval_ms: float,
    extent: tuple[int, ...],
    max_abs_threshold: float = 0.75,
    repeat_delay_ms: float = 2000,
    show: bool = False,
    savefile: Path | None = None,
) -> tuple[Figure, animation.FuncAnimation]:
    """Animate the video of the map evolution over time.

    Arguments:
        total_map (npt.NDArray): 3D array of shape (n_frames, n_pix_x, n_pix_y)
            containing the total map values for each frame.
        optical_video (npt.NDArray): 4D array of shape (n_frames, height, width, 3)
            containing the optical video frames for each frame.
        interval_ms (float): The interval between frames in milliseconds.
        extent (tuple[int, ...]): The extent of the map in the format (xmin, xmax, ymin,
             ymax).
        max_abs_threshold (float, optional): The maximum absolute value multiplier for
            the color scale in the animation. Defaults to 0.75.
        repeat_delay_ms (float, optional): The delay between repeats of the animation in
            milliseconds. Defaults to 2000 ms.
        show (bool, optional): Whether to display the animation. Defaults to False.
        savefile (Path, optional): The path to save the animation file. If None, the
            animation will not be saved. Defaults to None.
    """
    smoothed_map = np.transpose(total_map, (0, 2, 1))
    max_abs = max_abs_threshold * np.max(np.abs(smoothed_map))
    vmax = max_abs
    vmin = -max_abs
    vmax = 500
    vmin = -500

    fig, axes = plt.subplots(2, 1, figsize=(5, 10), sharex=True)
    im_mm = axes[0].imshow(
        smoothed_map[0],
        vmin=vmin,
        vmax=vmax,
        animated=True,
        cmap='Greys_r',
        extent=extent,
        aspect='equal',
    )
    im_opt = axes[1].imshow(
        optical_video[0], animated=True, extent=extent, aspect='equal'
    )
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
    """Create a video of the map evolution over time.

    Creates the following items in the HDF5 file:
    - /video: group containing the video datasets
    - /video/map_az: 1D array of azimuth values for the map pixels
    - /video/map_za: 1D array of zenith angle values for the map pixels
    - /video/netd: 1D array of length n_tones containing the NETD values for each tone
    - /video/sum_map: 4D array of shape (n_blocks, n_maps, n_pix_x, n_pix_y) containing
        the sum of the data values for each pixel, for each time block.
    - /video/hits_map: 4D array of shape (n_blocks, n_maps, n_pix_x, n_pix_y) containing
        the number of hitsfor each pixel, for each time block.
    - /video/map_val: 4D array of shape (n_blocks, n_maps, n_pix_x, n_pix_y) containing
        the binned map values (i.e. sum_map / hits_map).
    - /video/total_map: 3D array of shape (n_blocks, n_pix_x, n_pix_y) containing
        the total map values (sum over all maps).
    - /video/good_samples: 2D variable length array of length n_chan containing the
        indices of the good samples for each channel
    - /video/cropped_optical_video: 4D array of shape (n_blocks, height, width, 3)
        containing the cropped optical video frames for each time block.
    """

    name = 'MakeVideo'
    version = '1.2.0'

    produces: ClassVar[set] = {
        '/video',
        '/video/netd',
        '/video/hits_map',
        '/video/sum_map',
        '/video/map_val',
        '/video/total_map',
        '/video/map_az',
        '/video/map_za',
        '/video/cropped_optical_video',
        '/video/good_samples',
    }

    @ensure_path('savefile')
    def __init__(
        self,
        dataset: Literal['data_mK', 'data_freq'] = 'data_mK',
        hp_filter_freq: float = 0.5,
        lp_filter_freq: float = 10.0,
        med_netd_cut_threshold: float = 3.0,
        max_abs_threshold: float = 0.75,
        az_trim: float = 2.3,
        za_trim: float = 0.2,
        beam_map_mode: bool = False,
        dpix: int = DEFAULT_MAP_DPIX,
        r0: float = 0.15,
        sigma: float = 0.087 / 2.3,
        block_size_s: float = 1,
        plot: bool = True,
        show: bool = False,
        savefile: Path | None = None,
        overwrite: bool = True,
    ):
        """Initialize the MakeVideo routine.

        Arguments:
            dataset (str, optional): The name of the dataset to clean. Must be either
                'data_mK' or 'data_freq'. Defaults to 'data_mK'.
            hp_filter_freq (float, optional): The cutoff frequency for the high-pass
                filter applied to the data when computing NETD values.
            lp_filter_freq (float, optional): The cutoff frequency for the low-pass
                filter applied to the data when computing NETD values.
            med_netd_cut_threshold (float, optional): The threshold for cutting tones
                based on their NETD values.
            max_abs_threshold (float, optional): The maximum absolute value multiplier
                for the color scale in the plot. Defaults to 0.75.
            az_trim (float, optional): The amount to trim from the edges of the map in
                the azimuth direction, in degrees. Defaults to 2.3 degrees.
            za_trim (float, optional): The amount to trim from the edges of the map in
                the zenith angle direction, in degrees. Defaults to 0.2 degrees.
            beam_map_mode (bool, optional): Whether to create a beam map instead of a
                polarization map.
            dpix (float, optional): The pixel size of the map in degrees. Defaults to
                0.03 degrees.
            r0 (float, optional): The radius of the kernel used for smoothing the map,
                in degrees. Defaults to 0.15 degrees.
            sigma (float, optional): The standard deviation of the Gaussian kernel used
                for smoothing the map, in degrees. Defaults to 0.087/2.3 degrees, which
                corresponds to a FWHM of 0.087 degrees (the approximate beam size of
                SKIPR).
            block_size_s (float, optional): The size of the blocks in seconds to divide
                the data into when creating the video. Defaults to 1 second.
            plot (bool, optional): Whether to create an animated plot of the video.
                Defaults to True.
            show (bool, optional): Whether to display the animated plot. Defaults to
                False.
            savefile (Path, optional): The path to save the animated plot to. If None,
                the animation will not be saved.
            overwrite (bool, optional): Whether to overwrite existing video datasets
                in the HDF5 file. Defaults to True.
        """
        if dataset not in ('data_mK', 'data_freq'):
            msg = (
                f'{self.name}: Unable to use dataset {dataset}; choose "data_mK" or '
                '"data_freq".'
            )
            _logger.error(msg)
            raise ValueError(msg)
        if beam_map_mode:
            az_trim = 0.0
            za_trim = 0.0

        super().__init__(
            dataset=dataset,
            hp_filter_freq=hp_filter_freq,
            lp_filter_freq=lp_filter_freq,
            med_netd_cut_threshold=med_netd_cut_threshold,
            max_abs_threshold=max_abs_threshold,
            az_trim=az_trim,
            za_trim=za_trim,
            beam_map_mode=beam_map_mode,
            dpix=dpix,
            r0=r0,
            sigma=sigma,
            block_size_s=block_size_s,
            plot=plot,
            show=show,
            savefile=savefile,
            overwrite=overwrite,
        )

    @typing.override
    def _inputs(self, pdata: ProcessedData):
        dataset = self.params['dataset']
        if dataset == 'data_freq':
            dataset = 'data_freq_diss'
        return [
            f'/channels/{get_channel_group_name(i_chan)}/time_ordered_data/{dataset}'
            for i_chan in range(pdata.n_chan)
        ]
        # dsets.append('/global_data/optical_video')
        # dsets.append('/global_data/optical_timestamp')

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
        """Initialize the datasets for the video in the ProcessedData object.

        If the 'video' group already exists, it will overwrite it and create new
        datasets.
        """
        if pdata.has('video', exact_match=True):
            _logger.warning(
                f'{self.name}: Video group already exists in the file; '
                'overwriting datasets.'
            )
            del pdata['video']
        video_group = pdata.create_group('video')
        video_group.create_dataset('map_az', shape=(n_pix_x,), dtype=np.float64)
        video_group.create_dataset('map_za', shape=(n_pix_y,), dtype=np.float64)
        video_group.create_dataset('netd', shape=(pdata.n_tones,), dtype=np.float64)
        video_group.create_dataset(
            'sum_map',
            shape=(n_blocks, n_maps, n_pix_x, n_pix_y),
            chunks=(1, 1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        video_group.create_dataset(
            'hits_map',
            shape=(n_blocks, n_maps, n_pix_x, n_pix_y),
            chunks=(1, 1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        video_group.create_dataset(
            'map_val',
            shape=(n_blocks, n_maps, n_pix_x, n_pix_y),
            chunks=(1, 1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        video_group.create_dataset(
            'total_map',
            shape=(n_blocks, n_pix_x, n_pix_y),
            chunks=(1, n_pix_x, n_pix_y),
            dtype=np.float64,
        )
        video_group.create_dataset(
            'cropped_optical_video',
            shape=(n_blocks, *optical_video_shape),
            chunks=(1, *optical_video_shape),
            dtype=np.uint8,
        )
        video_group.attrs['dpix'] = dpix
        video_group.attrs['block_size_s'] = block_size_s
        good_samples = video_group.create_dataset(
            'good_samples', (pdata.n_chan,), dtype=h5py.vlen_dtype(np.uint32)
        )
        for i_chan in range(pdata.n_chan):
            interpolated_samples = pdata.get_from_channel(
                i_chan, 'time_ordered_data/interpolated_samples'
            )
            good_samples[i_chan] = np.setdiff1d(
                np.arange(pdata.n_samples), interpolated_samples
            )

    def _compute_new_maps(self, pdata: ProcessedData):  # noqa: PLR0912, PLR0915
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
            scaled_optical_image = get_scaled_optical_image(
                dpix, pdata.optical_image[:], map_az, map_za
            )
            optical_image_shape = scaled_optical_image.shape

        if 'optical_video_file' in pdata['global_data'].attrs:
            container = av.open(pdata['global_data'].attrs['optical_video_file'])
            video = container.streams.video[0]
            n_frames = video.frames
            shape = (video.height, video.width, 3, n_frames)
            full_optical_video = np.zeros(shape, dtype=np.uint8)
            _logger.info(f'{self.name}: Reading optical video from mp4 file...')
            for i_frame, frame in enumerate(container.decode(video=0)):
                full_optical_video[..., i_frame] = frame.to_ndarray(format='rgb24')
            _logger.info(f'{self.name}: Finished reading optical video.')
            scaled_optical_image = get_scaled_optical_image(
                dpix, full_optical_video[..., 0], map_az, map_za
            )
            optical_image_shape = scaled_optical_image.shape
        elif 'optical_video' in pdata['global_data']:
            full_optical_video = pdata['global_data/optical_video']
        else:
            msg = (
                f'{self.name}: Could not find optical video for provided '
                'procesed dataset.'
            )
            raise ValueError(msg)

        self._initialize_map_arrays(
            pdata,
            n_blocks,
            n_maps,
            n_pix_x,
            n_pix_y,
            optical_image_shape,
            dpix,
            block_size_s,
        )
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

        # Compute NETD values
        _logger.info(f'{self.name}: Computing netd...')
        wind = signal.get_window('hamming', pdata.n_samples)
        hp_filter_freq = self.params['hp_filter_freq']
        lp_filter_freq = self.params['lp_filter_freq']
        for i_tone in np.where(chanmask == 1)[0]:
            this_freq, this_psd = signal.periodogram(
                data[i_tone, :], pdata.fs, window=wind
            )
            valid_freq = np.where(
                (this_freq > hp_filter_freq) & (this_freq < lp_filter_freq)
            )
            netd[i_tone] = np.sqrt(np.median(this_psd[valid_freq]))
        _logger.info(f'{self.name}: Done computing netd')

        # Get rid of tones with bad weights
        med_netd_cut_threshold = self.params['med_netd_cut_threshold']
        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        chanmask[good_idx] = np.where(
            good_netd > med_netd_cut_threshold * np.nanmedian(good_netd),
            -1,
            chanmask[good_idx],
        )

        good_idx = np.argwhere(chanmask == 1).flatten()
        good_netd = netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        chanmask[good_idx] = np.where(
            good_netd > 10 ** (netd_med + netd_std * 2), -1, chanmask[good_idx]
        )
        chanmask[good_idx] = np.where(
            good_netd < 10 ** (netd_med - netd_std * 2), -1, chanmask[good_idx]
        )

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
                weight = 1.0
            else:
                map_idx = (
                    pdata.detector_pol[i_tone] - 1
                )  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1.0 / netd[i_tone] ** 2.0

            this_detector_az = detector_az[i_tone]
            this_detector_za = detector_za[i_tone]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_tone])

            # Get this detector's positions, need to account for rotation in EL based on
            # beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az - map_az[0]) / dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za - map_za[0]) / dpix))
            y_ind = y_ind.astype('int64')

            # eliminate samples outside the map
            i_chan = pdata.get_channel_index_from_tone_index(i_tone)
            good_samples = pdata['video/good_samples'][i_chan][:]
            valid_index = np.ndarray.flatten(
                np.argwhere(
                    np.logical_and(
                        np.logical_and(
                            x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x
                        ),
                        np.logical_and(
                            y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y
                        ),
                    )
                )
            )
            good_samples = good_samples[valid_index]

            # loop over samples to create sum and hits maps
            for i_block, block_end in enumerate(blocks[1:]):
                block_slice = slice(blocks[i_block], block_end)
                for time_sample in good_samples[block_slice]:
                    sum_map[
                        i_block, map_idx, x_ind[time_sample], y_ind[time_sample]
                    ] += this_clean_data[time_sample] * weight
                    hits_map[
                        i_block, map_idx, x_ind[time_sample], y_ind[time_sample]
                    ] += 1.0 * weight

        # Create kernel and convolve with map to get more accurate values for pixels
        # with few hits
        kernel = compute_map_kernel(
            r0=self.params['r0'], dpix=dpix, sigma=self.params['sigma']
        )
        for i_block in range(n_blocks):
            for map_idx in range(n_maps):
                sum_map[i_block, map_idx] = signal.convolve2d(
                    sum_map[i_block, map_idx], kernel, mode='same'
                )
                hits_map[i_block, map_idx] = signal.convolve2d(
                    hits_map[i_block, map_idx], kernel, mode='same'
                )

        pdata.set_chanmask(chanmask)
        pdata['video/hits_map'][:] = hits_map
        pdata['video/sum_map'][:] = sum_map
        with np.errstate(divide='ignore', invalid='ignore'):
            pdata['video/map_val'][:] = sum_map / hits_map
            total_map = np.nansum(sum_map[:] / hits_map[:], axis=1)
        pdata['video/total_map'][:] = total_map
        pdata['video/netd'][:] = netd
        _logger.info(f'{self.name}: Done creating maps.')

        # Optical Video processing
        if pdata.has('global_data/optical_video_timestamp', exact_match=True):
            _logger.info(f'{self.name}: Synchronizing mm and optical videos...')
            optical_timestamp = pdata['global_data/optical_video_timestamp'][:]
            full_scaled_video = get_scaled_optical_image(
                dpix, full_optical_video, map_az, map_za
            )
            video_timestamp = np.zeros(n_blocks)
            for i_block, block_end in enumerate(blocks[1:]):
                block_slice = slice(blocks[i_block], block_end)
                timestamp_block = pdata.timestamp[block_slice]
                this_timestamp = np.mean(timestamp_block)
                video_timestamp[i_block] = this_timestamp
                closest_optical_frame = argclosest(optical_timestamp, this_timestamp)
                optical_video[i_block] = full_scaled_video[..., closest_optical_frame]
        else:
            optical_video[:] = np.repeat(
                scaled_optical_image[np.newaxis], n_blocks, axis=0
            )

        optical_video[:] = np.clip(optical_video[:], 0, 127)
        optical_video[:] = optical_video[:] * 2

    @typing.override
    def _run(self, pdata: ProcessedData, inputs: Sequence[str] = []):
        if self.params['overwrite']:
            self._compute_new_maps(pdata)

        # Use existing datasets and make the video
        map_az = pdata['video/map_az'][:]
        map_za = pdata['video/map_za'][:]
        optical_video = pdata['video/cropped_optical_video'][:]

        total_map = pdata['video/total_map'][:]
        block_size_s = pdata['video'].attrs['block_size_s']
        dpix = pdata['video'].attrs['dpix']

        # Animation
        if self.params['plot']:
            _logger.info(f'{self.name}: Creating animation...')
            if self.params['savefile'] is None:
                savefile = str(pdata.folder / f'{pdata.file_stub}_Map_Animation.mp4')
            else:
                savefile = self.params['savefile']
            animate_video(
                total_map,
                optical_video[:],
                1000 * block_size_s,
                get_extent(map_az, map_za, dpix),
                max_abs_threshold=self.params['max_abs_threshold'],
                show=self.params['show'],
                savefile=savefile,
            )
        modified = {'input': self.produces} if not self.params['overwrite'] else {}
        created = {'input': self.produces} if self.params['overwrite'] else {}
        return RoutineResult(
            modified=modified,
            created=created,
        )
