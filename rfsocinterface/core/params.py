"""Handle RFSoC Parameter Files."""

from __future__ import annotations

import logging
import pdb
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from kidpy3 import RawDataFile
from matplotlib.figure import Figure
from packaging.version import Version

from rfsocinterface.core.utils import (
    DEFAULT_PARAMS_DIRECTORY,
    PERMISSIONS_ALL_FULL,
    PathLike,
    convert_path,
    ensure_path,
    get_params_file_template,
    mHz_axis_formatter,
    mHz_coordinate_formatter,
)

_logger = logging.getLogger(__name__)


PARAM_FILE_N_TONE_ATTRIBUTES = [
    'baseband_freqs',
    'tone_powers',
    'detector_delta_x',
    'detector_delta_y',
    'detector_pol',
    'detector_beam_ampl',
    'dfoverf_per_mK',
    'chanmask',
]


class RFSoCParameters:
    """Class wrapping around RFSoC parameters files."""

    VERSION = Version('1.0.0')

    @ensure_path(1)
    def __init__(self, file: Path, mode: str = 'r'):
        """Initialize a RFSoCParameters."""
        self._file = h5py.File(file, mode=mode)
        self._test_format()

    def _test_format(self):
        """Test that the params file is compatible with current format."""
        fail = False
        if 'params_version' not in self._file.attrs:
            fail = True  # Made before the version parameter
        elif self.version.release[0] != RFSoCParameters.VERSION.release[0]:
            # Major version differs (incompatible)
            fail = True  # Outdated format

        if fail:
            raise ValueError(
                f'File "{self._file.filename}" is not an appropriate format. '
                'Use `update_params_file_format` to update the file and try again.'
            )

    @classmethod
    def new_file(
        cls,
        tile_name: str,
        n_tones: int,
        mode: str = 'a',
        params_dir: Path = DEFAULT_PARAMS_DIRECTORY,
    ) -> RFSoCParameters:
        """Create a new parameters file with the desired tile name."""
        filename = Path(get_params_file_template(tile_name, params_dir=params_dir))
        if not filename.exists():
            filename.touch(PERMISSIONS_ALL_FULL)
        with h5py.File(filename, 'w') as fh:
            # Attributes
            fh.attrs['tile_name'] = tile_name
            fh.attrs['n_tones'] = n_tones
            fh.attrs['f_center'] = 400e6
            fh.attrs['rfin'] = 0.0
            fh.attrs['rfout'] = 0.0
            fh.attrs['tile_number'] = 0
            fh.attrs['chan_number'] = 0
            fh.attrs['ifslice_number'] = 0
            fh.attrs['params_version'] = str(RFSoCParameters.VERSION)

            # Datasets
            fh.create_dataset(
                'chanmask',
                shape=(n_tones,),
                maxshape=(1024,),
                dtype=np.int8,
                fillvalue=1,
            )
            fh.create_dataset(
                'baseband_freqs',
                shape=(n_tones,),
                maxshape=(1024,),
                dtype=np.float64,
            )
            fh.create_dataset(
                'tone_powers',
                data=np.ones(n_tones, dtype=np.float64),
                maxshape=(1024,),
                dtype=np.float64,
            )
            fh.create_dataset(
                'detector_delta_x',
                shape=(n_tones,),
                dtype=np.float64,
                maxshape=(1024,),
            )
            fh.create_dataset(
                'detector_delta_y',
                shape=(n_tones,),
                dtype=np.float64,
                maxshape=(1024,),
            )
            fh.create_dataset(
                'detector_beam_ampl',
                shape=(n_tones,),
                dtype=np.float64,
                maxshape=(1024,),
                fillvalue=1,
            )
            fh.create_dataset(
                'detector_pol',
                shape=(n_tones,),
                dtype=np.int8,
                maxshape=(1024,),
                fillvalue=1,
            )
            fh.create_dataset(
                'dfoverf_per_mK',
                shape=(n_tones,),
                dtype=np.float64,
                maxshape=(1024,),
                fillvalue=1,
            )
        _logger.info(f'Initialized params file {filename}')
        return cls(filename, mode=mode)

    def copy_and_update(
        self,
        new_tile_name: str,
        f_center: float | None = None,
        rfin: float | None = None,
        rfout: float | None = None,
        tile_number: int | None = None,
        chan_number: int | None = None,
        ifslice_number: int | None = None,
        chanmask: npt.NDArray = None,
        baseband_freqs: npt.NDArray = None,
        tone_powers: npt.NDArray = None,
        detector_delta_x: npt.NDArray = None,
        detector_delta_y: npt.NDArray = None,
        detector_beam_ampl: npt.NDArray = None,
        detector_pol: npt.NDArray = None,
        dfoverf_per_mK: npt.NDArray = None,
        params_dir: Path = DEFAULT_PARAMS_DIRECTORY,
    ) -> RFSoCParameters:
        """Create a copy of a parameters file while changing the specified dsets."""
        f_center = f_center if f_center is not None else self.f_center
        rfin = rfin if rfin is not None else self.rfin
        rfout = rfout if rfout is not None else self.rfout
        tile_number = tile_number if tile_number is not None else self.chan_number
        chan_number = chan_number if chan_number is not None else self.chan_number
        ifslice_number = (
            ifslice_number if ifslice_number is not None else self.ifslice_number
        )

        chanmask = chanmask if chanmask is not None else self.chanmask[:]
        baseband_freqs = (
            baseband_freqs if baseband_freqs is not None else self.baseband_freqs[:]
        )
        tone_powers = tone_powers if tone_powers is not None else self.tone_powers[:]
        detdx = (
            detector_delta_x
            if detector_delta_x is not None
            else self.detector_delta_x[:]
        )
        detdy = (
            detector_delta_y
            if detector_delta_y is not None
            else self.detector_delta_y[:]
        )
        detamp = (
            detector_beam_ampl
            if detector_beam_ampl is not None
            else self.detector_beam_ampl[:]
        )
        detpol = detector_pol if detector_pol is not None else self.detector_pol[:]
        dfoverf = (
            dfoverf_per_mK if dfoverf_per_mK is not None else self.dfoverf_per_mK[:]
        )

        new_params = RFSoCParameters.new_file(
            new_tile_name,
            baseband_freqs.size,
            params_dir=params_dir,
        )

        new_params.f_center = f_center
        new_params.rfin = rfin
        new_params.rfout = rfout
        new_params.tile_number = tile_number
        new_params.chan_number = chan_number
        new_params.ifslice_number = ifslice_number
        new_params.chanmask[:] = chanmask
        new_params.baseband_freqs[:] = baseband_freqs
        new_params.tone_powers[:] = tone_powers
        new_params.detector_delta_x[:] = detdx
        new_params.detector_delta_y[:] = detdy
        new_params.detector_beam_ampl[:] = detamp
        new_params.detector_pol[:] = detpol
        new_params.dfoverf_per_mK[:] = dfoverf

        return new_params

    @staticmethod
    def exists(
        tile_name: str, params_dir: str = DEFAULT_PARAMS_DIRECTORY
    ) -> tuple[bool, str]:
        """Whether there is a params file for the specified tile."""
        file_name = get_params_file_template(tile_name, params_dir=params_dir)
        return Path(file_name).is_file(), file_name

    @classmethod
    def from_tile_name(
        cls, tile_name: str, mode: str = 'r', params_dir: str = DEFAULT_PARAMS_DIRECTORY
    ) -> RFSoCParameters | None:
        """Load a parameters file using the tile name."""
        if (
            result := RFSoCParameters.exists(tile_name, params_dir=params_dir)
        ) and result[0]:
            return RFSoCParameters(result[1], mode=mode)
        return None

    def __enter__(self):
        """Create a RFSoCParameters."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Cleanup the RFSoCParameters."""
        self.close()

    def close(self):
        """Close the file."""
        self._file.close()

    # Attributes
    @property
    def version(self) -> Version:
        """The RFSoCParameters version this file is formatted to."""
        return Version(self._file.attrs['params_version'])

    @version.setter
    def version(self, version: str | Version):
        self._file.attrs['version'] = str(version)

    @property
    def n_tones(self) -> int:
        """The number of tones."""
        return self._file.attrs['n_tones']

    @n_tones.setter
    def n_tones(self, n: int):
        self._file.attrs['n_tones'] = n

    @property
    def tile_name(self) -> str:
        """The name of the tile."""
        return self._file.attrs['tile_name']

    @tile_name.setter
    def tile_name(self, name: str):
        self._file.attrs['tile_name'] = name

    @property
    def tile_number(self) -> int:
        """The number assigned to the tile."""
        return self._file.attrs['tile_number']

    @tile_number.setter
    def tile_number(self, n: int):
        self._file.attrs['tile_number'] = n

    @property
    def chan_number(self) -> int:
        """The channel number this tile is in its RFSoC."""
        return self._file.attrs['chan_number']

    @chan_number.setter
    def chan_number(self, n: int):
        self._file.attrs['chan_number'] = n

    @property
    def ifslice_number(self) -> int:
        """Which IF slice this tile is connected to."""
        return self._file.attrs['ifslice_number']

    @ifslice_number.setter
    def ifslice_number(self, n: int):
        self._file.attrs['ifslice_number'] = n

    @property
    def f_center(self) -> float:
        """The LO frequency to combine with the baseband frequencies."""
        return self._file.attrs['f_center']

    @f_center.setter
    def f_center(self, freq: float):
        self._file.attrs['f_center'] = freq

    @property
    def rfin(self) -> float:
        """The attenuation to use going into the tile."""
        return float(self._file.attrs['rfin'])

    @rfin.setter
    def rfin(self, x: float):
        self._file.attrs['rfin'] = float(x)

    @property
    def rfout(self) -> float:
        """The attenuation to use going out of the tile."""
        return float(self._file.attrs['rfout'])

    @rfout.setter
    def rfout(self, x: float):
        self._file.attrs['rfout'] = float(x)

    # Datasets
    @property
    def chanmask(self) -> h5py.Dataset:
        """Mask indicating on/off resonance tones and bad resonators."""
        return self._file['chanmask']

    @property
    def onres_ind(self) -> npt.NDArray:
        """Indices of on-resonance tones."""
        return np.argwhere(self.chanmask[:] == 1).flatten()

    @property
    def offres_ind(self) -> npt.NDArray:
        """Indices of off-resonance tones."""
        return np.argwhere(self.chanmask[:] == 0).flatten()

    @property
    def bad_ind(self) -> npt.NDArray:
        """Indices of bad resonances."""
        return np.argwhere(self.chanmask[:] == -1).flatten()

    @property
    def baseband_freqs(self) -> h5py.Dataset:
        """The frequencies relative to baseband."""
        return self._file['baseband_freqs']

    @property
    def detector_f(self) -> npt.NDArray:
        """The absolute frequency of each tone."""
        return self.baseband_freqs[:] + self.f_center

    @property
    def tone_powers(self) -> h5py.Dataset:
        """The relative power level for each tone."""
        return self._file['tone_powers']

    @property
    def detector_delta_x(self) -> h5py.Dataset:
        """The x position relative to the center of the focal plane."""
        return self._file['detector_delta_x']

    @property
    def detector_delta_y(self) -> h5py.Dataset:
        """The y position relative to the center of the focal plane."""
        return self._file['detector_delta_y']

    @property
    def detector_beam_ampl(self) -> h5py.Dataset:
        """The beam amplitude for each resonator."""
        return self._file['detector_beam_ampl']

    @property
    def detector_pol(self) -> h5py.Dataset:
        """The polarization (1 or 2) of each resonator."""
        return self._file['detector_pol']

    @property
    def dfoverf_per_mK(self) -> h5py.Dataset:
        """The change in df/f per mK for each resonator."""
        return self._file['dfoverf_per_mK']

    def flag_collided_resonances(
        self,
        collision_threshold: float = 1 / 5000,
        make_new_file: bool = False,
        new_tile_name: str | None = None,
        params_dir: Path = DEFAULT_PARAMS_DIRECTORY,
    ) -> RFSoCParameters | None:
        """Find and flag collided resonances.

        Arguments:
            collision_threshold (float, optional): Maximum fractional separation between
                collided resonances. Defaults to 1/2000.
            make_new_file (bool, optional): Whether to create a new parameters file, or
                update this one. Defaults to True.
            new_tile_name (str, optional): The new tile name to use when creating the
                new parameters file. Only used if `make_new_file` is True. Defaults to
                None.
            params_dir (Path, optional): The directory to create the new parameters
                file in. Defaults to '/data/params'.

        Raises:
            ValueError: If `new_tile_name` is unset (i.e. equal to None) and
                `make_new_file is True.

        Returns:
            (RFSoCParameters | None): The new parameters object, if a new file was
                created.
        """
        if make_new_file and new_tile_name is None:
            raise ValueError(
                '`new_tile_name` must be set when creating a new parameters' ' file'
            )
        new_chanmask = self.chanmask[:]

        # Find collided resonances
        bb_freqs = self.baseband_freqs[:]
        shift1 = np.abs(bb_freqs - np.roll(bb_freqs, 1))
        shift2 = np.abs(np.roll(bb_freqs, -1) - bb_freqs)
        nearest_res = np.abs(np.minimum(shift1, shift2) / self.detector_f)
        collided_ind = np.argwhere(
            (nearest_res < collision_threshold)
            & (
                self.chanmask[:] == 1
            )  # Only care about on-resonance tones for collisions
        )
        new_chanmask[collided_ind] = -1

        _logger.info(f'Found {collided_ind.size} collided resonances')

        if make_new_file:
            return self.copy_and_update(
                new_tile_name,
                chanmask=new_chanmask,
                params_dir=params_dir,
            )

        self.chanmask[:] = collided_ind
        return None

    def add_off_resonance_tones(
        self,
        new_tile_name: str,
        n_offres: int,
        f_min: float,
        f_max: float,
        q: float = 1 / 1000.0,
        delta_offres_min: float = 1e6,
        params_dir: Path = DEFAULT_PARAMS_DIRECTORY,
    ) -> RFSoCParameters:
        """Add off-resonance tones using this parameters file as the base.

        Off-resonance tones are added in the gaps between on-resonance tones, with more
        spacing between tones at higher frequencies.

        Arguments:
            new_tile_name (str): The new tile name to use when creating the
                new parameters file.
            n_offres (int): Maximum number of offres tones to add.
            f_min (float): Minimum frequency (Hz) of tones to add.
            f_max (float): Maximum frequency (Hz) of tones to add.
            q (float, optional): Fractional frequency spacing to consider a tone far
                enough from on-resonance tones. Defaults to 1/1000.
            delta_offres_min (float, optional): Minimum spacing (Hz) between offres
                tones at the LO frequency. Defaults to 1e5.
            params_dir (Path, optional): The directory to create the new parameters
                file in. Defaults to '/data/params'.

        Returns:
            RFSoCParameters: The parameters object corresponding to the new file.
        """
        baseband_freqs = self.baseband_freqs[:]
        tone_powers = self.tone_powers[:]
        detector_f = self.detector_f
        chanmask = self.chanmask[:]
        f_center = self.f_center
        detdx = self.detector_delta_x[:]
        detdy = self.detector_delta_y[:]
        det_beam_ampl = self.detector_beam_ampl[:]
        detector_pol = self.detector_pol[:]
        dfoverf_per_mK = self.dfoverf_per_mK[:]

        offres_tones = []
        tones_left = n_offres
        freqs_in_range = baseband_freqs[(detector_f >= f_min) & (detector_f <= f_max)]

        freqs_in_range = np.concatenate(
            ([f_min - f_center], freqs_in_range, [f_max - f_center])
        )
        gaps = np.diff(freqs_in_range)
        sorted_gap_ind = np.argsort(gaps)[::-1]
        for i_gap in sorted_gap_ind:
            f0 = freqs_in_range[i_gap]
            f1 = freqs_in_range[i_gap + 1]
            if tones_left == 0:
                break
            search_range = (f0 + np.abs(f0 * q), f1 - np.abs(f1 * q))
            # Insert as many off-resonance tones that will fit in the gap
            # Tones should be further apart as the frequency increases
            offres = []
            this_f = search_range[0]
            while this_f <= search_range[1]:
                offres.append(this_f)
                diff = delta_offres_min * np.abs((this_f + f_center) / f_center)
                this_f += diff
            this_offres_tones = np.array(offres)
            offres_tones.extend(this_offres_tones[:tones_left])
            tones_left -= len(this_offres_tones[:tones_left])

        # Restrict off-resonance tones to be within f_min and f_max
        offres_tones = np.array(offres_tones)
        offres_tones = offres_tones[
            (offres_tones + f_center >= f_min) & (offres_tones + f_center <= f_max)
        ]
        # Create new arrays with offres tones added in the correct locations
        tones_added = len(offres_tones)
        _logger.info(f'Added {tones_added} / {n_offres} new off-resonance tones.')
        all_tones = np.concatenate((baseband_freqs, offres_tones))
        sorted_ind = np.argsort(all_tones)

        new_baseband_freqs = all_tones[sorted_ind]
        new_chanmask = np.concatenate((chanmask, np.zeros(tones_added, dtype=np.int8)))[
            sorted_ind
        ]

        new_tone_powers = np.concatenate(
            (tone_powers, np.zeros(tones_added, dtype=np.float32))
        )[sorted_ind]
        new_detdx = np.concatenate((detdx, np.zeros(tones_added, dtype=np.float32)))[
            sorted_ind
        ]
        new_detdy = np.concatenate((detdy, np.zeros(tones_added, dtype=np.float32)))[
            sorted_ind
        ]
        new_det_beam_ampl = np.concatenate(
            (det_beam_ampl, np.ones(tones_added, dtype=np.float32))
        )[sorted_ind]
        new_detector_pol = np.concatenate(
            (detector_pol, np.ones(tones_added, dtype=np.int8))
        )[sorted_ind]
        new_dfoverf_per_mK = np.concatenate(
            (dfoverf_per_mK, np.ones(tones_added, dtype=np.float64))
        )[sorted_ind]

        new_params = RFSoCParameters.new_file(new_tile_name, len(all_tones))
        new_params.f_center = f_center
        new_params.rfin = self.rfin
        new_params = self.copy_and_update(
            new_tile_name,
            chanmask=new_chanmask,
            baseband_freqs=new_baseband_freqs,
            tone_powers=new_tone_powers,
            detector_delta_x=new_detdx,
            detector_delta_y=new_detdy,
            detector_beam_ampl=new_det_beam_ampl,
            detector_pol=new_detector_pol,
            dfoverf_per_mK=new_dfoverf_per_mK,
            params_dir=params_dir,
        )

    def plot_tones(
        self,
        show: bool = True,
    ) -> Figure:
        """Create a stem plot showing all tones, chanmask values, and power levels."""
        detector_f = self.detector_f[:]
        tone_powers = self.tone_powers[:]
        bad_ind = self.bad_ind
        onres_ind = self.onres_ind
        offres_ind = self.offres_ind

        fig = plt.figure()
        plt.stem(
            detector_f[onres_ind],
            tone_powers[onres_ind],
            linefmt='b',
            markerfmt='none',
            basefmt='none',
            label='On-resonance Tones',
        )
        if offres_ind.size > 0:
            # Increase 0 off-res tone powers so they're visible in the plot
            off_res_powers = tone_powers[offres_ind]
            off_res_powers[off_res_powers == 0] = 0.25
            plt.stem(
                detector_f[offres_ind],
                tone_powers[offres_ind],
                linefmt='orange',
                markerfmt='none',
                basefmt='none',
                label='Off-resonance Tones',
            )
        if bad_ind.size > 0:
            plt.stem(
                detector_f[bad_ind],
                tone_powers[bad_ind],
                linefmt='red',
                markerfmt='none',
                basefmt='none',
                label='Bad Resonances',
            )
        plt.xlabel('Frequency (MHz)')
        plt.ylabel('Tone Power')
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mHz_axis_formatter)
        ax.format_coord = mHz_coordinate_formatter
        plt.title(f'{self.tile_name} - Tone List')
        plt.legend()

        if show:
            plt.show()

        return fig

    @ensure_path(1)
    def append_to_TOD(self, file: Path):
        """Append global data from this parameters file to a TOD file."""
        rdf = RawDataFile(file, 'a')

        rdf.detector_delta_x[:] = self.detector_delta_x[:]
        rdf.detector_delta_y[:] = self.detector_delta_y[:]
        rdf.detector_beam_ampl[:] = self.detector_beam_ampl[:]
        rdf.detector_pol[:] = self.detector_pol[:]
        rdf.dfoverf_per_mK[:] = self.dfoverf_per_mK[:]

        rdf.close()


def update_params_file_format(*filenames: PathLike):
    """Update all parameters files in a directory to match the new format.

    Written for RFSoCParameters Version 1.0.0.

    """
    for filename in filenames:
        path = convert_path(filename)
        try:
            fh = h5py.File(path, 'a')
        except Exception:  # noqa: BLE001
            _logger.info(f'Skipping "{filename}"; Failed to open as an HDF5 file.')
            continue

        if (
            'params_version' in fh.attrs
            and Version(fh.attrs['params_version']) >= RFSoCParameters.VERSION
        ):
            _logger.info(f'Skipping "{filename}"; Already up to date.')
            continue

        # Attenuation Settings
        if 'rfin' not in fh.attrs:
            fh.attrs['rfin'] = 0.0
        if 'rfout' not in fh.attrs:
            fh.attrs['rfout'] = 0.0

        # Standardize LO Frequency
        if 'f_center' not in fh.attrs:
            if 'lo_freq' in fh.attrs:
                fh.attrs['f_center'] = fh.attrs['lo_freq']
            elif 'lo_freq' in fh:
                fh.attrs['f_center'] = fh['lo_freq'][()]
            else:
                fh.attrs['f_center'] = 400e6
        if 'lo_freq' in fh.attrs:
            del fh.attrs['lo_freq']
        if 'lo_freq' in fh:
            del fh['lo_freq']

        # Remove extra chanmasks
        if 'chanmask_non_collided' in fh:
            del fh['chanmask_non_collided']
        if 'chanmask_isolated' in fh:
            del fh['chanmask_isolated']

        # Finally, update version
        fh.attrs['params_version'] = str(RFSoCParameters.VERSION)

        fh.close()
        _logger.info(f'Updated "{filename}" to version {RFSoCParameters.VERSION}.')


if __name__ == '__main__':
    filenames = [
        'params_tile_Be260114Tr_100_tones.h5',
    ]
    # update_params_file_format(*filenames)
    params = RFSoCParameters(filenames[0])
    pdb.set_trace()
