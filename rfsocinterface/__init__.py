"""A user-friendly GUI for configuring and monitoring MKID readout software."""

__version__ = '0.1.0'

import logging.config
from pathlib import Path
logging.config.fileConfig('rfsocinterface/logging.conf')

GLOBAL_SETTINGS_PATH = Path('/etc/rfsocinterface/settings.json')
USER_SETTINGS_PATH = Path('~/.rfsocinterface/settings.json')