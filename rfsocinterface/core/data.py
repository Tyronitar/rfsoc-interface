"""Core functionality relating to data loading and processing."""

from __future__ import annotations
from pathlib import Path
import glob
from typing import Callable
from dataclasses import dataclass, field
import copy

import h5py
import numpy as np
import numpy.typing as npt
from kidpy3 import RawDataFile

from rfsocinterface.core.utils import ensure_path, get_filename
from rfsocinterface.core.losweep import LoSweepData


@ensure_path(0)
def load_time_ordered_IQ_data(path: Path, normalize: bool=True) -> tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
    with h5py.File(path, 'r') as f:
        data_i = f['time_ordered_data/adc_i'][:]
        data_q = f['time_ordered_data/adc_q'][:]
        input_data = np.empty((2, *data_i.shape))
        if normalize:
            amp = np.sqrt(data_i ** 2. + data_q ** 2.)
            amp = np.nanmedian(amp, axis=1)
            input_data[0, :, :] = data_i / np.outer(amp, np.ones(data_i.shape[1]))
            input_data[1, :, :] = data_q / np.outer(amp, np.ones(data_q.shape[1]))
        else:
            input_data[0, :, :] = data_i
            input_data[1, :, :] = data_q
        timestamp = f['time_ordered_data/timestamp'][:]
        chanmask = f['global_data/chanmask'][:]
    return input_data, timestamp, chanmask

def df_per_mK(beam_pol: npt.NDArray, detector_beam_amp: npt.NDArray, detector_f, dfoverf_per_mK):
    valid_index = np.ndarray.flatten(np.argwhere(beam_pol >= 1))
    valid_amp = detector_beam_amp[valid_index]

    min_amp = np.percentile(valid_amp, 10)
    valid_amp[valid_amp < min_amp] = min_amp

    valid_amp /= np.median(valid_amp)
    amps = np.where(beam_pol >= 1, valid_amp, detector_beam_amp)
    return dfoverf_per_mK * detector_f * amps


class Updateable:
    def update(self, new_vals: dict):
        for k, v in new_vals.items():
            if hasattr(self, k):
                setattr(self, k, v)

@dataclass
class DetectorData(Updateable):
    """Base class for storing data from a detector."""

@dataclass
class MapData(DetectorData):
    """Class for storingvalues for generating maps."""
    data: npt.NDArray 
    azimuth: npt.NDArray
    zenith_angle: npt.NDArray
    polarization: npt.NDArray
    timestamp: npt.NDArray
    flagged_values: npt.NDArray = field(default_factory=lambda: np.array([]))
    integration_time: npt.NDArray = field(default_factory=lambda: np.array([]))
    NETD: npt.NDArray = field(default_factory=lambda: np.array([]))
    chanmask: npt.NDArray = field(default_factory=lambda: np.array([]))

    @property
    def fs(self) -> float:
        return 1 / self.timestamp[1]
    
    def __copy__(self) -> MapData:
        return MapData(
            data=self.data[:],
            azimuth=self.azimuth[:],
            zenith_angle=self.zenith_angle[:],
            polarization=self.polarization[:],
            timestamp=self.timestam[:],
            flagged_values=self.flagged_values[:],
            integration_time=self.integration_time[:],
            NETD=self.NETD[:],
            chanmask=self.chanmask[:],
        )
    
    def with_values(self, **kwargs) -> MapData:
        new_map = copy.copy(self)
        new_map.update(kwargs)
        return new_map



@dataclass(init=False)
class ProcessedData(DetectorData):
    """Class contianing data from processed TOD files."""
    optical_image: npt.NDArray | None
    date: str
    setnum: int
    vis: float
    dI_df: npt.NDArray
    dQ_df: npt.NDArray
    df_per_mK: npt.NDArray
    data_f: npt.NDArray
    data_diss: npt.NDArray
    data_mK: npt.NDArray
    chanmask: npt.NDArray
    detector_pol: npt.NDArray
    detector_az: float | npt.NDArray
    detector_za: float | npt.NDArray
    timestamp: npt.NDArray

    @property
    def tod_template(self) -> str:
        return f'/data/{self.date}/{self.date}_*_TOD_set{self.setnum}.h5'

    @property
    def azel_template(self) -> str:
        return f'/data/{self.date}/{self.date}_AZEL_set{self.setnum}.h5'

    @property
    def optcam_template(self) -> str:
        return f'/data/{self.date}/{self.date}_optcam_set{self.setnum}.h5'
    
    @property
    def file_template(self) -> str:
        return f'/data/{self.date}/{self.date}_processed_data_set{self.setnum}.h5'

    def __init__(self, date: str, setnum: int, losweep: str | None):
        #20230803_rfsoc1_TOD_set1012
        self.date = date
        self.setnum = setnum
    
        todtemplate = self.tod_template
        tele_template = Path(self.azel_template)
        optcam_template = Path(self.optcam_template)

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = h5py.File(tele_template, 'r')
        
        if optcam_exists:
            optcam_file = h5py.File(optcam_template, 'r')
        

        # Create processed data file

        todlist = glob.glob(todtemplate)

        if len(todlist) == 0:
            print("no TOD files found")
            return

        if azel_exists:
            az_tel = azel_file['az_tel'][:]
            el_tel = azel_file['el_tel'][:]
            timestamp_tel = azel_file['timestamp_tel'][:]
            self.vis = azel_file['optical_visibility'][:]
        else:
            self.vis=0.
        
        
        if optcam_exists:
            self.optical_image = optcam_file['optical_image'][:]
        else:
            self.optical_image = None


        self.dI_df = np.array([])
        self.dQ_df = np.array([])
        self.df_per_mK = np.array([])
        self.data_f = 0
        self.data_diss = 0
        self.data_mK = 0
        self.chanmask = np.array([], dtype=np.int32)
        self.detector_pol = np.array([])
        self.detector_az = 0
        self.detector_za = 0
        # Iterate over the TOD Files
        for i, file in enumerate(todlist):

            #compute the derivatives to obtain frequency direction
            f = RawDataFile(file, 'r')
            if losweep:
                # f.append_lo_sweep(losweep)
                with h5py.File(losweep, 'r') as sweep_file:
                    sweep_data = sweep_file['global_data/lo_sweep'][:]
                sweep = LoSweepData(f.baseband_freqs[:], f.lo_freq[()], sweep_data, f.chanmask[:])
                this_dI_df, this_dQ_df = sweep.freq_direction()
                self.dI_df = np.concatenate((self.dI_df, this_dI_df))
                self.dQ_df = np.concatenate((self.dQ_df, this_dQ_df))
        
            #compute the calibration factor from dfoverf to mK
            self.detector_pol = f.detector_pol[:]
            detector_beam_ampl = f.detector_beam_ampl[:]
            dfoverf_per_mK = f.dfoverf_per_mK[:]
            detector_f = f.baseband_freqs[:] + f.lo_freq[:]
            this_df_per_mK = self.df_per_mK(self.detector_pol, detector_beam_ampl, detector_f, dfoverf_per_mK) 
            self.df_per_mK = np.concatenate((self.df_per_mK,this_df_per_mK))

            #create the calibrated datastreams-----------------------------------------------------------
            #first get the I and Q data
            data_I = np.ndarray.astype(f.adc_i[:], np.float64)
            data_Q = np.ndarray.astype(f.adc_q[:], np.float64)
            nsamples = f.n_sample[0]
            ntones = f.n_tones[0]
            valid_tone_index = np.ndarray.flatten(np.argwhere(data_IQ[0, :, 0] != 0.))
            valid_tone_index = valid_tone_index[:ntones]
            data_IQ = data_IQ[:, valid_tone_index, :]
            data_I = data_I[valid_tone_index,:]
            data_Q = data_Q[valid_tone_index,:]
            data_I = data_I - np.outer(np.mean(data_I, axis = 1), np.ones(nsamples))
            data_Q = data_Q - np.outer(np.mean(data_Q, axis = 1), np.ones(nsamples))
            
            #pdb.set_trace()

            #now use the derivatives to convert to a frequency shift
            #need to optimally weight the data based on the response
            #in each direction (assuming the noise is identical in I and Q)
            #this will then yield data_f
            this_dI_df = np.array(this_dI_df)
            this_dQ_df = np.array(this_dQ_df)
            eqiv_var_I = np.outer((1. / this_dI_df)**2., np.ones(nsamples))
            eqiv_var_Q = np.outer((1. / this_dQ_df)**2., np.ones(nsamples))
            this_data_f = ( (data_I / np.outer(this_dI_df, np.ones(nsamples)) ) / eqiv_var_I + \
                            (data_Q / np.outer(this_dQ_df, np.ones(nsamples)) ) / eqiv_var_Q ) / \
                        (1./eqiv_var_I + 1./eqiv_var_Q)
            this_data_diss = ( (data_I / np.outer(-this_dQ_df, np.ones(nsamples)) ) / eqiv_var_Q + \
                            (data_Q / np.outer(this_dI_df, np.ones(nsamples)) ) / eqiv_var_I ) / \
                        (1./eqiv_var_I + 1./eqiv_var_Q)
            if np.size(self.data_f) != 1:
                self.data_f = np.concatenate((self.data_f, this_data_f), axis=0)
                self.data_diss = np.concatenate((self.data_diss, this_data_diss), axis=0)
            else:
                self.data_f = np.copy(this_data_f)
                self.data_diss = np.copy(this_data_diss)
    #        del eqiv_var_I, eqiv_var_Q, data_I, data_Q

            #finally, we need to get data_mK
            this_df_per_mK = np.array(this_df_per_mK)
            this_data_mK = np.divide(this_data_f, np.outer(this_df_per_mK, np.ones(nsamples)))
            if np.size(self.data_mK) != 1:
                self.data_mK = np.concatenate((self.data_mK, this_data_mK), axis=0)
            else:
                self.data_mK = np.copy(this_data_mK)
    #        del this_data_f, this_data_mK
    #        import matplotlib.pyplot as plt
    #        pdb.set_trace()

            #now the telescope data to get coordinates
            time = f.timestamp[:]
            time_0 = time - time[0]
            total_time = np.max(time_0)
            n_samples = np.size(time)
            if i == 0:  # Only should make this once, since it's never changed
                self.timestamp = np.arange(0,total_time,total_time/n_samples) + time[0]
            if azel_exists:
                detector_dx_dy_elevation_angle = f.detector_dx_dy_elevation_angle[0]
                this_az_tel = np.interp(self.timestamp, timestamp_tel, az_tel)
                this_el_tel = np.interp(self.timestamp, timestamp_tel, el_tel)
                this_ang = np.pi/180.*(detector_dx_dy_elevation_angle-this_el_tel)
                this_detector_delta_x = f.detector_delta_x[:]
                this_detector_delta_y = f.detector_delta_y[:]
                this_det_az = np.outer(this_detector_delta_x, np.cos(this_ang)) - \
                            np.outer(this_detector_delta_y,np.sin(this_ang)) + \
                            np.outer(np.ones(ntones), this_az_tel)
                this_det_el = np.outer(this_detector_delta_y, np.cos(this_ang)) + \
                            np.outer(this_detector_delta_x, np.sin(this_ang)) + \
                            np.outer(np.ones(ntones), this_el_tel)
            
                #save the az/el information to the file
                if np.size(self.detector_az) != 1:
                    self.detector_az = np.concatenate((self.detector_az, this_det_az), axis=0)
                else:
                    self.detector_az = np.copy(this_det_az)
                if np.size(self.detector_za) != 1:
                    self.detector_za = np.concatenate((self.detector_za, this_det_el), axis=0)
                else:
                    self.detector_za = np.copy(this_det_el)

            #also save the chanmask and detector polarization information
            self.chanmask = np.concatenate((self.chanmask, f.chanmask[:]))
            no_pol = np.ndarray.flatten(np.argwhere(self.detector_pol < 1))
            if np.size(no_pol > 0):
                self.chanmask[no_pol] = -1
    #        detector_pol = np.concatenate((detector_pol, f.detector_pol[:]))

    #    print(dI_df.shape, dQ_df.shape, df_per_mK.shape, data_f.shape, data_mK.shape)
    def save(self):

        with h5py.File(self.file_template, 'w') as pfile:
            pfile.create_dataset("dI_df", data=self.dI_df)
            pfile.create_dataset("dQ_df", data=self.dQ_df)
            pfile.create_dataset("df_per_mK", data=self.df_per_mK)
            pfile.create_dataset("data_f", data=self.data_f)
            pfile.create_dataset("data_diss", data=self.data_diss)
            pfile.create_dataset("data_mK", data=self.data_mK)
            pfile.create_dataset("chanmask", data=self.chanmask)
            pfile.create_dataset("detector_pol", data=self.detector_pol)
            pfile.create_dataset("detector_az", data=self.detector_az)
            pfile.create_dataset("detector_za", data=self.detector_za)
            pfile.create_dataset("timestamp", data=self.timestamp)
            pfile.create_dataset("optical_visibility", data=self.vis)
    

if __name__ == '__main__':
    import pdb
    p = ProcessedData('20250409', 1001, losweep='/data/20250409/20250409_rfsoc2_LO_Sweep_hour16p6986.h5')
    pdb.set_trace()