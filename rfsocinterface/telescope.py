from PySide6.QtWidgets import QWidget, QMainWindow, QApplication
from PySide6.QtCore import Qt, Signal ,Slot, QObject
import serial.tools
import serial.tools.list_ports
from rfsocinterface.ui.telescope_control_ui import Ui_TelescopeControlWidget as Ui_TelescopeControlWidget
from kidpy import kidpy
from rfsocinterface.utils import analog_to_digital, digital_to_analog

import uldaq as ul
import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
import sys
import os
import pdb
import serial
from pyModbusTCP.client import ModbusClient
from telnetlib import Telnet
import h5py
import glob
from pathlib import Path

AZ_OUT_CHANNEL = 1
ZE_OUT_CHANNEL = 0
POS_SW_LIM = 181.000
NEG_SW_LIM = -181.000
POS_ZE_SW_LIM = -np.inf  # TODO: Is this supposed to be negative?
NEG_ZE_SW_LIM = -np.inf
AZ_HOME = 0
BAUDRATE = 38400
TIMEOUT = 2
AKD1 = "169.254.250.165"
AKD2 = "169.254.250.166"  ##switches back and forth between these two channels when faults occur.
ZEPORT = 23
GEAR_RATIO = 258

ADDR_PL_FB = 588  ##This is the position loop feedback. Includes some offset parameter and error based on homing position. Appropriate for this application, though I need to figure out the resolution.
ADDR_FB1_P = 1610  ##This is the absolute position from the FB1 (resolver).
ZERO_DATA = analog_to_digital(0, -10, 10, 16)


class StopMotion(Exception):
    """Exception for handling pressing of the stop button."""
    def __init__(self, *args):
        super().__init__(*args)

class TelescopeMotorController(QObject):
    """Class for controlling the motion of the telescope."""

    azimuthUpdated = Signal(float)
    azimuthCommanded = Signal(float)
    azimuthVelocityChanged = Signal(float)
    zenithUpdated = Signal(float)
    zenithCommanded = Signal(float)
    zenithVelocityChanged = Signal(float)

    def __init__(self, parent=None):
        self._initialized = False
        self._initialize_system()
        super().__init__(parent)
    
    def test_init(self):
        if not self._initialized:
            self._initialize_system
    
    def _initialize_system(self):
        try:
            # Connect to device
            descriptor = ul.get_daq_device_inventory(ul.InterfaceType.ANY)[0]
            device = ul.DaqDevice(descriptor)
            device.connect()
            self.device = device

            # Configure analog outputs
            self.ao_device = self.device.get_ao_device()
            self.ul_range_out = self.ao_device.get_info().get_ranges()[0]
            self.ao_flags = ul.AOutFlag.DEFAULT
            
            # Set output to zero
            self.set_ao_zero()
        except OSError as e:
            raise OSError('DAQ could nto be initialized; Check comport and power supply') from e
        
        # Init serial communication with S700 for high res positioning of AZ monitors
        comports = serial.tools.list_ports.comports()
        for dev in comports:
            # port_array[dev] = str(ports[dev].manufacturer)
            # print('dev #: ', dev)
            if dev.manufacturer == "Prolific Technology Inc.":
                az_port = dev.device
        ser_az = serial.Serial(
            az_port,
            baudrate=BAUDRATE,
            timeout=TIMEOUT,
            bytesize=8,
            parity='N',
            stopbits=1,
        )
        if ser_az.is_open:
            print('AZ motor connected to original port')
        else:
            print('Could not communicate with AZ controller. System could not initialize.')
        self.ser_az = ser_az
        self.az_pos = 0
        self.az_pos = self.get_ser_az_pos()
        print(f'Telescope AZ position is: {self.az_pos}')
        self.az_vel = 0

        # Zenith Angle
        self.ser_ze = Telnet(host=AKD1, port=ZEPORT)
        self.ser_ze.open(host=AKD1, port=ZEPORT)
        self.ser_ze.write(b'DRV.ACTIVE\r\n')
        status_string = self.ser_ze.read_until(b'\r', 0.1).decode()
        status = float(status_string.split('\r')[0])

        if status == 1:
            print('ZE motor connected and software already enabled.')
        else:
            self.ser_ze.write(b'DRV.EN\r\n')
            sw_en = self.ser_ze.read_until(b'\r', 0.1)
            print('ZE motor connected and software enabled by Python.')
        self.ze_pos = 0
        self.ze_pos = self.get_ser_ze_pos()
        print(f'Telescope ZE position is: {self.ze_pos}')
        self._initialized = True
        self.ze_vel = 0
    
    def close(self):
        self.ser_az.close()
        self.ser_ze.close()

    def set_ao_value(self, data: float, channel: int):
        self.ao_device.a_out(channel, self.ul_range_out, self.ao_flags, data)
    
    def set_ao_zero(self):
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)

    # Azimuth settings
    def set_az_home(self):
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        pfb = self.get_ser_az_pos()
        counter = 0
        # TODO: Finish this lol
        pass

    def get_ser_az_pos(self) -> float:
        old_pfb = self.az_pos
        try:
            if self.ser_az.is_open:
                self.ser_az.write(b'PFB\r\n')
                self.ser_az.readline()
                pfb = self.ser_az.read_until(b'\r\n')
                pfb = float(pfb.decode()) / 10000.0
                # self.az_pos = pfb
                self.ser_az.reset_input_buffer()
                self.ser_az.reset_output_buffer()
                return pfb
        except ValueError:
            print(
                'Error communicating with AZ controller; '
                'position set to most recent read.'
            )
            return old_pfb

    def set_az_pos(self, new_pos: int, scan_mode: bool=False):
        self.azimuthCommanded.emit(new_pos)
        pass

    def az_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        pass

    def jog_az_pos(self, speed: float=1):
        pass

    def az_oscillate(self, total_t: float, freq: float, deg: float):
        pass

    def set_az_speed_relation(self, voltage: float):
        pass

    # Zenith angle settings
    def set_ze_home(self):
        pass

    def get_ser_ze_pos(self) -> float | None:
        old_pos = self.ze_pos
        try:
            self.ser_ze.write('PL.FB\r\n'.encode('ASCII'))
            pos_str = self.ser_ze.read_until(b']', 0.1).decode()
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            # self.ze_pos = pos
            return pos
        except ValueError:
            print(
                'Error communicating with ZE controller; '
                'position set to most recent read.'
            )
            return old_pos

    def set_ze_pos(self, new_pos: int, scan_mode: bool=False):
        self.zenithCommanded.emit(new_pos)
        pass

    def ze_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        pass

    def set_ze_speed_relation(self, voltage: float):
        pass

    # Misc
    def talk_to_az(self, command: str):
        pass
            

class TelescopeControlWidget(QWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""
    def __init__(self, kpy: kidpy, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)
        self.kpy = kpy
        self.ctrl = TelescopeMotorController()
        self.update_ui()

        # Signal connections
        self.ctrl.azimuthUpdated.connect(self.update_az_pos)
        self.ctrl.azimuthCommanded.connect(self.update_az_cmd)
        self.ctrl.azimuthVelocityChanged.connect(self.update_az_vel)
        self.ctrl.zenithUpdated.connect(self.update_ze_pos)
        self.ctrl.zenithCommanded.connect(self.update_ze_cmd)
        self.ctrl.zenithVelocityChanged.connect(self.update_ze_vel)
    
    @Slot(float)
    def update_az_pos(self, new_pos: float):
        self.azimuth_actual_valLabel.setText(f'{new_pos:.3f}')
    
    @Slot(float)
    def update_az_cmd(self, new_pos: float):
        self.azimuth_commanded_valLabel.setText(f'{new_pos:.3f}')

    @Slot(float)
    def update_az_vel(self, new_vel: float):
        self.azimuth_velocity_valLabel.setText(f'{new_vel:.2f}')
    
    @Slot(float)
    def update_ze_pos(self, new_pos: float):
        self.zenith_actual_valLabel.setText(f'{new_pos:.3f}')

    @Slot(float)
    def update_ze_cmd(self, new_pos: float):
        self.zenith_commanded_valLabel.setText(f'{new_pos:.3f}')

    @Slot(float)
    def update_ze_vel(self, new_vel: float):
        self.zenith_velocity_valLabel.setText(f'{new_vel:.2f}')
    
    def update_ui(self):
        self.update_az_pos(self.ctrl.get_ser_az_pos())
        self.update_ze_pos(self.ctrl.get_ser_ze_pos())
        # TODO: Show other values (commanded, error, velocity)
    
    def closeEvent(self, event):
        self.ctrl.close()
        return super().closeEvent(event)
    


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
