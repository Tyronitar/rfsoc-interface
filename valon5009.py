"""
Provides a serial interface to the Valon 5009.
Adapted from Python2 Example code.
"""

# Python modules
import serial
import serial.tools.list_ports_linux
import struct
from time import sleep, time

# Handy aliases
SYNTH_A = 1
SYNTH_B = 2

INT_REF = 0
EXT_REF = 1


class Synthesizer:
    """A simple interface to the Valon 5009 synthesizer."""

    def __init__(self, port):
        self.conn = serial.Serial(
            None,
            115200,
            serial.EIGHTBITS,
            serial.PARITY_NONE,
            serial.STOPBITS_ONE,
            timeout=0.500,
        )

        self.conn.setPort(port)
        supportedBauds = [115200, 9600, 19200, 38400, 57600, 230400, 460800, 912600]

        def idCheck(baud):
            if self.conn.isOpen:
                self.conn.close()
            self.conn.baudrate = baud
            self.conn.open()
            self.conn.write(b"ID\r")
            r = self.conn.readlines()
            if not r:
                return False
            elif r[0] == b"ID\r\n" or r[0] == b"ID\r":
                self.conn.close()
                return True
            else:
                print("something went wrong when hunting for valon baudrates")
                print(r)

        # Hunt for, and set connection baud rate
        for baud in supportedBauds:
            print("Checking for baud {}".format(baud))
            a = idCheck(baud)
            if a:
                print("Connected at baud {}".format(baud))
                break

    def getSN(self):
        self.conn.open()
        self.conn.write(b"ID\r")
        info = self.conn.readlines()
        self.conn.flush()
        self.conn.close()
        print(info)
        if info is not None:
            inf = info[1].decode("ASCII")
            inf = inf.split(",")
            print(inf[2])
            return inf[2]
        else:
            return None

    def get_frequency(self, synth):
        """
        Returns the current output frequency for the selected synthesizer.

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @return: the frequency in MHz (float)
        """
        self.conn.open()

        data = "f" + str(synth) + "?\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        t = time()
        data = b""
        while len(data) < 40 and time() - t < 1:
            data += self.conn.read(40)
        self.conn.close()
        print(data)
        data = data.split(b" Act ")[1]
        data = data.split(b" ")[0]
        return float(data)  # in MHz#

    def set_frequency(self, synth, freq, chan_spacing=10.0):
        """
        Sets the synthesizer to the desired frequency

        Sets to the closest possible frequency, depending on the channel spacing.
        Range is determined by the minimum and maximum VCO frequency.

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @param freq : output frequency
        @type  freq : float

        @param chan_spacing : deprecated
        @type  chan_spacing : float

        @return: True if success (bool)
        """
        self.conn.open()
        print(f"\nvalon5009.py:set_frequency->SET FREQ TO {freq}")
        #b"s2;f400.1299999\r"
        data = "s" + str(synth) + ";f" + "{}".format(freq) + "\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        t = time()
        data = b""
        # while (len(data) < 40 and time()-t < 1): data += self.conn.read(40)
        # replacing the aboveline
        # to deal with variable length replys from the valon
        self.conn.readline()  # send this into the void
        data = self.conn.readline()
        self.conn.close()
        print(data)
        data = data.split(b" Act ")[1]
        data = data.split(b" ")[0]
        return float(data) == float(freq)

    def get_reference(self):
        """
        Get reference frequency in MHz
        """
        self.conn.open()
        data = b"REF?\r"
        self.conn.write(data)
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        freq = data.split(b" ")[1]
        return float(freq)  # in MHz

    def set_reference(self, freq):
        """
        Set reference frequency in MHz

        @param freq : frequency in MHz
        @type  freq : float

        @return: True if success (bool)
        """
        self.conn.open()
        data = "REF " + str(freq) + "M\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        t = time()
        data = b""
        while len(data) < 40 and time() - t < 1:
            data += self.conn.read(40)
        self.conn.close()
        # print data
        ack = data.split(b" ")[2]
        # print ack
        return ack == str(freq)

    def set_refdoubler(self, synth, enable):
        """
        Set reference doubler

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @param enable : turn on or off the reference doubler
        @type  enable : bool

        @return: True if success (bool)
        """
        if enable:
            self.conn.open()
            data = "s" + str(synth) + ";REFDB E\r"
            self.conn.write(data.encode("ASCII"))
            self.conn.flush()
        else:
            self.conn.open()
            data = "s" + str(synth) + ";REFDB D\r"
            self.conn.write(data.encode("ASCII"))
            self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        ack = data.split(b" ")[2]
        ack = ack.split(b";")[0]
        return int(ack) == 0

    def get_refdoubler(self, synth):
        """
        Get reference doubler

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @return: True if on, False if off (bool)
        """

        self.conn.open()
        data = "REFDB" + str(synth) + "?\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        ack = data.split(b"REFDB")[2]
        ack = ack.split(b";")[0]
        return int(ack)

    def get_rf_level(self, synth):
        """
        Returns RF level in dBm

        @param synth : synthesizer address, 1 or 2
        @type  synth : int

        @return: dBm (int)
        """
        self.conn.open()
        data = "s" + str(synth) + ";Att?\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        data = data.split(b"ATT ")[1]
        data = data.split(b";")[0]
        rf_level = float(data) - 15
        return int(rf_level)

    def set_rf_level(self, synth, rf_level):
        """
        Set RF level

        @param synth : synthesizer address, 1 or 2
        @type  synth : int

        @param rf_level : RF power in dBm
        @type  rf_level : float

        @return: True if success (bool)
        """
        "15 dB is equal to 0 dB ouput power"
        "can be set from 0 (+15) to 31.5 (-16.5)"
        # Writing 0 dBm results in ~0.7 dBm output
        rf_level -= 1.0
        if -16.5 <= rf_level <= 15:
            atten = -rf_level + 15
            # print atten
            data = "s" + str(synth) + ";att" + str(atten) + "\r"
            self.conn.open()
            self.conn.write(data.encode("ASCII"))
            self.conn.flush()
            data = self.conn.read(1000)
            self.conn.close()
            ack = data.split(b"ATT ")[1]
            ack = ack.split(b";")[0]
            # print ack
            return float(ack) == float(atten)
        else:
            return False

    def set_pfd(self, synth, freq):
        """
        Sets the synthesizer's phase/frequency detector to the desired frequency

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @param freq : pfd frequency
        @type  freq : float

        @return: True if success (bool)
        """
        self.conn.open()
        data = "s" + str(synth) + ";PFD" + str(freq) + "M\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        data = data.split(b"PFD ")[1]
        # print data
        data = data.split(b" MHz")[0]
        # print data
        return int(data) == int(freq)

    def get_pfd(self, synth):
        """
        Gets the synthesizer's phase/frequency detector to the desired frequency

        @param synth : synthesizer this command affects (1 or 2).
        @type  synth : int

        @return: True if success (bool)
        """
        self.conn.open()
        data = "PFD" + str(synth) + "?\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        # print data
        data = data.split(b"PFD ")[1]
        data = data.split(b" MHz")[0]
        return float(data)

    def get_ref_select(self):
        """
        Returns the currently selected reference clock.

        Returns 1 if the external reference is selected, 0 otherwise.
        """
        self.conn.open()
        data = "REFS?\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        t = time()
        data = b""
        while len(data) < 40 and time() - t < 1:
            data += self.conn.read(40)
        self.conn.close()
        data = data.split(b" ")[1]
        data = data.split(b";")[0]
        return int(data)

    def set_ref_select(self, e_not_i=1):
        """
        Selects either internal or external reference clock.

        @param e_not_i : 1 (external) or 0 (internal); default 1
        @type  e_not_i : int

        @return: True if success (bool)
        """
        data = "REFS" + str(e_not_i) + "\r"
        self.conn.open()
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        t = time()
        data = b""
        while len(data) < 40 and time() - t < 1:
            data += self.conn.read(40)
        self.conn.close()
        ack = data.split(b" ")[1]
        ack = ack.split(b";")[0]
        return ack == str(e_not_i)

    def get_vco_range(self, synth):
        """
        Returns (min, max) VCO range tuple.

        @param synth : synthesizer base address
        @type  synth : int

        @return: min,max in MHz
        """
        self.conn.open()
        data = struct.pack(">B", 0x83 | synth)
        self.conn.write(data)
        self.conn.flush()
        data = self.conn.read(4)
        checksum = self.conn.read(1)
        self.conn.close()
        # _verify_checksum(data, checksum)
        return struct.unpack(">HH", data)

    def get_phase_lock(self, synth):
        """
        Get phase lock status

        @param synth : synthesizer base address
        @type  synth : int

        @return: True if locked (bool)
        """
        self.conn.open()
        data = "LOCK" + str(synth) + "\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        if b"locked" in data:
            return True
        else:
            return False

    def flash(self):
        """
        Flash current settings for both synthesizers into non-volatile memory.

        @return: True if success (bool)
        """
        self.conn.open()
        data = "SAV\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        ack = self.conn.read(100)
        self.conn.close()
        if b"No" in ack:
            return False
        else:
            return True

    def reset(self):
        """
        Resets the Valon to factory settings

        @return: True if success (bool)
        """
        self.conn.open()
        data = "RST\r"
        self.conn.write(data.encode("ASCII"))
        self.conn.flush()
        data = self.conn.read(100)
        self.conn.close()
        print(data)
        return True
