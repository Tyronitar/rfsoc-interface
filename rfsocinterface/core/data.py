"""Core functionality relating to data loading and processing."""

from __future__ import annotations
from pathlib import Path
import glob
from typing import Callable
from dataclasses import dataclass, field
import copy
import pdb
import time

import h5py
import numpy as np
import numpy.typing as npt
from kidpy3 import RawDataFile
from scipy import signal
import matplotlib.pyplot as plt

from rfsocinterface.core.utils import ensure_path, gaussian_filter, GAUSSIAN_SIGMA, BAD_RFSOC_TONE_START_INDEX
from rfsocinterface.core.losweep import LoSweepData

DATA_DIRECTORY = '/data'
# DATA_DIRECTORY = 'reference_data'  # For testing with local data files

@ensure_path(0)
def load_time_ordered_IQ_data(path: Path, normalize: bool=True) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
    f = RawDataFile(path, 'r')
    data_i = f.adc_i[:]
    data_q = f.adc_q[:]
    input_data = np.empty((2, *data_i.shape))
    if normalize:
        amp = np.sqrt(data_i ** 2. + data_q ** 2.)
        amp = np.nanmedian(amp, axis=1)
        input_data[0, :, :] = data_i / np.outer(amp, np.ones(data_i.shape[1]))
        input_data[1, :, :] = data_q / np.outer(amp, np.ones(data_q.shape[1]))
    else:
        input_data[0, :, :] = data_i
        input_data[1, :, :] = data_q
    timestamp = f.timestamp[:]
    chanmask = f.chanmask[:]
    ntones = f.n_tones[0]
    return input_data[:, :ntones], timestamp, chanmask[:ntones]

def compute_df_per_mK(beam_pol: npt.NDArray, detector_beam_amp: npt.NDArray, detector_f, dfoverf_per_mK):
    valid_index = np.ndarray.flatten(np.argwhere(beam_pol >= 1))
    valid_amp = detector_beam_amp[valid_index]

    if np.size(valid_amp) > 1:
        min_amp = np.percentile(valid_amp, 10)
        valid_amp[valid_amp < min_amp] = min_amp
        valid_amp /= np.median(valid_amp)

    amps = detector_beam_amp[:]
    amps[valid_index] = valid_amp
    return dfoverf_per_mK * detector_f * amps

def generate_calibrated_data(clean_gain_phase_data: npt.NDArray, gain_phase_angle: npt.NDArray, dIQ_df: npt.NDArray, df_per_mK: npt.NDArray) -> tuple[npt.NDArray, npt.NDArray]:
    data_IQ = rotate_basis(clean_gain_phase_data, -gain_phase_angle)
    data_IQ -= np.mean(data_IQ, axis=2, keepdims=True)


    #now use the derivatives to convert to a frequency shift
    #need to optimally weight the data based on the response
    #in each direction (assuming the noise is identical in I and Q)
    #this will then yield data_f
    data_freq_diss = change_basis_to_frequency_dissipation(data_IQ, dIQ_df)

    # Finally, we need to get data_mK
    data_mK = np.divide(data_freq_diss[0], df_per_mK[:, np.newaxis])
    return data_freq_diss, data_mK


class Updateable:
    def update(self, new_vals: dict):
        for k, v in new_vals.items():
            if hasattr(self, k):
                setattr(self, k, v)

@dataclass
class ProcessedData(Updateable):
    """Class contianing data from processed TOD files."""
    date: str
    setnum: int
    optical_image: npt.NDArray | None
    dIQ_df: npt.NDArray
    carrier_amp_I: npt.NDArray
    carrier_amp_Q: npt.NDArray
    df_per_mK: npt.NDArray
    data_gain_phase: npt.NDArray
    IQ_to_gain_phase_angle: npt.NDArray
    data_freq_diss: npt.NDArray
    data_mK: npt.NDArray
    timestamp: npt.NDArray
    chanmask: npt.NDArray
    detector_pol: npt.NDArray
    detector_az: npt.NDArray
    detector_za: npt.NDArray
    vis: float | npt.NDArray

    @property
    def tod_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_*_TOD_set{self.setnum}.h5'

    @property
    def azel_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_AZEL_set{self.setnum}.h5'

    @property
    def optcam_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_optcam_set{self.setnum}.h5'
    
    @property
    def processed_file_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_processed_data_set{self.setnum}.h5'

    @property
    def cleaned_file_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_cleaned_data_set{self.setnum}.h5'
    
    @property
    def file_stub(self) -> str:
        return f'{self.date}_set{self.setnum}'

    @property
    def folder(self) -> Path:
        return Path(f'{DATA_DIRECTORY}/{self.date}')

    @property
    def data_gain(self) -> npt.NDArray:
        return self.data_gain_phase[0]

    @property
    def data_phase(self) -> npt.NDArray:
        return self.data_gain_phase[1]

    @property
    def data_freq(self) -> npt.NDArray:
        return self.data_freq_diss[0]

    @property
    def data_diss(self) -> npt.NDArray:
        return self.data_freq_diss[1]

    @property
    def dI_df(self) -> npt.NDArray:
        return self.dIQ_df[0]

    @property
    def dQ_df(self) -> npt.NDArray:
        return self.dIQ_df[1]

    def carrier_amplitude_norm(self) -> npt.NDArray:
        Z = self.carrier_amp_I + 1j*self.carrier_amp_Q
        return np.mean(np.abs(Z), axis=1)

    @property
    def time(self) -> npt.NDArray:
        return self.timestamp - self.timestamp[0]
    
    @property
    def delta_t(self) -> float:
        return np.median(self.time - np.roll(self.time, 1))

    @property
    def fs(self) -> float:
        return 1 / self.delta_t
    
    @property
    def nchan(self) -> int:
        return np.size(self.chanmask)

    @classmethod
    def from_tod(cls, date: str, setnum: int, losweep: str | None=None, save: bool=True) -> ProcessedData:
        #20230803_rfsoc1_TOD_set1012
        date = date
        setnum = setnum
    

        folder = Path(f'{DATA_DIRECTORY}/{date}')
        todtemplate = f'{DATA_DIRECTORY}/{date}/{date}_*_TOD_set{setnum}.h5'
        tele_template = Path(f'{DATA_DIRECTORY}/{date}/{date}_AZEL_set{setnum}.h5')
        optcam_template = Path(f'{DATA_DIRECTORY}/{date}/{date}_optcam_set{setnum}.h5')

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = h5py.File(tele_template, 'r')
        
        if optcam_exists:
            optcam_file = h5py.File(optcam_template, 'r')
        

        # Create processed data file

        todlist = glob.glob(todtemplate)

        if len(todlist) == 0:
            raise FileNotFoundError(f"No TOD files found for {date} set {setnum}")

        if azel_exists:
            az_tel = azel_file['az_tel'][:]
            try:
                za_tel = azel_file['el_tel'][:]
            except:
                za_tel = azel_file['za_tel'][:]
            timestamp_tel = azel_file['timestamp_tel'][:]
            vis = azel_file['optical_visibility'][0]
            if isinstance(vis, bytes):
                vis = np.nan
        else:
            vis=0.
        
        
        if optcam_exists:
            optical_image = optcam_file['optical_image'][:]
        else:
            optical_image = None



        dIQ_df = np.array([])
        carrier_amp_I = np.array([])
        carrier_amp_Q = np.array([])
        df_per_mK = np.array([])
        data_freq_diss = np.array([])
        data_gain_phase = np.array([])
        gain_phase_angle = np.array([])
        data_mK = 0
        chanmask = np.array([], dtype=np.int32)
        detector_pol = np.array([])
        detector_az = np.array([[]])
        detector_za = np.array([[]])
        # Iterate over the TOD Files
        for i, file in enumerate(todlist):

            #compute the derivatives to obtain frequency direction
            f = RawDataFile(file, 'r')

            # # Temporary fix for testing code:
            # f.baseband_freqs = np.load('/data/20250422/20250422_tone_list.npy')
            # f.lo_freq = np.array([4e8])

            if losweep:
                losweep = Path(losweep)
                # f.append_lo_sweep(losweep)
                if losweep.suffix == '.npy':
                    sweep_data = np.load(folder / losweep)
                else:
                    with h5py.File(folder / losweep, 'r') as sweep_file:
                        sweep_data = sweep_file['global_data/lo_sweep'][:]
            elif f.lo_sweep is not None:
                sweep_data = f.lo_sweep[:]
            else:
                raise RuntimeError('No LO sweep provided. Canceliing processing of file.')

            # f.lo_freq[:] = 4e8
            lo_freq = f.lo_freq[()]
            lo_freq = 4e8
            sweep = LoSweepData(f.baseband_freqs[:], lo_freq, sweep_data, f.chanmask[:])
            this_dIQ_df = sweep.freq_direction()
            if np.size(dIQ_df) > 0:
                dIQ_df = np.concatenate((dIQ_df, this_dIQ_df), axis=0)
            else:
                dIQ_df = np.copy(this_dIQ_df)
        
            #compute the calibration factor from dfoverf to mK
            detector_pol = f.detector_pol[:]
            if np.count_nonzero(detector_pol) == 0:
                detector_pol = np.ones_like(detector_pol)

            detector_beam_ampl = f.detector_beam_ampl[:]
            if np.count_nonzero(detector_beam_ampl) == 0:
                detector_beam_ampl= np.ones_like(detector_beam_ampl)

            dfoverf_per_mK = f.dfoverf_per_mK[:]
            if np.count_nonzero(dfoverf_per_mK) == 0:
                dfoverf_per_mK = np.ones_like(dfoverf_per_mK)

            detector_f = sweep.tone_list
            # detector_f = f.baseband_freqs[:] + f.lo_freq[:]

            # NOTE: Temporary fix: create dummy frequencies if they don't exist
            if np.count_nonzero(detector_f) == 0:  
                detector_f = np.linspace(0, 250e6, detector_f.size)

            this_df_per_mK = compute_df_per_mK(detector_pol, detector_beam_ampl, detector_f, dfoverf_per_mK) 
            df_per_mK = np.concatenate((df_per_mK,this_df_per_mK))

            #create the calibrated datastreams-----------------------------------------------------------
            #first get the I and Q data
            data_I = np.ndarray.astype(f.adc_i[:], np.float64)
            data_Q = np.ndarray.astype(f.adc_q[:], np.float64)
            nsamples = f.n_sample[0]
            ntones = f.n_tones[0]
            if int(date[:4]) < 2025:
                valid_tone_index = np.ndarray.flatten(np.argwhere(data_I[:,0] != 0.))
                valid_tone_index = valid_tone_index[:ntones]
            else:
                valid_tone_index = np.arange(ntones, dtype=int) + BAD_RFSOC_TONE_START_INDEX
            data_I = data_I[valid_tone_index,:]
            data_Q = data_Q[valid_tone_index,:]
            carrier_amp_I = np.nanmedian(data_I, axis=1)
            carrier_amp_Q = np.nanmedian(data_Q, axis=1)
            
            # Rotate to Gain / Phase

            this_gain_phase_angle = np.atan2(carrier_amp_I, carrier_amp_Q)  # N_chan

            this_data_gain_phase = rotate_basis(
                np.stack((data_I, data_Q)),
                this_gain_phase_angle
            )
            if np.size(data_gain_phase) > 0:
                data_gain_phase = np.concatenate((data_gain_phase, this_data_gain_phase), axis=0)
                gain_phase_angle = np.concatenate((gain_phase_angle, this_gain_phase_angle), axis=0)
            else:
                data_gain_phase= np.copy(this_data_gain_phase)
                gain_phase_angle = np.copy(this_gain_phase_angle)
            
            # TODO: Make this optional I guess
            clean_gain_phase_data = remove_electronics_noise(data_gain_phase)
            # pdb.set_trace()
            this_data_freq_diss, this_data_mK = generate_calibrated_data(
                clean_gain_phase_data,
                gain_phase_angle,
                dIQ_df,
                np.array(df_per_mK),
            )

            if np.size(data_freq_diss) > 0:
                data_freq_diss = np.concatenate((data_freq_diss, this_data_freq_diss), axis=0)
            else:
                data_freq_diss = np.copy(this_data_freq_diss)

            if np.size(data_mK) != 1:
                data_mK = np.concatenate((data_mK, this_data_mK), axis=0)
            else:
                data_mK = np.copy(this_data_mK)


            #now the telescope data to get coordinates
            time = f.timestamp[:]
            time_0 = time - time[0]
            total_time = np.max(time_0)
            n_samples = np.size(time)
            if i == 0:  # Only should make this once, since it's never changed
                timestamp = np.arange(0,total_time,total_time/n_samples) + time[0]
            if azel_exists:
                detector_dx_dy_elevation_angle = f.detector_dx_dy_elevation_angle[0]
                this_az_tel = np.interp(timestamp, timestamp_tel, az_tel)
                this_za_tel = np.interp(timestamp, timestamp_tel, za_tel)
                this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_za_tel)
                this_detector_delta_x = f.detector_delta_x[:]
                this_detector_delta_y = f.detector_delta_y[:]
                this_det_az = np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                            np.outer(this_detector_delta_y,np.sin(this_ang)) + \
                            np.outer(np.ones(ntones), this_az_tel)
                this_det_za = np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                            np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                            np.outer(np.ones(ntones), this_za_tel)
            
                #save the az/el information to the file
                if np.size(detector_az) > 0:
                    detector_az = np.concatenate((detector_az, this_det_az), axis=0)
                else:
                    detector_az = np.copy(this_det_az)
                if np.size(detector_za) > 0:
                    detector_za = np.concatenate((detector_za, this_det_za), axis=0)
                else:
                    detector_za = np.copy(this_det_za)

            #also save the chanmask and detector polarization information
            chanmask = np.concatenate((chanmask, f.chanmask[:]))
            no_pol = np.ndarray.flatten(np.argwhere(detector_pol < 1))
            if np.size(no_pol > 0):
                chanmask[no_pol] = -1
    #        detector_pol = np.concatenate((detector_pol, f.detector_pol[:]))
        # pdb.set_trace()
        pdata = cls(
            date,
            setnum,
            optical_image,
            dIQ_df,
            carrier_amp_I,
            carrier_amp_Q,
            df_per_mK,
            clean_gain_phase_data,
            gain_phase_angle,
            data_freq_diss,
            data_mK,
            timestamp,
            chanmask,
            detector_pol,
            detector_az,
            detector_za,
            vis
        )
        if save:
            pdata.save()
        return pdata

    #    print(dI_df.shape, dQ_df.shape, df_per_mK.shape, data_f.shape, data_mK.shape)
    def save(self):

        with h5py.File(self.processed_file_template, 'w') as pfile:
            pfile.create_dataset("dI_df", data=self.dI_df)
            pfile.create_dataset("dQ_df", data=self.dQ_df)
            pfile.create_dataset("df_per_mK", data=self.df_per_mK)
            pfile.create_dataset("data_gain", data=self.data_gain)
            pfile.create_dataset("data_phase", data=self.data_phase)
            pfile.create_dataset("IQ_to_gain_phase_angle", data=self.IQ_to_gain_phase_angle)
            pfile.create_dataset("data_freq", data=self.data_freq)
            pfile.create_dataset("data_diss", data=self.data_diss)
            pfile.create_dataset("data_mK", data=self.data_mK)
            pfile.create_dataset("chanmask", data=self.chanmask)
            pfile.create_dataset("detector_pol", data=self.detector_pol)
            pfile.create_dataset("detector_az", data=self.detector_az)
            pfile.create_dataset("detector_za", data=self.detector_za)
            pfile.create_dataset("timestamp", data=self.timestamp)
            pfile.create_dataset("optical_visibility", data=self.vis)
    
    def __copy__(self) -> ProcessedData:
        return ProcessedData(
            self.date,
            self.setnum,
            np.copy(self.optical_image),
            np.copy(self.dIQ_df),
            np.copy(self.carrier_amp_I),
            np.copy(self.carrier_amp_Q),
            np.copy(self.df_per_mK),
            np.copy(self.data_gain_phase),
            np.copy(self.IQ_to_gain_phase_angle),
            np.copy(self.data_freq_diss),
            np.copy(self.data_mK),
            np.copy(self.timestamp),
            np.copy(self.chanmask),
            np.copy(self.detector_pol),
            np.copy(self.detector_az),
            np.copy(self.detector_za),
            np.copy(self.vis),
        )

    def with_values(self, **kwargs) -> ProcessedData:
        new_data = copy.copy(self)
        new_data.update(kwargs)
        return new_data


@dataclass
class MapData(ProcessedData):
    """Class for storing values for generating maps."""
    good_samples: npt.NDArray = field(default_factory=lambda: np.array([]))
    netd: npt.NDArray = field(default_factory=lambda: np.array([]))
    sum_map: npt.NDArray = field(default_factory=lambda: np.array([]))
    hits_map: npt.NDArray = field(default_factory=lambda: np.array([]))
    map_x: npt.NDArray = field(default_factory=lambda: np.array([]))
    map_y: npt.NDArray = field(default_factory=lambda: np.array([]))
    map_dpix: float=0.04

    @property
    def map(self) -> npt.NDArray:
        return self.sum_map / self.hits_map

    @property
    def total_map(self) -> npt.NDArray:
        return np.sum(self.sum_map, axis=0) / np.sum(self.hits_map, axis=0)
    
    def get_good_samples(self) -> npt.NDArray:
        if np.size(self.good_samples) > 0:
            # Would be non-zero if it's been set somewhere (unless there are no good samples...)
            return np.copy(self.good_samples)
        else:
            return np.arange(np.shape(self.data_mK)[1])
    
    def get_netd_pol(self, polarization: int) -> npt.NDArray:
        return self.netd[self.detector_pol == polarization]
    
    @property
    def integration_time(self) -> npt.NDArray:
        integration_times = [
            np.flip(
                np.transpose(self.hits_map[i,::-1]) * \
                    np.median(self.get_netd_pol(pol)) ** 2. / self.fs,
                1,
            )
            for i, pol in enumerate(range(1, N_POLARIZATION + 1))
        ]
        return integration_times
    
    def get_combined_map(self, sigma: tuple[float,...]=GAUSSIAN_SIGMA) -> npt.NDArray:
        flagged_map_1 = gaussian_filter(self.map[0], sigma)
        flagged_map_2 = gaussian_filter(self.map[1], sigma)
        flagged_map_3 = gaussian_filter(self.total_map, sigma)
       # pdb.set_trace()
        # flagged_map_1 = np.copy(self.map[0])
        # flagged_map_2 = np.copy(self.map[1])
        # flagged_map_3 = np.copy(self.total_map)

        final_final_map1= np.copy(flagged_map_1)
        final_final_map2= np.copy(flagged_map_2)
        final_final_map3= np.copy(flagged_map_3)

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

        final_final_map1[combined_nan_map] = np.nan
        final_final_map2[combined_nan_map] = np.nan
        final_final_map3[combined_nan_map] = np.nan

        contour_levels = [1]

        final_final_map1= final_final_map1.flatten()
        final_final_map2= final_final_map2.flatten()
        final_final_map3= final_final_map3.flatten()

        final_final_map1 = [x for x in final_final_map1 if not np.isnan(x)]
        final_final_map2 = [x for x in final_final_map2 if not np.isnan(x)]
        final_final_map3 = [x for x in final_final_map3 if not np.isnan(x)]
        return flagged_map_1, flagged_map_2, flagged_map_3, contour_levels

    @classmethod
    def from_processed_data(cls, pd: ProcessedData) -> MapData:
        """Create a MapData object from a ProcessedData object."""
        return cls(
            pd.date,
            pd.setnum,
            np.copy(pd.optical_image),
            np.copy(pd.dIQ_df),
            np.copy(pd.carrier_amp_I),
            np.copy(pd.carrier_amp_Q),
            np.copy(pd.df_per_mK),
            np.copy(pd.data_gain_phase),
            np.copy(pd.IQ_to_gain_phase_angle),
            np.copy(pd.data_freq_diss),
            np.copy(pd.data_mK),
            np.copy(pd.timestamp),
            np.copy(pd.chanmask),
            np.copy(pd.detector_pol),
            np.copy(pd.detector_az),
            np.copy(pd.detector_za),
            np.copy(pd.vis),
        )
    
    def get_scaled_optical_image(self) -> npt.NDArray:
        opt_npix_per_tel_npix = self.map_dpix/0.0104
        opt_npix_az = int(np.size(self.map_x)*opt_npix_per_tel_npix/2)*2
        opt_npix_el = int(np.size(self.map_y)*opt_npix_per_tel_npix/2)*2
        opt_center_az = int(2592/2)+70
        opt_center_el = int(1944/2)+10
        return self.optical_image[opt_center_el-int(opt_npix_el/2):opt_center_el+int(opt_npix_el/2),\
                                    opt_center_az-int(opt_npix_az/2):opt_center_az+int(opt_npix_az/2)]
    
    def plot(self, save: bool=True):

        valid_cov_1 = np.argwhere(self.hits_map[0] > 0.5 * np.median(self.hits_map[0]))
        map_goodcov_1 = np.zeros(np.size(valid_cov_1[:,0]))
        for i_cov in np.arange(np.size(valid_cov_1[:,0])):
            map_goodcov_1[i_cov] = self.map[0, valid_cov_1[i_cov,0],valid_cov_1[i_cov,1]]
        valid_cov_2 = np.argwhere(self.hits_map[1] > 0.5 * np.median(self.hits_map[1]))
        map_goodcov_2 = np.zeros(np.size(valid_cov_2[:,0]))
        for i_cov in np.arange(np.size(valid_cov_2[:,0])):
            map_goodcov_2[i_cov] = self.map[1, valid_cov_2[i_cov,0],valid_cov_2[i_cov,1]]

        netd_1 = self.get_netd_pol(1)
        netd_2 = self.get_netd_pol(2)
        cb_shrink = 0.95
        this_xlim = min(self.map_x),max(self.map_x)
        this_ylim = max(self.map_y),min(self.map_y)
        max_abs = np.max(np.abs(np.append(map_goodcov_1,map_goodcov_2)))*0.75
        valid_netd_1 = np.argwhere(netd_1 > 0)
        med_netd_1 = 1./np.sqrt(np.sum(1./netd_1[valid_netd_1]**2)/np.size(valid_netd_1))
        valid_netd_2 = np.argwhere(netd_2 > 0)
        med_netd_2 = 1./np.sqrt(np.sum(1./netd_2[valid_netd_2]**2)/np.size(valid_netd_2))

        #Sage's plotting code---------------------------------------------------------------------------------------------

        # contour_levels, final_map_1_filt, final_map_2_filt, final_map_tot_filt, flagged_map_1_filt, flagged_map_2_filt, \
        # flagged_map_tot_filt, final_flagged_coordinates = combined_map(map_1_filt_final_map, map_2_filt_final_map, map_tot_filt_final_map)
        flagged_map_1_filt, flagged_map_2_filt, flagged_map_tot_filt, contour_levels = self.get_combined_map()

    #    pw = plotWindow()
        this_fig = plt.figure(figsize=(15,7.5))
        plt.subplot(4,1,1)
        plt.imshow(np.flip(np.transpose(self.map[0][::-1]),1), \
        extent = (min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), \
        aspect='equal', vmin=-max_abs, vmax=max_abs, cmap='Blues_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('V-Pol Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_1_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=(min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), colors='red')
        plt.title(self.file_stub + '\n' + 'Local Time = ' + time.asctime(time.localtime(self.timestamp[0]-7500.)) + \
        ', Optical Visibility = ' + str(self.vis) + ' meters \n' + 'NETD V-Pol (30Hz) = ' + "{:.1f}".format(med_netd_1) + \
        ' mK, ' + 'NETD H-Pol (30Hz) = ' + "{:.1f}".format(med_netd_2) + ' mK')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)

        plt.subplot(4,1,2)
        plt.imshow(np.flip(np.transpose(self.map[1][::-1]),1), \
        extent = (min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), \
        aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Reds_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('H-Pol Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_2_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=(min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), colors='black')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)

        plt.subplot(4,1,3)
        plt.imshow(np.flip(np.transpose(self.total_map[::-1]),1), \
        extent = (min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), \
        aspect='equal', vmin=-max_abs,vmax=max_abs, cmap='Greys_r')
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('Total Signal (mK)', rotation=270, labelpad=15)
        plt.contour(np.flip(np.flip(np.transpose(flagged_map_tot_filt[::-1]), axis=1), axis=0), levels=contour_levels, \
        extent=(min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), colors='red')
        plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)
        
        plt.subplot(4,1,4)
        optical_image = self.get_scaled_optical_image()
        valid_opt_pix = np.where(optical_image < 240)
        opt_vmax = 255. #np.percentile(optical_image[valid_opt_pix], 90)
        opt_vmin = -255. #np.percentile(optical_image[valid_opt_pix], 10)
        plt.imshow(optical_image, \
                extent = (min(self.map_x)-self.map_dpix/2.,max(self.map_x)+self.map_dpix/2,max(self.map_y)+self.map_dpix/2.,min(self.map_y)-self.map_dpix/2.), \
                aspect='equal', vmax=255, vmin=-255)
        cb = plt.colorbar(shrink=cb_shrink)
        cb.set_label('Optical Signal (rgb)', rotation=270, labelpad=15)
        ##Need to match aspect ratio of plots (and get rid of colorbar).
        plt.xlabel('Azimuth (degrees)'), plt.ylabel('ZA (degrees)')
        plt.xlim(this_xlim), plt.ylim(this_ylim)
            
        this_fig.subplots_adjust(wspace=0, hspace=0)
        plt.show()
    #    pw.addPlot("Raw Image", this_fig)
        if save:
            plt.savefig(self.folder / (self.file_stub + '_Source_Finder_Image.png'), bbox_inches='tight')




    def __copy__(self) -> MapData:
        return MapData(
            self.date,
            self.setnum,
            np.copy(self.optical_image),
            np.copy(self.dIQ_df),
            np.copy(self.carrier_amp_I),
            np.copy(self.carrier_amp_Q),
            np.copy(self.df_per_mK),
            np.copy(self.data_gain_phase),
            np.copy(self.IQ_to_gain_phase_angle),
            np.copy(self.data_freq_diss),
            np.copy(self.data_mK),
            np.copy(self.timestamp),
            np.copy(self.chanmask),
            np.copy(self.detector_pol),
            np.copy(self.detector_az),
            np.copy(self.detector_za),
            np.copy(self.vis),
            np.copy(self.good_samples),
            np.copy(self.netd),
            np.copy(self.hits_map),
            np.copy(self.sum_map),
            np.copy(self.map_x),
            np.copy(self.map_y),
            self.map_dpix,
        )
    


def iteratively_reject_outliers(data: npt.ArrayLike, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Repeatedly perform outlier rejection until there are no more outliers.

    Args:
        data (npt.ArrayLike): Input data (expected to be 1 dimensional)
        sigma (float, optional): The standard deviation cutoff for outliers. Defaults
            to 2.
        axis (None or int or tuple of ints, optional): The axis or axes to perform the
            outlier rejection along. Deafults to None.

    Returns:
        (npt.NDArray, npt.NDArray, npt.NDArray): `data` with the outliers removed,
        indices in `data` of the inliers, and indices in `data` of the outliers .
    """
    ind = np.arange(np.size(data))
    # ind = np.ones_like(data, dtype=int)
    # ind = get_all_indices(data)
    if np.ndim(data) != 1:
        data = np.flatten(data)
    while True:
        good_data, good_ind = reject_outliers(data[ind], sigma=sigma, axis=axis)
        if np.size(ind) == np.size(good_ind):
            break
        ind = ind[good_ind]
    return data[ind], ind, np.setdiff1d(np.arange(np.size(data)), ind)


def flag(data: npt.NDArray, fs: float, sigma: float=2):
    """Flag data outliers."""
    first_dimension, n_chan, _ = data.shape
    n_flag = np.zeros((first_dimension, n_chan))

    filt_cut = 1. / (0.5 * fs)
    b, a = signal.butter(5, filt_cut, btype='high', analog=False)
    hpf_data = signal.filtfilt(b, a, data)
    for i_complex in range(first_dimension):
        for i_res in range(n_chan):
            inliers, _, _ = iteratively_reject_outliers(hpf_data[i_complex, i_res, :], sigma=sigma)
            n_flag[i_complex, i_res] = hpf_data.shape[-1] - np.size(inliers)
    return n_flag, np.std(hpf_data, axis=-1)


def flag_outliers(data: npt.NDArray, fs: float, chanmask: npt.NDArray, sigma: float=2) -> npt.NDArray:
    good_channels = np.where(chanmask == 1)[0]
    n_flag, timestream_rms = flag(data[:, good_channels], fs, sigma=sigma)
    med_flag = np.median(n_flag)
    chanmask[np.where(np.any(n_flag > 2. * med_flag, axis=0))] = -1
    _, _, bad_indices_0 = iteratively_reject_outliers(timestream_rms[0], sigma=sigma)
    if np.ndim(timestream_rms) == 3:
        _, _, bad_indices_1 = iteratively_reject_outliers(timestream_rms[1], sigma=sigma)
        bad_indices = np.union1d(bad_indices_0, bad_indices_1)
    else:
        bad_indices = bad_indices_0
    chanmask[bad_indices] = -1
    return chanmask


def rotate_basis(input_data: npt.NDArray, rotation_angle: npt.NDArray) -> tuple[npt.NDArray, npt.NDArray]:
    """Compute change of basis, rotating with the specified angle."""
    assert input_data.ndim == 3
    assert input_data.shape[0] == 2

    new_data = np.zeros(shape=input_data.shape)
    new_data[0] = np.cos(rotation_angle)[:, np.newaxis] * input_data[0, :, :] + np.sin(rotation_angle)[:, np.newaxis] * input_data[1, :, :]
    new_data[1] = -np.sin(rotation_angle)[:, np.newaxis] * input_data[0, :, :] + np.cos(rotation_angle)[:, np.newaxis] * input_data[1, :, :]
    return new_data 

def change_basis_to_frequency_dissipation(input_IQ_data: npt.NDArray, dIQ_df: npt.NDArray) -> npt.NDArray:
    """Compute change of basis from IQ to frequency/dissipation."""
    data_I = input_IQ_data[0]
    data_Q = input_IQ_data[1]
    nsamples = input_IQ_data.shape[2]

    dI_df = dIQ_df[0]
    dQ_df = dIQ_df[1]
    eqiv_var_I = np.outer((1. / dI_df)**2., np.ones(nsamples))
    eqiv_var_Q = np.outer((1. / dQ_df)**2., np.ones(nsamples))

    data_f = ( (data_I / np.outer(dI_df, np.ones(nsamples)) ) / eqiv_var_I + \
                    (data_Q / np.outer(dQ_df, np.ones(nsamples)) ) / eqiv_var_Q ) / \
                (1./eqiv_var_I + 1./eqiv_var_Q)
    data_diss = ( (data_I / np.outer(-dQ_df, np.ones(nsamples)) ) / eqiv_var_Q + \
                    (data_Q / np.outer(dI_df, np.ones(nsamples)) ) / eqiv_var_I ) / \
                (1./eqiv_var_I + 1./eqiv_var_Q)
    return np.stack((data_f, data_diss))


def compute_templates(data: npt.NDArray) -> npt.NDArray:
    """Compute templates for correlated noise removal.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples).

    Returns:
        (npt.NDarray): Templates for noise removal (N_chan x 2 x N_samples).
            Computed using the first two eigenmodes of the correlation matrix.
    """
        # subtract the mean from each detector
    data_meansub = data - np.mean(data, axis=2)[:, :, np.newaxis]

    # select only the middle few detectors
    deproj = data_meansub[:, 8:1008, :]

    # create a separate correlation matrix for all data channels
    correlation_matrices = np.matmul(deproj, np.conj(np.transpose(deproj, axes=(0, 2, 1))))
    # calculate the eigenmodes of the correlation matrices
    _, v = np.linalg.eig(correlation_matrices)

    # create templates based on the 2 largest eigenmodes of each
    templates = np.einsum('ijk,ijl->ikl', v[:,:,0:2], deproj)

    # subtract the mean again to be sure
    templates = np.real(templates) - np.mean(np.real(templates), axis=(2))[:, :, np.newaxis]
    return templates


def remove_electronics_noise(data: npt.NDArray) -> npt.NDArray:
    """Remove correlated electronics noise templates from the data.

    Args:
        data (npt.NDArray): Input data (N_chan x N_detector x N_samples). Data should
            be in the amplitude/phase basis.

    Returns:
        npt.NDarray: Cleaned data (N_chan x N_detector x N_samples).
    """
    templates = compute_templates(data)  # N_chan x 2 x N_samples

    denominator = np.einsum('ijk,ijk->ij', templates, templates)  # N_chan x 2
    numerator0 = np.einsum('ijk,ik->ij', data, templates[:, 0])  # N_chan x N_detector
    corr0 = numerator0 / denominator[:, 0:1]  # N_chan x N_detector
    deproj = data - np.einsum('ij,ikl->ijl', corr0, templates[:, 0:1])  # N_chan x N_detector x N_samples

    numerator1 = np.einsum('ijk,ik->ij', deproj, templates[:, 1])  # N_chan x N_detector
    corr1 = numerator1 / denominator[:, 1:]  # N_chan x N_detector
    clean_data = deproj - np.einsum('ij,ikl->ijl', corr1, templates[:, 1:])
    return clean_data


def reject_outliers(data: npt.NDArray, sigma: float=2, axis: None | int | tuple[int, ...]=None):
    """Return the data without outliers and the rejected indices."""
    d = np.abs(data - np.median(data, axis=axis))
    std = np.std(data, axis=axis)
    ind = np.where(d < sigma * std)
    return data[ind], ind
    
if __name__ == "__main__":

    data = ProcessedData.from_tod('20241017', 1001)
    with h5py.File('/data/20241017/20241017_processed_data_set1001.h5', 'r') as f:
        og_data = f['data_mK'][:]
    pdb.set_trace()

N_POLARIZATION = 2