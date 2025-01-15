import yaml
from pathlib import Path
from re import match
from typing import Any
import numpy.typing as npt

from kidpy3 import RFSOC
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
        self.rfsoc = None
        # self.transceiver = Transceiver320d(str(self.settings['atten_comport']))
        self.transceiver = None
    
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

    def make_kidpy_rfsoc(self) -> RFSOC:
        yaml_contents = self.to_kidpy()
        fname = f'{self.name}.yml'
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
        return self.transceiver.set_atten(addr, value)
    