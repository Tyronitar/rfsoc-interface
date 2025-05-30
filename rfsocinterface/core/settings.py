"""Module for handling of settings files."""
import copy
import json
from pathlib import Path
import logging

from rfsocinterface.core.utils import GLOBAL_SETTINGS_PATH
from rfsocinterface.core.utils import USER_SETTINGS_PATH
from rfsocinterface.core.utils import ensure_path

_logger = logging.getLogger(__name__)


DEFAULT_SETTINGS = {
    "app": {
        "tabs": [
            "initialization",
            "losweep",
            "data",
            "telescope",
            "imaging"
        ],
        "activeTab": "initialization"
    },
    "telescope": {
        "jogVoltage": {
            "azimuth": 5,
            "zenith": 1
        },
        "controller": {
            "class": "TelescopeMotorController",
            "path": "./telescope.py"
        }
    },
    "defaults": {
        "loSweep": {
            "globalShift": 0,
            "df": 1.0,
            "deltaf": 100.0,
            "flaggingThreshold": 3.0,
            "fileSuffix": "none",
            "secondSweep": {
                "df": 1.0
            }
        },
        "data": {
            "useDefaultFilename": True,
            "directory": "/data/"
        },
        "rfsoc": {
            "bitstream": "/home/xilinx/dualchan_v2.bit",
            "channel": {
                "toneList": "/home/onrkids/readout/host/params/Default_tone_list.npy",
                "tone_powers": "/home/onrkids/readout/host/params/Device_aSi1_Channel2_20220222_300K_200mK_max_readout_power.npy",
                "dsp": {
                    "loFreq": 400,
                    "nAverages": 524288
                },
                "rfin": 0.0,
                "rfout": 0.0
            }
        }
    },
    "rfsocs": []
}


class Settings(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    # TODO: Global settings need sudo privelige to be created.
    # Although, when installing, that shouldn't be an issue
    @staticmethod
    @ensure_path(0)
    def _create_settings(path: Path):
        path.expanduser().parent.mkdir(exist_ok=True)
        with path.expanduser().open('w') as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        _logger.info(f'Created default settings file at {path}')

    def _load_global_settings(self):
        self.clear()
        with GLOBAL_SETTINGS_PATH.open('r') as f:
            self.update(json.load(f))
        self['rfsocs'] = self._load_rfsocs(self.pop('rfsocs', []))

    def default_rfsoc_settings(self) -> dict:
        return self['defaults'].get('rfsoc', {})

    def default_channel_settings(self) -> dict:
        return self.default_rfsoc_settings().get('channel', {})

    def _load_rfsocs(self, rfsocs: list[dict]) -> list[dict]:
        new_rfsocs = []
        default_rfsoc_settings = self.default_rfsoc_settings()
        if 'channel' in default_rfsoc_settings:
            default_channel_settings = default_rfsoc_settings.pop('channel')
        for rfsoc_dict in rfsocs:
            # Copy user RFSoC over defaults (minus channels)
            new_rfsoc_dict = copy.copy(default_rfsoc_settings)
            channel_dicts = rfsoc_dict.pop('channels', [])
            new_rfsoc_dict.update(rfsoc_dict)

            # Copy user channel settings over defaults
            new_channel_dicts = []
            for channel_dict in channel_dicts:
                new_channel_dict = copy.copy(default_channel_settings)
                new_channel_dict.update(channel_dict)
                new_channel_dicts.append(new_channel_dict)

            new_rfsoc_dict['channels'] = new_channel_dicts
            new_rfsocs.append(new_rfsoc_dict)
        return new_rfsocs

    @ensure_path(1)
    def load_settings(self, user_settings_path: Path=USER_SETTINGS_PATH):
        self._load_global_settings()
        if not user_settings_path.expanduser().exists():
            Settings._create_settings(user_settings_path)
        self._path = user_settings_path
        with user_settings_path.expanduser().open('r') as f:
            user_settings = json.load(f)
            self['defaults'].update(user_settings.get('defaults', {}))
            if 'rfsocs' in user_settings:
                user_settings['rfsocs'] = self._load_rfsocs(user_settings.pop('rfsocs'))
            self.update(user_settings)

    def __str__(self):
        return json.dumps(self, indent=4)


class SettingsError(Exception):
    def __init__(self, message: str):
        super().__init__("Error in settings file: " + message)


def convert_to_kidy_format(rfsoc_config: dict) -> dict:
    kidpy_config = {}
    kidpy_config['rfsoc_name'] = rfsoc_config['name']
    kidpy_config['bitstream'] = rfsoc_config['bitstream']
    kidpy_config['redis_ip'] = rfsoc_config['redis']['ip']
    kidpy_config['redis_port'] = rfsoc_config['redis']['port']
    kidpy_config['ethernet_config'] = {
        'udp_data_a_sourceip': rfsoc_config['channel1']['sourceip'],
        'udp_data_b_sourceip': rfsoc_config['channel2']['sourceip'],
        'udp_data_a_destip': rfsoc_config['channel1']['destip'],
        'udp_data_b_destip': rfsoc_config['channel2']['destip'],
        'port_a': rfsoc_config['channel1']['port'],
        'port_b': rfsoc_config['channel2']['port'],
    }
    return {'rfsoc_config': kidpy_config}