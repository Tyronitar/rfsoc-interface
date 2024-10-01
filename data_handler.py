"""
:Authors: - Cody Roberson
          - Jack Sayers
          - Daniel Cunnane

:Date: 2023-08-01

:Version: 2.0.0

Brief overview
--------------
Here we define the data types and format that is utilized throughout the project.
Our primary observation data is stored using HDF5  `HDF5 <https://www.hdfgroup.org/solutions/hdf5/>`_
via the `h5py python library <https://www.h5py.org/>`_


RawDataFile
--------------
The RawDataFile class is analogous to standard camera's raw file. Detector data is captured, unprocessed into this file.


Dimensions
--------------
n_resonator


ObservationDataFile
-------------------
000



"""

import h5py
import os
import time
import logging
import numpy as np
from dataclasses import dataclass
from datetime import date
from datetime import datetime
import glob

logger = logging.getLogger(__name__)

PARAMS_PATH = "/home/onrkids/readout/host/params/"

@dataclass
class RFChannel:
    """
    **Dataclass**; contains the state information relevant to an observation on a
    per-RF-chain basis going into a/the cryostat. Each rf channel gets it's own RF chain and
    subsequently it's own UDP connection. The information used here is pulled into the RawDataFile.


    :param str raw_filename: path to where the HDF5 file shall exist.

    :param str ip: ip address of UDP stream to listen to

    :param int port: port of UDP to listen to, default is 4096

    :param str name: Friendly Name to call the channel. This is relevant to logs, etc

    :param int n_sample: n_samples to take. While this is used to format the
        rawDataFile, it should be
        left as 0 for now since udp2.capture() dynamically resizes/allocates it's datasets.

    :param int n_resonator: Number of resonators we're interested in / Tones we're generating
        from the RFSOC dac mapped to this Channel.

    :param int n_attenuator: Dimension N Attenuators

    :param np.ndarray baseband_freqs: array of N resonator tones

    :param np.ndarray attenuator_settings: Array of N Attenuator settings

    :param int sample_rate: Data downlink sample rate ~488 Samples/Second

    :param int tile_number: Which tile this rf channel belongs to

    :param int rfsoc_number: Which rfsoc unit is used

    :param int chan_number: channel # of the rfsoc being used

    :param int ifslice_number: Which IF slice the rfsoc channel # is using.

    :param str lo_sweep_filename: path to the LO sweep data with which to append to the rawDataFile.

    """

    raw_filename: str
    ip: str
    baseband_freqs: np.ndarray
    tone_powers: np.ndarray
    attenuator_settings: np.ndarray
    n_tones: int

    port: int = 4096
    name: str = "Untitled"
    n_sample: int = 488    
    n_attenuators: int = 2
    sample_rate: np.ndarray = 488
    tile_number: int = 0
    rfsoc_number: int = 0
    chan_number: int = 0
    ifslice_number: int = 0
    lo_sweep_filename: str = "/path/to/some_s21_file_here.npy"
    n_fftbins: int = 1024
    lo_freq: float = 400.0

class RawDataFile:
    """A raw hdf5 data file object for incoming rfsoc-UDP data streams.

    UDP packets containing our downsampled data streaming from the RFSOC to the readout computer
    will be captured and saved to this hdf5 filetype.

    Previously, the user was responsible for specifying n_samples which was used to provision
    the arrays needed to hold the data. However, this is no longer the case. While the parameter 
    still exists, it shall be set to 0 as data collection is now dynamic.

    :param str path: /file/path/here/file.h5

    :param int n_tones: (Dimension) The number of resonance tones / DAC tones

    :param char filemode:  User Shall provide one of the following: 'r', 'w', 'a'.
        Filemode denotes how the RDF should be handled. If 'r', then the file is opened as 'read-only'.
        When the file opened, read() is called. If 'w' is specified, then the file is created, over-writing 
        a file of the same name if it exists. In this case, read() is not called. The file will be blank until
        format() is called.
        The file is opened and read() is called in the case of 'a'

         .. DANGER::
            Opening with 'w' unintentionally can cause data loss, especially if users are accustomed to
            the w+ file mode

        

    """

    def __init__(self, path, filemode):
        log = logger.getChild(__name__)

        self.filename = path
        if filemode == 'r':
            self.fh = h5py.File(path, "r")
            self.read()
            log.debug(f"Opened {path} for reading.")
        elif filemode == 'w':
            self.fh = h5py.File(self.filename, "w")
            log.debug(f"Opened {path} for (over)writing.")
        elif filemode == 'a':
            self.fh = h5py.File(self.filename, "a")
            self.read()
            log.debug(f"Opened {path} for writing.")        
        else:
            # do nothing
            pass


    def format(self, n_sample: int, n_tones: int, n_fftbins: int = 1024):
        """
        When called, populates the hdf5 file with our desired datasets
        """
        # ********************************* Dimensions *******************************
        GD = "global_data/"
        self.n_sample = self.fh.create_dataset(
            "dimension/n_sample",
            (1,),
            dtype=h5py.h5t.NATIVE_UINT64,
        )
        self.n_tones = self.fh.create_dataset(
            "dimension/n_tones",
            (1,),
            dtype=h5py.h5t.NATIVE_UINT64,
        )
        self.n_attenuators = self.fh.create_dataset(
            "dimension/n_attenuators",
            (1,),
            dtype=h5py.h5t.NATIVE_UINT64,
        )
        self.n_fftbins = self.fh.create_dataset(
            "dimension/n_fftbins",
            (1,),
            dtype=h5py.h5t.NATIVE_UINT64,
        )
        self.n_fftbins[0] = n_fftbins
        self.n_sample[0] = n_sample
        self.n_tones[0] = n_tones
        # ******************************** Global Data ******************************
        self.attenuator_settings = self.fh.create_dataset(
            "global_data/attenuator_settings",
            (2,),
            dtype=h5py.h5t.NATIVE_DOUBLE,
        )
        self.baseband_freqs = self.fh.create_dataset(
            "global_data/baseband_freqs", (n_tones,)
        )
        self.detector_dx_dy_elevation_angle = self.fh.create_dataset(
            "global_data/detector_dx_dy_elevation_angle", (1,), h5py.h5t.NATIVE_DOUBLE
        )
        self.sample_rate = self.fh.create_dataset("global_data/sample_rate", (1,))
        self.tile_number = self.fh.create_dataset(
            "global_data/tile_number", (n_tones,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.tone_powers = self.fh.create_dataset(
            "global_data/tone_powers", (n_tones,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        self.rfsoc_number = self.fh.create_dataset(
            "global_data/rfsoc_number", (1,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.chan_number = self.fh.create_dataset(
            "global_data/chan_number", (1,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.chan_number.attrs.create(
            "info", "possibility of multiple raw files per channel per RFSOC"
        )
        self.ifslice_number = self.fh.create_dataset(
            "global_data/ifslice_number", (1,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.chanmask = self.fh.create_dataset(
            "global_data/chanmask", (n_tones,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.detector_delta_x = self.fh.create_dataset(
            GD+"detector_delta_x", (n_tones,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        self.detector_delta_y = self.fh.create_dataset(
            GD+"detector_delta_y", (n_tones,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        self.detector_beam_ampl = self.fh.create_dataset(
            GD+"detector_beam_ampl", (n_tones,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        self.detector_pol = self.fh.create_dataset(
            GD+"detector_pol", (n_tones,), dtype=h5py.h5t.NATIVE_INT32
        )
        self.dfoverf_per_mK = self.fh.create_dataset(
            GD+"dfoverf_per_mK", (n_tones,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        self.lo_freq = self.fh.create_dataset(
            GD+"lo_freq", (1,), dtype=h5py.h5t.NATIVE_DOUBLE
        )
        #lo_freq
        # ****************************** Time Ordered Data *****************************
        self.adc_i = self.fh.create_dataset(
            "time_ordered_data/adc_i",
            (n_fftbins, n_sample),
            chunks=(n_fftbins, 488),
            maxshape=(n_fftbins, None),
            dtype=h5py.h5t.STD_I32LE,
        )
        self.adc_q = self.fh.create_dataset(
            "time_ordered_data/adc_q",
            (n_fftbins, n_sample),
            chunks=(n_fftbins, 488),
            maxshape=(n_fftbins, None),
            dtype=h5py.h5t.STD_I32LE,
        )

        self.timestamp = self.fh.create_dataset(
            "time_ordered_data/timestamp", (n_sample,), chunks=(488,), maxshape=(None,), dtype=h5py.h5t.IEEE_F64LE
        )
        self.fh.flush()

    def resize(self, n_sample: int):
        """
        resize the dynamically allocated datasets. This will mostly be used by udp2.py to
        expand the data file to accomodate more data.
        """
        self.n_sample[0] = n_sample
        self.adc_i.resize((1024, n_sample))
        self.adc_q.resize((1024, n_sample))
        self.timestamp.resize((n_sample,))

    def set_global_data(self, chan: RFChannel):
        self.attenuator_settings[:] = chan.attenuator_settings
        self.baseband_freqs[:] = chan.baseband_freqs
        self.sample_rate[0] = chan.sample_rate
        self.tile_number[:] = chan.tile_number
        self.tone_powers[:] = chan.tone_powers
        self.tile_number[0] = chan.tile_number
        self.rfsoc_number[0] = chan.rfsoc_number
        self.ifslice_number[0] = chan.ifslice_number
        self.n_attenuators[0] = chan.n_attenuators
        self.lo_freq[0] = chan.lo_freq
        
        # ONR specific params below this line
        # TODO: future proofing this shall involve a seperate function 
        # that appends these datafields based on file name
        
        # In kidpy, the user shall call a function along the lines of 
        # "Append or include External Data".
        chanmaskpath = PARAMS_PATH + f"chanmask_{chan.name}.npy"
        detdx = PARAMS_PATH + f"detector_delta_x_tile{chan.tile_number}.npy"
        detdy = PARAMS_PATH + f"detector_delta_y_tile{chan.tile_number}.npy"
        det_ba = PARAMS_PATH + f"detector_beam_ampl_tile{chan.tile_number}.npy"
        det_pol = PARAMS_PATH + f"detector_pol_tile{chan.tile_number}.npy"
        dfoverf_per_mK = PARAMS_PATH + f"dfoverf_per_mK_tile{chan.tile_number}.npy"
        

        self.chanmask[:] = np.load(chanmaskpath)
        self.detector_delta_x[:] = np.load(detdx)
        self.detector_delta_y[:] = np.load(detdy)
        self.detector_dx_dy_elevation_angle[:] = 89.0
        self.detector_beam_ampl[:] = np.load(det_ba)
        self.detector_pol[:] = np.load(det_pol)
        self.dfoverf_per_mK[:] = np.load(dfoverf_per_mK)
            

    def read(self):
        """
        When called, the hdf5 file is read into this class instances variables to give them a nicer handle to work with.
        read() is called when a RawDataFile object is initialized and a datafile bearing the same name exists. That file may not
        have the same data or be from an older version of this file in which case an error may occur. Future iterations should be made
        more robust.

        The code used below to read the datasets from the RawDataFile was actually generated from gen_read given a blank RawDataFile.

        .. warning::
            changes to the name of a dataset must be identical to the instance variable identifier with which that dataset belongs.
            self.identifier = self.fh["/some/path/here/identifier"]
            
        """
        log = logger.getChild(__name__)

        if '/dimension/n_attenuators' in self.fh:
            self.n_attenuators = self.fh['/dimension/n_attenuators']
        else:
            self.n_attenuators = None

        if '/dimension/n_fftbins' in self.fh:
            self.n_fftbins = self.fh['/dimension/n_fftbins']
        else:
            self.n_fftbins = None

        if '/dimension/n_sample' in self.fh:
            self.n_sample = self.fh['/dimension/n_sample']
        else:
            self.n_sample = None

        if '/dimension/n_tones' in self.fh:
            self.n_tones = self.fh['/dimension/n_tones']
        else:
            self.n_tones = None

        if '/global_data/attenuator_settings' in self.fh:
            self.attenuator_settings = self.fh['/global_data/attenuator_settings']
        else:
            self.attenuator_settings = None

        if '/global_data/dfoverf_per_mK' in self.fh:
            self.dfoverf_per_mK = self.fh['/global_data/dfoverf_per_mK']
        else:
            self.dfoverf_per_mK = None

        if '/global_data/baseband_freqs' in self.fh:
            self.baseband_freqs = self.fh['/global_data/baseband_freqs']
        else:
            self.baseband_freqs = None

        if '/global_data/lo_freq' in self.fh:
            self.lo_freq = self.fh['/global_data/lo_freq']
        else:
            self.lo_freq = None

        if '/global_data/chan_number' in self.fh:
            self.chan_number = self.fh['/global_data/chan_number']
        else:
            self.chan_number = None

        if '/global_data/chanmask' in self.fh:
            self.chanmask = self.fh['/global_data/chanmask']
        else:
            self.chanmask = None

        if '/global_data/detector_beam_ampl' in self.fh:
            self.detector_beam_ampl = self.fh['/global_data/detector_beam_ampl']
        else:
            self.detector_beam_ampl = None

        if '/global_data/detector_delta_x' in self.fh:
            self.detector_delta_x = self.fh['/global_data/detector_delta_x']
        else:
            self.detector_delta_x = None

        if '/global_data/detector_delta_y' in self.fh:
            self.detector_delta_y = self.fh['/global_data/detector_delta_y']
        else:
            self.detector_delta_y = None

        if '/global_data/detector_pol' in self.fh:
            self.detector_pol = self.fh['/global_data/detector_pol']
        else:
            self.detector_pol = None

        if '/global_data/ifslice_number' in self.fh:
            self.ifslice_number = self.fh['/global_data/ifslice_number']
        else:
            self.ifslice_number = None

        if '/global_data/lo_sweep' in self.fh:
            self.lo_sweep = self.fh['/global_data/lo_sweep']
        else:
            self.lo_sweep = None

        if '/global_data/rfsoc_number' in self.fh:
            self.rfsoc_number = self.fh['/global_data/rfsoc_number']
        else:
            self.rfsoc_number = None

        if '/global_data/sample_rate' in self.fh:
            self.sample_rate = self.fh['/global_data/sample_rate']
        else:
            self.sample_rate = None

        if '/global_data/tile_number' in self.fh:
            self.tile_number = self.fh['/global_data/tile_number']
        else:
            self.tile_number = None

        if '/global_data/tone_powers' in self.fh:
            self.tone_powers = self.fh['/global_data/tone_powers']
        else:
            self.tone_powers = None

        if "/global_data/detector_dx_dy_elevation_angle" in self.fh:
            self.detector_dx_dy_elevation_angle = self.fh["/global_data/detector_dx_dy_elevation_angle"]
        else:
            self.detector_dx_dy_elevation_angle = None

        if '/time_ordered_data/adc_i' in self.fh:
            self.adc_i = self.fh['/time_ordered_data/adc_i']
        else:
            self.adc_i = None

        if '/time_ordered_data/adc_q' in self.fh:
            self.adc_q = self.fh['/time_ordered_data/adc_q']
        else:
            self.adc_q = None

        if '/time_ordered_data/timestamp' in self.fh:
            self.timestamp = self.fh['/time_ordered_data/timestamp']
        else:
            self.timestamp = None


    def append_lo_sweep(self, sweeppath: str):
        """
        Call this function to provide the RawDataFile with
        """
        log = logger.getChild(__name__)
        log.debug(f"Checking for file {sweeppath}")
        if os.path.exists(sweeppath):
            log.debug("found sweep file, appending.")
            sweepdata = np.load(sweeppath)
            self.fh.create_dataset("/global_data/lo_sweep", data=sweepdata)
        else:
            log.info("Specified sweep file does not exist. Will not append.")

    def close(self):
        """
        Close the RawDataFile
        """
        self.fh.close()


def gen_read(h5: str):
    """
    Cheat function. Reads an hdf5 file and generates a block of code for reading the data
    into the relevant class-instance variables. The code block is then written to a file.
    This method worked because the hdf5 dataset name is identical the same as the variable name.

    .. code::
        /time_ordered_data/adc_i --> self.fh.adc_i
        /global_data/somevar --> self.fh.somevar

    """
    f = h5py.File(h5, "r")
    rf = open("rawdatafilereadfunction.txt", 'w') #overwrites, previous

    def somefunc(name, object):
        if isinstance(object, h5py.Dataset):
            prop = object.name.split("/").pop()
            rf.write(f"if '{object.name}' in self.fh:\n")
            rf.write(f"    self.{prop} = self.fh['{object.name}']\n")
            rf.write(f"else:\n")
            rf.write(f"    self.{prop} = None\n\n")


    for k, v in f.items():
        if isinstance(v, h5py.Dataset):
            pass
        elif isinstance(v, h5py.Group):
            v.visititems(somefunc)
    rf.close()


def get_yymmdd():
    """
    Duplicate from onrkidpy
    """
    # get today's date string
    yy = "{}".format(date.today().year)
    mm = "{}".format(date.today().month)
    if date.today().month < 10:
        mm = "0" + mm
    dd = "{}".format(date.today().day)
    if date.today().day < 10:
        dd = "0" + dd
    yymmdd = yy + mm + dd
    return yymmdd


def get_last_lo(name: str):
    """
    Modified function to get the laster sweep file from data.
    this function expects a general file format consisting of the
    following.

    .. code::

        "/data/{yymmdd}/{yymmdd}_{name}_LO_Sweep_*.npy"
        example.
        /data/20230730/20230730_rfsoc1_LO_Sweep_hour15p4622.npy
        /data/20230730/20230730_rfsoc1_LO_Sweep_hour15p4625.npy
        /data/20230730/20230730_rfsoc1_LO_Sweep_hour15p4628.npy
    """
    # see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = "/data/" + yymmdd + "/"
    check_date_folder = glob.glob(date_folder)
    if np.size(check_date_folder) == 0:
        return ""

    fstring = f"/data/{yymmdd}/{yymmdd}_{name}_LO_Sweep_*.npy"
    g = glob.glob(fstring)

    if len(g) == 0:
        return ""

    g.sort()
    return g[-1]

def get_TOD_fset():
    """
    Gets the set of hdf5 readout data files for the day.
    """
    # see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = "/data/" + yymmdd + "/"
    check_date_folder = glob.glob(date_folder)
    if np.size(check_date_folder) == 0:
        return ""

    fstring = f"/data/{yymmdd}/{yymmdd}_*_TOD_set*.h5"
    g = glob.glob(fstring)

    if len(g) == 0:
        return []

    g.sort()
    return g


def get_last_rdf(name: str):
    """
    Modified function to get the latest RawDataFile
    following.

    .. code::

        "/data/{yymmdd}/{yymmdd}_{name}_TOD_set*.h5"
        example.
        /data/20230731/20230731_rfsoc1_TOD_set1001.h5
        /data/20230731/20230731_rfsoc1_TOD_set1002.h5

    """
    # see if we already have the parent folder for today's date
    yymmdd = get_yymmdd()
    date_folder = "/data/" + yymmdd + "/"
    check_date_folder = glob.glob(date_folder)
    if np.size(check_date_folder) == 0:
        return ""

    fstring = f"/data/{yymmdd}/{yymmdd}_{name}_TOD_set*.h5"
    g = glob.glob(fstring)

    if len(g) == 0:
        return ""

    g.sort()
    return g[-1]


# 20230731_TOD_set1002
if __name__ == "__main__":
    pass
