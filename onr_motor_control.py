from __future__ import absolute_import, division, print_function

# from builtins import *  # @UnusedWildImport
from ctypes import cast, POINTER, c_ushort, c_ulong
from math import pi, sin
from time import sleep
import time

# from uldaq import ScanOptions, FunctionType, Status, InterfaceType
from uldaq import DaqDeviceInfo
import uldaq as ul
import numpy as np
import matplotlib.pyplot as plt
import sys, os
import pdb
import serial
import serial.tools.list_ports
import struct
from pyModbusTCP.client import ModbusClient
from telnetlib import Telnet

# import keyboard
from datetime import date
import glob
from pynput import keyboard
import onrkidpy
import h5py
import logging


##By D. Cunnane (and many others who contributed snippets of code, knowingly or unknowingly)
##This program is for programmable control of the motor system on the SKPR (ONR) telescope. The AZ motors are Kollmorgen AKM33H-ANGNR-00 models. A primary/secondary configuration is used to avoid backtracking/slipping (Not currently in use). The motors are controlled by a pair of S70662-NAPANA servo drives using 115 V (limits the speed of the motor). The position of telescope in the AZ direction is being read through a serial connection with the primary motor from an internal encoder. The control of the AZ motion is done through the analog output of a measurement computing 2408-DAQ (Output 1 of 2). The outputs of this DAQ is 16 Bit +/-10V. The inputs are 24 Bit +/- 10V range. The inputs can be used to measure the position, speed, etc of the motors, but are susceptible to noise and so absolute position can be an issue, which is why serial was used in the end (I did not actually test how noisy it would be, so given the high gearing ratio (1170) it might be within our specs for 0.01 degree resolution positioning. The EL motor is a AKM54K-ANGNR-00 controlled by an AKD-P01206-NBCN-0000 drive. The EL position is read through a telnet connection directly to the ethernet address of the EL motor controller.  Control is also done through an analog signal from the 2408-DAQ (Output 2 of 2).

##AZ encoder has 170 counts per turn (PGEARI = 170, PGEARO = 1). SRND = -100000, ERND = 100000. Actual position (PFB) = position * PGEARI/PGEARO. AnalogOut PFB = 10V * (PFB-SRND)/(ERND-SRND)


"220830 Updates (Version 2.0)"
"-Get rid of windows DAQ functions"
"-Normalize AZ position units (S700 Unit wants integer value from 180,000 to -180,000, but want user to input and readout in degrees, 180.000 to -180.000."
"-Add beam map mode with position and time data saved"
"-Change analog out expression to a function for creating well-controlled software limits (esp. in AZ)"

"Things to test on system! 1) AZ,EL speed relation, 2) Software limits, 3)Homing, 4) Saving, 5) oscillating mode."


"EXTREMELY IMPORTANT!!! THERE IS NO HARDWARE LIMIT SWITCHES YET INSTALLED AND INTERNAL SOFTWARE LIMIT SWITCHES ARE NOT AVAILABLE IN ANALOG CONTROL MODE. THIS PROGRAM IS THE ONLY PLACE THAT LIMIT SWITCHES ARE IN PLACE. THE SYSTEM SHOULD NOT BE CONTROLLED OUTSIDE THIS SOFTWARE."


def getdtime():
    """
    Gets the time in fractional hours since midnight
    of the current day with a precision down to seconds.

    :return: Fraction of hours since midnight

    :rtype: Float
    """
    t = time.localtime()
    t1 = time.mktime(t)  # current time

    t2 = time.struct_time(
        (
            t.tm_year,
            t.tm_mon,
            t.tm_mday,
            0,
            0,
            0,
            t.tm_wday,
            t.tm_yday,
            t.tm_isdst,
            t.tm_zone,
            t.tm_gmtoff,
        )
    )
    t2 = time.mktime(t2)
    return (t1 - t2) / 3600


os.system("")  ##I forget why I need this
# main_opts= ['Initialize System', 'Set AZ to Home position', 'Set EL to Home position','Get AZ Position','Get EL Position', 'Set AZ and EL to Home position', 'Set AZ location(Degrees)', 'Set EL location(Degrees)', 'Oscillate AZ','Set max AZ speed (RPM)', 'Exit']
main_opts = [
    "Initialize System (Obsolete!)",
    "Set AZ to Home position",
    "Set EL to Home position (Not Setup Yet!)",
    "Get AZ Position",
    "Get EL Position",
    "Set AZ position",
    "Set EL Position",
    "Observation Mode",
    "AZ Jog Mode",
    "Set max AZ speed (RPM)",
    "Exit",
    "Beam Mapping Mode",
    "20 Deg AZ Scan",
    "10 Deg AZ Scan",
    "10 Deg AZ Scan (2 Scans)",
    "10 Deg AZ Scan (8 Scans)",
    "10 Deg AZ Scan (32 Scans)",
    "Communicate with AZ controller",
]  ##Temporary
captions = []


class SKPR_Motor_Control:
    def __init__(self):
        self.daq_dev_info = None
        self.a_out_info = None
        self.ul_range_out = None
        self.a_out_flags = None
        self.use_device_detection = None
        self.dev_id_list = None
        self.board_num = None
        self.memhandle = None
        self.az_channel_out = 1  ###el is channel 0 on version 2 of panel
        self.el_channel_out = 0
        self.pfb = None  ##AZ position
        self.pos = None  ##EL position
        self.ser_AZ = None
        self.ser_EL = None
        self.pos_sw_lim = 181.000
        self.neg_sw_lim = -181.000
        self.pos_el_sw_lim = -np.inf
        self.neg_el_sw_lim = -np.inf
        self.limits = (self.neg_sw_lim, self.pos_sw_lim)
        self.az_home_pos = 0
        self.Initialized = False
        self.EL_en = False
        self.AZ_en = False

    def key_break(self, key):
        if key == keyboard.Key.space:
            return False

    def Initialize_System(self):
        ##First initilize DAQ for analog velocity control
        # Connect to DAQ and define for class
        try:
            devices = ul.get_daq_device_inventory(ul.InterfaceType.ANY)
            #            print(devices)
            device = devices[0]
            daq_dev_info = ul.DaqDevice(device)
            daq_dev_info.connect()
            self.daq_dev_info = daq_dev_info
            # Configure the analog outputs
            a_out_info = self.daq_dev_info.get_ao_device()
            self.a_out_info = a_out_info
            ul_range_out = a_out_info.get_info().get_ranges()[0]
            a_out_flags = ul.AOutFlag.DEFAULT
            self.ul_range_out = ul_range_out
            self.a_out_flags = a_out_flags
            data_value = self.convert_A_to_D(0, [-10, 10], 16)
            # set output to zero
            self.a_out_info.a_out(
                self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )
            #pdb.set_trace()
            self.a_out_info.a_out(
                self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )

        except OSError:
            print(
                "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
            )
        ##Now initialize serial communication with S700 for high resolution positioning of AZ motors...

        "These lines can help find the port in an intelligent way but for now, I know it is either USB1 or USB2"
        ports = serial.tools.list_ports.comports()
        port_counter = 0
        port_array = []
        for dev in range(len(ports)):
            # port_array[dev] = str(ports[dev].manufacturer)
            # print('dev #: ', dev)
            if ports[dev].manufacturer == "Prolific Technology Inc.":
                AZport = ports[dev].device

        # AZport = '/dev/ttyUSB1'
        # port = '/dev/ttyUSB1' ##I can set up a find usb vendor for port but need to test
        br = 38400
        to = 2
        p = "N"
        ser_AZ = serial.Serial(
            AZport, baudrate=br, timeout=to, bytesize=8, parity="N", stopbits=1
        )

        if ser_AZ.is_open:
            print("AZ Motor Connected to original port.")
        else:
            print("Could not communicate with AZ controller. System not initialized.")
        self.ser_AZ = ser_AZ
        pfb = self.AZ_Ser_Pos()
        self.pfb = pfb
        self.Initialized = True
        print("\033[33m Telescope AZ Position is: \033[0m", pfb)

        ##Now EL motion Outdated code using ModbusClient, Better way is to use Telnet, which behaves similar to serial

        AKD1 = "169.254.250.165"
        AKD2 = "169.254.250.166"  ##switches back and forth between these two channels when faults occur.
        ELport = 23
        Gear_ratio = 258

        ADDR_PL_FB = 588  ##This is the position loop feedback. Includes some offset parameter and error based on homing position. Appropriate for this application, though I need to figure out the resolution.
        ADDR_FB1_P = 1610  ##This is the absolute position from the FB1 (resolver).

        # code = 'DRV.ACTIVE\r\n'
        # write_code = code.encode('ascii') ##Convert code to bitwise
        ser_EL = Telnet(host=AKD1, port=ELport)
        self.ser_EL = ser_EL

        ser_EL.open(host=AKD1, port=ELport)

        # ser_EL.write(write_code) ##I shouldn't need the encode steps
        ser_EL.write(b"DRV.ACTIVE\r\n")

        status = ser_EL.read_until(b"\r", 0.1)

        status = status.decode()

        status = float(status.split("\r")[0])

        if status == 1:
            self.Initialized = True

            print("EL Motor Connected and software already enabled.")

        else:
            ser_EL.write(b"DRV.EN\r\n")
            sw_en = ser_EL.read_until(b"\r", 0.1)
            print("EL Motor Connected and Software enabled by Python")
        pos = self.EL_Ser_Pos()
        self.pos = pos
        #        print("Pos" + str(0) +"=" + str(pos))
        print("\033[33m Telescope EL Position is: \033[0m", str(pos))

    def init_test(self):
        if self.Initialized == False:
            self.Initialize_System()

    def set_ao_value(self, value, channel):
        # Seems eaiser that calling the command every time, will replace where needed if time.
        self.a_out_info.a_out(channel, self.ul_range_out, self.a_out_flags, value)

    ##Set motor analog control to zero. Needed for an exception to stop the motors in the event of an error (mostly due to connection issues with el controller)
    def set_ao_zero(self):
        data_value_zero = self.convert_A_to_D(0, [-10, 10], 16)
        # set output to zero
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value_zero
        )
        self.a_out_info.a_out(
            self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value_zero
        )

    ##Set AZ Home Position
    def Set_AZ_Home(self):
        # Set current position of the motor to zero. ASCII code for serial is NREF
        ser = self.ser_AZ
        if ser.is_open:
            command = "NREF\r\n"
            command = command.encode()
            ser.write(command)
            ser.readline()
            pfb = ser.read_until(b"\r\n")
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            print("Home Set.")
        else:
            print("Home command not executed. Check connection with S700")

    ##Read AZ Serial Position
    def AZ_Ser_Pos(self):
        ser_AZ = self.ser_AZ
        pfb_jic = self.pfb
        try:
            if ser_AZ.is_open:
                ser_AZ.write(b"PFB\r\n")
                ser_AZ.readline()
                pfb = ser_AZ.read_until(b"\r\n")
                pfb = float(pfb.decode()) / 10000.0

                # ser_AZ.write(b'ANDB\r\n')
                # ser_AZ.readline()
                # deadband = ser_AZ.read_until(b'\r\n')
                # deadband = deadband.decode()
                # print(deadband, 'is the deadband')
                self.pfb = pfb
                ser_AZ.reset_input_buffer()
                ser_AZ.reset_output_buffer()
                return pfb

        except ValueError:
            print(
                "Value error communicating with AZ controller. Position set to most recent read"
            )
            return pfb_jic

    ##Read EL Serial Position
    def EL_Ser_Pos(self):
        pos_jic = self.pos
        try:
            code = "PL.FB\r\n"
            write_code = code.encode("ascii")
            port = 23
            self.ser_EL.write(write_code)
            pos = self.ser_EL.read_until(b"]", 0.1)
            pos = pos.decode()
            pos = float(pos.split(" ")[0].split(">")[-1])
            # pos = int(pos)
            self.pos = pos
            return pos
        except ValueError:
            print(
                "Value error communicating with AZ controller. Position set to most recent read"
            )
            return pos_jic

    ##Set EL Home Position
    def set_EL_Home(self):
        # Set current position of the motor to zero.
        ser_EL = self.ser_EL
        pos = self.EL_Ser_Pos()
        pdb.set_trace()
        ser_EL.write(b"DRV.DIS\r\n")
        sw_en = ser_EL.read_until(b"\r\n", 0.1)
        time.sleep(1)
        offset_command = "FB1.OFFSET " + str(-1 * pos) + "\r\n"
        ser_EL.write(offset_command.encode("ascii"))
        ret = ser_EL.read_until(b"\r\n")
        ser_EL.write(b"DRV.EN\r\n")
        sw_en = ser_EL.read_until(b"\r", 0.1)
        pdb.set_trace()
        print("EL Home Set.")

    def setELposition(self, el_set_pos, scan_mode=False):
        el_set_pos = float(el_set_pos)
        data_value_zero = self.convert_A_to_D(0, [-10, 10], 16)  # For windows
        # set output to zero
        self.a_out_info.a_out(
            self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value_zero
        )

        ##confirm position
        pos = self.EL_Ser_Pos()
        if scan_mode:
            this_az = self.AZ_Ser_Pos()
            position_data = []
        counter = 0

        ##Run loop
        while abs(pos - el_set_pos) > 0.003:
            try:
                # Choose direction of motion
                if pos > el_set_pos:
                    direction = -1
                else:
                    direction = 1

                #                if keyboard.is_pressed("space"): ###DOES THIS WORK IN UBUNTU?
                #                    print("User terminated motion!")
                #                    break
                "I still need to double check motion direction for accuracy"
                ##Set Speed faster if more travel needed
                if scan_mode:
                    data_value = direction * self.convert_A_to_D(1.0, [-10, 10], 16)
                else:
                    if (
                        abs(pos - el_set_pos) > 15
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * self.convert_A_to_D(
                            7.25, [-10, 10], 16
                        )
                    elif (
                        abs(pos - el_set_pos) < 15
                    ):  ##If we are far from the setpoint, go at max speed
                        this_speed = 0.35 * abs(pos - el_set_pos) + 0.30
                        data_value = direction * self.convert_A_to_D(
                            this_speed, [-10, 10], 16
                        )

                # elif abs(pos-el_set_pos) < 5:##set to slower speed as approaching setpoint
                # data_value = direction*self.convert_A_to_D(2,[-10,10],16)
                # elif abs(pos-el_set_pos) < 1:##set to slower speed as approaching setpoint
                # self.set_EL_speedrelation(10)
                # data_value = direction*self.convert_A_to_D(.35,[-10,10],16)
                # else:##else: set to slowest speed
                #    data_value = direction*self.convert_A_to_D(.35,[-10,10],16)

                self.a_out_info.a_out(
                    self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
                )
                pos = self.EL_Ser_Pos()
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
                data_value = self.convert_A_to_D(0, [-10, 10], 16)
                self.a_out_info.a_out(
                    self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
                )
                break
            except ValueError:
                print("caught an exception regarding Float conversion")
                break
            finally:
                # This code always executes after leaving the try statement
                pass

        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        ## Read position again
        time.sleep(0.1)
        pos = self.EL_Ser_Pos()
        #        print ('EL Set to position: ', str(pos))
        #        print ('Position Set!')
        if scan_mode:
            return position_data

    ##Initialize DAQ
    def Exit_System(self):
        self.ser_AZ.close()
        self.ser_EL.close()
        "Need a try statement for when nothing was ever intialized"

    def Beammap_mode(
        self, AZ_deg, AZ_n_step, EL_deg, EL_n_step, int_time, position_data_file
    ):
        """
        :deprecated:
        """
        AZ_step_size = AZ_deg / (AZ_n_step - 1)
        EL_step_size = EL_deg / (EL_n_step - 1)
        AZ_pos_array = self.pfb - (AZ_deg / 2) + np.arange(AZ_n_step) * AZ_step_size
        EL_pos_array = self.pos - (EL_deg / 2) + np.arange(EL_n_step) * EL_step_size
        self.AZ_Ser_Pos()
        self.EL_Ser_Pos()
        position_data = []
        total_time_0 = time.time()

        def integrate_data_update(position_data, int_time, reqAZ, reqEL):
            pfb = self.AZ_Ser_Pos()
            pos = self.EL_Ser_Pos()
            print(
                "AZ Actual  Position = "
                + "{:.3f}".format(pfb)
                + ", EL Actual  Position = "
                + "{:.3f}".format(pos)
            )
            start_time = time.time()
            time.sleep(int_time)
            end_time = time.time()
            #            position_data = np.append(position_data,[pfb, pos, start_time, end_time])
            position_data = np.append(
                position_data, [reqAZ, reqEL, start_time, end_time]
            )
            return position_data

        # position_data = integrate_data_update(position_data,int_time)
        for AZ_count, AZ_pos in enumerate(AZ_pos_array):
            self.setAZposition(AZ_pos)
            for EL_count, EL_pos in enumerate(EL_pos_array):
                self.setELposition(EL_pos)
                print("")
                print(
                    "AZ Request Position = "
                    + "{:.3f}".format(AZ_pos)
                    + ", EL Request Position = "
                    + "{:.3f}".format(EL_pos)
                    + ", AZ count = "
                    + "{}".format(AZ_count + 1)
                    + "/"
                    + "{}".format(AZ_n_step)
                    + ", EL count = "
                    + "{}".format(EL_count + 1)
                    + "/"
                    + "{}".format(EL_n_step)
                )
                position_data = integrate_data_update(
                    position_data, int_time, AZ_pos, EL_pos
                )
            EL_pos_array = np.flipud(EL_pos_array)
        #            position_data = integrate_data_update(position_data,int_time)
        total_time = time.time()
        print(total_time - total_time_0)
        np.savez(
            position_data_file,
            az=position_data[0::4],
            el=position_data[1::4],
            start_time=position_data[2::4],
            end_time=position_data[3::4],
        )

    # Note that this has been modified to create an HDF5 file instead of a npz file.
    def AZ_scan_mode(
        self, AZ_start, AZ_stop, position_data_file, n_repeats=1, position_return=True
    ):
        AZ_start_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        AZ_end_buffer = 0.0  # 0.2 * np.sign(AZ_stop-AZ_start)
        current_AZ = self.AZ_Ser_Pos()
        current_EL = self.EL_Ser_Pos()
        AZ_start += current_AZ
        AZ_stop += current_AZ
        dummy = self.setAZposition(AZ_start - AZ_start_buffer)
        for i_rep in np.arange(n_repeats):
            if np.mod(i_rep, 2) == 0:
                self.setELposition(current_EL)
                this_position_data = self.setAZposition(
                    AZ_stop + AZ_end_buffer + 0.5, scan_mode=True
                )
                if i_rep == 0:
                    position_data = this_position_data
                else:
                    position_data = np.append(position_data, this_position_data)
            if np.mod(i_rep, 2) == 1:
                self.setELposition(current_EL + 0.04)
                this_position_data = self.setAZposition(
                    AZ_start - AZ_start_buffer - 0.5, scan_mode=True
                )
                position_data = np.append(position_data, this_position_data)

        # np.savez(position_data_file, az = position_data[0::3],el = position_data[1::3],time = position_data[2::3],az_start=AZ_start,
        #  az_stop=AZ_stop,el_start=np.nan,el_stop=np.nan)
        f = h5py.File(position_data_file, "a")
        f.create_dataset("az_tel", data=position_data[0::3])
        f.create_dataset("el_tel", data=position_data[1::3])
        f.create_dataset("timestamp_tel", data=position_data[2::3])
        f.create_dataset("optical_visibility", data=['****'])
        f.close()
        time.sleep(0.5)
        if position_return:
            dummy = self.setAZposition(current_AZ)
        #        else:
        #          dummy = self.setAZposition(current_AZ+15)
        print("Scan Complete")

    def EL_scan_mode(self, EL_start, EL_stop, position_data_file):
        EL_start_buffer = 0.2 * np.sign(EL_stop - EL_start)
        EL_end_buffer = 0.2 * np.sign(EL_stop - EL_start)
        dummy = self.setELposition(EL_start - EL_start_buffer, scan_mode=True)
        position_data = self.setELposition(EL_stop + EL_end_buffer, scan_mode=True)
        np.savez(
            position_data_file,
            az=position_data[0::3],
            el=position_data[1::3],
            time=position_data[2::3],
        )

    ##Self explanatory functions that might be used, particularly because the DAQ inputs and outputs have different resolution.
    def convert_A_to_D(self, A, ARANGE, Bits, linux_flag=True):
        "A is the value you want to convert, ARANGE is an array with min and max of range, Bits is resolution of A/D"
        values = np.linspace(ARANGE[0], ARANGE[1], (2**Bits) - 1)
        D = int(np.argmin(abs(values - A)))
        if linux_flag:
            D = A
        return D

    def convert_D_to_A(self, D, ARANGE, Bits, linux_flag=True):
        ##D is the value you want to convert, ARANGE is an array with min and max of range, Bits is resolution of A/D
        values = np.linspace(ARANGE[0], ARANGE[1], (2**Bits) - 1)
        A = values[D]
        return A

    def set_AZ_speedrelation(self, az_speed_voltage):
        # Set the speed of the motor in RPM/10V. Default is 500, which would roughly turn the telescope 2.5 degree/second for 10 V input. ASCII code for serial is VSCALE1. AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT! Needs more testing from Ubuntu, I think there is a lower limit set in the S700.
        ser = self.ser_AZ
        if ser.is_open:
            command = "VSCALE1 " + str(az_speed_voltage) + "\r\n"
            command = command.encode()
            ser.write(command)
            ser.readline()
            AZ_speed = ser.read_until(b"\r\n")
            print("AZ speed set to: ", AZ_speed)  ###THIS MAY BREAK
            ser.reset_input_buffer()
            ser.reset_output_buffer()

    def set_EL_speedrelation(self, el_speed_voltage):
        # Set the speed of the motor in RPM/1V. Default is 40, which would roughly turn the telescope 1 degree/second. ASCII code for serial is AIN.VSCALE. NOTE: AZ VALUE IS PER 10 VOLTS AND EL VALUE IS PER 1 VOLT!
        ser = self.ser_EL
        if ser.is_open:
            command = "AIN.VCALE " + str(el_speed_voltage) + "\r\n"
            command = command.encode()
            ser.write(command)
            ser.readline()
            EL_speed = ser.read_until(b"\r\n")
            print("EL speed set to: ", EL_speed)  ###THIS MAY BREAK
            ser.reset_input_buffer()
            ser.reset_output_buffer()

    def talk_to_az(self, cmd):
        # Function to test ASCII commands for the S700 motor controller
        ser = self.ser_AZ
        if ser.is_open:
            command = cmd + "\r\n"
            command = command.encode()
            ser.write(command)
            ser.readline()
            response = ser.read_until(b"\r\n")
            response = str(response.decode())
            print(response)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

    def setAZ_home_position(self):
        # Initial communication with MCC DAQ. I should do this in a more appropriate way. The only reason it works now is because I have already initiated the DAQ with my computer.
        # a_in_info = daq_dev_info.get_ai_info()
        # channel_in = 0
        # ul_range_in = a_in_info.supported_ranges[0]
        # a_out_info = self.daq_dev_info.get_ao_info()
        # channel_out = 0
        # ul_range_out = a_out_info.supported_ranges[0]
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        # set output to zero
        # ul.a_out(self.board_num, channel_out, ul_range_out, data_value)
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        # Measure input voltage
        # voltage_in = voltage_in_array[ul.a_in_32(board_num, channel_in, ul_range_in)]

        ##confirm position
        pfb = self.AZ_Ser_Pos()
        counter = 0
        ##Run loop
        while abs(pfb - self.az_home_pos) > 10:
            # Choose direction of motion
            if pfb > self.az_home_pos:
                direction = 1
            else:
                direction = -1

            "I still need to double check motion direction for accuracy"
            ##Set Speed faster if more travel needed
            if (
                abs(pfb - self.az_home_pos) > 10000
            ):  ##If we are far from the setpoint, go at max speed
                data_value = direction * self.convert_A_to_D(10, [-10, 10], 16)
            elif (
                abs(pfb - self.az_home_pos) < 10000
            ):  ##If we are far from the setpoint, go at max speed
                data_value = direction * self.convert_A_to_D(5, [-10, 10], 16)
            elif (
                abs(pfb - self.az_home_pos) < 1000
            ):  ##set to slower speed as approaching setpoint
                data_value = direction * self.convert_A_to_D(0.35, [-10, 10], 16)
            elif (
                abs(pfb - self.az_home_pos) < 200
            ):  ##set to slower speed as approaching setpoint
                self.set_AZ_speedrelation(10)
                data_value = direction * self.convert_A_to_D(0.35, [-10, 10], 16)
            else:  ##else: turn off motor if something is out of whack.
                data_value = direction * self.convert_A_to_D(0, [-10, 10], 16)
            # ul.a_out(self.board_num, channel_out, ul_range_out, data_value)##set the data value based on criterion in while loop
            self.a_out_info.a_out(
                self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )
            pfb = self.AZ_Ser_Pos()
            counter = counter + 1
            if 100 % counter == 0:
                print(pfb, data_value)
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        # ul.a_out(self.board_num, channel_out, ul_range_out, data_value)
        time.sleep(1)
        ## Read position again
        pfb = self.AZ_Ser_Pos()
        print("Homed to position: ", pfb)
        self.set_AZ_speedrelation(1000)

    def setAZposition(self, az_set_pos, scan_mode=False):
        # I want to accept a number in degrees, but put the number in the integer value desired by S700 controller
        # AZ controlled by 2 motors, the first to actually move the telescope, the second to put some tension on the gear for avoiding any backlash. Currently the secondary motor is disabled, probably providing little to no torque, but given the huge gearing ratio, it probably helps with backlash. The next easiest technique would be to run the secondary in "analog torque" mode, setting the zero value to some small torque. This could be improved by increasing the torque during motion and reducing when the first motor is not moving (probably by changing the zero value torque, since both analog outs are already in use). The proper way to do it, and the reason we were sold these S700 controllers is called RDP per the kollmorgen tech guy but my guess is he meant prd cogging mode.
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        # Measure input voltage

        ##confirm position
        pfb = self.AZ_Ser_Pos()
        if scan_mode:
            this_el = self.EL_Ser_Pos()
            position_data = []
        counter = 0
        ##Run loop
        pfb_time = time.time()

        while (
            np.abs(pfb - az_set_pos) > 0.016 ##currently overshoots by .018 degrees on average
            and pfb > self.neg_sw_lim
            and pfb < self.pos_sw_lim
        ):
            try:
                #get start time
                
                # Choose direction of motion. Negative Voltage goes clockwise when looking down at the telesecope from the sky!!
                #                if keyboard.is_pressed("space"):
                #                    print("User terminated motion!")
                #                   break
                if az_set_pos > pfb:
                    direction = -1
                else:
                    direction = 1
                "I still need to double check motion direction for accuracy"
                ##Set Speed faster if more travel needed
                if scan_mode:
                    # data_value = direction*self.convert_A_to_D(3.,[-10,10],16)
                    if (
                        abs(pfb - az_set_pos) > 0.5
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * self.convert_A_to_D(6.0, [-10, 10], 16)
                        #print(data_value)
                        #print("This is the voltage output")
                    else:
                        data_value = direction * self.convert_A_to_D(2.0, [-10, 10], 16)
                else:
                    if (
                        abs(pfb - az_set_pos) > 15
                    ):  ##If we are far from the setpoint, go at max speed
                        data_value = direction * self.convert_A_to_D(
                            7.25, [-10, 10], 16
                        )
                    elif (
                        abs(pfb - az_set_pos) < 15
                    ):  ##If we are far from the setpoint, go at max speed
                        this_speed = 0.35 * abs(pfb - az_set_pos) + 1.5
                        data_value = direction * self.convert_A_to_D(
                            this_speed, [-10, 10], 16
                        )

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
                self.a_out_info.a_out(
                    self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
                )
                #pdb.set_trace()
                this_dt = time.time() - pfb_time
                while this_dt < 0.02:
                   this_dt = time.time() - pfb_time
                   time.sleep(1.e-4)
                pfb_time = time.time()
                pfb = self.AZ_Ser_Pos()

                if scan_mode:
                    position_data = np.append(position_data, [pfb, this_el, pfb_time])
                    
                counter = counter + 1

            except KeyboardInterrupt:
                print("User terminated motion!")
                data_value = self.convert_A_to_D(0, [-10, 10], 16)
                self.a_out_info.a_out(
                    self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
                )
                break

            except ValueError:
                print("caught an exception regarding Float conversion")
                break
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        ## Read position again
        time.sleep(1)
        pfb = self.AZ_Ser_Pos()
        #        print ('Set to position: ', pfb)
        if scan_mode:
            return position_data

    def jog_AZ_pos(self):
        ##Start by ensuring analog out value is zero (no movement)
        global speed
        speed = 1  ##A number out of 10
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        print("speed set to: " + str(speed))
        ##Set speed to 10% of maximum to start

        data_value = self.convert_A_to_D(speed, [-10, 10], 16)

        def move_forward():
            data_value = self.convert_A_to_D(speed, [-10, 10], 16)
            self.a_out_info.a_out(
                self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )
            print("moving forward, speed set to: " + str(speed))

        def move_backward():
            data_value = self.convert_A_to_D(-1 * speed, [-10, 10], 16)
            self.a_out_info.a_out(
                self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )
            print("moving backward, speed set to: " + str(speed))

        def stop():
            data_value = self.convert_A_to_D(0, [-10, 10], 16)
            self.a_out_info.a_out(
                self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
            )
            print("stopped!")

        def increase_speed():
            global speed
            if speed < 10:
                speed = speed + 1

            else:
                speed = 10

            print("Speed increased to: " + str(speed))
            return speed

        def decrease_speed():
            global speed
            if speed > 1:
                speed = speed - 1
            else:
                speed = 1
            print("Speed decreased to: " + str(speed))
            return speed

        keyboard.add_hotkey("left", move_forward)  # unmute on keydown
        keyboard.add_hotkey("space", stop)  # mute on keyup
        keyboard.add_hotkey("right", move_backward)  # unmute on keydown
        keyboard.add_hotkey("up", increase_speed)  # unmute on keydown
        keyboard.add_hotkey("down", decrease_speed)  # mute on keyup
        # keyboard.add_hotkey('space',end_all)
        keyboard.wait("esc")  # wait forever
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.az_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )
        print("Leaving Jogging Mode...")

    def AZ_oscillate(self, total_t, freq, degrees):
        # self.set_AZ_speedrelation(150)##Not sure how fast this will be right now, can adjust later
        start_time = time.time()
        t = 0.0
        pos_osc = self.pos
        while t < total_t:
            if keyboard.is_pressed("space"):
                print("User terminated motion!")
                break
            self.setELposition(pos_osc + degrees / 2)
            self.setELposition(pos_osc - degrees / 2)
            t = time.time() - start_time
        data_value = self.convert_A_to_D(0, [-10, 10], 16)
        self.a_out_info.a_out(
            self.el_channel_out, self.ul_range_out, self.a_out_flags, data_value
        )

    def menu(self, captions, options):
        print("\t" + captions[0] + "\n")
        for i in range(len(options)):
            if i < 9:
                print(
                    "\t" + "\033[32m" + str(i) + " ..... " "\033[0m" + options[i] + "\n"
                )
        print("\t" + captions[1] + "\n")
        for i in range(len(options)):
            if i >= 9:
                print(
                    "\t" + "\033[32m" + str(i) + " ..... " "\033[0m" + options[i] + "\n"
                )
        opt = input()
        return opt

    def makePlotMenu(self, options):
        for i in range(len(options)):
            print("\t" + "\033[32m[" + str(i) + "]\033[0m ..... " + options[i] + "\n")
        opt = int(input("Please select from above options:"))
        return opt

    def menu(self, captions, options):
        print("\t" + captions[0] + "\n")
        for i in range(len(options)):
            if i < 9:
                print(
                    "\t" + "\033[32m" + str(i) + " ..... " "\033[0m" + options[i] + "\n"
                )
        print("\t" + captions[1] + "\n")
        for i in range(len(options)):
            if i >= 9:
                print(
                    "\t" + "\033[32m" + str(i) + " ..... " "\033[0m" + options[i] + "\n"
                )
        opt = input()
        opt = int(opt)
        return opt

    def main_opt(self, opt):
        if opt == 0:
            try:
                self.Initialize_System()
                print("System initiliazed")
                # pdb.set_trace()
            # except OSError:
            # print ('\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m')
            # except IndexError:
            # print ('\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m')
            except KeyboardInterrupt:
                pass

        if opt == 1:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                self.setAZ_home_position()

        if opt == 2:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                self.set_EL_Home()

        if opt == 3:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                self.AZ_Ser_Pos()
                print("The AZ position is: ", self.pfb)

        if opt == 4:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                self.EL_Ser_Pos()
                print("The EL position is: ", self.pos)

        if opt == 5:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                az_set_pos_req = float(
                    input(
                        "What position do you want to set the motor (-180.000 to 180.000 degrees)?"
                    )
                )
                az_set_pos = az_set_pos_req
                if az_set_pos > 180000 or az_set_pos < -180000:
                    print("This position is outside the limits of the Telescope!")
                else:
                    self.setAZposition(az_set_pos)
                print("The AZ position is: ", self.pfb)

        if opt == 6:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    pos = self.pos
                    el_set_pos = float(
                        input("What position do you want to set the motor (0-99450)?")
                    )
                    self.setELposition(el_set_pos)
                    print("The EL position is: ", self.pos)
            except:
                self.set_ao_zero()
                print(
                    "\033[93m UnboundLocalError: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )

        if opt == 7:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    print("Welcome to the SKPR Telescope Observation Mode!")
                    osc_deg = float(
                        input(
                            "How many degrees in AZ do you want to observe? (-180.000 to 180.000 degrees)?"
                        )
                    )
                    osc_deg = osc_deg
                    ##Set EL position to some nominal height
                    ##Set AZ position, but not too far since telescope is positionally confined
                    ##Oscillate AZ rotation.
                    # az_set_pos = int(input('What position do you want to set the motor (0-99450)?'))
                    # if az_set_pos > 99450 or az_set_pos < 0:
                    # print('This position is outside the limits of the Telescope!')
                    # else:
                    # self.setAZposition(az_set_pos)
                    # print("The AZ position is: ", self.pfb)
                    pos = self.pos
                    #                    el_set_pos = 20000000
                    #                    self.setELposition(pos+el_set_pos)
                    #                    print("The EL position is: ", self.pos)
                    self.AZ_oscillate(30.0, 0.0, osc_deg)
                    pos = self.pos
            #                    el_set_pos = -20000000
            #                    self.setELposition(pos+el_set_pos)
            #                    print("The EL position is: ", self.pos)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass
            except:
                print(
                    "\033[93m UnboundLocalError: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
        if opt == 8:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                self.jog_AZ_pos()
                self.set_ao_zero()

        if opt == 9:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                az_speed_voltage = int(input('What speed in RPM do you want for maximum (0-1000 for safety).'))
                if az_speed_voltage > 1000 or az_speed_voltage < 0:
                    print('This speed is outside the limits of the Telescope!')
                else:
                    self.set_AZ_speedrelation(az_speed_voltage)
                print("The AZ position is: ", self.pfb)
                #self.Set_AZ_Home()

        if opt == 10:
            self.Exit_System()
            print("Leaving...")
            exit()

        if opt == 11:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    filename = str(input("Input filename (as '.npz')"))
                    #                    self.Beammap_mode(2.,41,2.,41,1.5,filename)
                    #                    self.Beammap_mode(2.,5,2.,5,1.5,filename)
                    #                    self.Beammap_mode(2.2,56,2.2,56,1.,filename)
                    #                    self.Beammap_mode(2.4,56,0.4,10,1.,filename)
                    self.Beammap_mode(2.4, 56, 2.4, 56, 1.0, filename)
                    ##print("Welcome to the SKPR Telescope Beam Map  Mode!")
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass
        #            except:
        #                print ('\033[93m UnboundLocalError: DAQ could not be initialized: Check comm port and power supply\033[0m')
        #                self.set_ao_zero() ##For troubleshooting and looking at variables.
        ##            pdb.set_trace()

        if opt == 12:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    savefile = onrkidpy.get_filename(type="AZEL") + ".h5"
                    self.AZ_scan_mode(0.0, 10.0, savefile, position_return=True)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass

        if opt == 13:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    #                    filename = str(input("Input filename (as '.npz')"))
                    yy = "{}".format(date.today().year)
                    mm = "{}".format(date.today().month)
                    if date.today().month < 10:
                        mm = "0" + mm
                    dd = "{}".format(date.today().day)
                    if date.today().day < 10:
                        dd = "0" + dd
                    yymmdd = yy + mm + dd
                    this_dir_files = glob.glob("/home/peter/kidPy/data/" + yymmdd + "*")
                    if np.size(this_dir_files) == 0:
                        setnum = "0"
                    else:
                        this_dir_files.sort()
                        setnum = "{}".format(int(this_dir_files[-1][-4:]))
                    filename = (
                        yymmdd
                        + "_Device_aSi1_Channel2_set"
                        + setnum
                        + "/telescope_data"
                    )
                    print(filename)
                    self.AZ_scan_mode(0.0, 10.0, filename)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass

        if opt == 14:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    #                    filename = str(input("Input filename (as '.npz')"))
                    yy = "{}".format(date.today().year)
                    mm = "{}".format(date.today().month)
                    if date.today().month < 10:
                        mm = "0" + mm
                    dd = "{}".format(date.today().day)
                    if date.today().day < 10:
                        dd = "0" + dd
                    yymmdd = yy + mm + dd
                    this_dir_files = glob.glob("/home/peter/kidPy/data/" + yymmdd + "*")
                    if np.size(this_dir_files) == 0:
                        setnum = "0"
                    else:
                        this_dir_files.sort()
                        setnum = "{}".format(int(this_dir_files[-1][-4:]))
                    filename = (
                        yymmdd
                        + "_Device_aSi1_Channel2_set"
                        + setnum
                        + "/telescope_data"
                    )
                    print(filename)
                    self.AZ_scan_mode(0.0, 10.0, filename, n_repeats=2)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass

        if opt == 15:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    #                    filename = str(input("Input filename (as '.npz')"))
                    yy = "{}".format(date.today().year)
                    mm = "{}".format(date.today().month)
                    if date.today().month < 10:
                        mm = "0" + mm
                    dd = "{}".format(date.today().day)
                    if date.today().day < 10:
                        dd = "0" + dd
                    yymmdd = yy + mm + dd
                    this_dir_files = glob.glob("/home/peter/kidPy/data/" + yymmdd + "*")
                    if np.size(this_dir_files) == 0:
                        setnum = "0"
                    else:
                        this_dir_files.sort()
                        setnum = "{}".format(int(this_dir_files[-1][-4:]))
                    filename = (
                        yymmdd
                        + "_Device_aSi1_Channel2_set"
                        + setnum
                        + "/telescope_data"
                    )
                    print(filename)
                    self.AZ_scan_mode(0.0, 10.0, filename, n_repeats=8)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass

        if opt == 16:
            try:
                if self.Initialized != True:
                    print("\033[31m Need to initialize system first.\033[0m")
                else:
                    #                    filename = str(input("Input filename (as '.npz')"))
                    yy = "{}".format(date.today().year)
                    mm = "{}".format(date.today().month)
                    if date.today().month < 10:
                        mm = "0" + mm
                    dd = "{}".format(date.today().day)
                    if date.today().day < 10:
                        dd = "0" + dd
                    yymmdd = yy + mm + dd
                    this_dir_files = glob.glob("/home/peter/kidPy/data/" + yymmdd + "*")
                    if np.size(this_dir_files) == 0:
                        setnum = "0"
                    else:
                        this_dir_files.sort()
                        setnum = "{}".format(int(this_dir_files[-1][-4:]))
                    filename = (
                        yymmdd
                        + "_Device_aSi1_Channel2_set"
                        + setnum
                        + "/telescope_data"
                    )
                    print(filename)
                    self.AZ_scan_mode(0.0, 10.0, filename, n_repeats=32)
            except OSError:
                print(
                    "\033[93m OS Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()
            except IndexError:
                print(
                    "\033[93m Index Error: DAQ could not be initialized: Check comm port and power supply\033[0m"
                )
                self.set_ao_zero()

            except KeyboardInterrupt:
                self.set_ao_zero()
                pass

        if opt == 17:
            if self.Initialized != True:
                print("\033[31m Need to initialize system first.\033[0m")
            else:
                cmd = input(
                    "What command do you want to send (look up in ASCII ref guide)? "
                )
                self.talk_to_az(cmd)


if __name__ == "__main__":
    skpr = SKPR_Motor_Control()
    try:
        skpr.Initialize_System()
        print("System initiliazed")
    except KeyboardInterrupt:
        pass
    # if we're running in standard mode
    if np.size(sys.argv) == 1:
        opt = skpr.makePlotMenu(main_opts)
        while opt != 18:
            skpr.main_opt(opt)
            opt = skpr.makePlotMenu(main_opts)

    # or if we're running in execution mode
    else:
        option = int(sys.argv[1])
        skpr.main_opt(option)
