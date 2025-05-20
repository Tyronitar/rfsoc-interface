"""Functions for creating a map from data."""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Any
import pdb

import h5py
import numpy as np
import numpy.typing as npt
from scipy import signal, ndimage
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import gaussian_filter, GAUSSIAN_SIGMA
from rfsocinterface.core.data import N_POLARIZATION, ProcessedData, MapData, remove_electronics_noise, rotate_basis, generate_calibrated_data

DECIMATE_ORDER = 5
BUTTER_ORDER = 6
AZ_TRIM = 2.3
ZA_TRIM = 0.2
def get_map_size(map: MapData, az_trim: float, za_trim: float, map_dpix: float) -> npt.NDArray:

    max_az = np.max(map.detector_az) - az_trim
    min_az = np.min(map.detector_az) + az_trim
    max_za = np.max(map.detector_za) - za_trim
    min_za = np.min(map.detector_za) + za_trim
    n_pix_x = int(np.ceil((max_az - min_az) / map_dpix))
    n_pix_y = int(np.ceil((max_za - min_za) / map_dpix))
    map_x = np.arange(n_pix_x) * map_dpix + min_az + map_dpix / 2.
    map_y = np.arange(n_pix_y) * map_dpix + min_za + map_dpix / 2. + 0.1  # 0.1 accounts for assymmetry in array

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
    
    def add_routine(self, routine: DataRoutine):
        if not isinstance(routine, DataRoutine):
            raise TypeError(f'Expected DataRoutine, got {type(routine)}')
        self._routines.append(routine)
    
    def __call__(self, input: ProcessedData, save: bool=True):

        output = input
        for routine in self._routines:
            # if isinstance(routine, BinTODIntoMap):
            #     pdb.set_trace()
            output = routine(output)
        if save:
            output.save()
        return output


class RemoveElectronicsNoise(DataRoutine):
    def __init__(self):
        super().__init__()
    
    def forward(pd: ProcessedData) -> ProcessedData:
        gain_phase_data = pd.data_gain_phase
        clean_gain_phase_data = remove_electronics_noise(gain_phase_data)

        new_data_freq_diss, new_data_mK = generate_calibrated_data(
            clean_gain_phase_data,
            pd.IQ_to_gain_phase_angle,
            pd.dIQ_df,
            pd.df_per_mK
        )
        return pd.with_values(
            data_gain_phase=clean_gain_phase_data,
            data_freq_diss=new_data_freq_diss,
            data_mK=new_data_mK,
        )


class CleanTOD(DataRoutine):

    def __init__(
            self,
            save_file: bool=True,
    ):
        super().__init__()
        self.save_file = save_file

    def forward(self, md: MapData) -> MapData:

        if not isinstance(md, MapData):
            md = MapData.from_processed_data(md)
        data = md.data_mK
        chanmask = md.chanmask
        data_clean = np.copy(data)
        good_samples = md.get_good_samples()
        
        #average template subtraction
        goodchan = np.ndarray.flatten(np.argwhere(chanmask == 1))
        # pdb.set_trace()
        data_good = data[goodchan][:, good_samples]
        template = np.sum(data_good, axis=0)
        template = template - np.mean(template)
        template_corr = np.sum(np.multiply(data_good,template), axis=1) / \
                        np.sum(np.multiply(template,template))
        data_clean_good = data_good - np.outer(template_corr, template)
        data_clean[goodchan][:, good_samples] = data_clean_good

        if self.save_file:
            with h5py.File(md.cleaned_file_template, 'w') as cfile:
                cfile.create_dataset("chanmask", data=chanmask)
                cfile.create_dataset("detector_pol", data=md.detector_pol)
                cfile.create_dataset("clean_data", data=data_clean)
                cfile.create_dataset("time", data=md.timestamp)
                cfile.create_dataset("detector_az", data=md.detector_az)    
                cfile.create_dataset("detector_za", data=md.detector_za)


        return md.with_values(
            data_mK=data_clean,
        )


class RemovePointLomaPickup(DataRoutine):
    def __init__(self, ds_factor: int=6, pickup_filter_freq: float=1):
        super().__init__()
        self.ds_factor = ds_factor
        self.pickup_filter_freq = pickup_filter_freq
    
    def forward(self, pd: ProcessedData) -> MapData:
        #need to high pass filter the data to remove basline drift
        data_raw = pd.data_mK
        chanmask = pd.chanmask

        pickup_hpfilt_sos = signal.butter(6, self.pickup_filter_freq, 'hp', fs=pd.fs, output='sos', analog=False)

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

        m = MapData.from_processed_data(pd)
        m.good_samples = np.array(pickup_good_index)
        # pdb.set_trace()
        return m


class BinTODIntoMap(DataRoutine):
    def __init__(
            self,
            hp_filter_freq: float=0.5,
            lp_filter_freq: float=10.,
            az_trim: float=2.3,
            za_trim: float=0.2,
            med_netd_cut_threshold: float=3.,
    ):
        super().__init__()
        self.hp_filter_freq = hp_filter_freq
        self.lp_filter_freq = lp_filter_freq
        self.med_netd_cut_threshold = med_netd_cut_threshold
        self.az_trim = az_trim
        self.za_trim = za_trim
    
    def forward(
            self,
            md: ProcessedData,
    ) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray, npt.NDArray]:
        if not isinstance(md, MapData):
            md = MapData.from_processed_data(md)
        detector_pol = md.detector_pol
        detector_az = md.detector_az
        detector_za = md.detector_za
        fs = md.fs
        data_clean = md.data_mK

        n_pix_x, n_pix_y, map_az, map_za = get_map_size(md, self.az_trim, self.za_trim, md.map_dpix)

        
        netd = np.zeros(md.nchan)
        sum_map = np.zeros((N_POLARIZATION, n_pix_x, n_pix_y))
        hits_map = np.zeros((N_POLARIZATION, n_pix_x, n_pix_y))
        wind = signal.get_window('hamming', data_clean.shape[-1])

        # Compute NETD values
        for i_chan in np.where(md.chanmask == 1)[0]:
            this_clean_data = np.squeeze(data_clean[i_chan,:])

            this_freq, this_psd = signal.periodogram(this_clean_data, fs, window=wind)
            valid_freq = np.where((this_freq > self.hp_filter_freq) & (this_freq < self.lp_filter_freq))
            this_netd = np.sqrt(np.median(this_psd[valid_freq]))
            netd[i_chan] = this_netd

        # Get rid of channels with bad weights
        new_chanmask = np.copy(md.chanmask)
        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = netd[good_idx]
        new_chanmask[good_idx] = np.where(good_netd > self.med_netd_cut_threshold * np.nanmedian(good_netd), -1, new_chanmask[good_idx])

        good_idx = np.where(new_chanmask == 1)[0]
        good_netd = netd[good_idx]
        netd_med = np.median(np.log10(good_netd))
        netd_std = np.std(np.log10(good_netd))
        new_chanmask[good_idx] = np.where(good_netd > 10 ** (netd_med + netd_std * 2), -1, new_chanmask[good_idx])
        new_chanmask[good_idx] = np.where(good_netd < 10 ** (netd_med - netd_std * 2), -1, new_chanmask[good_idx])

        netd[new_chanmask != 1] = 0
        pdb.set_trace()

        # Create map
        for i_chan in np.where(new_chanmask == 1)[0]:
            weight = 1./ netd[i_chan] ** 2.
            i_pol = detector_pol[i_chan] - 1

            this_detector_az = detector_az[i_chan,:]
            this_detector_za = detector_za[i_chan,:]

            # Get the good samples if they haven't been specified
            this_good_index = md.get_good_samples()
            this_clean_data = np.squeeze(data_clean[i_chan,:])

            # Get this detector's positions, need to account for rotation in EL based on beammap taken at EL=89
            x_ind = np.squeeze(np.round((this_detector_az-map_az[0])/md.map_dpix))
            x_ind = x_ind.astype('int64')
            y_ind = np.squeeze(np.round((this_detector_za-map_za[0])/md.map_dpix))
            y_ind = y_ind.astype('int64')

            #eliminate samples outside the map
            valid_index = np.ndarray.flatten(np.argwhere(np.logical_and( \
                np.logical_and(x_ind[this_good_index] >= 0, x_ind[this_good_index] < sum_map.shape[1]), \
                np.logical_and(y_ind[this_good_index] >= 0, y_ind[this_good_index] < sum_map.shape[2]))))
            this_good_index = this_good_index[valid_index]

            #loop over samples to create sum and hits maps
            for time_sample in this_good_index:
                sum_map[i_pol, x_ind[time_sample],y_ind[time_sample]] += this_clean_data[time_sample] * weight
                hits_map[i_pol, x_ind[time_sample],y_ind[time_sample]] += 1. * weight
        # weights = 1 / netd[md.chanmask==1]**2
        # np.save('weight.npy', 1/all_NETDs**2)
        # plt.show()
        # pdb.set_trace()
        return md.with_values(
            sum_map=sum_map,
            hits_map=hits_map,
            netd=netd,
            map_x=map_az,
            map_y=map_za,
            chanmask=new_chanmask,
        )
            
class GaussianFilter(DataRoutine):
    def __init__(self, gaussian_sigma: tuple[float, float]=GAUSSIAN_SIGMA):
        super().__init__()
        self.gaussian_sigma = gaussian_sigma
    
    def forward(self, pd: ProcessedData, field: str='data_mK') -> ProcessedData:
        smoothed_data = gaussian_filter(pd.__getattribute__(field), self.gaussian_sigma)
        return pd.with_values(**{field: smoothed_data})


class CutoffFilter(DataRoutine):
    def __init__(self, filter_freq: float, btype: str):
        super().__init__()
        self.filter_freq = filter_freq
        self.btype = btype

    def forward(self, pd: ProcessedData) -> ProcessedData:
        filt_sos = signal.butter(BUTTER_ORDER, self.filter_freq, btype=self.btype, fs=pd.fs, output='sos', analog=False)

        # Apply cutoff filter
        data_gain_phase_filt = signal.sosfiltfilt(filt_sos, pd.data_gain_phase)
        data_freq_diss_filt = signal.sosfiltfilt(filt_sos, pd.data_freq_diss)
        data_mK_filt = signal.sosfiltfilt(filt_sos, pd.data_mK)
        return pd.with_values(
            data_gain_phase=data_gain_phase_filt,
            data_freq_diss=data_freq_diss_filt,
            data_mK=data_mK_filt,
        )

class LowPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='lowpass')


class HighPassFilter(CutoffFilter):
    def __init__(self, filter_freq: float):
        super().__init__(filter_freq, btype='highpass')


class Downsample(DataRoutine):
    def __init__(self, ds_factor: float=6, order: int=DECIMATE_ORDER):
        super().__init__()
        self.ds_factor = ds_factor
        self.order=order
    
    def forward(self, pd: ProcessedData) -> ProcessedData:
        data_freq_diss_ds = signal.decimate(pd.data_freq_diss, self.ds_factor)
        data_gain_phase_ds = signal.decimate(pd.data_gain_phase, self.ds_factor)
        data_mK_ds = signal.decimate(pd.data_mK, self.ds_factor)
        timestamp_ds = signal.decimate(pd.timestamp, self.ds_factor)
        detector_az_ds = signal.decimate(pd.detector_az, self.ds_factor, n=self.order, axis=1)
        detector_za_ds = signal.decimate(pd.detector_za, self.ds_factor, n=self.order, axis=1)
        return pd.with_values(
            data_freq_diss=data_freq_diss_ds,
            data_gain_phase=data_gain_phase_ds,
            data_mK=data_mK_ds,
            timestamp=timestamp_ds,
            detector_az=detector_az_ds,
            detector_za=detector_za_ds,
        )



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


if __name__ == '__main__':
    # from onr_map_observation import create_map
    # data = ProcessedData.from_tod('20241016', 1015)
    # old_data = h5py.File('/data/20241016/20241016_processed_data_set1014.h5')

    # old_raw_data = RawDataFile('/data/20241016/20241016_rfsoc2_TOD_set1014.h5', 'r')
    # new_raw_data = RawDataFile('/data/20250513/20250513_chan_1_TOD_set1008.h5', 'r')
    # pdb.set_trace()

    # new_raw_data = RawDataFile('/data/20250509/20250509_chan_1_TOD_set1014.h5', 'r')
    # data = ProcessedData.from_tod('20250509', 1014)
    # data = ProcessedData.from_tod('20250509', 1014, losweep='20250509_rfsoc2_LO_Sweep_hour13p8025.h5')
    # pdb.set_trace()
    # data = ProcessedData.from_tod('20241017', 1001, losweep='20241017_rfsoc2_LO_Sweep_hour07p6728.npy')
    # data = ProcessedData.from_tod('20250513', 1005, losweep='20250513_devrfsoc_rfsoc2_LO_Sweep_hour15p6778_high_res.h5')
    # data = ProcessedData.from_tod('20250513', 1007)

    # old_data = ProcessedData.from_tod('20241016', 1008, save=False)
    # new_data = ProcessedData.from_tod('20250513', 1008)
    # pdb.set_trace()



    # old_fs = data.fs
    # data.timestamp = data.dtime
    hp_filt_freq = 1
    lp_filt_freq = 10

    ds = Downsample(6)
    hpfilt = HighPassFilter(hp_filt_freq)
    lpfilt = LowPassFilter(lp_filt_freq)

    # mapper = Mapper([ds, hpfilt, lpfilt, cleaner])
    # clean_data = mapper(data)
    # # with h5py.File('/data/20241016/20241016_cleaned_data_set1012.h5', 'r') as f:
    # #     og_clean_data = f['clean_data'][:]
    # old_data = create_map('20241016', 1012)
    # new_data = clean_data.data_mK
    # # with h5py.File('/data/20241016/20241016_processed_data_set1012.h5', 'r') as f:
    # #     og_data = f['data_mK'][:]
    # pdb.set_trace()

    remove_pickup = RemovePointLomaPickup()
    binner = BinTODIntoMap(hp_filter_freq=hp_filt_freq, lp_filter_freq=lp_filt_freq)
    # mapper = Mapper([ds, hpfilt, lpfilt, cleaner, binner])
    


    # cleaner = CleanTOD(save_file=False)
    # data = ProcessedData.from_tod('20241016', 1008, save=False)

    cleaner = CleanTOD(save_file=True)
    data = ProcessedData.from_tod('20250513', 1008)

    mapper = Mapper([remove_pickup, ds, hpfilt, lpfilt, cleaner, binner])

    map: MapData = mapper(data, save=False)
    map.plot(save=False)