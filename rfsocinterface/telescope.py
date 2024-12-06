from __future__ import annotations
from PySide6.QtWidgets import QWidget, QMainWindow, QApplication, QAbstractButton, QDialog, QVBoxLayout
from PySide6.QtCore import Qt, Signal ,Slot, QObject, QThread, QTimer, QMutex, QMutexLocker
import serial.tools
import serial.tools.list_ports
from rfsocinterface.ui.telescope_control_ui import Ui_TelescopeControlWidget as Ui_TelescopeControlWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from rfsocinterface.camera import SKPR_Camera_Control
from kidpy import kidpy
from rfsocinterface.utils import analog_to_digital, digital_to_analog, P, R
from typing import Callable, Concatenate, Any
import functools
import time

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

def interruptable(
        func: Callable[
            Concatenate[TelescopeMotorController, P],
            R],
) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(ctrl: TelescopeMotorController, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(ctrl, *args, **kwargs)
        except StopMotion:
            # ctrl.stop()
            pass
    return wrapper

class TelescopeMotionJob(QThread):
    updateProgress = Signal()
    returned = Signal(Any)
    canceled = Signal()

    #You can do any extra things in this init you need, but for this example
    #nothing else needs to be done expect call the super's init
    def __init__(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        res = self.func(*self.args, **self.kwargs)
        self.returned.emit(res)


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
        self.run = False
        self.az_mutex = QMutex()
        self.ze_mutex = QMutex()
        self._active_jobs: list[TelescopeMotionJob] = []
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
            print('ZA motor connected and software already enabled.')
        else:
            self.ser_ze.write(b'DRV.EN\r\n')
            sw_en = self.ser_ze.read_until(b'\r', 0.1)
            print('ZA motor connected and software enabled by Python.')
        self.ze_pos = 0
        self.ze_pos = self.get_ser_ze_pos()
        print(f'Telescope ZA position is: {self.ze_pos}')
        self._initialized = True
        self.ze_vel = 0
    
    def close(self):
        az_locker = QMutexLocker(self.az_mutex)
        ze_locker = QMutexLocker(self.ze_mutex)
        self.ser_az.close()
        self.ser_ze.close()

    def set_ao_value(self, data: float, channel: int):
        self.ao_device.a_out(channel, self.ul_range_out, self.ao_flags, data)
    
    def set_ao_zero(self):
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)

    # Azimuth settings
    def set_az_home(self):
        if self.ser_az.is_open:
            command = "NREF\r\n"
            command = command.encode()
            self.ser_az.write(command)
            self.ser_az.readline()
            pfb = self.ser_az.read_until(b"\r\n")
            self.ser_az.reset_input_buffer()
            self.ser_az.reset_output_buffer()
            print("Home Set.")
        else:
            print("Home command not executed. Check connection with S700")
    
    # TODO: There's also a "setAZ_home_position"...

    ##Read AZ Serial Position

    def get_ser_az_pos(self) -> float:
        old_pfb = self.az_pos
        locker = QMutexLocker(self.az_mutex)
        try:
            if self.ser_az.is_open:
                self.ser_az.write(b'PFB\r\n')
                self.ser_az.readline()
                pfb = self.ser_az.read_until(b'\r\n')
                pfb = float(pfb.decode()) / 10000.0
                self.ser_az.reset_input_buffer()
                self.ser_az.reset_output_buffer()
                self.az_pos = pfb
                if self._initialized:
                    self.azimuthUpdated.emit(pfb)
                return pfb
        except ValueError:
            print(
                'Error communicating with AZ controller; '
                'position set to most recent read.'
            )
            return old_pfb

    def set_az_pos(self, new_pos: int, scan_mode: bool=False):
        self.azimuthCommanded.emit(new_pos)
        self.run = True
        worker = TelescopeMotionJob(self._set_az_pos, new_pos, scan_mode)
        self._active_jobs.append(worker)
        worker.start()
    
    def _set_az_pos(self, new_pos: int, scan_mode: bool=False):
        # I want to accept a number in degrees, but put the number in the integer value desired by S700 controller
        # AZ controlled by 2 motors, the first to actually move the telescope, the second to put some tension on the gear for avoiding any backlash. Currently the secondary motor is disabled, probably providing little to no torque, but given the huge gearing ratio, it probably helps with backlash. The next easiest technique would be to run the secondary in "analog torque" mode, setting the zero value to some small torque. This could be improved by increasing the torque during motion and reducing when the first motor is not moving (probably by changing the zero value torque, since both analog outs are already in use). The proper way to do it, and the reason we were sold these S700 controllers is called RDP per the kollmorgen tech guy but my guess is he meant prd cogging mode.
        self.set_ao_zero()
        # Measure input voltage

        ##confirm position
        pfb = self.get_ser_az_pos()
        if scan_mode:
            this_ze = self.get_ser_ze_pos()
            position_data = []
        counter = 0
        ##Run loop
        pfb_time = time.time()

        while (
            np.abs(pfb - new_pos) > 0.016 ##currently overshoots by .018 degrees on average
            and pfb > NEG_SW_LIM
            and pfb < POS_SW_LIM
            and self.run
        ):
            try:
                #get start time
                
                # Choose direction of motion. Negative Voltage goes clockwise when looking down at the telesecope from the sky!!
                #                if keyboard.is_pressed("space"):
                #                    print("User terminated motion!")
                #                   break
                if new_pos > pfb:
                    direction = -1
                else:
                    direction = 1
                # I still need to double check motion direction for accuracy
                ##Set Speed faster if more travel needed
                if scan_mode:
                    # data_value = direction*self.convert_A_to_D(3.,[-10,10],16)
                    if (
                        abs(pfb - new_pos) > 0.5
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(6.0, -10, 10, 16)
                        #print(data_value)
                        #print("This is the voltage output")
                    else:
                        data_value = direction * analog_to_digital(2.0, -10, 10, 16)
                else:
                    if (
                        abs(pfb - new_pos) > 15
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                    elif (
                        abs(pfb - new_pos) < 15
                    ):  ##If we are far from the setpoint, go at max speed
                        this_speed = 0.35 * abs(pfb - new_pos) + 1.5
                        data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                # elif abs(pfb-az_set_pos) < 1.:##set to slower speed as approaching setpoint
                # data_value = direction*self.convert_A_to_D(.35,[-10,10],16)
                # elif abs(pfb-az_set_pos) < .200:##set to slower speed as approaching setpoint
                # self.set_AZ_speedrelation(10)##Not sure about this one yet. Need to test!
                # data_value = direction*self.convert_A_to_D(.35,[-10,10],16)
                #            else:##else: set to slowest speed
                #                data_value = direction*self.convert_A_to_D(.35,[-10,10],16)
                if counter % 50 == 0:
                    print(pfb, data_value)
                # time.sleep(.3)
                # self.azimuthVelocityChanged.emit(data_value)
                self.set_ao_value(data_value, AZ_OUT_CHANNEL)
                #pdb.set_trace()
                this_dt = time.time() - pfb_time
                while this_dt < 0.02:
                   this_dt = time.time() - pfb_time
                   time.sleep(1.e-4)
                pfb_time = time.time()
                pfb = self.get_ser_az_pos()
                self.azimuthUpdated.emit(pfb)

                if scan_mode:
                    position_data = np.append(position_data, [pfb, this_ze, pfb_time])
                    
                counter = counter + 1

            except KeyboardInterrupt:
                print("User terminated motion!")
                break

            except ValueError:
                print("caught an exception regarding Float conversion")
                break
        self.set_ao_zero()
        self.run = False
        # self.azimuthVelocityChanged.emit(0)
        ## Read position again
        time.sleep(1)
        pfb = self.get_ser_az_pos()
        #        print ('Set to position: ', pfb)
        if scan_mode:
            return position_data

    def az_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        worker = TelescopeMotionJob(self._az_scan_mode, start, stop, file, n_repeats)
        self._active_jobs.append(worker)
        worker.start()

    def _az_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        az_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        az_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        current_az = self.get_ser_az_pos()
        current_ze = self.get_ser_ze_pos()
        az_start += current_az
        az_stop += current_az
        dummy = self._set_az_pos(az_start - az_start_buffer)  # Don't create a new thread
        for i_rep in np.arange(n_repeats):
            if np.mod(i_rep, 2) == 0:
                self._set_ze_pos(current_ze)
                this_position_data = self._set_az_pos(
                    az_stop + az_end_buffer + 0.5, scan_mode=True
                )
                if i_rep == 0:
                    position_data = this_position_data
                else:
                    position_data = np.append(position_data, this_position_data)
            if np.mod(i_rep, 2) == 1:
                self._set_ze_pos(current_ze + 0.04)
                this_position_data = self._set_az_pos(
                    az_start - az_start_buffer - 0.5, scan_mode=True
                )
                position_data = np.append(position_data, this_position_data)

        # np.savez(position_data_file, az = position_data[0::3],el = position_data[1::3],time = position_data[2::3],az_start=AZ_start,
        #  az_stop=AZ_stop,el_start=np.nan,el_stop=np.nan)
        f = h5py.File(file, "a")
        f.create_dataset("az_tel", data=position_data[0::3])
        f.create_dataset("za_tel", data=position_data[1::3])
        f.create_dataset("timestamp_tel", data=position_data[2::3])
        f.create_dataset("optical_visibility", data=['****'])
        f.close()
        time.sleep(0.5)
        print("Scan Complete")



    def jog_az_pos(self, speed: float=1):
        pass

    def az_oscillate(self, total_t: float, freq: float, deg: float):
        pass

    def set_az_speed_relation(self, voltage: float):
        # Set the speed of the motor in RPM/10V. Default is 500, which would roughly turn the telescope 2.5 degree/second for 10 V input. ASCII code for serial is VSCALE1. AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT! Needs more testing from Ubuntu, I think there is a lower limit set in the S700.
        if self.ser_az.is_open:
            command = "VSCALE1 " + str(voltage) + "\r\n"
            command = command.encode()
            self.ser_az.write(command)
            self.ser_az.readline()
            az_speed = self.ser_az.read_until(b"\r\n")
            print("AZ speed set to: ", az_speed)  ###THIS MAY BREAK
            self.azimuthVelocityChanged(az_speed)
            self.ser_az.reset_input_buffer()
            self.ser_az.reset_output_buffer()
        pass
    # Zenith angle settings
    def set_ze_home(self):
        # Set current position of the motor to zero.
        pos = self.get_ser_ze_pos()
        pdb.set_trace()
        self.ser_ze.write(b"DRV.DIS\r\n")
        sw_en = self.ser_ze.read_until(b"\r\n", 0.1)
        time.sleep(1)
        offset_command = "FB1.OFFSET " + str(-1 * pos) + "\r\n"
        self.ser_ze.write(offset_command.encode("ascii"))
        ret = self.ser_ze.read_until(b"\r\n")
        self.ser_ze.write(b"DRV.EN\r\n")
        sw_en = self.ser_ze.read_until(b"\r", 0.1)
        pdb.set_trace()
        print("EL Home Set.")

    def get_ser_ze_pos(self) -> float | None:
        old_pos = self.ze_pos
        locker = QMutexLocker(self.ze_mutex)
        try:
            self.ser_ze.write('PL.FB\r\n'.encode('ASCII'))
            pos_str = self.ser_ze.read_until(b']', 0.1).decode()
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            self.ze_pos = pos
            if self._initialized:
                self.zenithUpdated.emit(pos)
            return pos
        except ValueError:
            print(
                'Error communicating with ZA controller; '
                'position set to most recent read.'
            )
            return old_pos

    def set_ze_pos(self, new_pos: int, scan_mode: bool=False):
        self.zenithCommanded.emit(new_pos)
        self.run = True
        worker = TelescopeMotionJob(self._set_ze_pos, new_pos, scan_mode)
        self._active_jobs.append(worker)
        worker.start()

    def _set_ze_pos(self, new_pos: int, scan_mode: bool=False):
        new_pos = float(new_pos)
        self.set_ao_zero()

        ##confirm position
        pos = self.get_ser_ze_pos()
        self.zenithUpdated.emit(pos)
        if scan_mode:
            this_az = self.get_ser_az_pos()
            position_data = []
        counter = 0

        ##Run loop
        while abs(pos - new_pos) > 0.003 and self.run:
            try:
                # Choose direction of motion
                if pos > new_pos:
                    direction = -1
                else:
                    direction = 1

                #                if keyboard.is_pressed("space"): ###DOES THIS WORK IN UBUNTU?
                #                    print("User terminated motion!")
                #                    break
                #"I still need to double check motion direction for accuracy"
                ##Set Speed faster if more travel needed
                if scan_mode:
                    data_value = direction * analog_to_digital(1.0, -10, 10, 16)
                else:
                    if (
                        abs(pos - new_pos) > 15
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                    elif (
                        abs(pos - new_pos) < 15
                    ):  ##If we are far from the setpoint, go at max speed
                        this_speed = 0.35 * abs(pos - new_pos) + 0.30
                        data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                # elif abs(pos-el_set_pos) < 5:##set to slower speed as approaching setpoint
                # data_value = direction*self.convert_A_to_D(2,[-10,10],16)
                # elif abs(pos-el_set_pos) < 1:##set to slower speed as approaching setpoint
                # self.set_EL_speedrelation(10)
                # data_value = direction*self.convert_A_to_D(.35,[-10,10],16)
                # else:##else: set to slowest speed
                #    data_value = direction*self.convert_A_to_D(.35,[-10,10],16)

                # self.zenithVelocityChanged.emit(data_value)
                self.set_ao_value(data_value, ZE_OUT_CHANNEL)
                pos = self.get_ser_ze_pos()
                self.zenithUpdated.emit(pos)
                if scan_mode:
                    position_data = np.append(
                        position_data, [this_az, pos, time.time()]
                    )
                counter = counter + 1
                if counter % 500 == 0:
                    print(pos, data_value)
                # time.sleep(.3)
            except KeyboardInterrupt:
                print("User terminated motion!")
                break
            except ValueError:
                print("caught an exception regarding Float conversion")
                break
            finally:
                # This code always executes after leaving the try statement
                pass

        self.run = False
        self.set_ao_zero()
        # self.zenithVelocityChanged.emit(0)
        ## Read position again
        time.sleep(0.1)
        pos = self.get_ser_ze_pos()
        self.zenithUpdated.emit(pos)
        #        print ('EL Set to position: ', str(pos))
        #        print ('Position Set!')
        if scan_mode:
            return position_data


    def ze_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        worker = TelescopeMotionJob(self._az_scan_mode, start, stop, file, n_repeats)
        self._active_jobs.append(worker)
        worker.start()

    def _ze_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        ze_start_buffer = 0.2 * np.sign(stop - start)
        ze_end_buffer = 0.2 * np.sign(stop - start)
        dummy = self._set_ze_pos(start - ze_start_buffer, scan_mode=True)
        position_data = self._set_ze_pos(stop + ze_end_buffer, scan_mode=True)
        np.savez(
            file,
            az=position_data[0::3],
            el=position_data[1::3],
            time=position_data[2::3],
        )

    def set_ze_speed_relation(self, voltage: float):
        # Set the speed of the motor in RPM/1V. Default is 40, which would roughly turn the telescope 1 degree/second. ASCII code for serial is AIN.VSCALE. NOTE: AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT!
        if self.ser_ze.is_open:
            command = "AIN.VCALE " + str(voltage) + "\r\n"
            command = command.encode()
            self.ser_ze.write(command)
            self.ser_ze.readline()
            ze_speed = self.ser_ze.read_until(b"\r\n")
            print("ZA speed set to: ", ze_speed)  ###THIS MAY BREAK
            self.zenithVelocityChanged(ze_speed)
            self.ser_ze.reset_input_buffer()
            self.ser_ze.reset_output_buffer()

    # Misc
    def talk_to_az(self, command: str):
        # Function to test ASCII commands for the S700 motor controller
        if self.ser_az.is_open:
            command += "\r\n"
            command = command.encode()
            self.ser_az.write(command)
            self.ser_az.readline()
            response = self.ser_az.read_until(b"\r\n")
            response = str(response.decode())
            print(response)
            self.ser_az.reset_input_buffer()
            self.ser_az.reset_output_buffer()
            

class TelescopeControlWidget(QWidget, Ui_TelescopeControlWidget):
    """Window for controlling telescope motion."""
    def __init__(self, kpy: kidpy, parent: QWidget | None=None):
        super().__init__(parent)
        self.setupUi(self)
        self.kpy = kpy
        self.ctrl = TelescopeMotorController()
        self.interval = 200  # Milliseconds between update calls
        self.ze_jog_voltage = 1  # Degrees / second
        self.az_jog_voltage = 5  # Degrees / second

        # Control Connections
        self.stop_pushButton.clicked.connect(self.stop_motion)
        self.azimuth_setpushButton.clicked.connect(self.set_az_pos)
        self.zenith_setpushButton.clicked.connect(self.set_ze_pos)
        self.controller.buttonGroup.buttonPressed.connect(self.steer)
        self.controller.buttonGroup.buttonReleased.connect(self.stop_motion)
        self.manual_controlcheckBox.toggled.connect(self.toggle_steering)

        # Set up Optical Camera
        self.cam_ctrl = SKPR_Camera_Control()
        self.optical_pushButton.clicked.connect(self.take_pic)

        # Update Timer
        self.last_az = self.ctrl.az_pos
        self.last_ze = self.ctrl.ze_pos
        self.last_az_commanded = self.last_az
        self.last_ze_commanded = self.last_ze
        self.update_az_cmd(self.last_az_commanded)
        self.update_ze_cmd(self.last_ze_commanded)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

        # Signal connections
        self.ctrl.azimuthUpdated.connect(self.update_az_pos)
        self.ctrl.azimuthCommanded.connect(self.update_az_cmd)
        self.ctrl.azimuthVelocityChanged.connect(self.update_az_vel)
        self.ctrl.zenithUpdated.connect(self.update_ze_pos)
        self.ctrl.zenithCommanded.connect(self.update_ze_cmd)
        self.ctrl.zenithVelocityChanged.connect(self.update_ze_vel)

    def stop_motion(self):
        self.ctrl.run = False
        self.ctrl.set_ao_zero()
    
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
    
    def toggle_steering(self):
        if self.manual_controlcheckBox.isChecked():
            self.controller.setEnabled(True)
        else:
            self.controller.setEnabled(False)
    
    def steer(self, btn: QAbstractButton): 
        self.ctrl.run = True
        match btn:
            case self.controller.up_toolButton:
                self.ctrl.set_ao_value(-self.ze_jog_voltage, ZE_OUT_CHANNEL)
            case self.controller.down_toolButton:
                self.ctrl.set_ao_value(self.ze_jog_voltage, ZE_OUT_CHANNEL)
            case self.controller.left_toolButton:
                self.ctrl.set_ao_value(self.az_jog_voltage, AZ_OUT_CHANNEL)
            case self.controller.right_toolButton:
                self.ctrl.set_ao_value(-self.az_jog_voltage, AZ_OUT_CHANNEL)


    def set_az_pos(self):
        new_pos = float(self.azimuth_setlineEdit.text())
        self.ctrl.set_az_pos(new_pos)
    
    def set_ze_pos(self):
        new_pos = float(self.zenith_setlineEdit.text())
        self.ctrl.set_ze_pos(new_pos)
    
    @Slot(float)
    def update_az_pos(self, new_pos: float):
        self.azimuth_actual_valLabel.setText(f'{new_pos:.3f}°')
    
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
        new_az = self.ctrl.get_ser_az_pos()
        new_ze = self.ctrl.get_ser_ze_pos()
        az_velocity = (new_az - self.last_az) / self.interval * 1000
        ze_velocity = (new_ze - self.last_ze) / self.interval * 1000
        self.update_az_pos(new_az)
        self.update_ze_pos(new_ze)
        self.last_az = new_az
        self.last_ze = new_ze
        self.update_az_vel(az_velocity)
        self.update_ze_vel(ze_velocity)
        az_err = new_az - self.last_az_commanded
        ze_err = new_ze - self.last_ze_commanded
        self.update_az_err(az_err)
        self.update_ze_err(ze_err)
    
    def closeEvent(self, event):
        self.timer.stop()
        self.ctrl.close()
        return super().closeEvent(event)
    


if __name__ == '__main__':
    app = QApplication()

    tel = TelescopeControlWidget()
    win = QMainWindow()
    win.setCentralWidget(tel)
    win.show()
    app.exec()
