import yaml
from pathlib import Path
from re import match
from typing import Any
import numpy.typing as npt

from kidpy3 import RFSOC
from kidpy3.rfsoc import RedisConnection
from kidpy3.data_handler import Rfchan
from kidpy3.hardware import Valon5009, Transceiver320d

from rfsocinterface.utils import convert_to_kidy_format, convert_path, recursive_update, ensure_path

PATH_SETTINGS = ['tone_list', 'tone_powers', 'chanmask', 'lo_comport', 'atten_comport', 'bitstream']

class RFSOCWrapper:
    def __init__(self, default_settings: dict, rfsoc_settings: dict):
        self.settings = recursive_update(default_settings['rfsoc'], rfsoc_settings)

        # self.name: str = combined_settings['name']
        # self.redis_ip: str = combined_settings['redis']['ip']
        # self.redis_port: int = combined_settings['redis']['port']
        # self.bitstream: Path = convert_path(combined_settings['bitstream'])
        # self.atten_comport: Path = convert_path(combined_settings['atten_comport'])
        # self.lo_comport_a: Path = convert_path(combined_settings['lo_comport_a'])
        # self.lo_comport_b: Path = convert_path(combined_settings['lo_comport_b'])
        # self.settings = combined_settings

        chan_settings_a: dict[str, Any] = recursive_update({}, default_settings['channel'])
        chan_settings_a = recursive_update(chan_settings_a, rfsoc_settings['channel1'])
        chan_settings_b: dict[str, Any] = recursive_update({}, default_settings['channel'])
        chan_settings_b = recursive_update(chan_settings_b, rfsoc_settings['channel2'])
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

        # self.rfsoc = self.make_kidpy_rfsoc()
        # self.connect_to_comports()
        self.rfsoc = None
        self.atten_transceiver = None
        self.valon_a = None
        self.valon_b = None
    
    def connect_to_comports(self):
        self.connect_to_atten_comport()
        self.connect_to_lo_comport(0)
        self.connect_to_lo_comport(1)
    
    @ensure_path(1)
    def set_atten_comport(self, comport: Path):
        self.settings['atten_comport'] = comport
        if self.atten_transceiver is not None:
            self.atten_transceiver.close()
        self.connect_to_atten_comport()
    
    def connect_to_atten_comport(self):
        self.atten_transceiver = Transceiver320d(str(self.settings['atten_comport']))
    
    @ensure_path(2)
    def set_lo_comport(self, addr: int, comport: Path):
        match addr:
            case 0:
                self.settings['lo_comport_a'] = comport
            case 1:
                self.settings['lo_comport_b'] = comport
            case _:
                raise ValueError(f'Invalid address {addr}. Must be 0 or 1.')
        self.connect_to_lo_comport(addr)
    
    def connect_to_lo_comport(self, addr: int):
        match addr:
            case 0:
                self.valon_a = Valon5009(str(self.settings['lo_comport_a']))
            case 1:
                self.valon_b = Valon5009(str(self.settings['lo_comport_b']))
            case _:
                raise ValueError(f'Invalid address {addr}. Must be 0 or 1.')
    
    def to_kidpy(self) -> dict:
        kidpy_config = {}
        kidpy_config['rfsoc_name'] = self.settings['name']
        kidpy_config['bitstream'] = str(self.settings['bitstream'])
        kidpy_config['redis_ip'] = self.settings['redis']['ip']
        kidpy_config['redis_port'] = self.settings['redis']['port']
        kidpy_config['ethernet_config'] = {
            'udp_data_a_sourceip': self.settings['channel1']['sourceip'],
            'udp_data_b_sourceip': self.settings['channel2']['sourceip'],
            'udp_data_a_destip': self.settings['channel1']['destip'],
            'udp_data_b_destip': self.settings['channel2']['destip'],
            'port_a': self.settings['channel1']['port'],
            'port_b': self.settings['channel2']['port'],
        }
        return {'rfsoc_config': kidpy_config}
    
    def update_kidpy_rfsoc(self):
        data = self.to_kidpy()
        self.rfsoc.read_config(data)
        self.rfsoc.rcon = RedisConnection(
            self.settings['redis']['host'],
            self.settings['redis']['port'],
        )

    def make_kidpy_rfsoc(self) -> RFSOC:
        # TODO: Use a dictionary not a YAML file
        yaml_contents = self.to_kidpy()
        fname = f'{self.settings['name']}.yml'
        with open(fname, 'w') as f:
            yaml.dump(yaml_contents, f)
        return RFSOC(fname)

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
    
    def get_tone_list(self, chan: int=1) -> tuple[npt.NDArray, npt.NDArray]:
        return self.rfsoc.get_tone_list(chan)
    
    def set_tone_list(self, chan: int=1, tonelist: npt.ArrayLike=[], amplitudes: npt.ArrayLike=[]):
        self.rfsoc.set_tone_list(chan=chan, tonelist=tonelist, amplitudes=amplitudes)
    
    def set_atten(self, addr: int, value: float):
        return self.atten_transceiver.set_atten(addr, value)
    
    def configure_hardware(self):
        self.rfsoc.configure_hardware()
    
    @ensure_path(1)
    def set_chanmask(self, fname: Path):
        self.settings['chanmask'] = fname