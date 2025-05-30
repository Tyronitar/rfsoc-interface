import yaml
from pathlib import Path
from re import match
from typing import Any
import numpy as np
import numpy.typing as npt

from kidpy3 import RFSOC
from kidpy3.rfsoc import RedisConnection
from kidpy3.data_handler import Rfchan
from kidpy3.hardware import Valon5009, Transceiver320d

from rfsocinterface.core.settings import SettingsError, convert_to_kidy_format
from rfsocinterface.core.utils import convert_path, recursive_update, ensure_path

PATH_SETTINGS = ['toneList', 'tonePowers', 'chanmask', 'loComport', 'attenComport', 'bitstream']

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
        self.settings['channel1'] = chan_settings_a
        self.settings['channel2'] = chan_settings_b

        self.rfsoc = self.make_kidpy_rfsoc()
        self.connect_to_comports()
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
        self.connect_to_lo_comport(0)
        self.connect_to_lo_comport(1)
    
    @ensure_path(1)
    def set_atten_comport(self, comport: Path):
        self.settings['attenComport'] = comport
        if self.atten_transceiver is not None:
            self.atten_transceiver.close()
        self.connect_to_atten_comport()
    
    def connect_to_atten_comport(self):
        self.atten_transceiver = Transceiver320d(str(self.settings['attenComport']))
    
    @ensure_path(2)
    def set_lo_comport(self, addr: int, comport: Path):
        match addr:
            case 0:
                self.settings['channel1']['loComport'] = str(comport)
            case 1:
                self.settings['channel2']['loComport'] = str(comport)
            case _:
                raise ValueError(f'Invalid address {addr}. Must be 0 or 1.')
        self.connect_to_lo_comport(addr)
    
    def connect_to_lo_comport(self, addr: int):
        match addr:
            case 0:
                self.valon_a = Valon5009(str(self.settings['channel1']['loComport']))
            case 1:
                self.valon_b = Valon5009(str(self.settings['channel2']['loComport']))
            case _:
                raise ValueError(f'Invalid address {addr}. Must be 0 or 1.')
    
    def to_kidpy(self) -> dict:
        kidpy_config = {}
        kidpy_config['rfsoc_name'] = self.settings['name']
        kidpy_config['bitstream'] = str(self.settings['bitstream'])
        kidpy_config['redis_ip'] = self.settings['redis']['IP']
        kidpy_config['redis_port'] = self.settings['redis']['port']
        kidpy_config['ethernet_config'] = {
            'udp_data_a_sourceip': self.settings['channel1']['sourceIP'],
            'udp_data_b_sourceip': self.settings['channel2']['sourceIP'],
            'udp_data_a_destip': self.settings['channel1']['destIP'],
            'udp_data_b_destip': self.settings['channel2']['destIP'],
            'destmac_a': self.settings['channel1']['destMAC'],
            'destmac_b': self.settings['channel2']['destMAC'],
            'port_a': self.settings['channel1']['port'],
            'port_b': self.settings['channel2']['port'],
        }
        return {'rfsoc_config': kidpy_config}
    
    def update_kidpy_rfsoc(self):
        data = self.to_kidpy()
        self.rfsoc.read_config(data)
        self.rfsoc.rcon = RedisConnection(
            self.settings['redis']['IP'],
            self.settings['redis']['port'],
        )
    
    def set_tile_number(self, num: int):
        self.rfsoc.rf1.tile_number = num
        self.rfsoc.rf2.tile_number = num

    def set_channel_number(self, num: int):
        self.rfsoc.rf1.chan_number = num
        self.rfsoc.rf2.chan_number = num

    def make_kidpy_rfsoc(self) -> RFSOC:
        # TODO: Use a dictionary not a YAML file
        rfsoc = RFSOC(self.to_kidpy())
        rfsoc.rf1.name = self.settings['channel1'].get('name', 'chan1')
        rfsoc.rf2.name = self.settings['channel2'].get('name', 'chan2')
        tones1, _ = rfsoc.get_tone_list(1)
        tones2, _ = rfsoc.get_tone_list(2)
        chanmask1 = np.ones(np.size(tones1), dtype=int)
        chanmask2 = np.ones(np.size(tones2), dtype=int)
        rfsoc.rf1.ntones = np.size(tones1)
        rfsoc.rf2.ntones = np.size(tones2)
        rfsoc.rf1.chanmask = chanmask1
        rfsoc.rf2.chanmask = chanmask2
        rfsoc.rf1.tile_number = self.settings.get('tileNumber', 2)
        rfsoc.rf2.tile_number = self.settings.get('tileNumber', 2)
        return rfsoc
        # yaml_contents = self.to_kidpy()
        # fname = f'{self.settings['name']}.yml'
        # with open(fname, 'w') as f:
        #     yaml.dump(yaml_contents, f)
        # return RFSOC(fname)

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
    
    def set_frequency(self, channel: int, freq: float):
        valon = self.valon_a if channel == 1 else self.valon_b
        valon.set_frequency(channel, freq)
        self.get_channel(channel).lo_freq = freq
        self.settings[f'channel{channel}']['dsp']['loFreq'] = freq
    
    def get_tone_list(self, chan: int=1) -> tuple[npt.NDArray, npt.NDArray]:
        return self.rfsoc.get_tone_list(chan)
    
    def set_tone_list(self, chan: int=1, tonelist: npt.ArrayLike=[], amplitudes: npt.ArrayLike=[]):
        self.rfsoc.set_tone_list(chan=chan, tonelist=tonelist, amplitudes=amplitudes)
        self.get_channel(chan).n_tones = np.size(tonelist)
    
    def set_atten(self, addr: int, value: float):
        success, msg = self.atten_transceiver.set_atten(addr, value)
        if success:
            if addr < 3:
                old_atten = list(self.rfsoc.rf1.attenuator_settings)
                old_atten[(addr - 1) % 2] = value
                self.rfsoc.rf1.attenuator_settings = old_atten
            else:
                old_atten = self.rfsoc.rf2.attenuator_settings
                old_atten[(addr - 1) % 2] = value
                self.rfsoc.rf2.attenuator_settings = old_atten
        return success
    
    def configure_hardware(self):
        self.rfsoc.config_hardware()
    
    @ensure_path(1)
    def set_chanmask_file(self, fname: Path, chan: int):
        self.settings[f'channel{chan}']['chanmask'] = fname
        self.get_channel(chan).chanmask = np.load(fname)

    def get_chanmask_file(self, chan: int) -> Path | None:
        return self.settings[f'channel{chan}'].get('chanmask', None)

    def get_chanmask(self, chan: int) -> npt.ArrayLike:
        return self.get_channel(chan).chanmask 

    def set_chanmask(self, chanmask: npt.NDArray, chan: int):
        self.get_channel(chan).chanmask = np.copy(chanmask)
    
    def channel_as_text(self, channel: int) -> str:
        return f'{self.settings["name"]} - Channel {channel}'
    
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
    
    def get_channel_name(self, channel: int) -> str:
        rfchan = self.get_channel(channel)
        # return rfchan.name
        return f'{self.settings["name"]}_{rfchan.name}'

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
    chan = int(text.split(' - ')[1].split(' ')[-1])
    return rfsoc, chan
