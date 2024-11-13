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
            data_value = analog_to_digital(0, -10, 10, 16)
            
            # Set output to zero
            self.ao_device.a_out(
                AZ_OUT_CHANNEL,
                self.ul_range_out,
                self.ao_flags,
                data_value,
            )
            self.ao_device.a_out(
                ALT_OUT_CHANNEL,
                self.ul_range_out,
                self.ao_flags,
                data_value,
            )
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
            print('Could not communicate wit hAZ controller. System could not initialize.')
        self.ser_az = ser_az
        self.az_pos = self.ser_az_pos()
        print(f'Telescope AZ position is: {self.az_pos}')

        # Altitude
        self.ser_alt = Telnet(host=AKD1, port=ALTPORT)
        self.ser_alt.open(host=AKD1, port=ALTPORT)
        self.ser_alt.write(b'DRV.ACTIVE\r\n')
        status_string = self.ser_alt.read_until('b\r', 0.1).decode()
        status = float(status_string.split('\r')[0])
        if status == 1:
            print('ALT motor connected and software already enabled.')
        else:
            self.ser_alt.write(b'DRV.EN\r\n')
            sw_en = self.ser_alt.read_until('b\r', 0.1)
            print('ALT motor connected and software enabled by Python.')
        self.alt_pos = self.ser_alt_pos()
        print(f'Telescope ALT position is: {self.alt_pos}')

    def ser_az_pos(self) -> float | None:
        pass

    def ser_alt_pos(self) -> float | None:
        pass
            

class TelescopeControlWidget(QWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""
    def __init__(self, kpy: kidpy, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)
        self.kpy = kpy
        self.ctrl = TelescopeMotorController()
    
    def update_ui(self):
        # TODO: Update the values to show current position etc.
        pass


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
