from __future__ import annotations

import logging

import pdb
import time
from multiprocessing.connection import Connection
from multiprocessing import Queue
from threading import Thread

import h5py
import numpy as np
import serial
import serial.tools.list_ports
import uldaq as ul
from Exscript.protocols.telnetlib import Telnet

from rfsocinterface.core.utils import analog_to_digital

_logger = logging.getLogger(__name__)
_tele_logger = logging.getLogger('telescopeControl')


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

AZ_BASE_SPEED = 1.5
AZ_POS_TOL_DEG = .02
AZ_HOME = 0
ZE_BASE_SPEED = 0.3
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


class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self, queue: Queue):
        self._initialized = False
        self._run = False
        self.queue = queue
        self.connections: dict[str, Connection] = {}
        self._active_jobs: list[Thread] = []
        self.test_init()
        self._listener_loop()
    
    def add_connection(self, client_id: str, conn: Connection):
        """Add a connection to the telescope controller"""
        self.connections[client_id] = conn
    
    def remove_connection(self, client_id: str):
        self.send(client_id, 'remove_connection_succesful')
        del self.connections[client_id]
    
    def send_all(self, command: str, *args):
        for conn in self.connections.values():
            conn.send([command, *args])
    
    def send(self, client_id: str, command: str, *args):
        """Send a command to the telescope controller"""
        if client_id in self.connections:
            self.connections[client_id].send([command, *args])
        else:
            self.send_all('err', f'Unknown client "{client_id}".')

    def _listener_loop(self):
        while True:
            client_id, command, *args = self.queue.get()
            _tele_logger.debug(f'Client "{client_id}" sent command: "{command}", args: {args}')
            match command.lower():
                case 'add_connection':
                    self.add_connection(client_id, *args)
                    self.send(client_id, 'add_connection_succesful')
                case 'remove_connection':
                    self.remove_connection(client_id)
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
                    self.az_scan_mode(client_id, *args)
                case 'stop_telescope':
                    self._run = False
                    self.set_ao_zero()
                case 'terminate':
                    self.close()
                    break
                case _:
                    self.send(client_id, 'err', f'Unknown command "{command}" received.')

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
        except OSError as e:
            self.send_all('err', 'DAQ could not be initialized; Check comport and power supply')
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
            _tele_logger.critical('Could not communicate with AZ controller. System could not initialize.')
        self.ser_az = ser_az
        self.az_pos = 0
        self.az_pos = self.get_ser_az_pos()
        _tele_logger.info(f'Telescope AZ position is: {self.az_pos}')

        # Zenith Angle
        self.ser_ze = Telnet(host=AKD1, port=ZEPORT)
        self.ser_ze.open(host=AKD1, port=ZEPORT)
        self.ser_ze.write(b'DRV.ACTIVE\r\n')
        status_string = self.ser_ze.read_until(b'\r', 0.1)
        # _tele_logger.debug(status_string, type(status_string))
        # status_string = self.ser_ze.read_until(b'\r', 0.1).decode()
        status = float(status_string.split('\r')[0])

        if status == 1:
            _tele_logger.debug('ZA motor connected and software already enabled.')
        else:
            self.ser_ze.write(b'DRV.EN\r\n')
            sw_en = self.ser_ze.read_until(b'\r', 0.1)
            _tele_logger.debug('ZA motor connected and software enabled by Python.')
        self.ze_pos = 0
        self.ze_pos = self.get_ser_ze_pos()
        _tele_logger.info(f'Telescope ZA position is: {self.ze_pos}')
        self._initialized = True

    def close(self):
        self._run = False
        self.set_ao_zero()
        for job in self._active_jobs:
            job.join()
        self.ser_az.close()
        self.ser_ze.close()
        self.send_all('done')

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
            _logger.info("Home Set.")
        else:
            _tele_logger.error("Home command not executed. Check connection with S700")

    # TODO: There's also a "setAZ_home_position"...

    ##Read AZ Serial Position

    def get_ser_az_pos(self) -> float:
        old_pfb = self.az_pos
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
                    self.send_all('az_pos', pfb)
                return pfb
        except ValueError:
            self.send_all(
                'err',
                'Error communicating with AZ controller; '
                'position set to most recent read.',
            )
            return old_pfb

    def set_az_pos(self, new_pos: int, scan_mode: bool=False, stop_run: bool=True):
        self._run = True
        worker_thread = Thread(target=self._set_az_pos, args=(new_pos, scan_mode, stop_run))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_az_pos(self, new_pos: int, scan_mode: bool=False, stop_run: bool=True, speed_factor: float=1.):
        self.send_all('az_pos_comm', new_pos)
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
            np.abs(pfb - new_pos) > AZ_POS_TOL_DEG
            and pfb > NEG_SW_LIM
            and pfb < POS_SW_LIM
            and self._run
        ):
            try:
                if new_pos > pfb:
                    direction = -1
                else:
                    direction = 1
                # Set speed faster if more travel needed
                if scan_mode:
                    if abs(pfb - new_pos) > 0.5:
                        # If we are far from the setpoint, go at max speed
                        data_value = direction * analog_to_digital(6.0 * speed_factor, -10, 10, 16)
                    else:
                        data_value = direction * analog_to_digital(2.0 * speed_factor, -10, 10, 16)
                elif abs(pfb - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                else:
                    this_speed = SPEED_MULTIPLIER * abs(pfb - new_pos) + AZ_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                if counter % 50 == 0:
                    _tele_logger.debug(f'AZ pos: {pfb}; voltage: {data_value}')
                self.set_ao_value(data_value, AZ_OUT_CHANNEL)
                this_dt = time.time() - pfb_time
                while this_dt < 0.02:
                   this_dt = time.time() - pfb_time
                   time.sleep(1.e-4)
                pfb_time = time.time()
                pfb = self.get_ser_az_pos()
                if np.abs(pfb - new_pos) <= AZ_POS_TOL_DEG:
                    self.set_ao_value(ZERO_DATA, AZ_OUT_CHANNEL)
                # self.azimuthUpdated.emit(pfb)
                # self.conn.send(['az_pos', pfb])

                if scan_mode:
                    position_data = np.append(position_data, [pfb, this_ze, pfb_time])

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
        time.sleep(1)
        pfb = self.get_ser_az_pos()
        if scan_mode:
            return position_data

    def az_scan_mode(
            self,
            client_id: str,
            file: str,
            az_start: float,  # relative to current positions
            az_stop: float,
            n_repeats: int=1,
            ze_dither: float=0.04,
            position_return: bool=True,
            large_map_mode: bool=False,
    ):
        self._run = True
        worker_thread = Thread(target=self._az_scan_mode, args=(client_id, file, az_start, az_stop, n_repeats, ze_dither, position_return, large_map_mode))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _az_scan_mode(
            self,
            client_id: str,
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
        initial_az = self.get_ser_az_pos()
        initial_ze = self.get_ser_ze_pos()
        az_start += initial_az
        az_stop += initial_az

        # Set start position in current thread
        self._set_az_pos(az_start - az_start_buffer, stop_run=False)
        self.set_ze_speed_relation(ZE_SCAN_RPM_PER_VOLT)

        speed_factor = 1/3 if large_map_mode else 1.

        for i_rep in np.arange(n_repeats):
            _logger.info(f'AZ Scan Mode: Starting repeat {i_rep} of {n_repeats}')
            if not self._run:
                break
            if large_map_mode:
                new_ze = initial_ze + (i_rep - (n_repeats - 1) / 2) * ze_dither
            else:
                new_ze = initial_ze + (i_rep % 2) * ze_dither
            self._set_ze_pos(new_ze, stop_run=False)


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

        # self._run is only changed if the telescope was stopped mid scan
        # Don't save the telescope data in that case
        if not self._run:
            self.send(client_id, 'az_scan_mode_complete', 1)
            return
        
        with h5py.File(file, "a") as f:
            f.create_dataset("az_tel", data=position_data[0::3])
            f.create_dataset("za_tel", data=position_data[1::3])
            f.create_dataset("timestamp_tel", data=position_data[2::3])
            f.create_dataset("optical_visibility", data=['****'])
        if position_return:
            self._set_az_pos(initial_az, stop_run=False)
            self._set_ze_pos(initial_ze, stop_run=False)

        self.set_ze_speed_relation(ZE_DEAFULT_RPM_PER_VOLT)
        self._run = False
        _logger.info("Scan Complete")
        self.send(client_id, 'az_scan_mode_complete', 0)

    def jog_az_pos(self, speed: float=1):
        raise NotImplementedError("Jogging not implemented yet.")

    def az_oscillate(self, total_t: float, freq: float, deg: float):
        raise NotImplementedError("Oscillation not implemented yet.")

    def set_az_speed_relation(self, rpm_per_ten_volt: float):
        # Set the speed of the motor in RPM/10V. Default is 500, which would roughly turn the telescope 2.5 degree/second for 10 V input. ASCII code for serial is VSCALE1. AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT! Needs more testing from Ubuntu, I think there is a lower limit set in the S700.
        if self.ser_az.is_open:
            command = "VSCALE1 " + str(rpm_per_ten_volt) + "\r\n"
            command = command.encode()
            self.ser_az.write(command)
            self.ser_az.readline()
            az_speed = self.ser_az.read_until(b"\r\n")
            _logger.info("AZ speed set to: ", az_speed)  ###THIS MAY BREAK
            # self.azimuthVelocityChanged(az_speed)
            # self.send_all('az_vel', az_speed)
            self.ser_az.reset_input_buffer()
            self.ser_az.reset_output_buffer()

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
        _logger.info("EL Home Set.")

    def get_ser_ze_pos(self) -> float | None:
        old_pos = self.ze_pos
        # locker = QMutexLocker(self.ze_mutex)
        try:
            self.ser_ze.write('PL.FB\r\n'.encode('ASCII'))
            # pos_str = self.ser_ze.read_until(b']', 0.1).decode()
            pos_str = self.ser_ze.read_until(b']', 0.1)
            pos = float(pos_str.split(' ')[0].split('>')[-1])
            self.ze_pos = pos
            if self._initialized:
                self.send_all('ze_pos', pos)
            return pos
        except ValueError:
            _tele_logger.error(
                'Error communicating with ZA controller; '
                'position set to most recent read.'
            )
            return old_pos

    def set_ze_pos(self, new_pos: float, scan_mode: bool=False, stop_run: bool=True):
        # self.zenithCommanded.emit(new_pos)
        self._run = True
        worker_thread = Thread(target=self._set_ze_pos, args=(new_pos, scan_mode, stop_run))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_ze_pos(self, new_pos: float, scan_mode: bool=False, stop_run: bool=True):
        self.send_all('ze_pos_comm', new_pos)
        # new_pos = float(new_pos)
        self.set_ao_zero()

        # confirm position
        pos = self.get_ser_ze_pos()
        # self.conn.send(['ze_pos', pos])
        if scan_mode:
            this_az = self.get_ser_az_pos()
            position_data = []
        counter = 0

        # Run loop
        _tele_logger.debug(f'Zenith Angle - Pos: {pos}, New pos: {new_pos}, tolerance: {ZE_POS_TOL_DEG}, diff: {pos - new_pos}')
        # start_time = time.time()
        # profiler = cProfile.Profile()
        # profiler.enable()
        while abs(pos - new_pos) > ZE_POS_TOL_DEG and self._run:
            try:
                # Choose direction of motion
                if pos > new_pos:
                    direction = -1
                else:
                    direction = 1

                if scan_mode:
                    data_value = direction * analog_to_digital(1.0, -10, 10, 16)
                elif abs(pos - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                elif abs(pos - new_pos) > ZE_APPROACH_SEPARATION_DEG:
                    # If we are semifar from the setpoint, start slowing down
                    this_speed = SPEED_MULTIPLIER * abs(pos - new_pos) + ZE_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)
                else:
                    # If we are close to the setpoint, slow down a lot
                    this_speed = SPEED_MULTIPLIER * abs(pos - new_pos)**2 \
                        / ZE_APPROACH_SEPARATION_DEG + ZE_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                self.set_ao_value(data_value, ZE_OUT_CHANNEL)
                pos = self.get_ser_ze_pos()
                if abs(pos - new_pos) <= ZE_POS_TOL_DEG:
                    self.set_ao_value(ZERO_DATA, ZE_OUT_CHANNEL)
                # self.conn.send(['ze_pos', pos])
                if scan_mode:
                    position_data = np.append(
                        position_data, [this_az, pos, time.time()]
                    )
                counter = counter + 1
                if counter % 500 == 0:
                    _tele_logger.debug(f'ZA pos: {pos}l; voltage: {data_value}')
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
        time.sleep(0.1)
        pos = self.get_ser_ze_pos()
        _tele_logger.debug(f'After loop zenith pos: {pos}')
        if scan_mode:
            return position_data

    def ze_scan_mode(self, start: float, stop: float, file: str, n_repeats: int=1):
        # worker = TelescopeMotionJob(self._az_scan_mode, start, stop, file, n_repeats)
        # self._active_jobs.append(worker)
        # worker.start()
        self._ze_scan_mode(start, stop, file, n_repeats)

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

    def set_ze_speed_relation(self, rpm_per_volt: float):
        # Set the speed of the motor in RPM/1V. Default is 40, which would roughly turn the telescope 1 degree/second. ASCII code for serial is AIN.VSCALE. NOTE: AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT!
        if self._initialized:
            command = "AIN.VSCALE " + str(rpm_per_volt) + "\r\n"
            command = command.encode('ASCII')
            self.ser_ze.write(command)
            ze_speed = self.ser_ze.read_until(b'\r\n', 0.1)
            _logger.info(f'ZA speed set to: {ze_speed}')  ###THIS MAY BREAK
            # self.zenithVelocityChanged(ze_speed)
            # self.ser_ze.reset_input_buffer()
            # self.ser_ze.reset_output_buffer()

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


def make_controller(queue: Queue) -> TelescopeMotorController:
    return TelescopeMotorController(queue)

