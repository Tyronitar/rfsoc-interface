from __future__ import annotations
from rfsocinterface.core.utils import analog_to_digital


import h5py
import numpy as np
import serial
import serial.tools.list_ports
import uldaq as ul
from Exscript.protocols.telnetlib import Telnet
from PySide6.QtCore import QMutex


import pdb
import time
from multiprocessing.connection import Connection
from multiprocessing import Queue
from threading import Thread


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
ZE_POS_TOL_DEG = .05

SPEED_MULTIPLIER = 0.35
FAR_APPROACH_SEPARATION_DEG = 15
ZE_APPROACH_SEPARATION_DEG = 0.5

NEG_SW_LIM = -181.000
POS_SW_LIM = 181.000
NEG_ZE_SW_LIM = -np.inf
POS_ZE_SW_LIM = -np.inf  # TODO: Is this supposed to be negative?


class TelescopeMotorController:
    """Class for controlling the motion of the telescope."""

    def __init__(self, queue: Queue, client_id: str, conn: Connection):
        self._initialized = False
        self._run = False
        self.queue = queue
        self.connections: dict[str, Connection] = {}
        self.add_connection(client_id, conn)
        self.test_init()
        self._listener_loop()
    
    def add_connection(self, client_id: str, conn: Connection):
        """Add a connection to teh telescope controleer"""
        self.connections[client_id] = conn
    
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
            # command, *args = self.conn.recv()
            print(f'Client "{client_id}" sent command: "{command}", args: {args}')
            match command.lower():
                case 'get_ser_az_pos':
                    pfb = self.get_ser_az_pos()
                    # self.send(client_id, 'az_pos', pfb)
                case 'set_az_pos':
                    self.set_az_pos(*args)
                case 'get_ser_ze_pos':
                    pos = self.get_ser_ze_pos()
                    # self.send(client_id, 'ze_pos', pos)
                case 'set_ze_pos':
                    self.set_ze_pos(*args)
                case 'set_voltage':
                    self._run = True
                    self.set_ao_value(*args)
                case 'stop_telescope':
                    self._run = False
                    self.set_ao_zero()
                case 'terminate':
                    self.close()
                    break
                case _:
                    self.send_all('err', f'Unknown command "{command}" received from client "{client_id}".')

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
            self.send_all('err', 'DAQ could not be initialized; Check comport and power supply')
            return

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
        status_string = self.ser_ze.read_until(b'\r', 0.1)
        # print(status_string, type(status_string))
        # status_string = self.ser_ze.read_until(b'\r', 0.1).decode()
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
            print("Home Set.")
        else:
            print("Home command not executed. Check connection with S700")

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

    def set_az_pos(self, new_pos: int, scan_mode: bool=False):
        self.send_all('az_pos_comm', new_pos)
        self._run = True
        worker_thread = Thread(target=self._set_az_pos, args=(new_pos, scan_mode))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

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
                        data_value = direction * analog_to_digital(6.0, -10, 10, 16)
                    else:
                        data_value = direction * analog_to_digital(2.0, -10, 10, 16)
                elif abs(pfb - new_pos) > FAR_APPROACH_SEPARATION_DEG:
                    # If we are far from the setpoint, go at max speed
                    data_value = direction * analog_to_digital(7.25, -10, 10, 16)
                else:
                    this_speed = SPEED_MULTIPLIER * abs(pfb - new_pos) + AZ_BASE_SPEED
                    data_value = direction * analog_to_digital(this_speed, -10, 10, 16)

                if counter % 50 == 0:
                    print(pfb, data_value)
                self.set_ao_value(data_value, AZ_OUT_CHANNEL)
                this_dt = time.time() - pfb_time
                while this_dt < 0.02:
                   this_dt = time.time() - pfb_time
                   time.sleep(1.e-4)
                pfb_time = time.time()
                pfb = self.get_ser_az_pos()
                # self.azimuthUpdated.emit(pfb)
                # self.conn.send(['az_pos', pfb])

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
        self._run = False
        ## Read position again
        time.sleep(1)
        pfb = self.get_ser_az_pos()
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
    ):
        # worker = TelescopeMotionJob(self._az_scan_mode, az_start, az_stop, file, n_repeats, ze_dither, position_return)
        # self._active_jobs.append(worker)
        self._run = True
        # worker.start()
        self._az_scan_mode(file, az_start, az_stop, n_repeats, ze_dither, position_return)

    def _az_scan_mode(
            self,
            file: str,
            az_start: float,
            az_stop: float,
            n_repeats: int=1,
            ze_dither: float=0.04,
            position_return: bool=True,
    ):
        az_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        az_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        current_az = self.get_ser_az_pos()
        current_ze = self.get_ser_ze_pos()
        az_start += current_az
        az_stop += current_az

        # Set start position in current thread
        self._set_az_pos(az_start - az_start_buffer)

        for i_rep in np.arange(n_repeats):
            if not self._run:
                break
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
                self._set_ze_pos(current_ze + ze_dither)
                this_position_data = self._set_az_pos(
                    az_start - az_start_buffer - 0.5, scan_mode=True
                )
                position_data = np.append(position_data, this_position_data)

        # np.savez(position_data_file, az = position_data[0::3],el = position_data[1::3],time = position_data[2::3],az_start=AZ_start,
        #  az_stop=AZ_stop,el_start=np.nan,el_stop=np.nan)
        self._run = False
        f = h5py.File(file, "a")
        f.create_dataset("az_tel", data=position_data[0::3])
        f.create_dataset("za_tel", data=position_data[1::3])
        f.create_dataset("timestamp_tel", data=position_data[2::3])
        f.create_dataset("optical_visibility", data=['****'])
        f.close()
        time.sleep(0.5)
        if position_return:
            self._set_az_pos(current_az)
            self._set_ze_pos(current_ze)
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
        print("EL Home Set.")

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
            print(
                'Error communicating with ZA controller; '
                'position set to most recent read.'
            )
            return old_pos

    def set_ze_pos(self, new_pos: int, scan_mode: bool=False):
        # self.zenithCommanded.emit(new_pos)
        self.send_all('ze_pos_comm', new_pos)
        self._run = True
        worker_thread = Thread(target=self._set_ze_pos, args=(new_pos, scan_mode))
        self._active_jobs.append(worker_thread)
        worker_thread.start()

    def _set_ze_pos(self, new_pos: float, scan_mode: bool=False):
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
                # self.conn.send(['ze_pos', pos])
                if scan_mode:
                    position_data = np.append(
                        position_data, [this_az, pos, time.time()]
                    )
                counter = counter + 1
                if counter % 500 == 0:
                    print(pos, data_value)
            except KeyboardInterrupt:
                print("User terminated motion!")
                break
            except ValueError:
                print("caught an exception regarding Float conversion")
                break
            finally:
                # This code always executes after leaving the try statement
                pass

        self._run = False
        self.set_ao_zero()
        # self.zenithVelocityChanged.emit(0)
        ## Read position again
        time.sleep(0.1)
        pos = self.get_ser_ze_pos()
        # self.conn.send(['ze_pos', pos])
        #        print ('EL Set to position: ', str(pos))
        #        print ('Position Set!')
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

    def set_ze_speed_relation(self, voltage: float):
        # Set the speed of the motor in RPM/1V. Default is 40, which would roughly turn the telescope 1 degree/second. ASCII code for serial is AIN.VSCALE. NOTE: AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT!
        if self.ser_ze.is_open:
            command = "AIN.VCALE " + str(voltage) + "\r\n"
            command = command.encode()
            self.ser_ze.write(command)
            self.ser_ze.readline()
            ze_speed = self.ser_ze.read_until(b"\r\n")
            print("ZA speed set to: ", ze_speed)  ###THIS MAY BREAK
            # self.zenithVelocityChanged(ze_speed)
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

