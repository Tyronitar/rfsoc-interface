"""Module for data storage classes."""

from __future__ import annotations

import glob
import json
import logging
import pdb
import shutil
import typing
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import overload

import h5py
import numpy as np
import numpy.typing as npt
from kidpy3.data_handler import RawDataFile

from rfsocinterface import __version__ as VERSION
from rfsocinterface.core.data.utils import (
    CALIBRATION_TABLE_DTYPE,
    TONES_TABLE_DTYPE,
    compute_df_per_mK,
    find_missed_packets,
    find_missed_packets_with_indices,
    generate_calibrated_data,
    get_channel_group_name,
    get_detector_positions,
    get_detector_positions_no_interp,
    get_step_group_name,
    interpolate_missing_data,
    interpolate_telescope_position,
    interpolate_timestamp_streaming,
    rotate_basis,
)
from rfsocinterface.core.sweeps import LoSweepData
from rfsocinterface.core.utils import (
    DEFAULT_DATA_DIRECTORY,
    PERMISSIONS_ALL_FULL,
    H5pyObject,
    PathLike,
    chunked_downsample,
    compute_chunk_shape,
    decimate_in_chunks,
    ensure_path,
    get_azel_template,
    get_consolidated_file_template,
    get_file_stub,
    get_git_hash,
    get_optcam_template,
    get_processed_file_template,
    get_tod_template,
    iterate_chunks,
    list_datasets,
    search,
)

_logger = logging.getLogger(__name__)


class DataStorage:
    """Thin wrapper around HDF5 files for data storage.

    Attributes:
        file (h5py.File): The file that the file is stored in.
    """

    @ensure_path(1)
    def __init__(self, filename: Path, mode: str = 'a'):
        """Initialize a DataStorage Object."""
        self.filename = filename
        self.file = None
        self.mode = None
        self.open(mode=mode)

    @overload
    @classmethod
    def load(cls, filename: str, mode: str = 'a') -> DataStorage:
        pass

    @overload
    @classmethod
    def load(
        cls,
        date: str,
        setnum: int,
        mode: str = 'a',
        data_dir: str = DEFAULT_DATA_DIRECTORY,
    ) -> DataStorage:
        pass

    @classmethod
    def load(
        cls, *args, mode: str = 'a', data_dir: str = DEFAULT_DATA_DIRECTORY
    ) -> DataStorage:
        """Load a data file."""
        if len(args) == 1:
            return cls(args[0], mode=mode)
        if len(args) == 2:  # noqa: PLR2004
            date, setnum = args
            filename = cls.get_template(date, setnum, data_dir=data_dir)
            return cls(filename, mode=mode)
        raise ValueError('Invalid number of arguments')

    def open(self, mode: str = 'r'):
        """Open the file in the specified mode."""
        self.file = h5py.File(self.filename, mode=mode)
        self.mode = mode

    def close(self):
        """Close the file."""
        if self.file is None:
            raise OSError(f'Attempting to close {self.filename} before opening file.')
        self.file.close()

    def get(self, name: str) -> H5pyObject:
        """Get an object from the file."""
        return self.file[name]

    def __getitem__(self, key):
        """Get an object from the file."""
        return self.get(key)

    def __delitem__(self, key: str):
        """Remove an object from the file."""
        del self.file[key]

    def has(self, name: str, exact_match: bool = False) -> bool:
        """Whether an key is present in the file."""
        res = self.search(name, exact_match=exact_match)
        return res is not None

    def __contains__(self, key: str) -> bool:
        """Whether an key is present in the file."""
        return key in self.file

    def search(
        self, name: str, full_name: bool = True, exact_match: bool = False
    ) -> tuple[str, H5pyObject] | None:
        """Search for a key in the file."""
        return search(self.file, name, full_name=full_name, exact_match=exact_match)

    def list_datasets(self, full_names: bool = False) -> list[tuple[str, h5py.Dataset]]:
        """Return a list of all datasets in the file."""
        return list_datasets(self.file, full_names=full_names)

    def list_dataset_names(self, full_names: bool = False) -> list[str]:
        """Return a list of all dataset names in the file."""
        return [name for (name, _) in self.list_datasets(full_names=full_names)]

    def create_group(
        self,
        name: str,
        track_order: bool | None = None,
        track_times: bool | None = None,
    ) -> h5py.Group:
        """Create a group in the file."""
        return self.file.create_group(
            name, track_order=track_order, track_times=track_times
        )

    def create_dataset(
        self,
        name: str,
        shape: tuple | None = None,
        dtype: npt.DTypeLike | None = None,
        data: npt.ArrayLike | None = None,
        chunks: tuple | bool | None = True,
        **kwargs,
    ) -> h5py.Dataset:
        """Create a new dataset in the file.

        Auto chunking enabled by default.
        """
        return self.file.create_dataset(
            name,
            shape=shape,
            dtype=dtype,
            data=data,
            chunks=chunks,
            **kwargs,
        )

    @property
    def attrs(self) -> h5py.AttributeManager:
        """The file's attributes."""
        return self.file.attrs

    @property
    def date(self) -> str:
        """The date of data collection."""
        date = self.attrs['date']
        if isinstance(date, bytes):
            return str(self.attrs['date'], encoding='utf-8')
        return str(date)

    @date.setter
    def date(self, date: str):
        self.attrs['date'] = date

    @property
    def setnum(self) -> int:
        """The set number."""
        return self.attrs['setnum']

    @setnum.setter
    def setnum(self, setnum: int):
        self.attrs['setnum'] = setnum

    @staticmethod
    def get_template(
        date: str, setnum: int, data_dir: str = DEFAULT_DATA_DIRECTORY
    ) -> str:
        """Get the filename template for this file."""
        raise NotImplementedError('Must be implemented by subclass')

    @property
    def tod_template(self) -> str:
        """The TOD filename for this data's date and setnum."""
        return get_tod_template(self.date, self.setnum)

    @property
    def azel_template(self) -> str:
        """The AZEL filename for this data's date and setnum."""
        return get_azel_template(self.date, self.setnum)

    @property
    def optcam_template(self) -> str:
        """The optcam filename for this data's date and setnum."""
        return get_optcam_template(self.date, self.setnum)

    @property
    def consolidated_file_template(self) -> str:
        """The consolidated data filename for this data's date and setnum."""
        return get_consolidated_file_template(self.date, self.setnum)

    @property
    def processed_file_template(self) -> str:
        """The processed data filename for this data's date and setnum."""
        return get_processed_file_template(self.date, self.setnum)

    @property
    def file_stub(self) -> str:
        """The file stub (i.e. <date>_set<setnum>)."""
        return get_file_stub(self.date, self.setnum)

    @property
    def folder(self) -> Path:
        """The folder this data is stored in."""
        return Path(self.filename).parent

    def __enter__(self):
        """Load the data file."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Clean up  the data file."""
        self.close()


class ConsolidatedData(DataStorage):
    """Class representing the data from the various sources consolidated into one file.

    Combines the data from the TOD files, LO sweeps, and params files into one file.
    """

    @typing.override
    @staticmethod
    def get_template(date: str, setnum: int, data_dir=DEFAULT_DATA_DIRECTORY):
        return get_consolidated_file_template(date, setnum, data_dir=data_dir)

    @classmethod
    def from_tod(  # noqa: PLR0912, PLR0915
        cls,
        date: str,
        setnum: int,
        data_dir: PathLike = DEFAULT_DATA_DIRECTORY,
        downsampling_factor: int = 1,
        use_pps: bool = True,
    ) -> ConsolidatedData:
        """Consolidate the data for the specified data set."""
        todtemplate = get_tod_template(date, setnum)
        tele_template = Path(get_azel_template(date, setnum))
        optcam_template = Path(get_optcam_template(date, setnum))

        azel_exists = tele_template.exists()
        optcam_exists = optcam_template.exists()
        if not optcam_exists:
            # Try old file naming format
            optcam_template = Path(get_optcam_template(date, setnum, old=True))
            optcam_exists = optcam_template.exists()

        if azel_exists:
            azel_file = h5py.File(tele_template, 'r')

        if optcam_exists:
            optcam_file = h5py.File(optcam_template, 'r')

        # Find TOD files
        todlist = glob.glob(todtemplate)
        nchan = len(todlist)
        if nchan == 0:
            raise FileNotFoundError(f'No TOD files found for {date} set {setnum}')

        # Get the n_tones and n_samples from all TOD files to determine array sizes
        sample_counts = []
        missed_sample_counts = []
        missed_packets_list = []
        tile_names = []
        tone_counts = []
        for file in todlist:
            raw_data = RawDataFile(file, 'r')
            if raw_data.lo_sweep is None:
                msg = f'File "{file}" does not have an LO sweep. Cannot process data.'
                _logger.error(msg)
                raise KeyError(msg)
            tone_counts.append(raw_data.n_tones[0])

            # TODO: Make kidpy store the tile name in the file
            # Temporary way to determine tile name from file names
            this_file_stem = Path(file).stem
            this_tile_name = this_file_stem[: this_file_stem.index('TOD')].split('_')[1]
            tile_names.append(this_tile_name)

            # Find the total number of samples accounting for missed packets
            # NOTE: Temporary fix until n_sample is fixed in the raw files
            # n_samples = f.n_sample[0]
            n_samples = raw_data.adc_i.shape[-1]

            if raw_data.pkt_idx is not None:
                _logger.debug('ConsolidatedData: Using pkt_idx to find missed packets')
                missed_packets = find_missed_packets_with_indices(raw_data.pkt_idx)
            else:
                missed_packets = find_missed_packets(raw_data.timestamp, n_samples)

            n_missed = int(np.sum(missed_packets[:, 1]))
            missed_sample_counts.append(n_missed)
            sample_counts.append(n_samples)
            missed_packets_list.append(missed_packets)

            raw_data.fh.close()

        # Normalize samle counts to the minimum across all channels
        total_samples = min(np.add(sample_counts, missed_sample_counts))
        n_samples_ds = int(np.ceil(total_samples / downsampling_factor))

        # NOTE: I forsee a potnetial bug where we try to interpolate the data for channel
        # say 2, which missed packet X, but channel 0 only had X - 1 total packets, so
        # trying to operate on packet X would be out of bounds. For now, we will just
        # limit the total samples to the minimum across all channels, and hope that this
        # doesn't happen.

        if azel_exists:
            # pdb.set_trace()
            az_tel = azel_file['az_tel']
            telescope_params = json.loads(azel_file.attrs.get('params', '{}'))
            try:
                za_tel = azel_file['za_tel']
            except KeyError:
                za_tel = azel_file['el_tel']
            timestamp_tel = azel_file['timestamp_tel']
            if 'az_pps' in azel_file:
                az_pps_tel = azel_file['az_pps']
                za_pps_tel = azel_file['za_pps']
            else:
                az_pps_tel = za_pps_tel = None
            # vis = azel_tfile.root.optical_visibility[0]
            vis = np.nan
            if isinstance(vis, bytes):
                vis = np.nan
        else:
            vis = 0.0

        # Initialize coalesced data file
        cfile_path = Path(
            get_consolidated_file_template(date, setnum, data_dir=data_dir)
        )
        if not cfile_path.exists():
            cfile_path.parent.mkdir(
                mode=PERMISSIONS_ALL_FULL, parents=True, exist_ok=True
            )
            cfile_path.touch(PERMISSIONS_ALL_FULL)
        cdata = cls(cfile_path, mode='w')
        cdata.date = date
        cdata.setnum = setnum

        # Create processing history
        processing_history = cdata.create_group('processing_history')
        step_0 = processing_history.create_group(get_step_group_name(0, 'consolidated'))
        step_0.attrs['name'] = 'ConsolidatedData'
        step_0.attrs['params'] = json.dumps(
            {'downsampling_factor': downsampling_factor}
        )
        step_0.attrs['rfsocinterface_version'] = VERSION
        step_0.attrs['code_version'] = get_git_hash()

        try:
            kidpy_version = version('kidpy3')
        except Exception as e:  # noqa: BLE001
            _logger.warning(f'kidpy3 version could not be accessed: {e}')
            kidpy_version = 'N/A'
        step_0.attrs['kidpy_version'] = kidpy_version

        # Initialize global data group
        global_data_group = cdata.create_group('global_data')
        global_data_group.attrs['n_samples'] = n_samples_ds

        if azel_exists:
            global_data_group.attrs['telescope_params'] = json.dumps(telescope_params)

        # Optical image
        if optcam_exists:
            _logger.info('ConsolidatedData: Copying optical data...')
            # optical_image = optcam_file.root.optical_image
            if 'optical_image' in optcam_file:
                global_data_group.create_dataset(
                    'optical_image', data=optcam_file['optical_image'][:]
                )
            elif 'optical_video' in optcam_file:
                global_data_group.create_dataset(
                    'optical_image', data=optcam_file['optical_video'][..., 0]
                )
                optical_video = optcam_file['optical_video']
                chunk_shape = (*optical_video.shape[:-1], 1)
                global_data_group.create_dataset(
                    'optical_video',
                    data=optical_video,
                    compression='lzf',
                    chunks=chunk_shape,
                )
                global_data_group.create_dataset(
                    'optical_video_timestamp', data=optcam_file['timestamp']
                )
            elif 'timestamp' in optcam_file:
                # Only 'timestamp' exists (i.e. video was saved in a seperate file)
                global_data_group.attrs['optical_video_file'] = optcam_file.attrs[
                    'video_file'
                ]
                global_data_group.create_dataset(
                    'optical_video_timestamp', data=optcam_file['timestamp']
                )
                global_data_group.create_dataset('optical_image', data=np.array([]))
            optcam_file.close()
        else:
            global_data_group.create_dataset('optical_image', data=np.array([]))
        global_data_group.create_dataset('optical_visibility', data=vis)

        chunk_shape_1d = compute_chunk_shape((), 8, max_chunk_size=total_samples)
        chunk_shape_1d_ds = compute_chunk_shape((), 8, max_chunk_size=n_samples_ds)
        timestamp = global_data_group.create_dataset(
            'timestamp',
            shape=(n_samples_ds,),
            chunks=chunk_shape_1d_ds,
            dtype=np.float64,
        )
        temp_timestamp = global_data_group.create_dataset(
            'temp_timestamp',
            shape=(total_samples,),
            chunks=chunk_shape_1d,
            dtype=np.float64,
        )
        least_samples_channel = np.argmin(np.add(sample_counts, missed_sample_counts))

        # Interpolate timestamp using the channel with the limiting number of samples
        raw_data = RawDataFile(todlist[least_samples_channel], 'r')
        # NOTE: Temporary fix until n_sample is fixed in the raw files
        # n_samples = f.n_sample[0]
        n_samples = raw_data.adc_i.shape[-1]
        this_missed_packets = missed_packets_list[least_samples_channel]
        if raw_data.pkt_idx is not None:
            pkt_idx = raw_data.pkt_idx
        else:
            pkt_idx = np.arange(n_samples)
            pkt_idx[this_missed_packets[:, 0]] += this_missed_packets[:, 1]
        _logger.info('ConsolidatedData: Interpolating timestamp...')
        interpolate_timestamp_streaming(
            raw_data.timestamp,
            temp_timestamp,
            pkt_idx,
        )
        _logger.info('ConsolidatedData: Downsampling timestamp...')
        chunked_downsample(
            temp_timestamp,
            timestamp,
            downsampling_factor,
            temp_timestamp.chunks[-1],
            use_filter=False,
        )
        raw_data.close()
        fs = 1 / (timestamp[1] - timestamp[0])
        global_data_group.attrs['fs'] = fs

        # Intiialize group for storing data per-channel
        all_channels_group = cdata.create_group('channels')
        all_channels_group.attrs['n_channels'] = nchan

        # Get the data from each channel
        for i_chan, file in enumerate(todlist):
            raw_data = RawDataFile(file, 'r')

            this_missed_packets = missed_packets_list[i_chan]
            this_n_missed = missed_sample_counts[i_chan]

            # Create the HDF5 group for this channel
            this_channel_group = all_channels_group.create_group(
                get_channel_group_name(i_chan)
            )
            this_channel_group.attrs['tile_name'] = tile_names[i_chan]
            this_channel_group.attrs['f_center'] = raw_data.lo_freq[0]
            this_channel_group.attrs['detector_dx_dy_elevation_angle'] = (
                raw_data.detector_dx_dy_elevation_angle[:]
            )
            this_channel_group.attrs['attenuator_settings'] = (
                raw_data.attenuator_settings[:]
            )
            n_tones = raw_data.n_tones[0]
            this_channel_group.attrs['n_tones'] = n_tones

            # Store the tone parameters
            tones_table = this_channel_group.create_dataset(
                'tones', shape=(n_tones,), dtype=TONES_TABLE_DTYPE
            )

            tones_table['baseband_freq'] = raw_data.baseband_freqs[:]
            tones_table['power'] = raw_data.tone_powers[:]
            tones_table['delta_x'] = raw_data.detector_delta_x[:]
            tones_table['delta_y'] = raw_data.detector_delta_y[:]
            tones_table['beam_amplitude'] = raw_data.detector_beam_ampl[:]
            tones_table['polarization'] = raw_data.detector_pol[:]
            tones_table['dfoverf_per_mK'] = raw_data.dfoverf_per_mK[:] * -1
            chanmask = raw_data.chanmask[:]
            off_res = np.argwhere(chanmask == 0).flatten()
            no_pol = np.argwhere(tones_table['polarization'] < 1).flatten()
            chanmask[no_pol] = -1
            chanmask[off_res] = 0  # Preserve off-resonance indices
            tones_table['chanmask'] = chanmask

            # Copy LO sweep
            this_channel_group.create_dataset('lo_sweep', data=raw_data.lo_sweep[:])

            # Compute the chunk sizes to use
            azel_shape = (n_tones, total_samples) if azel_exists else (n_tones, 1)
            azel_shape_ds = (n_tones, n_samples_ds) if azel_exists else (n_tones, 1)
            chunk_shape_3d = compute_chunk_shape(
                (2, n_tones), 8, max_chunk_size=total_samples
            )
            chunk_shape_3d_ds = compute_chunk_shape(
                (2, n_tones), 8, max_chunk_size=n_samples_ds
            )
            chunk_shape_azel = compute_chunk_shape(
                (1,), 8, max_chunk_size=azel_shape[-1]
            )
            chunk_shape_azel_ds = compute_chunk_shape(
                (1,), 8, max_chunk_size=azel_shape_ds[-1]
            )

            # Time ordered data
            time_ordered_data_group = this_channel_group.create_group(
                'time_ordered_data'
            )
            interpolated_samples = time_ordered_data_group.create_dataset(
                'interpolated_samples',
                shape=(0,),
                maxshape=(None,),
                dtype=np.uint32,
            )
            data_IQ = time_ordered_data_group.create_dataset(
                'data_IQ',
                shape=(2, n_tones, n_samples_ds),
                dtype=np.float64,
                chunks=chunk_shape_3d_ds,
                compression='lzf',
                shuffle=True,
            )
            # Create temporary datasets for the pre-downsampled data
            temp_interpolated_samples = time_ordered_data_group.create_dataset(
                'temp_interpolated_samples',
                shape=(0,),
                maxshape=(None,),
                dtype=np.uint32,
            )
            temp_data_IQ = time_ordered_data_group.create_dataset(
                'temp_data_IQ',
                shape=(2, n_tones, total_samples),
                dtype=np.float64,
                chunks=chunk_shape_3d,
                compression='lzf',
                shuffle=True,
            )
            # Detector Positions
            temp_detector_az = time_ordered_data_group.create_dataset(
                'temp_detector_az',
                shape=azel_shape,
                chunks=chunk_shape_azel,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            temp_detector_za = time_ordered_data_group.create_dataset(
                'temp_detector_za',
                shape=azel_shape,
                chunks=chunk_shape_azel,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            detector_az = time_ordered_data_group.create_dataset(
                'detector_az',
                shape=azel_shape_ds,
                chunks=chunk_shape_azel_ds,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )
            detector_za = time_ordered_data_group.create_dataset(
                'detector_za',
                shape=azel_shape_ds,
                chunks=chunk_shape_azel_ds,
                dtype=np.float64,
                compression='lzf',
                shuffle=True,
            )

            if raw_data.pkt_idx is not None:
                pkt_idx = raw_data.pkt_idx
            else:
                pkt_idx = np.arange(n_samples)
                for sample, n_missed in this_missed_packets:
                    pkt_idx[sample:] += n_missed
            valid_tone_index = np.arange(n_tones, dtype=int) + 0

            # Interpolate missing IQ data
            if this_n_missed > 0:
                _logger.info('ConsolidatedData: Interpolating missing IQ data...')
                interpolate_missing_data(
                    raw_data.adc_i,
                    raw_data.adc_q,
                    temp_timestamp,
                    temp_data_IQ,
                    temp_interpolated_samples,
                    pkt_idx,
                    this_missed_packets,
                    valid_tone_index,
                )

            _logger.info('ConsolidatedData: Copying Raw IQ data...')
            chunk_shape_read_adc = compute_chunk_shape(
                (1024,), 8, max_chunk_size=n_samples
            )
            for chunk_start, chunk_end, chunk in iterate_chunks(
                raw_data.adc_i, chunk_size=chunk_shape_read_adc[-1]
            ):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[0, :, sample_indices] = chunk[valid_tone_index]

            for chunk_start, chunk_end, chunk in iterate_chunks(
                raw_data.adc_q, chunk_size=chunk_shape_read_adc[-1]
            ):
                sample_indices = pkt_idx[chunk_start:chunk_end] - pkt_idx[0]
                temp_data_IQ[1, :, sample_indices] = chunk[valid_tone_index]

            # Detector Positions
            if azel_exists:
                _logger.info('ConsolidatedData: Computing detector positions...')
                if (
                    use_pps
                    and raw_data.pps is not None
                    and az_pps_tel is not None
                    and za_pps_tel is not None
                ):
                    corrected_az_tel = interpolate_telescope_position(
                        temp_timestamp,
                        timestamp_tel[:],
                        az_tel[:],
                        az_pps_tel[:],
                        raw_data.pps[:],
                        direction='az',
                    )
                    corrected_za_tel = interpolate_telescope_position(
                        temp_timestamp,
                        timestamp_tel[:],
                        za_tel[:],
                        za_pps_tel[:],
                        raw_data.pps[:],
                        direction='za',
                    )
                    get_detector_positions_no_interp(
                        corrected_az_tel,
                        corrected_za_tel,
                        temp_detector_az,
                        temp_detector_za,
                        tones_table['delta_x'][:],
                        tones_table['delta_y'][:],
                        this_channel_group.attrs['detector_dx_dy_elevation_angle'],
                    )
                else:
                    get_detector_positions(
                        temp_timestamp,
                        timestamp_tel[:],
                        az_tel[:],
                        za_tel[:],
                        temp_detector_az,
                        temp_detector_za,
                        tones_table['delta_x'][:],
                        tones_table['delta_y'][:],
                        this_channel_group.attrs['detector_dx_dy_elevation_angle'],
                    )

            # Downsample timestamp and IQ data
            _logger.info('ConsolidatedData: Downsampling IQ data...')
            decimate_in_chunks(
                temp_data_IQ,
                data_IQ,
                downsampling_factor,
                chunk_shape=temp_data_IQ.chunks,
            )
            downsampled_interpolated_samples = np.array(
                [
                    sample // downsampling_factor
                    for sample in temp_interpolated_samples
                    if sample % downsampling_factor == 0
                ]
            )
            interpolated_samples.resize(downsampled_interpolated_samples.shape)
            interpolated_samples = downsampled_interpolated_samples[:]

            if azel_exists:
                _logger.info(
                    'ConsolidatedData: Downsampling detector position arrays...'
                )
                chunked_downsample(
                    temp_detector_az,
                    detector_az,
                    downsampling_factor,
                    detector_az.chunks[-1],
                    use_filter=False,
                )
                chunked_downsample(
                    temp_detector_za,
                    detector_za,
                    downsampling_factor,
                    detector_za.chunks[-1],
                    use_filter=False,
                )

            # Delete temporary datasets
            del time_ordered_data_group['temp_data_IQ']
            del time_ordered_data_group['temp_interpolated_samples']
            del time_ordered_data_group['temp_detector_az']
            del time_ordered_data_group['temp_detector_za']

        # Get rid of full timestamp now that data from all channels read
        del global_data_group['temp_timestamp']

        # Create virtual datasets
        vdsets = cdata.create_group('vdsets')
        total_tones = sum(tone_counts)
        vdsets.attrs['n_tones'] = total_tones
        vdsets.attrs['n_samples'] = n_samples_ds
        channel_groups = all_channels_group.items()
        data_IQ_layout = h5py.VirtualLayout((2, total_tones, n_samples_ds), 'f8')
        azel_shape = (total_tones, n_samples_ds) if azel_exists else (total_tones, 1)
        detector_az_layout = h5py.VirtualLayout(azel_shape, 'f8')
        detector_za_layout = h5py.VirtualLayout(azel_shape, 'f8')
        tones_table_layout = h5py.VirtualLayout((total_tones,), TONES_TABLE_DTYPE)

        i_tone = 0
        for _, channel_group in channel_groups:
            n_tones = channel_group.attrs['n_tones']
            this_data_group = channel_group['time_ordered_data']
            data_IQ_layout[:, i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['data_IQ']
            )
            detector_az_layout[i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['detector_az']
            )
            detector_za_layout[i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['detector_za']
            )
            tones_table_layout[i_tone : i_tone + n_tones] = h5py.VirtualSource(
                channel_group['tones']
            )
            i_tone += n_tones

        vdsets.create_virtual_dataset('data_IQ', data_IQ_layout)
        vdsets.create_virtual_dataset('detector_az', detector_az_layout)
        vdsets.create_virtual_dataset('detector_za', detector_za_layout)
        vdsets.create_virtual_dataset('tones', tones_table_layout)

        return cdata

    def create_processed_data(self, mode: str = 'a') -> ProcessedData:
        """Create the processed data from this consolidated data."""
        pfile_path = Path(self.processed_file_template)
        self.close()
        shutil.copy2(self.filename, pfile_path)
        if self.mode == 'w':
            self.mode = 'a'
        self.open(self.mode)

        pd = ProcessedData(pfile_path, mode=mode)
        pd.initialize_processed_data_fields()
        return pd


class ProcessedData(DataStorage):
    """Storage of downstream processed data."""

    @typing.override
    @staticmethod
    def get_template(date: str, setnum: int, data_dir=DEFAULT_DATA_DIRECTORY):
        return get_processed_file_template(date, setnum, data_dir=data_dir)

    def initialize_processed_data_fields(self):
        """Initialize the datasets unique to the ProcessedData File.

        Will create the following datasets for each channel:
            * data_gain_phase (2, n_tones, n_samples): Detector data rotated to
                gain/phase basis.
            * data_freq_diss (2, n_tones, n_samples): Detector data rotated to
                frequency/dissipation basis.
            * data_mK (n_tones, n_samples): Calibrated detector data in mK units.
            * carrier_amplitudes (2, n_tones): The median I/Q values for each tone.
            * calibration_info (n_tones,): Structered datset containing various
                information for creating the calibrated data. Contains:
                * adc_units_to_hz: Conversion factor from ADC units (IQ data) to
                    Hz (frequency/dissipation).
                * IQ_to_gain_phase_angle: Angle in radians to rotate IQ basis to
                    gain/phase.
                * IQ_to_freq_diss_angle: Angle in radians to rotate IQ basis to
                    frequency/dissipation.
                * df_per_mK: Conversion factor to convert Hz to mK.
        Also creates virtual datasets for each dataset, combined across channels.
        """
        n_samples = self['global_data'].attrs['n_samples']
        for channel_group in self['channels'].values():
            time_ordered_data_group: h5py.Group = channel_group['time_ordered_data']
            n_tones = channel_group.attrs['n_tones']
            data_IQ = time_ordered_data_group['data_IQ']
            tones_table = channel_group['tones']

            # Initialize caliibration-related datasets
            data_gain_phase = time_ordered_data_group.create_dataset_like(
                'data_gain_phase', data_IQ
            )
            data_freq_diss = time_ordered_data_group.create_dataset_like(
                'data_freq_diss', data_IQ
            )
            mK_chunks = compute_chunk_shape((n_tones,), 8, max_chunk_size=n_samples)
            data_mK = time_ordered_data_group.create_dataset(
                'data_mK',
                (n_tones, n_samples),
                dtype=np.float64,
                chunks=mK_chunks,
            )
            carrier_amplitudes = time_ordered_data_group.create_dataset(
                'carrier_amplitudes', data=np.nanmedian(data_IQ[:], axis=-1)
            )
            calibration_info = channel_group.create_dataset(
                'calibration_info',
                shape=(n_tones,),
                dtype=CALIBRATION_TABLE_DTYPE,
            )

            # Collect calibration information
            sweep = LoSweepData(
                tones_table['baseband_freq'],
                channel_group.attrs['f_center'],
                channel_group['lo_sweep'][:],
                tones_table['chanmask'],
                channel_group.attrs['tile_name'],
            )
            IQ_to_freq_diss_angle, adc_units_to_hz = sweep.freq_direction()
            calibration_info['IQ_to_freq_diss_angle'] = IQ_to_freq_diss_angle
            calibration_info['adc_units_to_hz'] = adc_units_to_hz

            detector_f = tones_table['baseband_freq'] + channel_group.attrs['f_center']
            df_per_mK = compute_df_per_mK(
                tones_table['polarization'],
                tones_table['beam_amplitude'],
                detector_f,
                tones_table['dfoverf_per_mK'],
            )
            calibration_info['df_per_mK'] = df_per_mK

            # Rotate to Gain / Phase
            IQ_to_gain_phase_angle = np.atan2(
                carrier_amplitudes[0], carrier_amplitudes[1]
            )
            calibration_info['IQ_to_gain_phase_angle'] = IQ_to_gain_phase_angle
            rotate_basis(
                data_IQ,
                data_gain_phase,
                IQ_to_gain_phase_angle,
            )

            # Generate calibrated data
            # First mean center IQ data
            data_IQ[:] = data_IQ[:] - np.mean(data_IQ, axis=-1, keepdims=True)
            generate_calibrated_data(
                data_IQ,
                data_freq_diss,
                data_mK,
                IQ_to_freq_diss_angle,
                adc_units_to_hz,
                df_per_mK,
            )

        # Make virtual datasets for the new stuff
        total_tones = self['vdsets'].attrs['n_tones']
        data_gain_phase_layout = h5py.VirtualLayout((2, total_tones, n_samples), 'f8')
        data_freq_diss_layout = h5py.VirtualLayout((2, total_tones, n_samples), 'f8')
        data_mK_layout = h5py.VirtualLayout((total_tones, n_samples), 'f8')
        carrier_amplitudes_layout = h5py.VirtualLayout((2, total_tones), 'f8')
        calibration_info_layout = h5py.VirtualLayout(
            (total_tones,), CALIBRATION_TABLE_DTYPE
        )

        i_tone = 0
        for channel_group in self['channels'].values():
            n_tones = channel_group.attrs['n_tones']
            this_data_group = channel_group['time_ordered_data']
            data_gain_phase_layout[:, i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['data_gain_phase']
            )
            data_freq_diss_layout[:, i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['data_freq_diss']
            )
            data_mK_layout[i_tone : i_tone + n_tones] = h5py.VirtualSource(
                this_data_group['data_mK']
            )
            carrier_amplitudes_layout[:, i_tone : i_tone + n_tones] = (
                h5py.VirtualSource(this_data_group['carrier_amplitudes'])
            )
            calibration_info_layout[i_tone : i_tone + n_tones] = h5py.VirtualSource(
                channel_group['calibration_info']
            )
            i_tone += n_tones

        self['vdsets'].create_virtual_dataset('data_gain_phase', data_gain_phase_layout)
        self['vdsets'].create_virtual_dataset('data_freq_diss', data_freq_diss_layout)
        self['vdsets'].create_virtual_dataset('data_mK', data_mK_layout)
        self['vdsets'].create_virtual_dataset(
            'carrier_amplitudes', carrier_amplitudes_layout
        )
        self['vdsets'].create_virtual_dataset(
            'calibration_info', calibration_info_layout
        )

    #
    # Useful getter methods
    #
    def list_history(self) -> list[dict]:
        """Return a list of each processing step."""
        if not self.has('processing_history'):
            return []
        hist = self['processing_history']
        return list(hist.keys())

    def print_history(self, verbose: bool = False):
        """Print the processing history for this file."""
        if not self.has('processing_history'):
            print('No history')  # noqa: T201
            return

        hist = self.file['processing_history']

        for k in sorted(hist.keys()):
            step = hist[k]
            name = step.attrs.get('name', '?')
            if verbose:
                print(f'[{k}]:\n{json.dumps(dict(step.attrs), indent=4)}')  # noqa: T201
            else:
                params = json.loads(step.attrs.get('params', '{}'))

                param_str = ', '.join(f'{k}={v}' for k, v in params.items())
                print(f'[{k}] {name}({param_str})')  # noqa: T201

    def channels(self) -> Iterator[h5py.Group]:
        """Return an iterator over each channel group."""
        yield from self['channels'].values()

    def get_channel_group(self, i_chan: int) -> h5py.Group:
        """Return the specified channel group."""
        return self[f'channels/channel_{i_chan:03d}']

    def get_channel_group_from_tile_name(self, tile_name: str) -> h5py.Group:
        """Return the specified channel group by tile name."""
        tile_names = []
        for channel_group in self['channels'].values():
            this_tile_name = channel_group.attrs['tile_name']
            tile_names.append(this_tile_name)
            if this_tile_name == tile_name:
                return channel_group
        msg = (
            f'Unable to find channel with name "{tile_name}". Tile names found: '
            f'{tile_names}'
        )
        raise KeyError(msg)

    def get_from_channel(self, i_chan: int, obj_name: str) -> H5pyObject:
        """Return the object from the specified channel group."""
        return self.get_channel_group(i_chan)[obj_name]

    def get_from_all_channels(self, obj_name: str) -> list[H5pyObject]:
        """Return a list of `obj_name` from each channel group."""
        return [channel_group[obj_name] for channel_group in self['channels'].values()]

    def search_in_channel(
        self, i_chan: int, name: str, full_name: bool = True, exact_match: bool = False
    ) -> tuple[str, H5pyObject] | None:
        """Search for the name in the specified channel group."""
        return search(
            self.get_channel_group(i_chan),
            name,
            full_name=full_name,
            exact_match=exact_match,
        )

    def search_in_all_channels(
        self, name: str, full_name: bool = True, exact_match: bool = False
    ) -> list[tuple[str, H5pyObject]] | None:
        """Search for the name in the each channel group."""
        return [
            search(channel_group, name, full_name=full_name, exact_match=exact_match)
            for channel_group in self['channels'].values()
        ]

    def get_n_tones(self, i_chan: int) -> int:
        """Return n_tones for the specified channel."""
        return self.get_channel_group(i_chan).attrs['n_tones']

    def get_chanmask(self, i_chan: int) -> npt.NDArray:
        """Return the chanmask for the specified channel."""
        return self.get_from_channel(i_chan, 'tones')['chanmask']

    def get_onres_ind(self, i_chan: int) -> npt.NDArray:
        """Return on-resonance indices for the specified channel."""
        return np.argwhere(self.get_chanmask(i_chan) == 1).flatten()

    def get_offres_ind(self, i_chan: int) -> npt.NDArray:
        """Return off-resonance indices for the specified channel."""
        return np.argwhere(self.get_chanmask(i_chan) == 0).flatten()

    #
    # Useful properties
    #
    @property
    def n_chan(self) -> int:
        """The nmuber of channels."""
        return self['channels'].attrs['n_channels']

    @property
    def n_samples(self) -> int:
        """The nmuber of samples collected."""
        return self['vdsets'].attrs['n_samples']

    @property
    def n_tones(self) -> int:
        """The total nmuber of tones."""
        return self['vdsets'].attrs['n_tones']

    @property
    def fs(self) -> float:
        """Return the averaged sampling rate across channels."""
        return self['global_data'].attrs['fs']

    @property
    def virtual_datasets(self) -> h5py.Group:
        """The virtual dataset group in the file."""
        return self['vdsets']

    # Time-ordered data
    @property
    def timestamp(self) -> h5py.Dataset:
        """The timestamps for each data sample.."""
        return self['global_data/timestamp']

    @property
    def optical_image(self) -> h5py.Dataset:
        """The optical image."""
        return self['global_data/optical_image']

    @property
    def optical_visibility(self) -> h5py.Dataset:
        """The optical visibility at the time of data capture."""
        return self['global_data/optical_visibility']

    @property
    def data_IQ(self) -> h5py.Dataset:
        """The data in ADC units."""
        return self['vdsets/data_IQ']

    @property
    def data_gain_phase(self) -> h5py.Dataset:
        """The data in the gain/phase basis."""
        return self['vdsets/data_gain_phase']

    @property
    def data_freq_diss(self) -> h5py.Dataset:
        """The data in the frequency/dissipation basis."""
        return self['vdsets/data_freq_diss']

    @property
    def data_mK(self) -> h5py.Dataset:
        """The data in milikelvin."""
        return self['vdsets/data_mK']

    @property
    def detector_az(self) -> h5py.Dataset:
        """Azimuthal angle for each detector at each timestamp."""
        return self['vdsets/detector_az']

    @property
    def detector_za(self) -> h5py.Dataset:
        """Zenith angle for each detector at each timestamp."""
        return self['vdsets/detector_za']

    #
    # Tone/detector properties
    #
    @property
    def tones_table(self) -> h5py.Dataset:
        """The table containing tone-specific values.

        Contains the keys:
            baseband_freq: The frequency of the tone relative to the baseband.
            power: The relative power of this tone.
            delta_x: The x position relative to the center of the focal plane.
            delta_y: The y position relative to the center of the focal plane.
            beam_amplitude: The beam amplitude for this resonator.
            polarization: The polarization for this resonator.
            dfoverf_per_mK: The change in df/f per mK for this tone.
            chanmask: Mask value indicating if this tone is on-resonance (1),
                off-resonance (0), or flagged as bad (-1).
        """
        return self['vdsets/tones']

    def _set_table_field(
        self, table_name: str, field_name: str, new_values: npt.NDArray
    ):
        """Utility function for setting table fields.

        Setting values through virtual datasets doesn't work for tables, so this is the
        work around.
        """
        i_tone = 0
        for i_chan in range(self.n_chan):
            channel_group = self.get_channel_group(i_chan)
            n_tones = channel_group.attrs['n_tones']
            channel_group[table_name][field_name] = new_values[
                i_tone : i_tone + n_tones
            ]
            i_tone += n_tones

    @property
    def tone_counts(self) -> npt.NDArray:
        """The number of tones for each channel."""
        counts = [self.get_n_tones(i_chan) for i_chan in range(self.n_chan)]
        return np.array(counts)

    def get_channel_index_from_tone_index(self, tone_index: int) -> int:
        """Get which channel `tone_index` is a part of."""
        cumulative_counts = np.cumsum(self.tone_counts)
        return np.searchsorted(cumulative_counts, tone_index, side='right')

    @property
    def baseband_freqs(self) -> npt.NDArray:
        """The frequencies relative to baseband."""
        return self.tones_table['baseband_freq']

    def set_baseband_freqs(self, new_freqs: npt.NDArray):
        """Set the frequencies relative to baseband."""
        self._set_table_field('tones', 'baseband_freq', new_freqs)

    def get_f_center(self, i_chan: int) -> float:
        """Return the LO frequency for the specified channel."""
        return self.get_channel_group(i_chan).attrs['f_center']

    def detector_f(self) -> npt.NDArray:
        """The absolute frequency of each tone."""
        f = self.baseband_freqs
        i_tone = 0
        for channel_group in self.channels():
            n_tones = channel_group.attrs['n_tones']
            f[i_tone : i_tone + n_tones] += channel_group.attrs['f_center']
            i_tone += n_tones
        return f

    @property
    def tone_powers(self) -> npt.NDArray:
        """The relative power level for each tone."""
        return self.tones_table['power']

    def set_tone_powers(self, new_powers: npt.NDArray):
        """Set the relative power level for each tone."""
        self._set_table_field('tones', 'power', new_powers)

    @property
    def chanmask(self) -> npt.NDArray:
        """Mask indicating on/off resonance tones and bad resonators."""
        return self.tones_table['chanmask']

    def set_chanmask(self, new_chanmask: npt.NDArray):
        """Update the chanmask."""
        self._set_table_field('tones', 'chanmask', new_chanmask)

    @property
    def onres_ind(self) -> npt.NDArray:
        """The indices of on-resonance tones."""
        return np.argwhere(self.chanmask == 1).flatten().astype(int)

    @property
    def offres_ind(self) -> npt.NDArray:
        """The indices of off-resonance tones."""
        return np.argwhere(self.chanmask == 0).flatten().astype(int)

    @property
    def detector_pol(self) -> npt.NDArray:
        """The polarization of each resonator."""
        return self.tones_table['polarization']

    def set_detector_pol(self, new_pols: npt.NDArray):
        """Update detector_pol."""
        self._set_table_field('tones', 'polarization', new_pols)

    @property
    def pol_ind_1(self) -> npt.NDArray:
        """Which tones are polarization 1."""
        return np.argwhere(self.detector_pol == 1).flatten()

    @property
    def pol_ind_2(self) -> npt.NDArray:
        """Which tones are polarization 2."""
        return np.argwhere(self.detector_pol == 2).flatten()  # noqa: PLR2004

    @property
    def detector_beam_ampl(self) -> npt.NDArray:
        """The beam amplitude for each resonator."""
        return self.tones_table['beam_amplitude']

    def set_detector_beam_ampl(self, new_ampls: npt.NDArray):
        """Update the detector_beam_ampl."""
        self._set_table_field('tones', 'beam_amplitude', new_ampls)

    @property
    def detector_delta_x(self) -> npt.NDArray:
        """The x position relative to the center of the focal plane."""
        return self.tones_table['delta_x']

    def set_detector_delta_x(self, new_delta_x: npt.NDArray):
        """Update detector_delta_x."""
        self._set_table_field('tones', 'delta_x', new_delta_x)

    @property
    def detector_delta_y(self) -> npt.NDArray:
        """The y position relative to the center of the focal plane."""
        return self.tones_table['delta_y']

    def set_detector_delta_y(self, new_delta_y: npt.NDArray):
        """Update detector_delta_y."""
        self._set_table_field('tones', 'delta_y', new_delta_y)

    @property
    def dfoverf_per_mK(self) -> npt.NDArray:
        """The change in df/f per mK for each resonator."""
        return self.tones_table['dfoverf_per_mK']

    def set_dfoverf_per_mK(self, new_dfoverf_per_mK: npt.NDArray):
        """Update dfoverf_per_mK."""
        self._set_table_field('tones', 'dfoverf_per_mK', new_dfoverf_per_mK)

    @property
    def carrier_amplitudes(self) -> h5py.Dataset:
        """The median amplitude of the raw I and Q signals."""
        return self['vdsets/carrier_amplitudes']

    def carrier_amplitude_norm(self) -> float:
        """The norm of the carrier amplitudes."""
        amps = self.carrier_amplitudes[:]
        z = amps[0] + amps[1] * 1j
        return np.mean(np.abs(z))

    #
    # Calibration information
    #
    @property
    def calibration_info(self) -> h5py.Dataset:
        """Table containing calibration-relevant information.

        Contains the keys:
            adc_units_to_hz: The conversion factor from ADC units to Hz.
            IQ_to_gain_phase_angle: The rotation angle from ADC units to gain/phase.
            IQ_to_freq_diss_angle: The rotation angle from ADC units to frequency/
                dissipation.
            df_per_mK: The change in frequency per mK.
        """
        return self['vdsets/calibration_info']

    @property
    def adc_units_to_hz(self) -> npt.NDArray:
        """The conversion factor from ADC units to Hz."""
        return self.calibration_info['adc_units_to_hz']

    def set_adc_units_to_hz(self, new_adc_units_to_hz: npt.NDArray):
        """Update adc_units_to_hz."""
        self._set_table_field(
            'calibration_info', 'adc_units_to_hz', new_adc_units_to_hz
        )

    @property
    def IQ_to_gain_phase_angle(self) -> npt.NDArray:
        """The rotation angle from ADC units to gain/phase."""
        return self.calibration_info['IQ_to_gain_phase_angle']

    def set_IQ_to_gain_phase_angle(self, new_angle: npt.NDArray):
        """Update IQ_to_gain_phase_angle."""
        self._set_table_field('calibration_info', 'IQ_to_gain_phase_angle', new_angle)

    @property
    def IQ_to_freq_diss_angle(self) -> npt.NDArray:
        """The rotation angle from ADC units to frequency/dissipation."""
        return self.calibration_info['IQ_to_freq_diss_angle']

    def set_IQ_to_freq_diss_angle(self, new_angle: npt.NDArray):
        """Update IQ_to_freq_diss_angle."""
        self._set_table_field('calibration_info', 'IQ_to_freq_diss_angle', new_angle)

    @property
    def df_per_mK(self) -> npt.NDArray:
        """The change in frequency per mK."""
        return self.calibration_info['df_per_mK']

    def set_df_per_mK(self, new_df_per_mK: npt.NDArray):
        """Update df_per_mK."""
        self._set_table_field('calibration_info', 'df_per_mK', new_df_per_mK)


if __name__ == '__main__':
    # Telescope Testing
    date = '20260320'
    setnum = 1010
    # Lab Testing
    # date = '20260212'
    # setnum = 1003

    cd = ConsolidatedData.from_tod(date, setnum, downsampling_factor=8)
    pd = cd.create_processed_data()

    pdb.set_trace()
