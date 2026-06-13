"""Main entry point for the rfsocinterface package."""

import logging
import logging.config
import sys
from argparse import ArgumentParser
from pathlib import Path

from pdfjs_viewer.stability import configure_global_stability
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QMainWindow

from rfsocinterface.gui.main_window import MainWindow


def move_to_center(win: QMainWindow, screen: QScreen):
    win.move(screen.geometry().center() - win.geometry().center())


if __name__ == '__main__':
    logconf_file = Path(__file__).parent / 'logging.conf'
    logging.config.fileConfig(logconf_file)
    _logger = logging.getLogger('rfsocinterface')

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

    _logger.handlers[0].setLevel(log_level)  # Update the level for the console handler

    # NOTE: Testing logging output
    # _logger.debug('DEBUG message')
    # _logger.info('INFO message')
    # _logger.warning('WARNING message')
    # _logger.error('ERROR message')
    # _logger.critical('CRITICAL message')

    # Ensure PDF viewer stability BEFORE QApplication creation
    configure_global_stability(
        disable_gpu=True,
        disable_webgl=True,
        disable_gpu_compositing=True,
        disable_unnecessary_features=True,
    )

    app = QApplication(sys.argv)
    screen = app.primaryScreen()

    w = MainWindow()
    w.setScreen(screen)
    move_to_center(w, screen)
    w.show()

    app.exec()
