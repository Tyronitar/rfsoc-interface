from __future__ import annotations

# from telnetlib import Telnet
import logging
import time
from threading import Thread
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtCore import (
    QCoreApplication,
    QTimer,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.camera import (
    MAX_FRAME_HEIGHT,
    MAX_FRAME_WIDTH,
)
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.telescope import (
    AZ_OUT_CHANNEL,
    ZA_OUT_CHANNEL,
)
from rfsocinterface.core.utils import TabName
from rfsocinterface.gui.main_widget import TelescopeMainWidget
from rfsocinterface.gui.uic.telescope_control_ui import (
    Ui_TelescopeControlWidget as Ui_TelescopeControlWidget,
)
from rfsocinterface.gui.widgets import get_num_value
from rfsocinterface.gui.widgets.canvas import ToolbarCanvas

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_tele_logger = logging.getLogger('rfsocinterface.telescopeControl')


class TelescopeControlWidget(TelescopeMainWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""

    tab_name = TabName.TELESCOPE

    def __init__(
        self,
        main_window: MainWindow,
        rfsocs: list[RFSOCWrapper],
        settings: dict,
        client_id: str,
        parent: QWidget | None = None,
    ):
        super().__init__(main_window, rfsocs, settings, client_id, parent=parent)
        self.setupUi(self)

        self.azimuth_commanded_valLabel.setText('N/A')
        self.zenith_commanded_valLabel.setText('N/A')

        self.interval = 200  # Milliseconds between update calls
        self.za_jog_voltage = 1  # Degrees / second
        self.az_jog_voltage = 5  # Degrees / second

        # Control Connections
        self.enable_motion_checkBox.toggled.connect(self.toggle_motion_enabled)
        self.stop_pushButton.clicked.connect(self.stop_motion)
        self.azimuth_setpushButton.clicked.connect(self.set_az_pos)
        self.zenith_setpushButton.clicked.connect(self.set_za_pos)
        self.controller.buttonGroup.buttonPressed.connect(self.jog)
        self.controller.buttonGroup.buttonReleased.connect(self.stop_motion)
        self.manual_controlcheckBox.toggled.connect(self.toggle_jogging)

        self.connect_to_telescope_command('az_pos', self.update_az_pos)
        self.connect_to_telescope_command('za_pos', self.update_za_pos)
        self.connect_to_telescope_command('az_pos_comm', self.update_az_cmd)
        self.connect_to_telescope_command('za_pos_comm', self.update_za_cmd)

        # Set up Optical Camera
        self.live_footage_fig, self.live_footage_ax = plt.subplots(figsize=(12, 9))
        self.live_footage_im = self.live_footage_ax.imshow(
            np.zeros((MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3))
        )
        self.live_footage_fig.tight_layout()
        self.live_footage_ax.set_axis_off()

        self.live_footage_canvas = ToolbarCanvas(parent=self, fig=self.live_footage_fig)
        self.gridLayout_2.addWidget(self.live_footage_canvas, 2, 0)
        self.live_footage_canvas.hide()

        self.live_footage_thread = None
        self.optical_pushButton.clicked.connect(self.toggle_live_footage)
        self.frame_rate = 5  # FPS

        # Initialize the numbers in the GUI
        self.az_pos = self.last_az = 0
        self.az_pps_pos = None
        self.za_pos = self.last_za = 0
        self.za_pps_pos = None

        self.send_telescope_command('get_ser_az_pos')
        self.send_telescope_command('get_ser_za_pos')

        self.last_az_commanded = None
        self.last_za_commanded = None

        # Update Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui_telescope)
        self.timer.start(500)

    def toggle_controls_enabled(self, enabled: bool):
        self.azimuth_setlineEdit.setEnabled(enabled)
        self.zenith_setlineEdit.setEnabled(enabled)
        self.azimuth_setpushButton.setEnabled(enabled)
        self.zenith_setpushButton.setEnabled(enabled)

    @Slot()
    def toggle_motion_enabled(self):
        if self.enable_motion_checkBox.isChecked():
            self.toggle_controls_enabled(True)
            self.toggle_jogging()
        else:
            self.toggle_controls_enabled(False)
            self.controller.setEnabled(False)

    def stop_motion(self):
        self.send_telescope_command('stop_telescope')

    def take_pic(self):
        pic_data = self.get_current_image()[0]
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.imshow(pic_data)
        ax.set_axis_off()
        fig.tight_layout()

        dialog = QDialog(self)
        dialog.setWindowTitle('Optical Image')
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.addWidget(FigureCanvas(fig))
        dialog.setLayout(dialog_layout)
        dialog.show()

    def toggle_jogging(self):
        if self.manual_controlcheckBox.isChecked():
            self.controller.setEnabled(True)
        else:
            self.controller.setEnabled(False)

    def jog(self, btn: QAbstractButton):
        match btn:
            case self.controller.up_toolButton:
                self.send_telescope_command(
                    'set_voltage', -self.za_jog_voltage, ZA_OUT_CHANNEL
                )
            case self.controller.down_toolButton:
                self.send_telescope_command(
                    'set_voltage', self.za_jog_voltage, ZA_OUT_CHANNEL
                )
            case self.controller.left_toolButton:
                self.send_telescope_command(
                    'set_voltage', self.az_jog_voltage, AZ_OUT_CHANNEL
                )
            case self.controller.right_toolButton:
                self.send_telescope_command(
                    'set_voltage', -self.az_jog_voltage, AZ_OUT_CHANNEL
                )

    def set_az_pos(self):
        new_pos = get_num_value(self.azimuth_setlineEdit)
        self.send_telescope_command('set_az_pos', new_pos)

    def set_za_pos(self):
        new_pos = get_num_value(self.zenith_setlineEdit)
        self.send_telescope_command('set_za_pos', new_pos)

    @Slot(float, float)
    def update_az_pos(self, new_pos: float, pps_pos: float | None):
        self.azimuth_actual_valLabel.setText(f'{new_pos:.3f}°')
        if pps_pos is None:
            self.azimuth_pps_valLabel.setText('N/A')
        else:
            self.azimuth_pps_valLabel.setText(f'{pps_pos:.3f}°')
        self.az_pos = new_pos
        self.az_pps_pos = pps_pos

    @Slot(float)
    def update_az_cmd(self, new_pos: float):
        self.last_az_commanded = new_pos
        self.azimuth_commanded_valLabel.setText(f'{new_pos:.3f}°')

    @Slot(float)
    def update_az_vel(self, new_vel: float):
        self.azimuth_velocity_valLabel.setText(f'{new_vel:.2f}°/sec')

    @Slot(float)
    def update_az_err(self, new_err: float):
        self.azimuth_error_valLabel.setText(f'{new_err:.3f}°')

    @Slot(float, float)
    def update_za_pos(self, new_pos: float, pps_pos: float | None):
        self.zenith_actual_valLabel.setText(f'{new_pos:.3f}°')
        if pps_pos is None:
            self.zenith_pps_valLabel.setText('N/A')
        else:
            self.zenith_pps_valLabel.setText(f'{pps_pos:.3f}°')
        self.za_pos = new_pos
        self.za_pps_pos = pps_pos

    @Slot(float)
    def update_za_cmd(self, new_pos: float):
        self.last_za_commanded = new_pos
        self.zenith_commanded_valLabel.setText(f'{new_pos:.3f}°')

    @Slot(float)
    def update_za_vel(self, new_vel: float):
        self.zenith_velocity_valLabel.setText(f'{new_vel:.2f}°/sec')

    @Slot(float)
    def update_za_err(self, new_err: float):
        self.zenith_error_valLabel.setText(f'{new_err:.3f}°')

    def update_ui_telescope(self):
        az_velocity = (self.az_pos - self.last_az) / self.interval * 1000
        za_velocity = (self.za_pos - self.last_za) / self.interval * 1000
        self.update_az_pos(self.az_pos, self.az_pps_pos)
        self.update_za_pos(self.za_pos, self.za_pps_pos)
        self.last_az = self.az_pos
        self.last_za = self.za_pos
        self.update_az_vel(az_velocity)
        self.update_za_vel(za_velocity)
        if self.last_az_commanded is not None:
            az_err = self.az_pos - self.last_az_commanded
            self.update_az_err(az_err)
        if self.last_za_commanded is not None:
            za_err = self.za_pos - self.last_za_commanded
            self.update_za_err(za_err)

    #
    # Camera Handlers
    #
    def optical_camera_loop(self):
        while self.optical_pushButton.isChecked():
            self.update_live_footage()
            time.sleep(1 / self.frame_rate)

    @Slot()
    def toggle_live_footage(self):
        if self.optical_pushButton.isChecked():
            # Start showing live footage
            self.live_footage_canvas.show()
            self.live_footage_thread = Thread(target=(self.optical_camera_loop))
            self.live_footage_thread.start()
            self.optical_pushButton.setText('Hide Optical Video')
        else:
            # Stop showing live footage
            self.live_footage_canvas.hide()
            while self.live_footage_thread.is_alive():
                self.live_footage_thread.join(0)
                QCoreApplication.processEvents()
                time.sleep(5e-3)
            self.optical_pushButton.setText('Show Optical Video')

    def update_live_footage(self):
        if self.is_active_tab:  # Only update the canvas if the tab is in focus
            image, _ = self.get_current_image()
            self.live_footage_im.set_array(image)
            self.live_footage_canvas.canvas.draw()
            self.live_footage_canvas.canvas.flush_events()

    def closeEvent(self, event):
        self.timer.stop()
        # don't need to wait for success msg, since listener thread will eat the message
        # Stop the live footage thread if it's still going
        if self.live_footage_thread is not None and self.live_footage_thread.is_alive():
            self.optical_pushButton.click()
        return super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
