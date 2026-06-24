import yaml
from pathlib import Path
from re import match
from typing import Any, Callable
import numpy as np
import numpy.typing as npt
import logging
from serial import SerialException

from kidpy3 import RFSOC, capture, capture_packets
from kidpy3.rfsoc import RedisConnection
from kidpy3.data_handler import Rfchan
from kidpy3.hardware import Valon5009, Transceiver320d
from kidpy3.hardware.Valon5009 import SYNTH_B
import tables

from rfsocinterface.core.utils import DEFAULT_PARAMS_DIRECTORY, P, R, PathLike
from rfsocinterface.core.settings import SettingsError, convert_to_kidy_format
from rfsocinterface.core.utils import convert_path, recursive_update, ensure_path
from rfsocinterface.core.params import RFSoCParameters
from rfsocinterface.core.sweeps import LoSweepData

_logger = logging.getLogger(__name__)   

PATH_SETTINGS = ['loComport', 'attenComport', 'bitstream']


class RFSOCWrapper:
    def __init__(self, rfsoc_settings: dict):
        # self.settings = recursive_update(default_settings['rfsoc'], rfsoc_settings)
        self.settings = rfsoc_settings

        # self.name: str = combined_settings['name']
        # self.redis_ip: str = combined_settings['redis']['ip']
        # self.redis_port: int = combined_settings['redis']['port']
        # self.bitstream: Path = convert_path(combined_settings['bitstream'])
        # self.atten_comport: Path = convert_path(combined_settings['atten_comport'])
        # self.lo_comport_a: Path = convert_path(combined_settings['lo_comport_a'])
        # self.lo_comport_b: Path = convert_path(combined_settings['lo_comport_b'])
        # self.settings = combined_settings

        # chan_settings_a: dict[str, Any] = recursive_update({}, default_settings['channel'])
        # chan_settings_a = recursive_update(chan_settings_a, rfsoc_settings['channel1'])
        # chan_settings_b: dict[str, Any] = recursive_update({}, default_settings['channel'])
        # chan_settings_b = recursive_update(chan_settings_b, rfsoc_settings['channel2'])
        chan_settings_a = rfsoc_settings['channels'][0]
        chan_settings_b = rfsoc_settings['channels'][1]
        # Convert correct settings to Path
        for k in PATH_SETTINGS:
            if k in self.settings:
                self.settings[k] = convert_path(self.settings[k])
            if k in chan_settings_a:
                chan_settings_a[k] = convert_path(chan_settings_a[k])
            if k in chan_settings_b:
                chan_settings_b[k] = convert_path(chan_settings_b[k])

        self.connect_to_comports()
        self.make_kidpy_rfsoc()
        # self.rfsoc = None
        # self.atten_transceiver = None
        # self.valon_a = None
        # self.valon_b = None
    
    @property
    def name(self) -> str:
        return self.settings['name']

    @name.setter
    def name(self, name: str):
        self.settings['name'] = name
    
    def connect_to_comports(self):
        self.connect_to_atten_comport()
        self.connect_to_lo_comport(1)
        self.connect_to_lo_comport(2)
    
    @ensure_path(1)
    def set_atten_comport(self, comport: Path):
        self.settings['attenComport'] = comport
        if self.atten_transceiver is not None:
            self.atten_transceiver.close()
        self.connect_to_atten_comport()
    
    def connect_to_atten_comport(self):
        comport_name = str(self.settings['attenComport'])
        try:
            self.atten_transceiver = Transceiver320d(comport_name)
            self.atten_transceiver.open()
            _logger.debug(f'Succesfully opened serial connection to attenuation comport {comport_name}')
        except SerialException as e:
            msg = f'Unable to open serial connection to attenuation comport {comport_name}. ' \
                'Check the file exists, or check that the connection is secure.',
            _logger.critical(
                msg,
                exc_info=True,
            )
            raise FileNotFoundError(msg) from e
    
    @ensure_path(2)
    def set_lo_comport(self, channel: int, comport: Path):
        self.channel_settings(channel)['loComport'] = comport
        self.connect_to_lo_comport(channel)
    
    def connect_to_lo_comport(self, channel: int):
        match channel:
            case 1:
                valon = 'valon_a'
            case 2:
                valon = 'valon_b'
            case _:
                raise ValueError(f'Invalid channel {channel}. Must be 1 or 2.')
        comport_name = str(self.channel_settings(channel)['loComport'])
        try:
            setattr(self, valon, Valon5009(comport_name))
            _logger.debug(f'Succesfully opened serial connection to LO comport {comport_name}')
        except SerialException as e:
            _logger.critical(
                f'Unable to open serial connection to LO comport {comport_name}.'
                'Check the file exists, or check that the connection is secure.',
                exc_info=True,
            )
    
    def to_kidpy(self) -> dict:
        chan1_settings = self.channel_settings(1)
        chan2_settings = self.channel_settings(2)
        kidpy_config = {}
        kidpy_config['rfsoc_name'] = self.settings['name']
        kidpy_config['bitstream'] = str(self.settings['bitstream'])
        kidpy_config['redis_ip'] = self.settings['redis']['IP']
        kidpy_config['redis_port'] = self.settings['redis']['port']
        kidpy_config['ethernet_config'] = {
            'udp_data_a_sourceip': chan1_settings['sourceIP'],
            'udp_data_b_sourceip': chan2_settings['sourceIP'],
            'udp_data_a_destip': chan1_settings['destIP'],
            'udp_data_b_destip': chan2_settings['destIP'],
            'destmac_a': chan1_settings['destMAC'],
            'destmac_b': chan2_settings['destMAC'],
            'port_a': chan1_settings['port'],
            'port_b': chan2_settings['port'],
        }
        return {'rfsoc_config': kidpy_config}
    
    def update_kidpy_rfsoc(self):
        data = self.to_kidpy()
        self.rfsoc.read_config(data)
        self.rfsoc.rcon = RedisConnection(
            self.settings['redis']['IP'],
            self.settings['redis']['port'],
        )
        _logger.debug(f'RFSoC {self.name} uccesfully updated kidpy RFSOC object.')
    
    def set_tile_number(self, num: int):
        self.rfsoc.rf1.tile_number = num
        self.rfsoc.rf2.tile_number = num

    def set_channel_number(self):
        self.rfsoc.rf1.chan_number = 1
        self.rfsoc.rf2.chan_number = 2
    
    def get_last_tones(self) -> tuple[tuple[npt.NDArray, npt.NDArray], tuple[npt.NDArray, npt.NDArray]]:
        res = [None, None]
        for chan in [1, 2]:
            tones_and_pow = self.get_tone_list(chan)
            res[chan - 1] = tones_and_pow
            if tones_and_pow is not None:
                rfchan = self.get_channel(chan)
                tones, powers = tones_and_pow
                ntones = np.size(tones)
                rfchan.baseband_freqs = tones
                rfchan.tone_powers = powers
                rfchan.n_tones = ntones
                chanmask = np.ones(ntones, dtype=int)
                rfchan.chanmask = chanmask
        return tuple(res)
    
    def get_last_lo_freqs(self) -> tuple[float, float]:
        res = [0.0, 0.0]
        for chan in [1, 2]:
            res[chan - 1] = self.get_frequency(chan)
        return tuple(res)


    def make_kidpy_rfsoc(self) -> RFSOC:
        # TODO: Use a dictionary not a YAML file
        rfsoc = RFSOC(self.to_kidpy())
        rfsoc.rf1.tile_name = self.channel_settings(1).get('tile_name', 'chan1')
        rfsoc.rf2.tile_name = self.channel_settings(2).get('tile_name', 'chan2')
        rfsoc.rf1.tile_number = self.settings.get('tileNumber', 2)
        rfsoc.rf2.tile_number = self.settings.get('tileNumber', 2)
        self.rfsoc = rfsoc
        
        # Update metadata stored in the Rfchan objects
        self.get_last_tones()
        self.get_last_lo_freqs()
        self.set_channel_number()
        self.get_last_attenuations()
        if 'paramsFile' in self.channel_settings(1):
            self.load_params_file(1, self.channel_settings(1)['paramsFile'], upload_tones=False, set_freq=False, set_atten=False)
        if 'paramsFile' in self.channel_settings(2):
            self.load_params_file(2, self.channel_settings(2)['paramsFile'], upload_tones=False, set_freq=False, set_atten=False)
        _logger.debug(f'RFSoC {self.name} initialized kidpy RFSOC object')
    
    def channel_settings(self, channel: int) -> dict:
        """Get the settings for the specified channel."""
        if channel not in [1, 2]:
            raise ValueError(f'Invalid channel {channel}. Must be 1 or 2.')
        return self.settings['channels'][channel - 1]

    @ensure_path(1)
    def set_bitstream(self, path: Path):
        self.rfsoc.bitstream = str(path)
        self.settings['bitstream'] = path

    @ensure_path(1)
    def upload_bitstream(self, path: Path | None=None):
        if path is not None:
            self.set_bitstream(path)
        if path is None:
            path = ''
        self.rfsoc.upload_bitstream(str(path))
        _logger.info(f'RFSoC {self.name} succesfully uploaded bitstream "{path}"')
    
    def set_frequency(self, channel: int, freq: float):
        """Set the frequency of the specified channel in Hz."""
        valon = self.get_valon(channel)
        valon.set_frequency(SYNTH_B, freq * 1e-6)
        _logger.info(f'RFSoC {self.name} succesfully set frequency for channel {channel} to {freq * 1e-6:.3f} MHz')
        self.get_channel(channel).lo_freq = freq
        self.channel_settings(channel)['dsp']['loFreq'] = freq

    def get_frequency(self, channel: int) -> float:
        """Get the current frequency of the specified channel in Hz."""
        valon = self.get_valon(channel)
        freq = valon.get_frequency(SYNTH_B) * 1e6
        self.get_channel(channel).lo_freq = freq 
        self.channel_settings(channel)['dsp']['loFreq'] = freq
        _logger.info(f'RFSoC {self.name} got last LO frequency for channel {channel}: {freq * 1e-6:.3f} MHz')
        return freq
    
    def get_tone_list(self, chan: int) -> tuple[npt.NDArray, npt.NDArray]:
        res = self.rfsoc.get_tone_list(chan)
        with np.printoptions(threshold=20):
            _logger.debug(f'RFSoC {self.name} got last tones for channel {chan}: {res[0]} with powers {res[1]}')
        return res
    
    def set_tone_list(self, chan: int, tonelist: npt.ArrayLike=[], amplitudes: npt.ArrayLike=[]):
        self.rfsoc.set_tone_list(chan=chan, tonelist=tonelist, amplitudes=amplitudes)
        rfchan = self.get_channel(chan)
        rfchan.baseband_freqs = tonelist
        rfchan.tone_powers = amplitudes
        rfchan.n_tones = np.size(tonelist)
        with np.printoptions(threshold=20):
            _logger.debug(f'RFSoC {self.name} sucessfully set tone list for channel {chan}: {tonelist} with powers {amplitudes}')
    
    def get_last_attenuations(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Get the last attenuations for all addresses from the settings file.
        
        Returns:
            (tuple[tuple[float, float], tuple[float, float]]: The (rfin, rfout) for both
                channels.
        """
        res = [[0, 0], [0, 0]]
        for addr in range(1, 5):
            channel = 1 if addr < 3 else 2
            attenuator = 'rfin' if addr % 2 == 0 else 'rfout'
            value = self.channel_settings(channel)[attenuator]
            res[channel - 1][addr % 2] = value
            _logger.info(f'RFSoC {self.name} got last value for "{attenuator}" for channel {channel}: {value:.2f} dB')
            self.set_atten(addr, value)
        return tuple(tuple(r) for r in res)
    
    def get_atten(self, addr: int) -> float:
        """Get the attenuation for the specified address."""
        channel = 1 if addr < 3 else 2
        rfchan = self.get_channel(channel)
        return rfchan.attenuator_settings[(addr - 1) % 2]

    def get_rfin(self, channel: int) -> float:
        """Get rfin for the specified channel."""
        addr = 2 if channel == 1 else 4
        rfchan = self.get_channel(channel)
        return rfchan.attenuator_settings[0]

    def get_rfout(self, channel: int) -> float:
        """Get rfout for the specified channel."""
        addr = 1 if channel == 1 else 3
        rfchan = self.get_channel(channel)
        return rfchan.attenuator_settings[1]
    
    def set_atten(self, addr: int, value: float) -> bool:
        """Set the attenuation for the specified address."""
        attenuator = 'rfin' if addr % 2 == 0 else 'rfout'
        channel = 1 if addr < 3 else 2
        response = self.atten_transceiver.set_atten(addr, value)
        success = response[0]
        msg = response[1]
        if success:
            
            # Update the RFChan object
            rfchan = self.get_channel(channel)
            old_atten = list(rfchan.attenuator_settings)
            old_atten[(addr - 1) % 2] = value
            rfchan.attenuator_settings = old_atten

            # Update settings
            _logger.info(f'RFSoC {self.name} succesfully set attenuation for {attenuator} (address ={addr}) to {value:.2f} dB')
            self.channel_settings(channel)[attenuator] = value
        else:
            _logger.error(f'RFSoC {self.name} failed to set attenuation for {attenuator} (address={addr}). Message: "{msg}"')
        return success
    
    def set_rfin(self, channel: int, value: float) -> bool:
        addr = 2 if channel == 1 else 4
        return self.set_atten(addr, value)

    def set_rfout(self, channel: int, value: float) -> bool:
        addr = 1 if channel == 1 else 3
        return self.set_atten(addr, value)

    def configure_hardware(self):
        res = self.rfsoc.config_hardware()
        if res:
            _logger.info(f'RFSoC {self.name} succesfully configured hardware')
        else:
            _logger.error(f'RFSoC {self.name} failed to configure hardware')
    
    @ensure_path(1)
    def set_chanmask_file(self, fname: Path, chan: int):
        self.channel_settings(chan)['chanmask'] = fname
        # chanmask = np.load(fname)
        # self.set_chanmask(chanmask, chan)
    
    def set_chanmask(self, chan: int, chanmask: npt.NDArray):
        self.get_channel(chan).chanmask = chanmask
        with np.printoptions(threshold=20):
            _logger.debug(f'RFSoC {self.name} set `chanmask` for channel {chan} to {chanmask}')

    def get_chanmask(self, chan: int) -> npt.NDArray:
        return self.get_channel(chan).chanmask

    def set_ntones(self, chan: int, ntones: int):
        self.get_channel(chan).n_tones = ntones
        _logger.debug(f'RFSoC {self.name} set `n_tones` for channel {chan} to {ntones}')

    def get_ntones(self, chan: int) -> int:
        return self.get_channel(chan).n_tones
    
    def get_min_resonance_frequency(self, chan: int) -> float:
        return self.channel_settings(chan)['minResonanceFrequency']

    def set_min_resonance_frequency(self, chan: int, freq: float):
        self.channel_settings(chan)['minResonanceFrequency'] = freq

    def get_max_resonance_frequency(self, chan: int) -> float:
        return self.channel_settings(chan)['maxResonanceFrequency']

    def set_max_resonance_frequency(self, chan: int, freq: float):
        self.channel_settings(chan)['maxResonanceFrequency'] = freq

    def get_min_distance_from_lo(self, chan: int) -> float:
        return self.channel_settings(chan)['minResonanceDistanceFromLo']

    def set_min_distance_from_lo(self, chan: int, x: float) -> float:
        self.channel_settings(chan)['minResonanceDistanceFromLo'] = x

    def get_chanmask_file(self, chan: int) -> Path | None:
        return self.settings[f'channel{chan}'].get('chanmask', None)

    def channel_as_text(self, channel: int) -> str:
        tile_name = self.get_channel(channel).tile_name
        return f'{self.settings["name"]} - {tile_name}'
    
    def get_channel(self, channel: int) -> Rfchan:
        match channel:
            case 1:
                return self.rfsoc.rf1
            case 2:
                return self.rfsoc.rf2
            case _:
                raise ValueError(f'Invalid channel {channel}. Must be 1 or 2.')

    def get_valon(self, channel: int) -> Valon5009:
        match channel:
            case 1:
                return self.valon_a
            case 2:
                return self.valon_b
            case _:
                raise ValueError(f'Invalid channel {channel}. Must be 1 or 2.')
    
    def get_tile_name(self, channel: int) -> str:
        rfchan = self.get_channel(channel)
        return str(rfchan.tile_name)
    
    def set_tile_name(self, channel: int, tile_name: str):
        rfchan = self.get_channel(channel)
        rfchan.tile_name = tile_name
        self.channel_settings(channel)['tile_name'] = tile_name
        _logger.info(f'RFSoC {self.name} set channel {channel} tile name to {tile_name}')
    
    def get_channel_from_name(self, tile_name: str) -> int:
        """Get the channel number from the tile name."""
        for i in [1, 2]:
            if tile_name == self.get_tile_name(i):
                return i
        raise SettingsError(f'Could not find channel with tile name {tile_name} in RFSoC {self.name}. Valid names are {[self.get_tile_name(i) for i in [1, 2]]}')
        
    @ensure_path(2)
    def load_params_file(
        self,
        channel: int,
        params_filename: Path,
        upload_tones: bool=True,
        set_freq: bool=True,
        set_atten: bool=True,
    ):

        if not params_filename.exists():
            raise SettingsError(f'Params file {params_filename} does not exist.')

        with RFSoCParameters(params_filename, mode='r') as params:
            _logger.info(f'Loading parameters from "{params_filename}" into {self.name} channel {channel}')
            tone_list = params.baseband_freqs[:]
            tone_powers = params.tone_powers[:]
            lo_freq = params.f_center
            chanmask = params.chanmask[:]
            ntones = params.n_tones
            tile_name = params.tile_name
            rfin = params.rfin
            rfout = params.rfout

        self.set_tile_name(channel, tile_name)
        self.set_ntones(channel, ntones)
        if set_freq:
            self.set_frequency(channel, lo_freq)
        if set_atten:
            self.set_rfout(channel, rfout)
            self.set_rfin(channel, rfin)
        if upload_tones:
            self.set_tone_list(channel, tonelist=tone_list, amplitudes=tone_powers)
        self.set_chanmask(channel, chanmask)
        self.channel_settings(channel)['paramsFile'] = params_filename

        _logger.info(f'RFSoC {self.name} loaded parameters from {params_filename} for channel {channel}')
    
    # TODO: Expand this
    def save_changes_to_params_file(self, channel: int):
        """Save the current state of the RFSoC to the parameters file.
        
        Currently, only updates the chanmask.
        """
        with RFSoCParameters(self.channel_settings(channel)['paramsFile'], 'a') as params:
            params.chanmask[:] = self.get_chanmask(channel)
    
    @ensure_path(1)
    def setup_capture(self, file: Path, channels: list[int]) -> list[Rfchan]:
        """Setup data capture for the specified channels"""
        rfchans = []
        for channel in channels:
            rfchan = self.get_channel(channel)
            rfchan.raw_filename = str(file)
            rfchans.append(rfchan)
        return rfchans
    
    def capture(self, channels: list[int], file: PathLike, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """Capture data from this RFSoC."""
        rfchans = self.setup_capture(file, channels)
        return capture(rfchans, fn, *args, **kwargs)
    
    @ensure_path(2)
    def append_global_data(self, channel: int, file: Path):
        """Append global data and the most recent LO sweep for a tile to a TOD file."""
        with RFSoCParameters(self.channel_settings(channel)['paramsFile'], 'r') as params:
            params.append_to_TOD(file)
        tile_name = self.get_tile_name(channel)
        sweep = LoSweepData.load_most_recent(tile_name)
        if sweep is not None:
            sweep.append_to_TOD(file)

        _logger.debug(f'Appended global data from tile "{tile_name}" to {str(file)}')

    
    def capture_packets(self, channel: int, n_packets: int) -> npt.NDArray:
        """Capture the specified number of packets from the specified channel.
        
        Arguments:
            channel (int): The channel number to capture packets from (1 or 2).
            n_packets (int): The number of packets to capture.
        
        Returns:
            npt.NDArray: The captured packets. Has shape (2052, n_packets), with 
                each even row being I data and the next odd row being the corresponding
                Q data.
        """
        return capture_packets(self.get_channel(channel), n_packets)


def get_channel_from_text(text: str, rfsocs: list[RFSOCWrapper]) -> tuple[RFSOCWrapper, int]:
    if text == '':
        raise SettingsError('No channel selected')
    try:
        rfsoc_name = text.split(' - ')[0]
        rfsoc = None
        for rf in rfsocs:
            if rf.settings['name'] == rfsoc_name:
                rfsoc = rf
                break
        if rfsoc is None:
            raise SettingsError(f'Could not find an RFSOC with name: {rfsoc_name}')
    except (IndexError, SettingsError) as e:
        raise SettingsError(f'Could not find a channel from text: {text}') from e
    tile_name = text.split(' - ')[1].strip()
    chan = rfsoc.get_channel_from_name(tile_name)
    return rfsoc, chan



