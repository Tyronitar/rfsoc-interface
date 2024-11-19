from PySide6.QtWidgets import QWidget, QMainWindow, QApplication
from PySide6.QtCore import Qt
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
ALT_OUT_CHANNEL = 0
POS_SW_LIM = 181.000
NEG_SW_LIM = -181.000
POS_ALT_SW_LIM = -np.inf  # TODO: Is this supposed to be negative?
NEG_ALT_SW_LIM = -np.inf
AZ_HOME = 0
BAUDRATE = 38400
TIMEOUT = 2
AKD1 = "169.254.250.165"
AKD2 = "169.254.250.166"  ##switches back and forth between these two channels when faults occur.
ALTPORT = 23
GEAR_RATIO = 258

ADDR_PL_FB = 588  ##This is the position loop feedback. Includes some offset parameter and error based on homing position. Appropriate for this application, though I need to figure out the resolution.
ADDR_FB1_P = 1610  ##This is the absolute position from the FB1 (resolver).


class StopMotion(Exception):
    """Exception for handling pressing of the stop button."""
    def __init__(self, *args):
        super().__init__(*args)

class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self):
        self._initialized = False
        self._initialize_system()
    
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

        # Altitude
        self.ser_alt = Telnet(host=AKD1, port=ALTPORT)
        self.ser_alt.open(host=AKD1, port=ALTPORT)
        self.ser_alt.write(b'DRV.ACTIVE\r\n')
        status_string = self.ser_alt.read_until(b'\r', 0.1).decode()
        status = float(status_string.split('\r')[0])

        if status == 1:
            print('ALT motor connected and software already enabled.')
        else:
            self.ser_alt.write(b'DRV.EN\r\n')
            sw_en = self.ser_alt.read_until(b'\r', 0.1)
            print('ALT motor connected and software enabled by Python.')
        self.alt_pos = 0
        self.alt_pos = self.get_ser_alt_pos()
        print(f'Telescope ALT position is: {self.alt_pos}')
        self._initialized = True
    
    def close(self):
        self.ser_az.close()
        self.ser_alt.close()

    def set_ao_value(self, data: float, channel: int):
        self.ao_device.a_out(channel, self.ul_range_out, self.ao_flags, data)
    
    def set_ao_zero(self):
        zero_data = analog_to_digital(0, -10, 10, 16)
        self.set_ao_value(zero_data, AZ_OUT_CHANNEL)
        self.set_ao_value(zero_data, ALT_OUT_CHANNEL)

    # Azimuth settings
    def set_az_home(self):
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
        pass

    def az_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        pass

    def jog_az_pos(self, speed: float=1):
        pass

    def az_oscillate(self, total_t: float, freq: float, deg: float):
        pass

    def set_az_speed_relation(self, voltage: float):
        pass

    # Altitude settings
    def set_alt_home(self):
        pass

    def get_ser_alt_pos(self) -> float | None:
        old_pos = self.alt_pos
        try:
            self.ser_alt.write('PL.FB\r\n'.encode('ASCII'))
            pos_str = self.ser_alt.read_until(b']', 0.1).decode()
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            # self.alt_pos = pos
            return pos
        except ValueError:
            print(
                'Error communicating with ALT controller; '
                'position set to most recent read.'
            )
            return old_pos

    def set_alt_pos(self, new_pos: int, scan_mode: bool=False):
        pass

    def alt_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        pass

    def set_alt_speed_relation(self, voltage: float):
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
    
    def update_ui(self):
        self.azimuth_actual_valLabel.setText(f'{self.ctrl.get_ser_az_pos():.3f}')
        self.zenith_actual_valLabel.setText(f'{self.ctrl.get_ser_alt_pos():.3f}')
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
