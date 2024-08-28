"""Main entry point for the rfsocinterface package."""

from rfsocinterface.loconfig import LOConfigWindow
from PySide6.QtWidgets import QApplication

from kidpy import kidpy
from onr_fit_lo_sweeps import main


if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()

    main()