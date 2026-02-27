from __future__ import annotations

import logging
import signal

import pdb
import time
from multiprocessing.connection import Connection
from multiprocessing import Queue
import queue
import sys
import threading
from threading import Thread
from time import sleep
try:
    import thread
except ImportError:
    import _thread as thread
from pathlib import Path

import h5py
import numpy as np
import serial
import serial.tools.list_ports
import uldaq as ul
# from Exscript.protocols.telnetlib import Telnet
from telnetlib3.telnetlib import Telnet

from rfsocinterface.core.utils import analog_to_digital, PERMISSIONS_USR_RW

_logger = logging.getLogger(__name__)
_tele_logger = logging.getLogger('rfsocinterface.telescopeControl')


ZEPORT = 23
AKD1 = "169.254.250.165"
AKD2 = "169.254.250.166"  ##switches back and forth between these two channels when faults occur.
TIMEOUT = 2
BAUDRATE = 38400
ADDR_FB1_P = 1610  ##This is the absolute position from the FB1 (resolver).
ADDR_PL_FB = 588  ##This is the position loop feedback. Includes some offset parameter and error based on homing position. Appropriate for this application, though I need to figure out the resolution.
GEAR_RATIO = 258

AZ_OUT_CHANNEL = 1
ZE_OUT_CHANNEL = 0

ZERO_DATA = analog_to_digital(0, -10, 10, 16)

AZ_SAMPLING_TIME = 0.002


AZ_BASE_SPEED = 1.5
AZ_POS_TOL_DEG = .02
AZ_HOME = 0
ZE_BASE_SPEED = 0.4
ZE_POS_TOL_DEG = .01
ZE_DEAFULT_RPM_PER_VOLT = 40
ZE_SCAN_RPM_PER_VOLT = 4

SPEED_MULTIPLIER = 0.35
FAR_APPROACH_SEPARATION_DEG = 15
ZE_APPROACH_SEPARATION_DEG = 0.5

NEG_SW_LIM = -181.000
POS_SW_LIM = 181.000
NEG_ZE_SW_LIM = -np.inf
POS_ZE_SW_LIM = -np.inf  # TODO: Is this supposed to be negative?


def quit_function():
    thread.interrupt_main() # raises KeyboardInterrupt


def exit_after(timeout: int):
    '''
    use as decorator to exit process if 
    function takes longer than s seconds
    '''
    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(timeout, quit_function, args=[fn.__name__, *args], kwargs=kwargs)
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result
        return inner
    return outer


class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self, connection: Connection):
        self._initialized = False
        self._run = False
        self.connection = connection
        self._active_jobs: list[Thread] = []
        self.test_init()
        _tele_logger.debug(f'Result of TelescopeMotorController initialization: {self._initialized}')
        self._listener_loop()
    
    
    def send(self, command: str, *args, timeout: float=None):
        """Send a command to the telescope client"""
        if timeout:
            timer = threading.Timer(
                timeout,
                quit_function,
            )
            timer.start()
            try:
                self.connection.send([command, *args])
                _tele_logger.debug(f'CONTROLLER sent command "{command}" with data {args}')
            except KeyboardInterrupt:
                _tele_logger.error(f'Timed out sending command "{command}"')
            finally:
                timer.cancel()
        else:
            self.connection.send([command, *args])
            _tele_logger.debug(f'CONTROLLER sent command "{command}" with data {args}')

    def _listener_loop(self):
        if not self._initialized:
            return
        while True:
            try:
                command, *args = self.connection.recv()
                _tele_logger.debug(f'CONTROLLER received command: "{command}", args: {args}')
                match command.lower():
                    case 'get_ser_az_pos':
                        self.get_ser_az_pos()
                    case 'set_az_pos':
                        self.set_az_pos(*args)
                    case 'get_ser_ze_pos':
                        self.get_ser_ze_pos()
                    case 'set_ze_pos':
                        self.set_ze_pos(*args)
                    case 'set_voltage':
                        self._run = True
                        self.set_ao_value(*args)
                    case 'set_az_speed_relation':
                        self.set_az_speed_relation(*args)
                    case 'set_ze_speed_relation':
                        self.set_ze_speed_relation(*args)
                    case 'az_scan_mode':
                        self.az_scan_mode(*args)
                    case 'dither_pattern':
                        self.dither_pattern(*args)
                    case 'stop_telescope':
                        self._run = False
                        self.set_ao_zero()
                    case 'terminate':
                        self.close()
                        break
                    case _:
                        self.send('err', 'NON-CRITICAL', f'Unknown command "{command}" received.')
            except queue.Empty:
                continue

    def test_init(self):
        if not self._initialized:
            self._initialize_system()

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
        except ul.ul_exception.ULException as e:
            msg = f'Error encounterd when attempting to connect to device: {e.error_message}'
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return
        except OSError as e:
            msg = 'DAQ could not be initialized; Check comport and power supply'
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return

        # Init serial communication with S700 for high res positioning of AZ monitors
        comports = serial.tools.list_ports.comports()
        for dev in comports:
            # port_array[dev] = str(ports[dev].manufacturer)
            # _tele_logger.debug('dev #: ', dev)
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
            # _logger.debug('AZ motor connected to original port')
            _tele_logger.debug('AZ motor connected to original port')
        else:
            # _logger.error('Could not communicate with AZ controller. System could not initialize.')
            msg = 'Could not communicate with AZ controller. System could not initialize.'
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return

        # Initialize AZ values
        self.ser_az = ser_az
        self.az_pos = self.az_pps_pos = 0
        self.get_ser_az_pos()
        _tele_logger.info(f'Telescope AZ position is: {self.az_pos}')

        # Zenith Angle
        try:
            self.ser_ze = Telnet(host=AKD1, port=ZEPORT)
            self.ser_ze.open(host=AKD1, port=ZEPORT)
        except OSError as e:
            msg = 'Could not communicate with ZA controller. System could not initialize.'
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return

        status_string = self.write_ser_ze('DRV.ACTIVE', timeout=0.1)
        status = float(status_string.split('\r')[0])
        if status == 1:
            _tele_logger.debug('ZA motor connected and software already enabled.')
        else:
            sw_en = self.write_ser_ze('DRV.EN', timeout=0.1)
            _tele_logger.debug('ZA motor connected and software enabled by Python.')

        # Allow continuous reading of last ZE position synced with PPS
        self.write_ser_ze('DIN1.FILTER 0', timeout=0.1)

        self.write_ser_ze('CAP0.EVENT', timeout=0.1)
        self.write_ser_ze('CAP0.TRIGGER 1', timeout=0.1)
        self.write_ser_ze('CAP0.EDGE 1', timeout=0.1)
        self.write_ser_ze('CAP0.MODE 0', timeout=0.1)
        self.write_ser_ze('CAP0.EN 1', timeout=0.1)

        # Initialize ZE values
        self.ze_pos = self.ze_pps_pos = 0
        self.get_ser_ze_pos(timeout=0.1)
        _tele_logger.info(f'Telescope ZA position is: {self.ze_pos}')
        self._initialized = True

    def write_ser_az(self, command: str | bytes, stop: str=b'\r\n', timeout: float=None) -> str:
        """Write a command to the azimuth motor.
        
        Possible commands include:
            COLDSTART: Cold restart.
            DIS: Disable the motor.
            EN: Enable the motor. Need to run SAVE and COLDSTART before enabling.
            EXTLATCH <source>: Define the source for the position information using 
                the latch functions. 0 = PFB for both, 1 = PFB0 for digital input 1 
                and PFB for input 2.
            IN1MODE <mode>: Assign the position to the latch. 
                Mode 26 = "Hardware Capture / Latch"
            IN1TRIG (0|1): Set the trigger for the latch to the rising / falling edge.
            LATCH1P32: Get the current latched position.
            NREF: ...
            PFB: Get the current position of the motor in degrees * 1e4.
            PFB0: Get the current position of the motor in raw encoder units.
            SAVE: Save the current configuration.
            VSCALE1 <speed>: Set the speed of the motor in RPM/10V.
        """
        if timeout is not None:
            self.ser_az.timeout = timeout

        data = command
        if not isinstance(data, bytes):
            if command[-2:] != '\r\n':
                data = data + '\r\n'
            data = data.encode()

        start_time = time.time()
        self.ser_az.write(data)
        self.ser_az.readline()
        status = self.ser_az.read_until(stop).decode()  # Empty buffer
        elapsed = time.time() - start_time
        _tele_logger.debug(f'AZ Command {repr(data)} returned result {repr(status)} in {elapsed*1e3:.2f} ms')
        self.ser_az.reset_input_buffer()
        self.ser_az.reset_output_buffer()
        return status
    
    def write_ser_ze(self, command: str | bytes, stop: str=b'\r\n', timeout: float=None) -> str:
        """Write a command to the zenith angle motor.
        
        Possible commands include:
            AIN.VSCALE <speed>: Set the speed of the motor in RPM/V.
            CAP0.EDGE (0|1): Set to trigger on the falling/rising edge of the pulse. Set
                during initialization.
            CAP0.EN (0|1): Reset the latch of the specified channel.
            CAP0.EVENT: ...
            CAP0.MODE (0|1): Indicates digital latch. Should be set to 0 at initialization.
            CAP0.PLFB: Get the position of the motor at the last pulse in degrees.
            CAP0.STATE: Whether it has been latched (1) or not (0).
            CAP0.TRIGGER (0|1): Set digital input channel. Set to 1 during initializaiton.
            DIN1.FILTER (0|1): Disable/enable the filter.
            DRV.ACTIVE: Check whether the motor is engaged (0 or 1).
            DRV.DIS: Disable the motor.
            DRV.EN: Enable the motor.
            FB1.OFFSET:
            PL.FB: Get the current position of the motor in degrees.
        """
        data = command
        if not isinstance(data, bytes):
            if command[-2:] != '\r\n':
                data = data + '\r\n'
            data = data.encode()
        start_time = time.time()
        self.ser_ze.write(data)
        status = self.ser_ze.read_until(stop, timeout).decode()  # Empty buffer
        elapsed = time.time() - start_time
        _tele_logger.debug(f'ZA Command {repr(data)} returned result {repr(status)} in {elapsed*1e3:.2f} ms')
        return status
    
    def close(self):
        self._run = False
        self.set_ao_zero()
        for job in self._active_jobs:
            job.join()
        self.ser_az.close()
        self.ser_ze.close()
        self.send('done')

    def set_ao_value(self, data: float, channel: int):
        self.ao_device.a_out(channel, self.ul_range_out, self.ao_flags, data)
        _tele_logger.debug(f'Set ao value for channel {channel} to {data}')

    def set_ao_zero(self):
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)
        _tele_logger.debug('Set voltages to zero.')

    # Azimuth settings
    def set_az_home(self):
        if self.ser_az.is_open:
            pfb = self.write_ser_az('NREF')
            _logger.info("Home Set.")
        else:
            _tele_logger.error("Home command not executed. Check connection with S700")

    # TODO: There's also a "setAZ_home_position"...

    ##Read AZ Serial Position

    def get_ser_az_pos(self, timeout: float=0.1) -> tuple[float, float]:
        # Get old values as a fallback
        old_pos = self.az_pos
        old_pps_pos = self.az_pps_pos

        # Make sure the connection is still open
        if not self.ser_az.is_open:
            msg = 'AZ serial connection is not open; Check connection.'
            self.send('err', 'CRITICAL', msg)
            return old_pos, old_pps_pos
        
        # Try getting the AZ position
        try:
            new_pos_str = self.write_ser_az('PFB', timeout=timeout / 2)
            new_pos = float(new_pos_str) / 10000.0
        except ValueError:
            # Couldn't convert the string to a float
            msg = 'Error communicating with AZ controller; ' \
                f'position set to most recent read ({old_pos:.2f})'
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pos = old_pos

        # Try getting the PPS position
        try:
            new_pps_pos_str = self.write_ser_az('LATCH1P32', timeout=timeout / 2)
            new_pps_pos = float(new_pps_pos_str) / 10000.0
        except ValueError:
            msg = 'Error communicating with AZ controller; when attempting to get PPS position' \
                f'PPS position set to most recent read ({old_pps_pos:.2f})',
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pps_pos = old_pps_pos

        self.az_pos = new_pos
        self.az_pps_pos = new_pps_pos

        if self._initialized:
            self.send('az_pos', new_pos, new_pps_pos, timeout=timeout)
        return new_pos, new_pps_pos

    def set_az_pos(self, new_pos: int, scan_mode: bool=False, stop_run: bool=True):
        self._run = True
        worker_thread = Thread(target=self._set_az_pos, args=(new_pos, scan_mode, stop_run))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_az_pos(self, new_pos: int, scan_mode: bool=False, stop_run: bool=True, speed_factor: float=1.):
        self.send('az_pos_comm', new_pos, timeout=0.25)
        # I want to accept a number in degrees, but put the number in the integer value desired by S700 controller
        # AZ controlled by 2 motors, the first to actually move the telescope, the second to put some tension on the gear for avoiding any backlash. Currently the secondary motor is disabled, probably providing little to no torque, but given the huge gearing ratio, it probably helps with backlash. The next easiest technique would be to run the secondary in "analog torque" mode, setting the zero value to some small torque. This could be improved by increasing the torque during motion and reducing when the first motor is not moving (probably by changing the zero value torque, since both analog outs are already in use). The proper way to do it, and the reason we were sold these S700 controllers is called RDP per the kollmorgen tech guy but my guess is he meant prd cogging mode.
        self.set_ao_zero()
        # Measure input voltage

        ##confirm position
        az_pos, az_pps_pos = self.get_ser_az_pos()
        if scan_mode:
            za_pos, za_pps_pos = self.get_ser_ze_pos()
            position_data = []
        counter = 0
        ##Run loop
        pfb_time = time.time()

        while (
            np.abs(az_pos - new_pos) > AZ_POS_TOL_DEG
            and az_pos > NEG_SW_LIM
            and az_pos < POS_SW_LIM
            and self._run
        ):
            try:
                if new_pos > az_pos:
                    direction = -1
                else:
                    direction = 1
                # Set speed faster if more travel needed
                if scan_mode:
                    if abs(az_pos - new_pos) > 0.5:
                        # If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(6.0 * speed_factor, -10, 10, 16)
                    else:
                        data_value = direction * analog_to_digital(2.0 * speed_factor, -10, 10, 16)
                elif abs(az_pos - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                else:
                    this_speed = SPEED_MULTIPLIER * abs(az_pos - new_pos) + AZ_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                if counter % 50 == 0:
                    _tele_logger.debug(f'AZ pos: {az_pos}; voltage: {data_value}')
                self.set_ao_value(data_value, AZ_OUT_CHANNEL)
                this_dt = time.time() - pfb_time
                while this_dt < AZ_SAMPLING_TIME:
                   this_dt = time.time() - pfb_time
                   time.sleep(1.e-4)
                pfb_time = time.time()
                az_pos, az_pps_pos = self.get_ser_az_pos()
                if np.abs(az_pos - new_pos) <= AZ_POS_TOL_DEG:
                    self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
                # self.azimuthUpdated.emit(pfb)
                # self.conn.send(['az_pos', pfb])

                if scan_mode:
                    position_data = np.append(position_data, [az_pos, za_pos, pfb_time, az_pps_pos, za_pps_pos])

                counter = counter + 1

            except KeyboardInterrupt:
                _tele_logger.info("User terminated motion!")
                break

            except ValueError:
                _tele_logger.error("Caught an exception regarding Float conversion")
                break
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        if stop_run:
            self._run = False
        ## Read position again
        # time.sleep(1)
        az_pos, _ = self.get_ser_az_pos()
        _tele_logger.debug(f'Finished setting az_pos to {new_pos}. Actual={az_pos}, Error={az_pos - new_pos:.5f}')
        if scan_mode:
            return position_data

    def az_scan_mode(
            self,
            file: str,
            az_start: float,  # relative to current positions
            az_stop: float,
            n_repeats: int=1,
            ze_dither: float=0.04,
            position_return: bool=True,
            large_map_mode: bool=False,
    ):
        self._run = True
        worker_thread = Thread(target=self._az_scan_mode, args=(file, az_start, az_stop, n_repeats, ze_dither, position_return, large_map_mode))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _az_scan_mode(
            self,
            file: str,
            az_start: float,
            az_stop: float,
            n_repeats: int=2,
            ze_dither: float=0.04,
            position_return: bool=True,
            large_map_mode: bool=False,
    ):
        """Dither the telescope...
        
        Arguments:
            large_map_mode (bool): If True, the telescoep will continue to step in ZE in
                the same direction between each dither, to create a larger map in the ZE
                direction. Defaults to False.
        
        """
        az_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        az_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        initial_az, _ = self.get_ser_az_pos()
        initial_ze, _ = self.get_ser_ze_pos()
        az_start += initial_az
        az_stop += initial_az

        # Set start position in current thread
        _tele_logger.info(f'Moving telescope to initial position')
        self.send('az_scan_mode_label', 'Running AZ Scan Mode\nMoving telescope to initial position')
        self._set_az_pos(az_start - az_start_buffer, stop_run=False)
        self.set_ze_speed_relation(ZE_SCAN_RPM_PER_VOLT)

        speed_factor = 1/3 if large_map_mode else 1.

        self.send('az_scan_mode_maximum', n_repeats)
        start_time = time.time()
        rep_times = []
        for i_rep in np.arange(n_repeats):
            rep_start_time = time.time()
            _tele_logger.info(f'AZ Scan Mode: Starting repeat {i_rep + 1} of {n_repeats}')
            label_text = \
                f'Running AZ Scan Mode\n' \
                f'Repeat {i_rep + 1} / {n_repeats}'
            if len(rep_times) > 0:
                label_text += f'\nEstimated time remaining: {np.mean(rep_times) * (n_repeats - i_rep):.2f} s'
            self.send(
                'az_scan_mode_label',
                label_text
            )
            if not self._run:
                break
            if large_map_mode:
                new_ze = initial_ze + (i_rep - (n_repeats - 1) / 2) * ze_dither
            else:
                new_ze = initial_ze + (i_rep % 2) * ze_dither
            self._set_ze_pos(new_ze, stop_run=False, primary_scan_direction='az')


            if np.mod(i_rep, 2) == 0:
                this_position_data = self._set_az_pos(
                    az_stop + az_end_buffer + 0.5, scan_mode=True, stop_run=False, speed_factor=speed_factor,
                )
                if i_rep == 0:
                    position_data = this_position_data
                else:
                    position_data = np.append(position_data, this_position_data)
            if np.mod(i_rep, 2) == 1:
                this_position_data = self._set_az_pos(
                    az_start - az_start_buffer - 0.5, scan_mode=True, stop_run=False, speed_factor=speed_factor,
                )
                position_data = np.append(position_data, this_position_data)
            rep_end_time = time.time()
            elapsed_time = rep_end_time - rep_start_time
            rep_times.append(elapsed_time)
            self.send('az_scan_mode_progress', i_rep + 1)
            _tele_logger.info(f'AZ Scan Mode: Finished repeat {i_rep + 1} in {elapsed_time:.3f}s')
            _tele_logger.info(f'AZ Scan Mode: Average time per repetition is {np.mean(rep_times):.3f}s')

        stop_time = time.time()
        _logger.info(f'AZ Scan Mode: Finished {n_repeats} repeats in {stop_time - start_time:.3f}s')

        # self._run is only changed if the telescope was stopped mid scan
        # Don't save the telescope data in that case
        if not self._run:
            _tele_logger.info("AZ Scan Mode canceled before completion.")
            self.send('az_scan_mode_complete', 1)
            self.set_ze_speed_relation(ZE_DEAFULT_RPM_PER_VOLT)
            if position_return:
                _tele_logger.info('Canceling AZ Scan Mode\nResetting telescope position...')
                self.send('az_scan_mode_label', 'Resetting telescope position')
                self._set_az_pos(initial_az, stop_run=False)
                self._set_ze_pos(initial_ze, stop_run=False, primary_scan_direction='az')
            return
        
        path = Path(file)
        with h5py.File(path, 'w') as f:
            f.create_dataset("az_tel", data=position_data[0::5])
            f.create_dataset("za_tel", data=position_data[1::5])
            f.create_dataset("timestamp_tel", data=position_data[2::5])
            f.create_dataset('az_pps', data=position_data[3::5])
            f.create_dataset('za_pps', data=position_data[4::5])
            f.create_dataset("optical_visibility", data=['****'])
        path.chmod(PERMISSIONS_USR_RW)
        self.set_ze_speed_relation(ZE_DEAFULT_RPM_PER_VOLT)
        if position_return:
            _tele_logger.info('AZ Scan Mode: Resetting telescope position...')
            self.send('az_scan_mode_label', 'Running AZ Scan Mode\nResetting telescope position')
            self._set_az_pos(initial_az, stop_run=False)
            self._set_ze_pos(initial_ze, stop_run=False, primary_scan_direction='az')

        self._run = False
        _tele_logger.info("Scan Complete")
        self.send('az_scan_mode_complete', 0)

    def jog_az_pos(self, speed: float=1):
        raise NotImplementedError("Jogging not implemented yet.")

    def az_oscillate(self, total_t: float, freq: float, deg: float):
        raise NotImplementedError("Oscillation not implemented yet.")

    def set_az_speed_relation(self, rpm_per_ten_volt: float):
        # Set the speed of the motor in RPM/10V. Default is 500, which would roughly turn the telescope 2.5 degree/second for 10 V input. ASCII code for serial is VSCALE1. AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT! Needs more testing from Ubuntu, I think there is a lower limit set in the S700.
        if self.ser_az.is_open:
            command = "VSCALE1 " + str(rpm_per_ten_volt) + "\r\n"
            command = command.encode()
            az_speed = self.write_ser_az(command)
            _logger.info(f'AZ speed relation set to: {rpm_per_ten_volt * 10} RPM / V')

    # Zenith angle settings
    def set_ze_home(self):
        # Set current position of the motor to zero.
        pos, _ = self.get_ser_ze_pos()
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
        _logger.info("EL Home Set.")

    def get_ser_ze_pos(self, timeout: float=0.1) -> tuple[float, float]:
        # Get old values as a fallback
        old_pos = self.ze_pos
        old_pps_pos = self.ze_pps_pos

        # Query the values from the motor
        pos_str = self.write_ser_ze('PL.FB', timeout=timeout / 3)
        state_str = self.write_ser_ze('CAP0.STATE', timeout=timeout / 3)
        state = float(state_str.split(' ')[0].split('>')[-1])
        if state == 1:
            # It's been latched so get the position and reset the latch
            pps_pos_str = self.write_ser_ze('CAP0.PLFB', timeout=timeout / 3)
            self.write_ser_ze('CAP0.EN 1', timeout=timeout / 3)
        else:
            new_pps_pos = old_pps_pos

        # Try to get the ZA position
        try:
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            new_pos = pos
        except ValueError:
            # Couldn't convert the string to a float
            msg = 'Error communicating with ZA controller; ' \
                f'position set to most recent read ({old_pos:.2f})'
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pos = old_pos

        # Check that the PPS position is accesible
        if state == 1:
            pps_split_string = pps_pos_str.split(' ')[0].split('>')
            if len(pps_split_string[-1]) == 0:
                # Not receiving pulse
                msg = 'Attempted to access PPS position from ZA controller; No pulse detected; ' \
                f'PPS position set to most recent read ({old_pps_pos:.2f})',
                _tele_logger.warning(msg)
                self.send('err', 'NON-CRITICAL', msg)
                new_pps_pos = old_pps_pos
            else:
                new_pps_pos = float(pps_split_string[-1])
  
        self.ze_pos = new_pos
        self.ze_pps_pos = new_pps_pos

        if self._initialized:
            # _tele_logger.debug(f'Sending ze_pos to GUI')
            self.send('ze_pos', new_pos, new_pps_pos, timeout=timeout)
        return new_pos, new_pps_pos

    def set_ze_pos(self, new_pos: float, scan_mode: bool=False, stop_run: bool=True, primary_scan_direction: str='ze'):
        # self.zenithCommanded.emit(new_pos)
        self._run = True
        worker_thread = Thread(target=self._set_ze_pos, args=(new_pos, scan_mode, stop_run, primary_scan_direction))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_ze_pos(self, new_pos: float, scan_mode: bool=False, stop_run: bool=True, primary_scan_direction: str='za'):
        self.send('ze_pos_comm', new_pos, timeout=0.25)
        # new_pos = float(new_pos)
        self.set_ao_zero()

        # confirm position
        za_pos, _ = self.get_ser_ze_pos()
        # self.conn.send(['ze_pos', pos])
        if scan_mode:
            az_pos, az_pps_pos = self.get_ser_az_pos()
            position_data = []
        if scan_mode and primary_scan_direction.lower() == 'za':
            tolerance = ZE_POS_TOL_DEG * 5
        else:
            tolerance = ZE_POS_TOL_DEG
        counter = 0

        # Run loop
        _tele_logger.debug(f'Zenith Angle - Pos: {za_pos}, New pos: {new_pos}, tolerance: {tolerance}, diff: {za_pos - new_pos}')
        # start_time = time.time()
        # profiler = cProfile.Profile()
        # profiler.enable()
        while abs(za_pos - new_pos) > tolerance and self._run:
            _tele_logger.debug(f'Starting ZE loop #{counter}')
            try:
                # Choose direction of motion
                if za_pos > new_pos:
                    direction = -1
                else:
                    direction = 1

                if scan_mode:
                    data_value = direction * analog_to_digital(1.0, -10, 10, 16)
                elif abs(za_pos - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                elif abs(za_pos - new_pos) > ZE_APPROACH_SEPARATION_DEG:
                    # If we are semifar from the setpoint, start slowing down
                    this_speed = SPEED_MULTIPLIER * abs(za_pos - new_pos) + ZE_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)
                else:
                    # If we are close to the setpoint, slow down a lot
                    this_speed = SPEED_MULTIPLIER * abs(za_pos - new_pos)**2 \
                        / ZE_APPROACH_SEPARATION_DEG + ZE_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                self.set_ao_value(data_value, ZE_OUT_CHANNEL)
                _tele_logger.debug('Getting ser ze pos')
                za_pos, za_pps_pos = self.get_ser_ze_pos()
                if abs(za_pos - new_pos) <= tolerance:
                    self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)
                # self.conn.send(['ze_pos', pos])
                if scan_mode:
                    _tele_logger.debug('appending scan mode position data')
                    position_data = np.append(
                        position_data, [az_pos, za_pos, time.time(), az_pps_pos, za_pps_pos]
                    )
                counter = counter + 1
                if counter % 500 == 0:
                    _tele_logger.debug(f'ZA pos: {za_pos}l; voltage: {data_value}')
            except KeyboardInterrupt:
                _tele_logger.info("User terminated motion!")
                break
            except ValueError:
                _tele_logger.error("caught an exception regarding Float conversion")
                break
            finally:
                # This code always executes after leaving the try statement
                pass

        if stop_run:
            self._run = False
        self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)
        # stop_time = time.time()
        # print(f'Average time per loop: {(stop_time - start_time) / counter}')
        # profiler.disable()
        # profiler.print_stats()
        # self.zenithVelocityChanged.emit(0)
        ## Read position again
        # time.sleep(0.1)
        za_pos, _ = self.get_ser_ze_pos()
        _tele_logger.debug(f'Finished setting ze_pos to {new_pos}. Actual={za_pos}, Error={za_pos - new_pos:.5f}')
        if scan_mode:
            return position_data
        
    def dither_pattern(
        self,
        file: str,
        primary_start: float,  # relative to current positions
        primary_stop: float,
        n_repeats: int=1,
        secondary_dither: float=0.04,
        position_return: bool=True,
        large_map_mode: bool=False,
        primary_dither_direction: str='az',
    ):
        """Dither the telescope along the specified direction.

        Arguments:
            primary_start (float): Starting location relative to current position in deg.
            primary_stop (float): Ending location relative to current position in deg.
            primary_dither_direction (str): Which direction is the pimary direction (must be 'az' or 'za')
        """
        self._run = True
        worker_thread = Thread(
            target=self._dither_pattern,
            args=(
                file,
                primary_start,
                primary_stop,
                n_repeats,
                secondary_dither,
                position_return,
                large_map_mode,
                primary_dither_direction,))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _dither_pattern(
            self,
            file: str,
            primary_start: float,
            primary_stop: float,
            n_repeats: int=2,
            secondary_dither: float=0.04,
            position_return: bool=True,
            large_map_mode: bool=False,
            primary_dither_direction: str='az',
    ):
        """Dither the telescope...
        
        Arguments:
            large_map_mode (bool): If True, the telescoep will continue to step in ZE in
                the same direction between each dither, to create a larger map in the ZE
                direction. Defaults to False.
        
        """
        if primary_dither_direction not in ['az', 'za']:
            # TODO: Handle error
            pass
        primary_az = primary_dither_direction.lower() == 'az'
        primary_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        primary_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        initial_az, _ = self.get_ser_az_pos()
        initial_ze, _ = self.get_ser_ze_pos()
        if primary_az:
            primary_start += initial_az
            primary_stop += initial_az
        else:
            primary_start += initial_ze
            primary_stop += initial_ze

        # Set start position in current thread
        _tele_logger.info(f'Moving telescope to initial position')
        self.send('dither_pattern_label', 'Running Dither Pattern\nMoving telescope to initial position')
        if primary_az:
            self._set_az_pos(primary_start - primary_start_buffer, stop_run=False)
        else:
            self._set_ze_pos(primary_start - primary_start_buffer, stop_run=False)

        if primary_az:
            self.set_ze_speed_relation(ZE_SCAN_RPM_PER_VOLT)


        az_speed_factor = 1/3 if large_map_mode else 1.

        self.send('dither_pattern_maximum', n_repeats)
        start_time = time.time()
        rep_times = []
        for i_rep in np.arange(n_repeats):
            rep_start_time = time.time()
            _tele_logger.info(f'Dither Pattern: Starting repeat {i_rep + 1} of {n_repeats} ---------------------------------------------')
            label_text = \
                f'Running Dither Pattern\n' \
                f'Repeat {i_rep + 1} / {n_repeats}'
            if len(rep_times) > 0:
                label_text += f'\nEstimated time remaining: {np.mean(rep_times) * (n_repeats - i_rep):.2f} s'
            self.send(
                'dither_pattern_label',
                label_text
            )
            if not self._run:
                break
            if large_map_mode:
                new_ze = initial_ze + (i_rep - (n_repeats - 1) / 2) * secondary_dither
                self._set_ze_pos(new_ze, stop_run=False)
            else:
                if primary_az:
                    new_ze = initial_ze + (i_rep % 2) * secondary_dither
                    self._set_ze_pos(new_ze, stop_run=False)
                else:
                    new_az = initial_az + (i_rep % 2) * secondary_dither
                    self._set_az_pos(new_az, stop_run=False)


            if np.mod(i_rep, 2) == 0:
                if primary_az:
                    this_position_data = self._set_az_pos(
                        primary_stop + primary_end_buffer + 0.5, scan_mode=True, stop_run=False, speed_factor=az_speed_factor,
                    )
                else:
                    this_position_data = self._set_ze_pos(
                        primary_stop + primary_end_buffer + 0.5, scan_mode=True, stop_run=False,
                        primary_scan_direction=primary_dither_direction,
                    )
                if i_rep == 0:
                    position_data = this_position_data
                else:
                    position_data = np.append(position_data, this_position_data)
            if np.mod(i_rep, 2) == 1:
                if primary_az:
                    this_position_data = self._set_az_pos(
                        primary_start - primary_start_buffer - 0.5, scan_mode=True, stop_run=False, speed_factor=az_speed_factor,
                    )
                else:
                    this_position_data = self._set_ze_pos(
                        primary_start - primary_start_buffer - 0.5, scan_mode=True, stop_run=False,
                        primary_scan_direction=primary_dither_direction,
                    )
                position_data = np.append(position_data, this_position_data)
            rep_end_time = time.time()
            elapsed_time = rep_end_time - rep_start_time
            rep_times.append(elapsed_time)
            self.send('dither_pattern_progress', i_rep + 1)
            _tele_logger.info(f'Dither Pattern: Finished repeat {i_rep + 1} in {elapsed_time:.3f}s')
            _tele_logger.info(f'Dither Pattern: Average time per repetition is {np.mean(rep_times):.3f}s')

        stop_time = time.time()
        _logger.info(f'Dither Pattern: Finished {n_repeats} repeats in {stop_time - start_time:.3f}s')

        # self._run is only changed if the telescope was stopped mid scan
        # Don't save the telescope data in that case
        if not self._run:
            _tele_logger.info("Dither Pattern canceled before completion.")
            if primary_az:
                self.set_ze_speed_relation(ZE_DEAFULT_RPM_PER_VOLT)
            if position_return:
                _tele_logger.info('Canceling Dither Pattern\nResetting telescope position...')
                self.send('dither_pattern_label', 'Resetting telescope position')
                self._set_az_pos(initial_az, stop_run=False)
                self._set_ze_pos(initial_ze, stop_run=False)
            self.send('dither_pattern_complete', 1)
            return
        
        path = Path(file)
        with h5py.File(path, 'w') as f:
            f.create_dataset("az_tel", data=position_data[0::5])
            f.create_dataset("za_tel", data=position_data[1::5])
            f.create_dataset("timestamp_tel", data=position_data[2::5])
            f.create_dataset('az_pps', data=position_data[3::5])
            f.create_dataset('za_pps', data=position_data[4::5])
            f.create_dataset("optical_visibility", data=['****'])
        path.chmod(PERMISSIONS_USR_RW)
        if primary_az:
            self.set_ze_speed_relation(ZE_DEAFULT_RPM_PER_VOLT)
        if position_return:
            _tele_logger.info('Dither Pattern: Resetting telescope position...')
            self.send('dither_pattern_label', 'Running Dither Pattern\nResetting telescope position')
            self._set_az_pos(initial_az, stop_run=False)
            self._set_ze_pos(initial_ze, stop_run=False)

        self._run = False
        _tele_logger.info("Scan Complete")
        self.send('dither_pattern_complete', 0)

    def set_ze_speed_relation(self, rpm_per_volt: float):
        # Set the speed of the motor in RPM/1V. Default is 40, which would roughly turn the telescope 1 degree/second. ASCII code for serial is AIN.VSCALE. NOTE: AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT!
        if self._initialized:
            command = "AIN.VSCALE " + str(rpm_per_volt) + "\r\n"
            command = command.encode('ASCII')
            self.ser_ze.write(command)
            ze_speed = self.ser_ze.read_until(b'\r\n', 0.1).decode()
            _logger.info(f'ZA speed relation set to: {rpm_per_volt} RPM / V')

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
            _tele_logger.debug(response)
            self.ser_az.reset_input_buffer()
            self.ser_az.reset_output_buffer()


def make_controller(connection: Connection) -> TelescopeMotorController:
    return TelescopeMotorController(connection)

if __name__ == '__main__':
    try:
        # Connect to device
        descriptor = ul.get_daq_device_inventory(ul.InterfaceType.ANY)[0]
        device = ul.DaqDevice(descriptor)
        device.connect()
        device = device

        # Configure analog outputs
        ao_device = device.get_ao_device()
        sul_range_out = ao_device.get_info().get_ranges()[0]
        ao_flags = ul.AOutFlag.DEFAULT

        # Set output to zero
        # self.set_ao_zero()
    except ul.ul_exception.ULException as e:
        msg = f'Error encounterd when attempting to connect to device: {e.error_message}'
        _tele_logger.critical(msg, exc_info=True)
        # self.send('err', 'CRITICAL', msg)
        # self.send('done')
        exit(1)
    except OSError as e:
        msg = 'DAQ could not be initialized; Check comport and power supply'
        _tele_logger.critical(msg, exc_info=True)
        # self.send('err', 'CRITICAL', msg)
        # self.send('done')
        exit(1)

    # Init serial communication with S700 for high res positioning of AZ monitors
    comports = serial.tools.list_ports.comports()
    for dev in comports:
        # port_array[dev] = str(ports[dev].manufacturer)
        # _tele_logger.debug('dev #: ', dev)
        if dev.manufacturer == "Prolific Technology Inc.":
            az_port = dev.device
    print(az_port)
    # ser_az = serial.Serial(
    #     az_port,
    #     baudrate=BAUDRATE,
    #     timeout=TIMEOUT,
    #     bytesize=8,
    #     parity='N',
    #     stopbits=1,
    # )