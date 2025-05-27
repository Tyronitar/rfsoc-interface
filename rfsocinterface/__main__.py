"""Main entry point for the rfsocinterface package."""

import logging
_logger = logging.getLogger(__name__)

from argparse import ArgumentParser

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QGridLayout, QTabWidget
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QScreen
from rfsocinterface.gui.main_window import MainWindow
from rfsocinterface import BAD_LOGGERS


def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())

if __name__ == '__main__':
    parser = ArgumentParser(
        prog='rfsocinterface',
        description='A user-friendly GUI for configuring and monitoring MKID readout software.',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        help='Enable verbose logging',
        default=0,
    )
    args = parser.parse_args()
    
    # Set the log level
    if args.verbose > 1:
        log_level = logging.DEBUG
    elif args.verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    # print(logging.root.handlers)
    # print(_logger.level)
    # logging.root.setLevel(log_level)  # Updating root affects all children
    # print(logging.root.handlers)
    # print(_logger.level)

    # Update the level of the console handlers
    logging.root.handlers[0].setLevel(log_level)
    logging.getLogger('telescopeControl').handlers[0].setLevel(log_level)

    # print(logging.root.handlers)
    # print(_logger.level)
    # exit()
    # print(logging.Logger.manager.loggerDict)
    # for logger in loggers:
    #     logger.setLevel(logging.INFO)

    loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    for name in logging.root.manager.loggerDict:
        if any(name.startswith(prefix) for prefix in BAD_LOGGERS):
            logger = logging.getLogger(name)
            # logger.disabled = True
            # print(f'disabled {logger}')
            logger.setLevel(logging.WARNING)
            # logger.setLevel(logging.WARNING)

    _logger.debug('DEBUG message')
    _logger.info('INFO message')
    _logger.warning('WARNING message')
    _logger.error('ERROR message')
    # app = QApplication()
    # screen = app.primaryScreen()

    # # w = MainWindow("settings.toml")
    # w = MainWindow()
    # w.setScreen(screen)
    # move_to_center(w, screen)
    # w.show()

    # app.exec()
