"""A user-friendly GUI for configuring and monitoring MKID readout software."""

import os

__version__ = '0.4.0'

os.umask(
    0
)  # Set user file-creation mask to 0 so files are created with permissions we set
