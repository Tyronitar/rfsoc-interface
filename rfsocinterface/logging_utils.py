"""Custom classes for logging."""

import logging


class CustomConsoleFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = '\x1b[38;21m'
    yellow = '\x1b[33;21m'
    red = '\x1b[31;21m'
    bold_red = '\x1b[31;1m'
    reset = '\x1b[0m'
    debug_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)'
    info_format = '%(message)s'
    warning_format = '%(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)'

    FORMATS = {
        logging.DEBUG: grey + debug_format + reset,
        logging.INFO: grey + info_format + reset,
        logging.WARNING: yellow + warning_format + reset,
        logging.ERROR: red + warning_format + reset,
        logging.CRITICAL: bold_red + warning_format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
