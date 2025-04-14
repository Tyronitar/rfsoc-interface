"""Functions for creating a map from data."""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Any

import h5py
import numpy as np
import numpy.typing as npt
from scipy import signal, ndimage
from sklearn.cluster import DBSCAN

from rfsocinterface.core.utils import ensure_path
from rfsocinterface.core.data import ProcessedData, MapData

DECIMATE_ORDER = 5
BUTTER_ORDER = 6
AZ_TRIM = 2.3
ZA_TRIM = 0.2


def get_map_size(map: MapData, az_trim: float, za_trim: float, map_dpix: float) -> npt.NDArray:

    max_az = np.max(map.azimuth) - az_trim
    min_az = np.min(map.azimuth) + az_trim
    max_za = np.max(map.zenith_angle) - za_trim
    min_za = np.min(map.zenith_angle) + za_trim
    n_pix_x = int(np.ceil((max_az - min_az) / map_dpix))
    n_pix_y = int(np.ceil((max_za - min_za) / map_dpix))
    map_coords = np.mgrid[0:n_pix_x, 0:n_pix_y]
    map_x = np.arange(n_pix_x) * map_dpix + min_az + map_dpix / 2.
    map_y = np.arange(n_pix_x) * map_dpix + min_za + map_dpix / 2. + 0.1  # 0.1 accounts for assymmetry in array

    return n_pix_x, n_pix_y, map_x, map_y


def _unimplemented_forward(self, *args):
    raise NotImplementedError(
        f'DataRoutine [{type(self).__name__}] is missing a forward method'
    )
  

class DataRoutine:
    forward: Callable[..., Any] = _unimplemented_forward

    def __init__(self):
        self._receipt = ''

    def __call__(self, *input, **kwargs):
        output = self.forward(*input, **kwargs)
        # do something to the receipt...
        return output


class Mapper:
    def __init__(self, routines: list[DataRoutine]):
        self._routines = routines
    
    def __call__(self, input: ProcessedData):

        output = input
        for routine in self._routines:
            output = routine(output)
        return output


class CleanTOD(DataRoutine):

    def __init__(
            self,
            ds_factor: int=6,
            hp_filt_freq: float=0.5,
            lp_filt_freq: float=10.,
    ):
        super().__init__()
        self.hp_filt_freq = hp_filt_freq
        self.lp_filt_freq = lp_filt_freq
        self.ds_factor = ds_factor

    def forward(self, processed_data: ProcessedData) -> MapData:
            #Setup filters that will be used later
        #get the sampling frequency and make a window that can be
        #used later for the power spectrum computation

        data_raw = processed_data.data_mK
        chanmask = processed_data.chanmask
        detector_az = processed_data.detector_az
        detector_za = processed_data.detector_za
        detector_pol = processed_data.detector_pol

        timestamp = processed_data.timestamp - processed_data.timestamp[0]
        dtime = timestamp - np.roll(timestamp, 1)
        
        fs = float(1./np.median(dtime))
        hpfilt_sos = signal.butter(BUTTER_ORDER, self.hp_filt_freq, 'hp', fs=fs/self.ds_factor, output='sos', analog=False)
        lpfilt_sos = signal.butter(BUTTER_ORDER, self.lp_filt_freq, 'lp', fs=fs/self.ds_factor, output='sos', analog=False)

        #downsample the data and apply hp filter
        data_ds = signal.decimate(data_raw, self.ds_factor)
        data_filt_1 = signal.sosfiltfilt(hpfilt_sos, data_ds)
        data_filt = signal.sosfiltfilt(lpfilt_sos, data_filt_1)

        #average template subtraction
        goodchan = np.ndarray.flatten(np.argwhere(chanmask == 1))
        data_filt_chanmask = data_filt[goodchan,:]
        template = np.sum(data_filt_chanmask, axis=0)
        template = template - np.mean(template)
        template_corr = np.sum(np.multiply(data_filt_chanmask,template), axis=1) / \
                        np.sum(np.multiply(template,template))
        data_clean_chanmask = data_filt_chanmask - np.outer(template_corr, template)
        data_clean = data_filt
        data_clean[goodchan,:] = data_clean_chanmask

        #downsample ancillary data
        time_ds = signal.decimate(timestamp, self.ds_factor)
        detector_az_ds = signal.decimate(detector_az, self.ds_factor, n=DECIMATE_ORDER, axis=1)
        detector_za_ds = signal.decimate(detector_za, self.ds_factor, n=DECIMATE_ORDER, axis=1)

        return MapData(
            data_clean,
            detector_az_ds,
            detector_za_ds,
            detector_pol,
            time_ds,
            chanmask=processed_data.chanmask,
        )


class RemovePointLomaPickup(DataRoutine):
    def __init__(self, ds_factor: int=6, pickup_filter_freq: float=1):
        super().__init__()
        self.ds_factor = ds_factor
        self.pickup_filter_freq = pickup_filter_freq
    
    def forward(self, data_raw: ProcessedData) -> npt.NDArray:
        #need to high pass filter the data to remove basline drift
        data_raw = data_raw.data_mK
        timestamp = data_raw.timestamp
        chanmask = data_raw.chanmask

        time = timestamp - timestamp[0]

        dtime = time - np.roll(time,1)
        fs = float(1./np.median(dtime))
        pickup_hpfilt_sos = signal.butter(6, self.pickup_hp_filt_freq, 'hp', fs=fs, output='sos', analog=False)

        #sum all the data at each time sample, then look for outliers in this sum
        data_sum_raw = np.zeros(np.size(data_raw[0,:]))
        for i_chan in range(np.size(chanmask)):
            if chanmask[i_chan] == 1:      
                data_sum_raw += np.abs(data_raw[i_chan,:])
        data_sum = signal.sosfiltfilt(pickup_hpfilt_sos, data_sum_raw)

        pickup_data = np.ndarray.flatten(np.argwhere(np.abs(data_sum) > 5.*np.median(np.abs(data_sum))))
        pickup_good_index = []
        valid_time = np.arange(np.size(data_sum))
        if np.size(pickup_data > 0):
            pickup_start = pickup_data[np.argwhere(pickup_data - np.roll(pickup_data,1) != 1)]
            pickup_end = pickup_data[np.argwhere(np.roll(pickup_data,-1) - pickup_data != 1)]
            for i_start in pickup_start:
                pickup_data = np.append(pickup_data, i_start - 1 - np.arange(10))
            for i_end in pickup_end:
                pickup_data = np.append(pickup_data, i_end + 1 + np.arange(10))
            pickup_data.sort()
            valid_pickup = np.ndarray.flatten(np.argwhere(np.bitwise_and(pickup_data >= 0,pickup_data < np.size(valid_time))))
            pickup_data = pickup_data[valid_pickup]
            pickup_good_index = [element for element in np.arange(np.size(valid_time)) if element not in pickup_data]
            pickup_good_index = np.divide(pickup_good_index[0::self.ds_factor], self.ds_factor)
            pickup_good_index = pickup_good_index.astype(int)

        return np.array(pickup_good_index)


class BinTODIntoMap(DataRoutine):
    def __init__(
            self,
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            map_dpix: float=0.04,
    ):
        super().__init__()
        self.hp_filter_freq = hp_filter_freq
        self.lp_filter_freq = lp_filter_freq
        self.az_trim = az_trim
        self.za_trim = za_trim
        self.map_dpix = map_dpix
    
    def forward(
            self,
            map_data: MapData,
            pickup_good_index: npt.NDArray=[],
    ) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
        detector_pol = map_data.polarization
        detector_az = map_data.azimuth
        detector_za = map_data.zenith_angle
        fs = map_data.fs
        data_clean = map_data.data

        print(get_map_size(map_data, self.az_trim, self.za_trim, self.map_dpix))
        exit()

        if np.size(pickup_good_index) == 0:
            pickup_good_index = np.arange(data_clean.shape[1])

        for i, pol in enumerate([1, 2]):
            channel_index = np.argwhere(detector_pol == 1)
            NETD = np.zeros((np.size(channel_index)))
            for index, i_chan in enumerate(channel_index):
                this_clean_data = data_clean[i_chan,:]
                this_detector_az = detector_az[i_chan,:]
                this_detector_za = detector_za[i_chan,:]
                wind = signal.get_window('hamming', data_clean.shape[1])
                this_freq, this_psd = signal.periodogram(this_clean_data, fs, window=wind)
                valid_freq = np.where(this_freq > self.hp_filter_freq and this_freq < self.lp_filter_freq)
                NETD[index] = np.sqrt(np.median(this_psd[valid_freq]))
            #    NETD[index] = np.sqrt(np.median(this_psd[-int(np.size(this_psd)/2):]*30.))
                weight = 1./NETD[index]**2.

                #get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
                x_ind = np.round((detector_az-map_az[0])/map_dpix)
                x_ind = x_ind.astype('int64')
                y_ind = np.round((detector_el-map_el[0])/map_dpix)
                y_ind = y_ind.astype('int64')
            
    
    def _inner(self, sum_map, hits_map, NETD, map_dpix, index, data_cleaned, detector_az, detector_el, fs, map_az, map_el, hp_filt_freq, lp_filt_freq, pickup_good_index = []):

        #get the good samples if they haven't been specified
        if np.size(pickup_good_index) == 0:
            pickup_good_index = np.arange(np.size(data_cleaned))

        #compute NETD in white noise regime
        wind = signal.get_window('hamming', np.size(data_cleaned))
        this_freq, this_psd = signal.periodogram(data_cleaned, fs, window=wind)
        valid_freq = np.where(np.logical_and(this_freq>hp_filt_freq,this_freq<lp_filt_freq))
        NETD[index] = np.sqrt(np.median(this_psd[valid_freq]))
    #    NETD[index] = np.sqrt(np.median(this_psd[-int(np.size(this_psd)/2):]*30.))
        weight = 1./NETD[index]**2.
    
        #get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
        x_ind = np.round((detector_az-map_az[0])/map_dpix)
        x_ind = x_ind.astype('int64')
        y_ind = np.round((detector_el-map_el[0])/map_dpix)
        y_ind = y_ind.astype('int64')

        #eliminate samples outside the map
        valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
            np.logical_and(x_ind[pickup_good_index] >= 0, x_ind[pickup_good_index] < np.size(sum_map[:,0])), \
            np.logical_and(y_ind[pickup_good_index] >= 0, y_ind[pickup_good_index] < np.size(sum_map[0,:])))))
        pickup_good_index = pickup_good_index[valid_index]

    #    pdb.set_trace()
        #loop over samples to create sum and hits maps
        for time_sample in pickup_good_index:
            sum_map[x_ind[time_sample],y_ind[time_sample]] += data_cleaned[time_sample] * weight
            hits_map[x_ind[time_sample],y_ind[time_sample]] += 1. * weight

        return sum_map, hits_map, NETD
            

class Smooth(DataRoutine):
    def __init__(self, gaussian_sigma: tuple[float, float]=(0.5, 0.33)):
        super().__init__()
        self.gaussian_sigma = gaussian_sigma
    
    def forward(self, data: MapData) -> npt.NDArray:
        smoothed_data = ndimage.gaussian_filter(
            data,
            self.gaussian_sigma,
            mode='reflect',
            truncate=1. / self.gaussian_sigma[1],
        )
        return data.with_values(data=smoothed_data)


class BasicMapRemoval(DataRoutine):
    def forward(self, map: MapData) -> MapData:
        map_data = map.data
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
        dbscan_map = map.data[:]
        flagged_values = map.flagged_values

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
        new_map = map.data[:]
        flagged_values = map.flagged_values

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
        new_map = map.data[:]
        flagged_values = map.flagged_values

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

if __name__ == '__main__':
    data = ProcessedData('20250414', 1001, losweep="/data/20250414/20250414_rfsoc2_LO_Sweep_hour16p3303.h5")
    cleaner = CleanTOD()
    map = cleaner.forward(data)

    binner = BinTODIntoMap()
    map1 = binner.forward(map)