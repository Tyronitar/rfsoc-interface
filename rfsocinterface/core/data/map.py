"""Data routines for binning time-ordered data (TOD) into maps."""

from __future__ import annotations
import pdb

import numpy as np
import numpy.typing as npt
from scipy import signal
from scipy.spatial.distance import cdist
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from rfsocinterface.core.data.data import DEFAULT_MAP_DPIX, MapData, ProcessedData
from rfsocinterface.core.data.routines import DataRoutine, ProcessingStage, DataRoutine

class BasicMapRemoval(DataRoutine):
    def forward(self, map: MapData) -> MapData:
        map_data = map.data_mK
        nans_removed = map_data[np.isnan(map_data)]
        map_values = map_data[~np.isnan(map_data)]
        _, outlier_pixels = outlier_removal(map_values)
    
        flagged_values = np.concatenate((nans_removed, outlier_pixels))  # Add any flagged values to this list

        # Create a copy of map for later use if needed
        basic_removal_map = np.copy(map_data)

        for value in flagged_values:
            basic_removal_map[np.isclose(basic_removal_map, value)] = 1

        basic_removal_map[basic_removal_map != 1] = 0
        return map.with_values(data=basic_removal_map, flagged_values=flagged_values)


class DBSCANMapRemoval(DataRoutine):
    def __init__(self, eps: float=3, min_samples: int=2):
        #**eps**: Two points are considered neighbors if the distance between the two points is below the threshold epsilon.
        #**min_samples**: The minimum number of neighbors a given point should have in order to be classified as a core point
        #(^^^ this includes the point itself) 
        super().__init__()
        self.dbscan = DBSCAN(eps=eps, min_samples=min_samples)

    def forward(self, map: MapData) -> MapData:
        dbscan_map = map.data_mK[:]
        flagged_values = map.good_samples

        # Find the indices of the flagged pixels
        flagged_indices = np.where(np.isin(dbscan_map, flagged_values))
        flagged_points = np.column_stack(flagged_indices)

        labels = self.dbscan.fit_predict(flagged_points)

        # Extract the original values of pixels that are flagged in the map    
        flagged_pixel_values = dbscan_map[flagged_indices]

        # Create a new variable to store only the flagged values that pass the DBSCAN
        flagged_values_passing_dbscan = []

        # Iterate through each cluster label and mark the pixels that PASS the DBSCAN as 1s
        for cluster_label in np.unique(labels):
            if cluster_label == -1:  # Skip noise points
                continue

            cluster_indices = flagged_indices[0][labels == cluster_label]
            cluster_values = flagged_pixel_values[labels == cluster_label]

            # Check if the cluster has at least two samples (min_samples) to PASS the DBSCAN
            if len(cluster_values) >= 2:
                dbscan_map[cluster_indices] = 1
                # Add the values that passed DBSCAN to the new variable
                flagged_values_passing_dbscan.extend(cluster_values)


        dbscan_map[dbscan_map != 1] = 0
        
        return map.with_values(data=dbscan_map, flagged_values=np.array(flagged_values_passing_dbscan))


class NeighborRemoval(DataRoutine):
    def __init__(self, dist_threshold: float=4):
        super().__init__()
        self.dist_threshold = dist_threshold
    
    def forward(self, map: MapData) -> MapData:
        new_map = map.data_mK[:]
        flagged_values = map.good_samples

        # empty list to store the indices of flagged pixels
        flagged_indices = []

        # Find the indices of the flagged values in the flattened map
        for value in flagged_values:
            flagged_indices.extend(np.where(new_map.flatten() == value)[0])

        # Convert these indices to 2D coordinates
        flagged_coords = np.unravel_index(flagged_indices, new_map.shape)

        indices_to_keep = []

        for i, coord in enumerate(zip(*flagged_coords)):
            distances = []
            for j, other_coord in enumerate(zip(*flagged_coords)):
                if i != j:
                    distance = np.sqrt((coord[0] - other_coord[0])**2 + (coord[1] - other_coord[1])**2)
                    distances.append(distance)
            if np.sum(np.array(distances) < 4) >= 3:
                indices_to_keep.append(i)

        # Create a new variable for the flagged values that meet the criteria
        filtered_flagged_values = [flagged_values[i] for i in indices_to_keep]

        # Now set the corresponding pixels in map 1
        for index in indices_to_keep:
            new_map[flagged_coords[0][index], flagged_coords[1][index]] = 1

        new_map[new_map != 1] = 0
        return map.with_values(data=new_map, flagged_values=np.array(filtered_flagged_values))


class NeighborFlagging(DataRoutine):
    def __init__(
            self,
            margin: float=3,
            radius: float=4,
    ):
        super().__init__()
        self.margin = margin
        self.radius = radius
    
    def forward(self, map: MapData) -> MapData:
        new_map = map.data_mK[:]
        flagged_values = map.good_samples

        # Iterate over all flagged values
        for value in flagged_values:
            # Find the indices of flagged pixels
            indices = np.where(np.isclose(new_map, value))

            for idx in range(len(indices[0])):
                x, y = indices[0][idx], indices[1][idx]

                # Skip flagged pixels near the borders
                if x < self.margin or x >= new_map.shape[0] - self.margin or y < self.margin or y >= new_map.shape[1] - self.margin:
                    continue

                # Iterate through neighbors within the radius
                for i in range(-self.radius, self.radius+1):
                    for j in range(-self.radius, self.radius+1):
                        # Check if the neighbor is within the circular radius
                        if i**2 + j**2 > self.radius**2:
                            continue

                        #neighbor coordinates
                        nx, ny = x + i, y + j

                        # Check if neighbor is within bounds and not too close to borders
                        if nx >= self.margin and nx < new_map.shape[0] - self.margin and ny >= self.margin and ny < new_map.shape[1] - self.margin:
                            new_map[nx, ny] = 1

        new_map[new_map != 1] = 0
        return map.with_values(data=new_map)


def outlier_removal(data):
    map_pixels= data
    outlier_pixels = []
    sigma = np.std(map_pixels)
    
    while np.any((map_pixels > 3*sigma) | (map_pixels < -3*sigma)):
        for x in map_pixels:
            if x > 3*sigma or x < -3*sigma:
               outlier_pixels.append(x)
        map_pixels= [x for x in map_pixels if (x < 3*sigma) and (x > -3*sigma)]
        map_pixels=  np.array(map_pixels)
        sigma = np.std(map_pixels)
        if np.all((map_pixels < 3*sigma) & (map_pixels > -3*sigma)):
            final_pixels = map_pixels
    if np.size(outlier_pixels) == 0:
        outlier_pixels = map_pixels[0:1].tolist()
        final_pixels = map_pixels[1:]
    return final_pixels, np.array(outlier_pixels)



def get_map_size(detector_az: npt.NDArray, detector_za: npt.NDArray, az_trim: float, za_trim: float, map_dpix: float, beam_map_mode: bool=False) -> npt.NDArray:

    max_az = np.nanmax(detector_az) - az_trim
    min_az = np.nanmin(detector_az) + az_trim
    max_za = np.nanmax(detector_za) - za_trim
    min_za = np.nanmin(detector_za) + za_trim
    n_pix_x = int(np.ceil((max_az - min_az) / map_dpix))
    n_pix_y = int(np.ceil((max_za - min_za) / map_dpix))
    map_x = np.arange(n_pix_x) * map_dpix + min_az + map_dpix / 2.
    map_y = np.arange(n_pix_y) * map_dpix + min_za + map_dpix / 2.
    if not beam_map_mode:
        map_y += 0.1  # 0.1 accounts for assymmetry in array

    # if map.setnum in [1007, 1009]:
    #     np.savez('map_size.npz', n_pix_x, n_pix_y, map_x, map_y)
    # elif map.setnum in [1008, 1010]:
    #     data = np.load('map_size.npz')
    #     n_pix_x = data['arr_0']
    #     n_pix_y = data['arr_1']
    #     map_x = data['arr_2']
    #     map_y = data['arr_3']
    return n_pix_x, n_pix_y, map_x, map_y


def compute_kernel(
    r0: float=0.15,
    dpix: float=DEFAULT_MAP_DPIX,
    sigma: float=0.087/2.3,
):
    kernel_radius = int(r0 // dpix)  
    kernel_size = kernel_radius * 2 + 1  # Number of pixels to include in the kernel
    kernel_pos = np.linspace(-r0, r0, kernel_radius * 2 + 1)
    pos = np.array(np.meshgrid(kernel_pos, kernel_pos)).T.reshape(-1, 2)
    distances = cdist(pos, np.atleast_2d([0, 0]), 'sqeuclidean').reshape(kernel_size, kernel_size)
    kernel = np.exp(-np.pow(distances / (2 * sigma ** 2), 2))
    kernel[distances>r0] = 0
    return kernel


class BinTODIntoMap(DataRoutine):
    stage = ProcessingStage.POST_PROCESSING
    def __init__(
            self,
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            med_netd_cut_threshold: float=3.,
            beam_map_mode: bool=False,
            dataset: str='data_mK',
    ):
        super().__init__()
        self.hp_filter_freq = hp_filter_freq
        self.lp_filter_freq = lp_filter_freq
        self.med_netd_cut_threshold = med_netd_cut_threshold
        self.beam_map_mode = beam_map_mode
        self.dataset = dataset
        if beam_map_mode:
            self.az_trim = 0.
            self.za_trim = 0.
        else:
            self.az_trim = az_trim
            self.za_trim = za_trim

    def forward(
            self,
            md: MapData,
    ):

        n_pix_x, n_pix_y, map_az, map_za = get_map_size(md.detector_az, md.detector_za, self.az_trim, self.za_trim, DEFAULT_MAP_DPIX, self.beam_map_mode)
        md.setup_map_arrays(n_pix_x, n_pix_y, beammap_mode=self.beam_map_mode)
        md.map_az[:] = map_az
        md.map_za[:] = map_za

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
        md.chanmask[bad_tones] = -1

        wind = signal.get_window('hamming', md.n_samples)

        # data = getattr(md, self.dataset)[:]
        # if self.beam_map_mode:
        #     data = md.get_data_freq()
        # else:
        #     data = md.data_mK[:]
        data = md.data_mK[:]
        sum_map = np.zeros(md.sum_map.shape)
        hits_map = np.zeros(md.hits_map.shape)

        kernel = compute_kernel()

        print('computing netd...')
        # Compute NETD values
        for i_chan in np.where(md.chanmask[:] == 1)[0]:
            this_freq, this_psd = signal.periodogram(data[i_chan, :], md.fs, window=wind)
            valid_freq = np.where((this_freq > self.hp_filter_freq) & (this_freq < self.lp_filter_freq))
            this_netd = np.sqrt(np.median(this_psd[valid_freq]))
            md.netd[i_chan] = this_netd

        print('netd done!')

        # Get rid of channels with bad weights
        new_chanmask = np.copy(md.chanmask[:])
        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = md.netd[good_idx]
        new_chanmask[good_idx] = np.where(good_netd > self.med_netd_cut_threshold * np.nanmedian(good_netd), -1, new_chanmask[good_idx])

        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = md.netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        new_chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, new_chanmask[good_idx])
        new_chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, new_chanmask[good_idx])

        md.netd[new_chanmask != 1] = 0

        if self.beam_map_mode:
            channels_to_map = np.where(md.chanmask[:] != 0)[0]
        else:
            channels_to_map = np.where(new_chanmask == 1)[0]

        # Create map
        print('creating map...')
        for n_loop, i_chan in enumerate(channels_to_map):
            if n_loop == np.size(channels_to_map) // 2:
                print('halfway done...')
            if self.beam_map_mode:
                map_idx = i_chan
                weight = 1.
            else:
                map_idx = md.detector_pol[i_chan] - 1  # Polarization 1 -> Index 0, 2 -> 1, etc.
                weight = 1./ md.netd[i_chan] ** 2.

            this_detector_az = md.detector_az[i_chan,:]
            this_detector_za = md.detector_za[i_chan,:]

            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_chan,:])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/DEFAULT_MAP_DPIX))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/DEFAULT_MAP_DPIX))
            y_ind = y_ind.astype('int64')


            #eliminate samples outside the map
            good_samples = md.good_samples[:]
            valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
                np.logical_and(x_ind[good_samples] >= 0, x_ind[good_samples] < n_pix_x), \
                np.logical_and(y_ind[good_samples] >= 0, y_ind[good_samples] < n_pix_y))))
            good_samples = good_samples[valid_index]

            # #loop over samples to create sum and hits maps
            for time_sample in good_samples:
                sum_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += this_clean_data[time_sample] * weight
                hits_map[map_idx, x_ind[time_sample],y_ind[time_sample]] += 1. * weight
        # weights = 1 / netd[md.chanmask==1]**2
        # np.save('weight.npy', 1/all_NETDs**2)
        # plt.show()
        for map_idx in range(sum_map.shape[0]):
            sum_map[map_idx] = signal.convolve2d(sum_map[map_idx], kernel, mode='same')
            hits_map[map_idx] = signal.convolve2d(hits_map[map_idx], kernel, mode='same')
        md.chanmask[:] = new_chanmask
        md.sum_map[:] = sum_map
        md.hits_map[:] = hits_map

    def get_receipt_entry(self) -> str:
        return f'BinTODIntoMap: {{\n' \
               f'  hp_filter_freq: {self.hp_filter_freq},\n' \
               f'  lp_filter_freq: {self.lp_filter_freq},\n' \
               f'  az_trim: {self.az_trim},\n' \
               f'  za_trim: {self.za_trim},\n' \
               f'  med_netd_cut_threshold: {self.med_netd_cut_threshold},\n' \
               f'  dataset: {self.dataset},\n' \
               f'}}'

class MakeVideo(DataRoutine):
    stage = ProcessingStage.POST_PROCESSING

    def __init__(
        self,
        hp_filter_freq: float=0.5,
        lp_filter_freq: float=15.,
        az_trim: float=0.1,
        za_trim: float=0.2,
        med_netd_cut_threshold: float=3.,
        block_size_s: float=0.25,
        dpix: float=0.08,
    ):
        super().__init__()
        self.hp_filter_freq = hp_filter_freq
        self.lp_filter_freq = lp_filter_freq
        self.med_netd_cut_threshold = med_netd_cut_threshold
        self.az_trim = az_trim
        self.za_trim = za_trim
        self.block_size_s = block_size_s
        self.dpix = dpix
    
    def forward(self, md: MapData):
        # Bin along time dimension into time chunks
        # Create corresponding map for each time chunk
        # Connect all into a time stream of maps
        blocks = np.arange(0, md.n_samples, int(md.fs * self.block_size_s))
        n_blocks = blocks.size - 1
        n_pix_x, n_pix_y, map_az, map_za = get_map_size(
            md.detector_az,
            md.detector_za,
            self.az_trim,
            self.za_trim,
            self.dpix,
            False,
        )
        # md.setup_map_arrays(n_pix_x, n_pix_y)
        md.setup_map_video_arrays(n_pix_x, n_pix_y, n_blocks=n_blocks)
        sum_map = np.zeros(md.get_node_value('video_sum_map').shape)
        hits_map = np.zeros(md.get_node_value('video_hits_map').shape)
        md.map_az[:] = map_az
        md.map_za[:] = map_za

        wind = signal.get_window('hamming', md.n_samples)

        kernel = compute_kernel()

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
        md.chanmask[bad_tones] = -1

        data = md.data_mK[:]

        print('computing netd...')
        # Compute NETD values
        for i_chan in np.where(md.chanmask[:] == 1)[0]:
            this_freq, this_psd = signal.periodogram(data[i_chan, :], md.fs, window=wind)
            valid_freq = np.where((this_freq > self.hp_filter_freq) & (this_freq < self.lp_filter_freq))
            this_netd = np.sqrt(np.median(this_psd[valid_freq]))
            md.netd[i_chan] = this_netd

        print('netd done!')


        # Get rid of channels with bad weights
        new_chanmask = np.copy(md.chanmask[:])
        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = md.netd[good_idx]
        new_chanmask[good_idx] = np.where(good_netd > self.med_netd_cut_threshold * np.nanmedian(good_netd), -1, new_chanmask[good_idx])

        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = md.netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        new_chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, new_chanmask[good_idx])
        new_chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, new_chanmask[good_idx])

        md.netd[new_chanmask != 1] = 0

        channels_to_map = np.where(new_chanmask == 1)[0]

        # Create map
        print('creating map...')
        for n_loop, i_chan in enumerate(channels_to_map):
            if n_loop == np.size(channels_to_map) // 2:
                print('halfway done...')

            map_idx = md.detector_pol[i_chan] - 1  # Polarization 1 -> Index 0, 2 -> 1, etc.
            weight = 1./ md.netd[i_chan] ** 2.

            this_detector_az = md.detector_az[i_chan]
            this_detector_za = md.detector_za[i_chan]


            # Get the good samples if they haven't been specified
            this_clean_data = np.squeeze(data[i_chan,:])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/self.dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/self.dpix))
            y_ind = y_ind.astype('int64')

            #eliminate samples outside the map
            good_samples = md.good_samples[:]
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


        for i_block in range(n_blocks):
            for map_idx in range(sum_map.shape[1]):
                sum_map[i_block, map_idx] = signal.convolve2d(sum_map[i_block, map_idx], kernel, mode='same')
                hits_map[i_block, map_idx] = signal.convolve2d(hits_map[i_block, map_idx], kernel, mode='same')
        this_map = sum_map / hits_map
        total_map = np.nansum(this_map, axis=1)

        smoothed_map = np.transpose(total_map[..., ::-1], (0, 2, 1))
        gaussian = np.ones((1,3,3)) / 16
        gaussian[0, 1, 1] = 0.25
        smoothed_map = signal.convolve(smoothed_map, gaussian)
        max_abs = 0.75 * np.max(np.abs(smoothed_map))
        vmax = max_abs
        vmin = -max_abs

        def get_image_i(i: int) -> npt.NDArray:
            return smoothed_map[i]
            # im = np.flip(
            # gaussian = np.ones((3,3)) / 16
            # gaussian[1, 1] = 0.25
            # return signal.convolve2d(im, gaussian)

        
        im = plt.imshow(get_image_i(0), vmin=vmin, vmax=vmax, animated=True, cmap='Greys_r')
        plt.colorbar()
        an = animation.FuncAnimation(
            plt.gcf(),
            lambda i: im.set_array(get_image_i(i)),
            frames=total_map.shape[0],
            interval=1000 * self.block_size_s,
            repeat_delay=2000,
        )
        an.save('video.gif')
        plt.show()
        pdb.set_trace()
            

def find_bad_resonators_in_image(data: MapData, za_step: float=0.025):
    bad_resonators = []
    for za in np.arange(np.min(data.map_za), np.max(data.map_za), za_step):
        fig, ax = plt.subplots()
        slice_data = []
        for i_tone in range(data.n_tones):
            if data.chanmask[i_tone] != 1 or i_tone in bad_resonators:
                continue
            # Get the samples for this detector that are in the correct ZA slice
            this_det_za = data.detector_za[i_tone]
            samples = np.where((this_det_za >= za) & (this_det_za < za + za_step))[0]
            if samples.size > 0:
                slice_data.append((i_tone, samples))
                ax.plot(data.detector_az[i_tone, samples], data.data_mK[i_tone, samples], label=f'Tone {i_tone}')
        ax.set_title(f'ZA slice: {za:.2f} - {za + za_step:.2f}')
        ax.set_xlabel('Detector Azimuth (degrees)')
        ax.set_ylabel('Detector Response (mK)')
        ax.legend()
        fig.show()
        pdb.set_trace()

    return bad_resonators



if __name__ == '__main__':
    from rfsocinterface.core.data.routines import DataRoutine, CleanTOD, HighPassFilter, LowPassFilter
    date = '20260227'
    setnum = 1009

    data = MapData.from_file(date, setnum)
    find_bad_resonators_in_image(data)

    pdb.set_trace()
