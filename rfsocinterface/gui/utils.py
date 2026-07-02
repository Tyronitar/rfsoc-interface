from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMainWindow

# Useful Aliases
tr = QCoreApplication.translate


DATA_ROUTINE_FUNCTION_WIDGET_ARGS = {
    # 'CleanTOD': (
    #     'CleanTOD',
    #     CleanTOD,
    #     [],
    # ),
    # 'BinTODIntoMap': (
    #     'Bin TOD Into Map',
    #     BinTODIntoMap,
    #     [
    #         (('High Pass Filter Frequency: ', ArgumentType.FLOAT), {'default': 0.5}),
    #         (('Low Pass Filter Frequency: ', ArgumentType.FLOAT), {'default': 10}),
    #         (('Azimuth Trim: ', ArgumentType.FLOAT), {'default': 2.3}),
    #         (('Zenith Angle Trim: ', ArgumentType.FLOAT), {'default': 0.2}),
    #         (('Beam Map Mode', ArgumentType.BOOL), {'default': False}),
    #     ],
    # ),
    # 'GaussianFilter': (
    #     'Gaussian Filter',
    #     GaussianFilter,
    #     [
    #         (('Sigma: ', (ArgumentType.FLOAT, ArgumentType.FLOAT)), {'default': GAUSSIAN_SIGMA}),
    #     ],
    # ),
    # 'LowPassFilter': (
    #     'Low Pass Filter',
    #     LowPassFilter,
    #     [
    #         (('Filter Frequency: ', ArgumentType.FLOAT), {}),
    #     ]
    # ),
    # 'HighPassFilter': (
    #     'High Pass Filter',
    #     HighPassFilter,
    #     [
    #         (('Filter Frequency: ', ArgumentType.FLOAT), {}),
    #     ]
    # ),
    # 'Downsample': (
    #     'Downsample',
    #     Downsample,
    #     [
    #         (('Downsample Factor: ', ArgumentType.FLOAT), {'default': 6}),
    #         (('Order: ', ArgumentType.INT), {'default': DECIMATE_ORDER}),
    #     ]
    # ),
}


def move_to_center(win: QMainWindow, screen: QScreen):
    """Move a window to the center of the screen."""
    win.move(screen.geometry().center() - win.geometry().center())
