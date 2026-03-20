from __future__ import annotations

import logging

from PySide6.QtWidgets import QWidget, QMainWindow, QApplication, QAbstractButton, QDialog, QVBoxLayout
from PySide6.QtCore import Qt, Signal ,Slot, QObject, QThread, QTimer, QMutexLocker
import serial.tools
from rfsocinterface.core.telescope import ZE_OUT_CHANNEL
from rfsocinterface.core.telescope import AZ_OUT_CHANNEL
from rfsocinterface.core.telescope import make_controller
from rfsocinterface.gui.uic.telescope_control_ui import Ui_TelescopeControlWidget as Ui_TelescopeControlWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from rfsocinterface.core.camera import SKPR_Camera_Control, MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH
from rfsocinterface.core.utils import P, R, TabName
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.main_widget import TelescopeMainWidget
from rfsocinterface.gui.widgets import get_num_value
from typing import Callable, Concatenate, Any, TYPE_CHECKING
import functools

from multiprocessing import Process, Pipe, Queue
from threading import Thread
import time
import numpy as np
import numpy.typing as npt

import matplotlib.pyplot as plt
import sys
import os
import serial
from pyModbusTCP.client import ModbusClient
# from telnetlib import Telnet
import glob
from pathlib import Path


if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_tele_logger = logging.getLogger('rfsocinterface.telescopeControl')

class TelescopeControlWidget(TelescopeMainWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""

    tab_name = TabName.TELESCOPE

    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, client_id: str, parent: QWidget | None=None):
        super().__init__(main_window, rfsocs, settings, client_id, parent=parent)
        self.setupUi(self)

        self.azimuth_commanded_valLabel.setText('N/A')
        self.zenith_commanded_valLabel.setText('N/A')

        self.interval = 200  # Milliseconds between update calls
        self.ze_jog_voltage = 1  # Degrees / second
        self.az_jog_voltage = 5  # Degrees / second

        # Control Connections
        self.stop_pushButton.clicked.connect(self.stop_motion)
        self.azimuth_setpushButton.clicked.connect(self.set_az_pos)
        self.zenith_setpushButton.clicked.connect(self.set_ze_pos)
        self.controller.buttonGroup.buttonPressed.connect(self.jog)
        self.controller.buttonGroup.buttonReleased.connect(self.stop_motion)
        self.manual_controlcheckBox.toggled.connect(self.toggle_jogging)

        self.connect_to_telescope_command('az_pos', self.update_az_pos)
        self.connect_to_telescope_command('ze_pos', self.update_ze_pos)
        self.connect_to_telescope_command('az_pos_comm', self.update_az_cmd)
        self.connect_to_telescope_command('ze_pos_comm', self.update_ze_cmd)

        self.live_footage_fig, self.live_footage_ax = plt.subplots()
        self.live_footage_im = self.live_footage_ax.imshow(np.zeros((MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3)))
        self.live_footage_canvas.set_figure(self.live_footage_fig)
        self.live_footage_ax.set_axis_off()
        self.connect_to_camera_command('image', self.update_live_footage)


        # Set up Optical Camera
        self.optical_pushButton.clicked.connect(self.take_pic)


        # Initialize the numbers in the GUI
        self.az_pos = self.last_az = 0
        self.az_pps_pos = None
        self.ze_pos = self.last_ze = 0
        self.ze_pps_pos = None

        self.send_telescope_command('get_ser_az_pos')
        self.send_telescope_command('get_ser_ze_pos')

        self.last_az_commanded = None
        self.last_ze_commanded = None
        # self.update_az_cmd(self.last_az_commanded)
        # self.update_ze_cmd(self.last_ze_commanded)

        # Update Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui_telescope)
        self.timer.start(500)


    def stop_motion(self):
        self.send_telescope_command('stop_telescope')
    
    def take_pic(self):
        pic_data = self.cam_ctrl.take_pic(show=False)
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
                self.send_telescope_command('set_voltage', -self.ze_jog_voltage, ZE_OUT_CHANNEL)
            case self.controller.down_toolButton:
                self.send_telescope_command('set_voltage', self.ze_jog_voltage, ZE_OUT_CHANNEL)
            case self.controller.left_toolButton:
                self.send_telescope_command('set_voltage', self.az_jog_voltage, AZ_OUT_CHANNEL)
            case self.controller.right_toolButton:
                self.send_telescope_command('set_voltage', -self.az_jog_voltage, AZ_OUT_CHANNEL)
    
    def set_az_pos(self):
        new_pos = get_num_value(self.azimuth_setlineEdit)
        self.send_telescope_command('set_az_pos', new_pos)
    
    def set_ze_pos(self):
        new_pos = get_num_value(self.zenith_setlineEdit)
        self.send_telescope_command('set_ze_pos', new_pos)
    
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
    def update_ze_pos(self, new_pos: float, pps_pos: float | None):
        self.zenith_actual_valLabel.setText(f'{new_pos:.3f}°')
        if pps_pos is None:
            self.zenith_pps_valLabel.setText('N/A')
        else:
            self.zenith_pps_valLabel.setText(f'{pps_pos:.3f}°')
        self.ze_pos = new_pos
        self.ze_pps_pos = pps_pos

    @Slot(float)
    def update_ze_cmd(self, new_pos: float):
        self.last_ze_commanded = new_pos
        self.zenith_commanded_valLabel.setText(f'{new_pos:.3f}°')

    @Slot(float)
    def update_ze_vel(self, new_vel: float):
        self.zenith_velocity_valLabel.setText(f'{new_vel:.2f}°/sec')

    @Slot(float)
    def update_ze_err(self, new_err: float):
        self.zenith_error_valLabel.setText(f'{new_err:.3f}°')
    
    def update_ui_telescope(self):
        az_velocity = (self.az_pos - self.last_az) / self.interval * 1000
        ze_velocity = (self.ze_pos - self.last_ze) / self.interval * 1000
        self.update_az_pos(self.az_pos, self.az_pps_pos)
        self.update_ze_pos(self.ze_pos, self.ze_pps_pos)
        self.last_az = self.az_pos
        self.last_ze = self.ze_pos
        self.update_az_vel(az_velocity)
        self.update_ze_vel(ze_velocity)
        if self.last_az_commanded is not None:
            az_err = self.az_pos - self.last_az_commanded
            self.update_az_err(az_err)
        if self.last_ze_commanded is not None:
            ze_err = self.ze_pos - self.last_ze_commanded
            self.update_ze_err(ze_err)
    
    #
    # Camera Handlers
    #
    def update_live_footage(self, timestamp: float):
        if self.is_active_tab:
            self.live_footage_im.set_array(self.get_current_image())
            self.live_footage_canvas.canvas.draw()
            self.live_footage_canvas.canvas.flush_events()

    def closeEvent(self, event):
        self.timer.stop()
        # don't need to wait for success msg, since listener thread will eat the message
        return super().closeEvent(event)
    


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
