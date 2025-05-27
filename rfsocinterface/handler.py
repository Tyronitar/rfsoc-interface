"""Custom file handler for logging."""

import logging
import logging.handlers
from pathlib import Path
from rfsocinterface import USER_PATH


class UserRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Custom file handler that uses the user's home directory for log files."""

    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):

        log_file = USER_PATH / filename
        super().__init__(log_file, mode, maxBytes, backupCount, encoding, delay)