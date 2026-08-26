"""Code for controlling a telescope in a parralel process."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Thread
from typing import Literal

import h5py
import numpy as np
import serial
import serial.tools.list_ports
import uldaq as ul

# from Exscript.protocols.telnetlib import Telnet
from telnetlib3.telnetlib import Telnet

from rfsocinterface.core.utils import (
    PERMISSIONS_ALL_FULL,
    analog_to_digital,
    quit_function,
)

_logger = logging.getLogger(__name__)
_tele_logger = logging.getLogger('rfsocinterface.telescopeControl')


ZA_PORT = 23

# ZA motor switches back and forth between these two channels when faults occur.
AKD1 = '169.254.250.165'
AKD2 = '169.254.250.166'

TIMEOUT = 2
BAUDRATE = 38400
ADDR_FB1_P = 1610  # This is the absolute position from the FB1 (resolver).
# This is the position loop feedback.
# Includes some offset parameter and error based on homing position.
# Appropriate for this application, though I need to figure out the resolution.
ADDR_PL_FB = 588
GEAR_RATIO = 258

AZ_OUT_CHANNEL = 1
ZA_OUT_CHANNEL = 0

ZERO_DATA = analog_to_digital(0, -10, 10, 16)

AZ_SAMPLING_TIME = 0.002


AZ_BASE_SPEED = 1.5
AZ_POS_TOL_DEG = 0.02
AZ_HOME = 0
ZA_BASE_SPEED = 0.4
ZA_POS_TOL_DEG = 0.01
ZA_DEAFULT_RPM_PER_VOLT = 40
ZA_SCAN_RPM_PER_VOLT = 4

SPEED_MULTIPLIER = 0.35
SCAN_MODE_FAR_APPROACH_SEPARATION_DEG = 0.5
FAR_APPROACH_SEPARATION_DEG = 15
ZA_APPROACH_SEPARATION_DEG = 0.5

NEG_SW_LIM = -181.000
POS_SW_LIM = 181.000
NEG_ZA_SW_LIM = -np.inf
POS_ZA_SW_LIM = -np.inf  # TODO: Is this supposed to be negative?


class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self, connection: Connection):
        """Initialize a TelescopeMotorController."""
        self._initialized = False
        self._run = False
        self.connection = connection
        self._active_jobs: list[Thread] = []
        self.test_init()
        self._listener_loop()

    def send(self, command: str, *args, timeout: float | None = None):
        """Send a command to the telescope client."""
        if timeout:
            timer = threading.Timer(
                timeout,
                quit_function,
            )
            timer.start()
            try:
                self.connection.send([command, *args])
                _tele_logger.debug(
                    f'TELESCOPE sent command "{command}" with data {args}'
                )
            except KeyboardInterrupt:
                _tele_logger.exception(f'CAMERA timed out sending command "{command}"')
            finally:
                timer.cancel()
        else:
            self.connection.send([command, *args])
            _tele_logger.debug(f'TELESCOPE sent command "{command}" with data {args}')

    def _listener_loop(self):
        if not self._initialized:
            return
        while True:
            try:
                command, *args = self.connection.recv()
                _tele_logger.debug(
                    f'TELESCOPE received command: "{command}", args: {args}'
                )
                match command.lower():
                    case 'get_ser_az_pos':
                        self.get_ser_az_pos()
                    case 'set_az_pos':
                        self.set_az_pos(*args)
                    case 'get_ser_za_pos':
                        self.get_ser_za_pos()
                    case 'set_za_pos':
                        self.set_za_pos(*args)
                    case 'set_voltage':
                        self._run = True
                        self.set_ao_value(*args)
                    case 'set_az_speed_relation':
                        self.set_az_speed_relation(*args)
                    case 'set_za_speed_relation':
                        self.set_za_speed_relation(*args)
                    case 'stared_image':
                        self.stared_image(*args)
                    case 'dither_pattern':
                        self.dither_pattern(*args)
                    case 'stop_telescope':
                        self._run = False
                        self.set_ao_zero()
                    case 'terminate':
                        self.close()
                        break
                    case _:
                        self.send(
                            'err',
                            'NON-CRITICAL',
                            f'Unknown command "{command}" received.',
                        )
            except queue.Empty:
                continue

    def test_init(self):
        """Initialize the controller if needed."""
        if not self._initialized:
            self._initialize_system()

    def _initialize_system(self):
        _tele_logger.debug('Initializing TelescopeMotorController')
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
            msg = (
                f'Error encounterd when attempting to connect to device: '
                f'{e.error_message}'
            )
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return
        except OSError:
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
            if dev.manufacturer == 'Prolific Technology Inc.':
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
            msg = (
                'Could not communicate with AZ controller. System could not initialize.'
            )
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
            self.ser_za = Telnet(host=AKD1, port=ZA_PORT)
            self.ser_za.open(host=AKD1, port=ZA_PORT)
        except OSError:
            msg = (
                'Could not communicate with ZA controller. System could not initialize.'
            )
            _tele_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return

        status_string = self.write_ser_za('DRV.ACTIVE', timeout=0.1)
        status = float(status_string.split('\r')[0])
        if status == 1:
            _tele_logger.debug('ZA motor connected and software already enabled.')
        else:
            self.write_ser_za('DRV.EN', timeout=0.1)
            _tele_logger.debug('ZA motor connected and software enabled by Python.')

        # Allow continuous reading of last ZA position synced with PPS
        self.write_ser_za('DIN1.FILTER 0', timeout=0.1)

        self.write_ser_za('CAP0.EVENT', timeout=0.1)
        self.write_ser_za('CAP0.TRIGGER 1', timeout=0.1)
        self.write_ser_za('CAP0.EDGE 1', timeout=0.1)
        self.write_ser_za('CAP0.MODE 0', timeout=0.1)
        self.write_ser_za('CAP0.EN 1', timeout=0.1)

        # Initialize ZA values
        self.za_pos = self.za_pps_pos = 0
        self.get_ser_za_pos(timeout=0.1)
        _tele_logger.info(f'Telescope ZA position is: {self.za_pos}')
        self._initialized = True
        _tele_logger.debug('Succesfully initialized TelescopeMotorController')

    def write_ser_az(
        self, command: str | bytes, stop: str = b'\r\n', timeout: float | None = None
    ) -> str:
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
        _tele_logger.debug(
            f'AZ Command {data!r} returned result {status!r} in {elapsed * 1e3:.2f} ms'
        )
        self.ser_az.reset_input_buffer()
        self.ser_az.reset_output_buffer()
        return status

    def write_ser_za(
        self, command: str | bytes, stop: str = b'\r\n', timeout: float | None = None
    ) -> str:
        """Write a command to the zenith angle motor.

        Possible commands include:
            AIN.VSCALE <speed>: Set the speed of the motor in RPM/V.
            CAP0.EDGE (0|1): Set to trigger on the falling/rising edge of the pulse. Set
                during initialization.
            CAP0.EN (0|1): Reset the latch of the specified channel.
            CAP0.EVENT: ...
            CAP0.MODE (0|1): Indicates digital latch. Should be set to 0 at
                initialization.
            CAP0.PLFB: Get the position of the motor at the last pulse in degrees.
            CAP0.STATE: Whether it has been latched (1) or not (0).
            CAP0.TRIGGER (0|1): Set digital input channel. Set to 1 during
                initializaiton.
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
        self.ser_za.write(data)
        status = self.ser_za.read_until(stop, timeout).decode()  # Empty buffer
        elapsed = time.time() - start_time
        _tele_logger.debug(
            f'ZA Command {data!r} returned result {status!r} in {elapsed * 1e3:.2f} ms'
        )
        return status

    def close(self):
        """Close the connection and clean up the controller."""
        self._run = False
        self.set_ao_zero()
        for job in self._active_jobs:
            job.join()
        self.ser_az.close()
        self.ser_za.close()
        self.send('done')

    def set_ao_value(self, data: float, channel: int):
        """Set the output voltage."""
        self.ao_device.a_out(channel, self.ul_range_out, self.ao_flags, data)
        _tele_logger.debug(f'Set ao value for channel {channel} to {data}')

    def set_ao_zero(self):
        """Set the output voltage to 0."""
        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        self.set_ao_value(ZERO_DATA, ZA_OUT_CHANNEL)
        _tele_logger.debug('Set voltages to zero.')

    # Azimuth settings
    def get_ser_az_pos(self, timeout: float = 0.1) -> tuple[float, float]:
        """Read the serail azimuth position."""
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
            msg = (
                'Error communicating with AZ controller; '
                f'position set to most recent read ({old_pos:.2f})'
            )
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pos = old_pos

        # Try getting the PPS position
        try:
            new_pps_pos_str = self.write_ser_az('LATCH1P32', timeout=timeout / 2)
            new_pps_pos = float(new_pps_pos_str) / 10000.0
        except ValueError:
            msg = (
                'Error communicating with AZ controller when getting PPS position. '
                f'PPS position set to most recent read ({old_pps_pos:.2f})',
            )
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pps_pos = old_pps_pos

        self.az_pos = new_pos
        self.az_pps_pos = new_pps_pos

        if self._initialized:
            self.send('az_pos', new_pos, new_pps_pos, timeout=timeout)
        return new_pos, new_pps_pos

    def set_az_pos(self, new_pos: int, scan_mode: bool = False, stop_run: bool = True):
        """Set the serial azimuth position."""
        self._run = True
        worker_thread = Thread(
            target=self._set_az_pos, args=(new_pos, scan_mode, stop_run)
        )
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_az_pos(
        self,
        new_pos: int,
        scan_mode: bool = False,
        stop_run: bool = True,
        speed_factor: float = 1.0,
    ):
        """Set the serial azimuth position."""
        self.send('az_pos_comm', new_pos, timeout=0.25)
        self.set_ao_zero()
        # Measure input voltage

        ##confirm position
        az_pos, az_pps_pos = self.get_ser_az_pos()
        if scan_mode:
            za_pos, za_pps_pos = self.get_ser_za_pos()
            position_data = []
        counter = 0
        ##Run loop
        pfb_time = time.time()

        try:
            while (
                np.abs(az_pos - new_pos) > AZ_POS_TOL_DEG
                and az_pos > NEG_SW_LIM
                and az_pos < POS_SW_LIM
                and self._run
            ):
                direction = -1 if new_pos > az_pos else 1
                # Set speed faster if more travel needed
                if scan_mode:
                    if abs(az_pos - new_pos) > SCAN_MODE_FAR_APPROACH_SEPARATION_DEG:
                        # If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(
                            6.0 * speed_factor, -10, 10, 16
                        )
                    else:
                        data_value = direction * analog_to_digital(
                            2.0 * speed_factor, -10, 10, 16
                        )
                elif abs(az_pos - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                else:
                    this_speed = (
                        SPEED_MULTIPLIER * abs(az_pos - new_pos) + AZ_BASE_SPEED
                    )
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                if counter % 50 == 0:
                    _tele_logger.debug(f'AZ pos: {az_pos}; voltage: {data_value}')
                self.set_ao_value(data_value, AZ_OUT_CHANNEL)
                this_dt = time.time() - pfb_time
                while this_dt < AZ_SAMPLING_TIME:
                    this_dt = time.time() - pfb_time
                    time.sleep(1.0e-4)
                pfb_time = time.time()
                az_pos, az_pps_pos = self.get_ser_az_pos()
                if np.abs(az_pos - new_pos) <= AZ_POS_TOL_DEG:
                    self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
                # self.azimuthUpdated.emit(pfb)
                # self.conn.send(['az_pos', pfb])

                if scan_mode:
                    position_data = np.append(
                        position_data,
                        [az_pos, za_pos, pfb_time, az_pps_pos, za_pps_pos],
                    )

                counter = counter + 1

        except KeyboardInterrupt:
            _tele_logger.info('User terminated motion!')
        except ValueError:
            _tele_logger.exception('Caught an exception regarding Float conversion')

        self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
        if stop_run:
            self._run = False
        ## Read position again
        # time.sleep(1)
        az_pos, _ = self.get_ser_az_pos()
        _tele_logger.debug(
            f'Finished setting az_pos to {new_pos}. '
            'Actual={az_pos}, Error={az_pos - new_pos:.5f}'
        )
        if scan_mode:
            return position_data
        return None

    def set_az_speed_relation(self, rpm_per_ten_volt: float):
        """Set the speed of the motor in RPM/10V.

        Default is 500, which would roughly turn the telescope 2.5
        degree/second for 10 V input. ASCII code for serial is VSCALE1.
        AZ value is per 10 volts and EL value is per 1 volt. Needs more
        testing from Ubuntu; there may be a lower limit set in the S700.
        """
        if self.ser_az.is_open:
            command = 'VSCALE1 ' + str(rpm_per_ten_volt) + '\r\n'
            command = command.encode()
            self.write_ser_az(command)
            _logger.info(f'AZ speed relation set to: {rpm_per_ten_volt * 10} RPM / V')

    # Zenith angle settings
    def get_ser_za_pos(self, timeout: float = 0.1) -> tuple[float, float]:
        """Get the serial zenith angle position."""
        # Get old values as a fallback
        old_pos = self.za_pos
        old_pps_pos = self.za_pps_pos

        # Query the values from the motor
        pos_str = self.write_ser_za('PL.FB', timeout=timeout / 3)
        state_str = self.write_ser_za('CAP0.STATE', timeout=timeout / 3)
        state = float(state_str.split(' ')[0].split('>')[-1])
        if state == 1:
            # It's been latched so get the position and reset the latch
            pps_pos_str = self.write_ser_za('CAP0.PLFB', timeout=timeout / 3)
            self.write_ser_za('CAP0.EN 1', timeout=timeout / 3)
        else:
            new_pps_pos = old_pps_pos

        # Try to get the ZA position
        try:
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            new_pos = pos
        except ValueError:
            # Couldn't convert the string to a float
            msg = (
                'Error communicating with ZA controller; '
                f'position set to most recent read ({old_pos:.2f})'
            )
            _tele_logger.warning(msg)
            self.send('err', 'NON-CRITICAL', msg)
            new_pos = old_pos

        # Check that the PPS position is accesible
        if state == 1:
            pps_split_string = pps_pos_str.split(' ')[0].split('>')
            if len(pps_split_string[-1]) == 0:
                # Not receiving pulse
                msg = (
                    'Attempted to access PPS position from ZA controller; '
                    'No pulse detected; '
                    f'PPS position set to most recent read ({old_pps_pos:.2f})',
                )
                _tele_logger.warning(msg)
                self.send('err', 'NON-CRITICAL', msg)
                new_pps_pos = old_pps_pos
            else:
                new_pps_pos = float(pps_split_string[-1])

        self.za_pos = new_pos
        self.za_pps_pos = new_pps_pos

        if self._initialized:
            self.send('za_pos', new_pos, new_pps_pos, timeout=timeout)
        return new_pos, new_pps_pos

    def set_za_pos(
        self,
        new_pos: float,
        scan_mode: bool = False,
        stop_run: bool = True,
        primary_scan_direction: str = 'za',
    ):
        """Set the serial zenith angle position."""
        # self.zenithCommanded.emit(new_pos)
        self._run = True
        worker_thread = Thread(
            target=self._set_za_pos,
            args=(new_pos, scan_mode, stop_run, primary_scan_direction),
        )
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_za_pos(
        self,
        new_pos: float,
        scan_mode: bool = False,
        stop_run: bool = True,
        primary_scan_direction: str = 'za',
    ):
        self.send('za_pos_comm', new_pos, timeout=0.25)
        # new_pos = float(new_pos)
        self.set_ao_zero()

        # confirm position
        za_pos, _ = self.get_ser_za_pos()
        if scan_mode:
            az_pos, az_pps_pos = self.get_ser_az_pos()
            position_data = []
        if scan_mode and primary_scan_direction.lower() == 'za':
            tolerance = ZA_POS_TOL_DEG * 5
        else:
            tolerance = ZA_POS_TOL_DEG
        counter = 0

        # Run loop
        _tele_logger.debug(
            f'Zenith Angle - Pos: {za_pos}, New pos: {new_pos}, '
            f'tolerance: {tolerance}, diff: {za_pos - new_pos}'
        )
        # start_time = time.time()
        # profiler = cProfile.Profile()
        # profiler.enable()
        try:
            _tele_logger.debug(f'Starting ZA loop #{counter}')
            while abs(za_pos - new_pos) > tolerance and self._run:
                # Choose direction of motion
                direction = -1 if za_pos > new_pos else 1

                if scan_mode:
                    data_value = direction * analog_to_digital(1.0, -10, 10, 16)
                elif abs(za_pos - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                elif abs(za_pos - new_pos) > ZA_APPROACH_SEPARATION_DEG:
                    # If we are semifar from the setpoint, start slowing down
                    this_speed = (
                        SPEED_MULTIPLIER * abs(za_pos - new_pos) + ZA_BASE_SPEED
                    )
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)
                else:
                    # If we are close to the setpoint, slow down a lot
                    this_speed = (
                        SPEED_MULTIPLIER
                        * abs(za_pos - new_pos) ** 2
                        / ZA_APPROACH_SEPARATION_DEG
                        + ZA_BASE_SPEED
                    )
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                self.set_ao_value(data_value, ZA_OUT_CHANNEL)
                _tele_logger.debug('Getting ser za pos')
                za_pos, za_pps_pos = self.get_ser_za_pos()
                if abs(za_pos - new_pos) <= tolerance:
                    self.set_ao_value(ZERO_DATA, ZA_OUT_CHANNEL)
                if scan_mode:
                    _tele_logger.debug('Appending scan mode position data')
                    position_data = np.append(
                        position_data,
                        [az_pos, za_pos, time.time(), az_pps_pos, za_pps_pos],
                    )
                counter = counter + 1
                if counter % 500 == 0:
                    _tele_logger.debug(f'ZA pos: {za_pos}l; voltage: {data_value}')
        except KeyboardInterrupt:
            _tele_logger.info('User terminated motion!')
        except ValueError:
            _tele_logger.exception('caught an exception regarding Float conversion')

        if stop_run:
            self._run = False
        self.set_ao_value(ZERO_DATA, ZA_OUT_CHANNEL)
        # stop_time = time.time()
        # print(f'Average time per loop: {(stop_time - start_time) / counter}')
        # profiler.disable()
        # profiler.print_stats()
        # self.zenithVelocityChanged.emit(0)
        ## Read position again
        # time.sleep(0.1)
        za_pos, _ = self.get_ser_za_pos()
        _tele_logger.debug(
            f'Finished setting za_pos to {new_pos}. '
            f'Actual={za_pos}, Error={za_pos - new_pos:.5f}'
        )
        if scan_mode:
            return position_data
        return None

    def stared_image(
        self,
        file: str,
        duration: float,
    ):
        """Collect an image without moving the telescope."""
        self._run = True
        worker_thread = Thread(target=self._stared_image, args=(file, duration))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _stared_image(
        self,
        file: str,
        duration: float,
    ):
        self.send('stared_image_label', 'Running Stared Image')
        self.send('stared_image_maximum', 100)
        start_time = time.time()
        end_time = start_time + duration
        az_pos, az_pos_pps = self.get_ser_az_pos()
        za_pos, za_pos_pps = self.get_ser_za_pos()
        position_data = []
        while self._run and time.time() < end_time:
            position_data.extend([az_pos, za_pos, time.time(), az_pos_pps, za_pos_pps])
            label_text = (
                f'Running Stared Image\nTime Remaining: {end_time - time.time():.2f} s'
            )
            self.send('stared_image_label', label_text)
            self.send(
                'stared_image_progress',
                int((time.time() - start_time) / duration * 100),
            )
            time.sleep(AZ_SAMPLING_TIME)
        self.send('stared_image_progress', 100)

        if not self._run:
            _tele_logger.info('Stared Image canceled before completion.')
            self.send('stared_image_complete', 1)
            return

        path = Path(file)
        with h5py.File(path, 'w') as f:
            f.create_dataset('az_tel', data=position_data[0::5])
            f.create_dataset('za_tel', data=position_data[1::5])
            f.create_dataset('timestamp_tel', data=position_data[2::5])
            f.create_dataset('az_pps', data=position_data[3::5])
            f.create_dataset('za_pps', data=position_data[4::5])
            f.create_dataset('optical_visibility', data=['****'])
        path.chmod(PERMISSIONS_ALL_FULL)

        self._run = False
        _tele_logger.info('Scan Complete')
        self.send('stared_image_complete', 0)

    def dither_pattern(
        self,
        file: str,
        primary_start: float,  # relative to current positions
        primary_stop: float,
        n_repeats: int = 1,
        secondary_dither: float = 0.04,
        position_return: bool = True,
        large_map_mode: bool = False,
        primary_dither_direction: Literal['az', 'za'] = 'az',
    ):
        """Dither the telescope along the specified direction.

        Arguments:
            file (str): The file to save position data to.
            primary_start (float): Starting location relative to current position in
                degrees.
            primary_stop (float): Ending location relative to current position in
                degrees.
            n_repeats (int, optional): Total number of dithers to do. Defaults to 1.
            secondary_dither (float, optional): The amount to dither the telescope in
                the secondary direction in degrees.. Defaults to 0.04.
            position_return (bool, optional): Whether to return to the initial
                position. Defaults to True.
            large_map_mode (bool, optional): Whether to perform the dither in large map
                mode. In large map mode, secondary dithers are cummulative. Otherwise,
                the telescope will oscillate back and forth in the secondar ydirection.
                Defaults to False.
            primary_dither_direction (str, optional): Which direction is the pimary
                direction (must be 'az' or 'za'). Defaults to 'az'.
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
                primary_dither_direction,
            ),
        )
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _dither_pattern(  # noqa: PLR0912
        self,
        file: str,
        primary_start: float,
        primary_stop: float,
        n_repeats: int = 2,
        secondary_dither: float = 0.04,
        position_return: bool = True,
        large_map_mode: bool = False,
        primary_dither_direction: str = 'az',
    ):
        """Dither the telescope along the specified direction."""
        if primary_dither_direction not in ['az', 'za']:
            # TODO: Handle error
            pass
        primary_az = primary_dither_direction.lower() == 'az'
        primary_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        primary_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        initial_az, _ = self.get_ser_az_pos()
        initial_za, _ = self.get_ser_za_pos()
        if primary_az:
            primary_start += initial_az
            primary_stop += initial_az
        else:
            primary_start += initial_za
            primary_stop += initial_za

        # Set start position in current thread
        _tele_logger.info('Moving telescope to initial position')
        self.send(
            'dither_pattern_label',
            'Running Dither Pattern\nMoving telescope to initial position',
        )
        if primary_az:
            self._set_az_pos(primary_start - primary_start_buffer, stop_run=False)
        else:
            self._set_za_pos(primary_start - primary_start_buffer, stop_run=False)

        if primary_az:
            self.set_za_speed_relation(ZA_SCAN_RPM_PER_VOLT)

        az_speed_factor = 1 / 3 if large_map_mode else 1.0

        self.send('dither_pattern_maximum', n_repeats)
        start_time = time.time()
        rep_times = []
        for i_rep in np.arange(n_repeats):
            rep_start_time = time.time()
            _tele_logger.info(
                f'Dither Pattern: Starting repeat {i_rep + 1} of {n_repeats} '
                '---------------------------------------------'
            )
            label_text = f'Running Dither Pattern\nRepeat {i_rep + 1} / {n_repeats}'
            if len(rep_times) > 0:
                label_text += (
                    f'\nEstimated time remaining: '
                    f'{np.mean(rep_times) * (n_repeats - i_rep):.2f} s'
                )
            self.send('dither_pattern_label', label_text)
            if not self._run:
                break
            if large_map_mode:
                new_za = initial_za + (i_rep - (n_repeats - 1) / 2) * secondary_dither
                self._set_za_pos(new_za, stop_run=False)
            elif primary_az:
                new_za = initial_za + (i_rep % 2) * secondary_dither
                self._set_za_pos(new_za, stop_run=False)
            else:
                new_az = initial_az + (i_rep % 2) * secondary_dither
                self._set_az_pos(new_az, stop_run=False)

            if np.mod(i_rep, 2) == 0:
                if primary_az:
                    this_position_data = self._set_az_pos(
                        primary_stop + primary_end_buffer + 0.5,
                        scan_mode=True,
                        stop_run=False,
                        speed_factor=az_speed_factor,
                    )
                else:
                    this_position_data = self._set_za_pos(
                        primary_stop + primary_end_buffer + 0.5,
                        scan_mode=True,
                        stop_run=False,
                        primary_scan_direction=primary_dither_direction,
                    )
                if i_rep == 0:
                    position_data = this_position_data
                else:
                    position_data = np.append(position_data, this_position_data)
            if np.mod(i_rep, 2) == 1:
                if primary_az:
                    this_position_data = self._set_az_pos(
                        primary_start - primary_start_buffer - 0.5,
                        scan_mode=True,
                        stop_run=False,
                        speed_factor=az_speed_factor,
                    )
                else:
                    this_position_data = self._set_za_pos(
                        primary_start - primary_start_buffer - 0.5,
                        scan_mode=True,
                        stop_run=False,
                        primary_scan_direction=primary_dither_direction,
                    )
                position_data = np.append(position_data, this_position_data)
            rep_end_time = time.time()
            elapsed_time = rep_end_time - rep_start_time
            rep_times.append(elapsed_time)
            self.send('dither_pattern_progress', i_rep + 1)
            _tele_logger.info(
                f'Dither Pattern: Finished repeat {i_rep + 1} in {elapsed_time:.3f}s'
            )
            _tele_logger.info(
                f'Dither Pattern: Average time per repetition is '
                f'{np.mean(rep_times):.3f}s'
            )

        stop_time = time.time()
        _logger.info(
            f'Dither Pattern: Finished {n_repeats} repeats in '
            f'{stop_time - start_time:.3f}s'
        )

        # Save pointing information
        path = Path(file)
        with h5py.File(path, 'w') as f:
            f.create_dataset('az_tel', data=position_data[0::5])
            f.create_dataset('za_tel', data=position_data[1::5])
            f.create_dataset('timestamp_tel', data=position_data[2::5])
            f.create_dataset('az_pps', data=position_data[3::5])
            f.create_dataset('za_pps', data=position_data[4::5])
            f.create_dataset('optical_visibility', data=['****'])
            f.attrs['params'] = json.dumps(
                {
                    # Generic parameters
                    'initial_az': initial_az,
                    'initial_za': initial_za,
                    # self._run can only be False here if the dither was cancelled
                    'completed': self._run,
                    # Arguments to this function
                    'primary_start': primary_start,
                    'primary_stop': primary_stop,
                    'n_repeats': n_repeats,
                    'secondary_dither': secondary_dither,
                    'position_return': position_return,
                    'large_map_mode': large_map_mode,
                    'primary_dither_direction': primary_dither_direction,
                }
            )
        path.chmod(PERMISSIONS_ALL_FULL)

        # Reset telescope
        if primary_az:
            self.set_za_speed_relation(ZA_DEAFULT_RPM_PER_VOLT)
        if position_return:
            _tele_logger.info('Dither Pattern: Resetting telescope position...')
            self.send(
                'dither_pattern_label',
                'Running Dither Pattern\nResetting telescope position',
            )
            self._set_az_pos(initial_az, stop_run=False)
            self._set_za_pos(initial_za, stop_run=False)

        # self._run is only changed if the telescope was stopped mid scan
        if not self._run:
            _tele_logger.info('Dither Pattern canceled before completion.')
            self.send('dither_pattern_complete', 1)
            return

        self._run = False
        _tele_logger.info('Scan Complete')
        self.send('dither_pattern_complete', 0)

    def set_za_speed_relation(self, rpm_per_volt: float):
        """Set the speed of the motor in RPM/1V.

        Default is 40, which would roughly turn the telescope 1 degree/second.
        ASCII code for serial is AIN.VSCALE.
        """
        if self._initialized:
            command = 'AIN.VSCALE ' + str(rpm_per_volt) + '\r\n'
            command = command.encode('ASCII')
            self.ser_za.write(command)
            self.ser_za.read_until(b'\r\n', 0.1).decode()
            _logger.info(f'ZA speed relation set to: {rpm_per_volt} RPM / V')


def make_controller(connection: Connection) -> TelescopeMotorController:
    """Create a TelescopeMotorController."""
    return TelescopeMotorController(connection)


if __name__ == '__main__':
    import sys

    try:
        # Connect to device
        descriptor = ul.get_daq_device_inventory(ul.InterfaceType.ANY)[0]
        device = ul.DaqDevice(descriptor)
        device.connect()

        # Configure analog outputs
        ao_device = device.get_ao_device()
        sul_range_out = ao_device.get_info().get_ranges()[0]
        ao_flags = ul.AOutFlag.DEFAULT
    except ul.ul_exception.ULException as e:
        msg = (
            f'Error encounterd when attempting to connect to device: {e.error_message}'
        )
        _tele_logger.critical(msg, exc_info=True)
        # self.send('err', 'CRITICAL', msg)
        # self.send('done')
        sys.exit(1)
    except OSError:
        msg = 'DAQ could not be initialized; Check comport and power supply'
        _tele_logger.critical(msg, exc_info=True)
        # self.send('err', 'CRITICAL', msg)
        # self.send('done')
        sys.exit(1)

    # Init serial communication with S700 for high res positioning of AZ monitors
    comports = serial.tools.list_ports.comports()
    for dev in comports:
        # port_array[dev] = str(ports[dev].manufacturer)
        # _tele_logger.debug('dev #: ', dev)
        if dev.manufacturer == 'Prolific Technology Inc.':
            az_port = dev.device
    print(az_port)  # noqa: T201
    # ser_az = serial.Serial(
    #     az_port,
    #     baudrate=BAUDRATE,
    #     timeout=TIMEOUT,
    #     bytesize=8,
    #     parity='N',
    #     stopbits=1,
    # )
