"""Core functionality relating to data loading and processing."""

from __future__ import annotations
from pathlib import Path
import glob
from typing import Callable
from dataclasses import dataclass, field
import copy
import pdb

import h5py
import numpy as np
import numpy.typing as npt
from kidpy3 import RawDataFile
from scipy import signal

from rfsocinterface.core.utils import ensure_path, get_filename
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
    dIQ_df: npt.NDArray
    carrier_amp_I: npt.NDArray
    carrier_amp_Q: npt.NDArray
    df_per_mK: npt.NDArray
    data: npt.NDArray
    data_mK: npt.NDArray
    chanmask: npt.NDArray
    detector_pol: npt.NDArray
    detector_az: float | npt.NDArray
    detector_za: float | npt.NDArray
    timestamp: npt.NDArray

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
    def file_template(self) -> str:
        return f'{DATA_DIRECTORY}/{self.date}/{self.date}_processed_data_set{self.setnum}.h5'

    @property
    def folder(self) -> Path:
        return Path(f'{DATA_DIRECTORY}/{self.date}')

    @property
    def data_f(self) -> npt.NDArray:
        return self.data[0]

    @property
    def data_diss(self) -> npt.NDArray:
        return self.data[1]

    @property
    def dI_df(self) -> npt.NDArray:
        return self.dIQ_df[0]

    @property
    def dQ_df(self) -> npt.NDArray:
        return self.dIQ_df[1]

    def carrier_amplitude_norm(self) -> npt.NDArray:
        Z = self.carrier_amp_I + 1j*self.carrier_amp_Q
        return np.mean(np.abs(Z), axis=1)

    def __init__(self, date: str, setnum: int, losweep: str | None=None):
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


        self.dIQ_df = np.array([])
        self.carrier_amp_I = np.array([])
        self.carrier_amp_Q = np.array([])
        self.df_per_mK = np.array([])
        self.data = np.array([])
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
                losweep = Path(losweep)
                # f.append_lo_sweep(losweep)
                if losweep.suffix == '.npy':
                    sweep_data = np.load(self.folder / losweep)
                else:
                    with h5py.File(self.folder / losweep, 'r') as sweep_file:
                        sweep_data = sweep_file['global_data/lo_sweep'][:]
                sweep = LoSweepData(f.baseband_freqs[:], f.lo_freq[()], sweep_data, f.chanmask[:])
                this_dIQ_df = sweep.freq_direction()
                if np.size(self.dIQ_df) > 0:
                    self.dIQ_df = np.concatenate((self.dIQ_df, this_dIQ_df), axis=0)
                else:
                    self.dIQ_df = np.copy(this_dIQ_df)
        
            #compute the calibration factor from dfoverf to mK
            self.detector_pol = f.detector_pol[:]
            detector_beam_ampl = f.detector_beam_ampl[:]
            dfoverf_per_mK = f.dfoverf_per_mK[:]
            detector_f = f.baseband_freqs[:] + f.lo_freq[:]
            this_df_per_mK = compute_df_per_mK(self.detector_pol, detector_beam_ampl, detector_f, dfoverf_per_mK) 
            self.df_per_mK = np.concatenate((self.df_per_mK,this_df_per_mK))

            #create the calibrated datastreams-----------------------------------------------------------
            #first get the I and Q data
            data_I = np.ndarray.astype(f.adc_i[:], np.float64)
            data_Q = np.ndarray.astype(f.adc_q[:], np.float64)
            nsamples = f.n_sample[0]
            ntones = f.n_tones[0]
            # valid_tone_index = np.ndarray.flatten(np.argwhere(data_IQ[0, :, 0] != 0.))
            valid_tone_index = np.ndarray.flatten(np.argwhere(data_I[:, 0] != 0.))
            valid_tone_index = valid_tone_index[:ntones]
            # data_IQ = data_IQ[:, valid_tone_index, :]
            data_I = data_I[valid_tone_index,:]
            data_Q = data_Q[valid_tone_index,:]
            self.carrier_amp_I = np.mean(data_I, axis=1)
            self.carrier_amp_Q = np.mean(data_Q, axis=1)
            data_I = data_I - np.outer(self.carrier_amp_I, np.ones(nsamples))
            data_Q = data_Q - np.outer(self.carrier_amp_Q, np.ones(nsamples))
            
            #now use the derivatives to convert to a frequency shift
            #need to optimally weight the data based on the response
            #in each direction (assuming the noise is identical in I and Q)
            #this will then yield data_f
            this_data = rotate_to_frequency_dissipation(
                np.stack((data_I, data_Q)),
                this_dIQ_df,
            )
            if np.size(self.data) > 0:
                self.data = np.concatenate((self.data, this_data), axis=0)
            else:
                self.data = np.copy(this_data)

            #finally, we need to get data_mK
            this_df_per_mK = np.array(this_df_per_mK)
            this_data_mK = np.divide(this_data[0], np.outer(this_df_per_mK, np.ones(nsamples)))
            if np.size(self.data_mK) != 1:
                self.data_mK = np.concatenate((self.data_mK, this_data_mK), axis=0)
            else:
                self.data_mK = np.copy(this_data_mK)

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


def rotate_to_amplitude_and_phase(input_IQ_data: npt.NDArray) -> npt.NDArray:
    """Compute chnage of basis to amplitude/phase."""
    assert input_IQ_data.ndim == 3
    assert input_IQ_data.shape[0] == 2
    atan = np.atan2(input_IQ_data[1, :, :], input_IQ_data[0, :, :])
    rotation_angle = np.nanmedian(atan, axis=-1)

    amp = np.cos(rotation_angle)[:, np.newaxis] * input_IQ_data[0, :, :] + np.sin(rotation_angle)[:, np.newaxis] * input_IQ_data[1, :, :]
    phase = -np.sin(rotation_angle)[:, np.newaxis] * input_IQ_data[0, :, :] + np.cos(rotation_angle)[:, np.newaxis] * input_IQ_data[1, :, :]
    new_data = np.zeros(shape=input_IQ_data.shape)
    new_data[0] = amp
    new_data[1] = phase
    return new_data

def rotate_to_frequency_dissipation(input_IQ_data: npt.NDArray, dIQ_df: npt.NDArray) -> npt.NDArray:
    """Compute chnage of basis to frequency/dissipation."""
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
    
