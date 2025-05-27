"""A user-friendly GUI for configuring and monitoring MKID readout software."""

__version__ = '0.1.0'

import logging.config
from pathlib import Path
logging.config.fileConfig('rfsocinterface/logging.conf')

# Disable logging for imported modules


GLOBAL_SETTINGS_PATH = Path('/etc/rfsocinterface/settings.json')
USER_SETTINGS_PATH = Path('~/.rfsocinterface/settings.json')
BAD_LOGGERS = [
    'matplotlib',
    'h5py',
    'fontTools'
]
