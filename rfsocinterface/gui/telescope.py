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
from rfsocinterface.core.camera import SKPR_Camera_Control
from rfsocinterface.core.utils import P, R
from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.gui.main_widget import TelescopeMainWidget
from typing import Callable, Concatenate, Any, TYPE_CHECKING
import functools

from multiprocessing import Process, Pipe, Queue
from threading import Thread

import matplotlib.pyplot as plt
import sys
import os
import serial
from pyModbusTCP.client import ModbusClient
# from telnetlib import Telnet
import glob
from pathlib import Path

from rfsocinterface.gui.utils import get_num_value

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow

_tele_logger = logging.getLogger('rfsocinterface.telescope')

class TelescopeControlWidget(TelescopeMainWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""
    def __init__(self, main_window: 'MainWindow', rfsocs: list[RFSOCWrapper], settings: dict, client_id: str, parent: QWidget | None=None):
        super().__init__(main_window, rfsocs, settings, client_id, parent=parent)
        self.setupUi(self)

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

        self._listener_thread = Thread(target=self._connection_loop)


        # Set up Optical Camera
        self.cam_ctrl = SKPR_Camera_Control()
        self.optical_pushButton.clicked.connect(self.take_pic)


        # Initialize the numbers in the GUI
        self.az_pos = self.last_az = 0
        self.ze_pos = self.last_ze = 0
        self._listener_thread.start()

        self._telescope_queue.put([self._client_id, 'get_ser_az_pos'])
        self._telescope_queue.put([self._client_id, 'get_ser_ze_pos'])

        self.last_az_commanded = self.last_az
        self.last_ze_commanded = self.last_ze
        self.update_az_cmd(self.last_az_commanded)
        self.update_ze_cmd(self.last_ze_commanded)

        # Update Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)


    def stop_motion(self):
        self._telescope_queue.put([self._client_id, 'stop_telescope'])
    
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
                self._telescope_queue.put([self._client_id, 'set_voltage', -self.ze_jog_voltage, ZE_OUT_CHANNEL])
            case self.controller.down_toolButton:
                self._telescope_queue.put([self._client_id, 'set_voltage', self.ze_jog_voltage, ZE_OUT_CHANNEL])
            case self.controller.left_toolButton:
                self._telescope_queue.put([self._client_id, 'set_voltage', self.az_jog_voltage, AZ_OUT_CHANNEL])
            case self.controller.right_toolButton:
                self._telescope_queue.put([self._client_id, 'set_voltage', -self.az_jog_voltage, AZ_OUT_CHANNEL])
    
    def _connection_loop(self):
        while True:
            response, *data = self._conn_parent.recv()
            _tele_logger.debug(f'{self._client_id} got response: {response}, data: {data}')
            match response.lower():
                case 'az_pos':
                    self.update_az_pos(*data)
                case 'ze_pos':
                    self.update_ze_pos(*data)
                case 'az_pos_comm':
                    self.update_az_cmd(*data)
                case 'ze_pos_comm':
                    self.update_ze_cmd(*data)
                case 'err':
                    raise RuntimeError(f'Error from telescope controller: {data}')
                case 'done' | 'remove_connection_succesful':
                    break 
                case _:
                    raise RuntimeError(f'Unknown response from telescope controller: {response}')

    def set_az_pos(self):
        new_pos = get_num_value(self.azimuth_setlineEdit)
        self._telescope_queue.put([self._client_id, 'set_az_pos', new_pos])
    
    def set_ze_pos(self):
        new_pos = get_num_value(self.zenith_setlineEdit)
        self._telescope_queue.put([self._client_id, 'set_ze_pos', new_pos])
    
    @Slot(float)
    def update_az_pos(self, new_pos: float):
        self.azimuth_actual_valLabel.setText(f'{new_pos:.3f}°')
        self.az_pos = new_pos
    
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

    @Slot(float)
    def update_ze_pos(self, new_pos: float):
        self.zenith_actual_valLabel.setText(f'{new_pos:.3f}°')
        self.ze_pos = new_pos

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
    
    def update_ui(self):
        az_velocity = (self.az_pos - self.last_az) / self.interval * 1000
        ze_velocity = (self.ze_pos - self.last_ze) / self.interval * 1000
        self.update_az_pos(self.az_pos)
        self.update_ze_pos(self.ze_pos)
        self.last_az = self.az_pos
        self.last_ze = self.ze_pos
        self.update_az_vel(az_velocity)
        self.update_ze_vel(ze_velocity)
        az_err = self.az_pos - self.last_az_commanded
        ze_err = self.ze_pos - self.last_ze_commanded
        self.update_az_err(az_err)
        self.update_ze_err(ze_err)

    def closeEvent(self, event):
        self.timer.stop()
        self._telescope_queue.put([self._client_id, 'remove_connection'])
        # don't need to wait for success msg, since listener thread will eat the message
        self._listener_thread.join()
        self._conn_parent.close()
        self._conn_child.close()
        return super().closeEvent(event)
    


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
