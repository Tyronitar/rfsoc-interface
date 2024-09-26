"""Main entry point for the rfsocinterface package."""

from PySide6.QtWidgets import QApplication

from onr_fit_lo_sweeps import main
from rfsocinterface.loconfig import LOConfigWindow

if __name__ == '__main__':
    app = QApplication()

    lo_window = LOConfigWindow()
    lo_window.show()
    app.exec()

    main()
