"""
:Date: 2023-07-20
:Version: 2.0.0
:Authors: - Cody Roberson
          - Adrian Sinclair
          - Ryan Stephenson
          - Philip Mauskopf
          - Jack Sayers

kidpy is where users can interact with the mkid readout system. Simply launch with
.. codeblock::
    python kidpy.py


When an operation is selected, a command is created and published on a redis
pubsub channel. Any listening RFSOC(s) would then parse and execute the specified command
    
"""

import numpy as np
import sys, os
import redis
import json
import configparser
import time
import serial.tools.list_ports_linux
import udpcap
import datetime
import valon5009
import sweeps
import udp2
import data_handler
import matplotlib.pyplot as plt

# from datetime import date
# from datetime import datetime
import pdb
import glob
import logging

### Logging ###
# Configures the logger such that it prints to a screen and file including the format
__LOGFMT = "%(asctime)s|%(levelname)s|%(filename)s|%(lineno)d|%(funcName)s|%(message)s"

logging.basicConfig(format=__LOGFMT, level=logging.INFO)
logger = logging.getLogger(__name__+"-kidpy")
__logh = logging.FileHandler("./kidpy.log")
logging.root.addHandler(__logh)
logger.log(100, __LOGFMT)
__logh.flush()
__logh.setFormatter(logging.Formatter(__LOGFMT))
################


default_f_center = 400.0

# for the ONR features
onr_repo_dir = os.path.expanduser("~") + "/onrkidpy"
onr_check = glob.glob(onr_repo_dir)
if np.size(onr_check) == 0:
    onr_flag = False
else:
    onr_flag = True
if onr_flag:
    sys.path.append(onr_repo_dir)
    import onrkidpy
    import onr_fit_lo_sweeps as fit_lo
    import onr_motor_control
    import subprocess
    import onr_process_observation as onrp
    import onr_map_observation as onrm
    motor = onr_motor_control.SKPR_Motor_Control()
    import onr_analyze_noise_data as onrn

def testConnection(r):
    try:
        tr = r.set("testkey", "123")
        return True
    except redis.exceptions.ConnectionError as e:
        print(e)
        return False


def wait_for_free(r, delay=0.25, timeout=10):
    count = 0
    r.set("status", "busy")
    while r.get("status") != b"free":
        time.sleep(delay)
        count = count + 1
        if count == timeout:
            print("TIMED OUT WHILE WAITING FOR RFSOC")
            return False
    return True


def wait_for_reply(redis_pubsub, cmd, max_timeout=15):
    """

    This is the eventual replacement for the waitForFree() method.
    We want to have smarter replies that can ferry data back from the RFSOC.

    Once a command is sent out, listen for a reply on the <cmd_reply> channel
        Format for replying to commands from redis
            message = {
                'cmd' : 'relay command',
                'status' : 'OK'|'FAIL',
                'data' : 'nil' | <arbitrary data>
            }

    :param max_timeout: int :
        time in seconds to wait for the RFSOC to reply. If it fails in this time,
        this should indicate a failure of some kind has occured
    :param cmd: str :
        Command sent out
    :param redis_pubsub: redis.Redis.pubsub :
        reference to a Redis pubsub object that has already subscribed to relevant channels
    """
    current_time = 0
    while current_time < max_timeout:
        m = redis_pubsub.get_message()
        if m is not None and m["channel"] == b"picard_reply":
            msg = m["data"].decode("ASCII")
            data = json.loads(msg)
            if data["cmd"] == cmd and data["status"] == "OK":
                return True, data["data"]
            else:
                return False, data["data"]
        time.sleep(1)
        current_time = current_time + 1
    print(
        "WARINNG: TIMED OUT WAITING FOR REPLY -->  def waitForReply(redisIF, cmd, maxTimeout = 15):"
    )
    return False, None


def checkBlastCli(r, p):
    """
    Rudamentary "is the rfsoc control software running" check.
    """
    cmd = {"cmd": "ping", "args": []}
    cmd = json.dumps(cmd)
    r.publish("picard", cmd)
    count = 1
    delay = 0.5
    timeout = 6
    while 1:
        m = p.get_message()
        if m is not None and m["data"] == b"Hello World":
            print("redisControl is running")
            return True
        if count >= timeout:
            print("RFSOC didn't reply, is it running redisControl?")
            return False

        time.sleep(delay)
        count = count + 1


def write_fList(self, fList, ampList):
    """
    Function for writing tones to the rfsoc. Accepts both numpy arrays and lists.
    :param fList: List of desired tones
    :type fList: list
    :param ampList: List of desired amplitudes
    :type ampList: list
    .. note::
        fList and ampList must be the same size
    """
    log = logger.getChild("write_fList")
    f = fList
    a = ampList

    # Convert to numpy arrays as needed
    if isinstance(fList, np.ndarray):
        f = fList.tolist()
    if isinstance(ampList, np.ndarray):
        a = ampList.tolist()

    # Format Command based on provided parameters
    cmd = {}
    if len(f) == 0:
        cmd = {"cmd": "ulWaveform", "args": []}
    elif len(f) > 0 and len(a) == 0:
        a = np.ones_like(f).tolist()
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    elif len(f) > 0 and len(a) > 0:
        assert len(a) == len(
            f
        ), "Frequency list and Amplitude list must be the same dimmension"
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    else:
        log.error("Weird edge case, something went very wrong.....")
        return

    cmdstr = json.dumps(cmd)
    self.r.publish("picard", cmdstr)
    success, _ = wait_for_reply(self.p, "ulWaveform", max_timeout=10)
    if success:
        log.info("Wrote waveform.")
    else:
        log.error("FAILED TO WRITE WAVEFORM")


def menu(captions, options):
    """Creates menu for terminal interface
    inputs:
        list captions: List of menu captions
        list options: List of menu options
    outputs:
        int opt: Integer corresponding to menu option chosen by user"""
    log = logger.getChild("menu")
    print("\t" + captions[0] + "\n")
    for i in range(len(options)):
        print("\t" + "\033[32m" + str(i) + " ..... " "\033[0m" + options[i] + "\n")
    opt = None
    try:
        x = input("Option? ")
        opt = int(x)
    except KeyboardInterrupt:
        exit()
    except ValueError:
        print("Not a valid option")
        return 999999
    except TypeError:
        print("Not a valid option")
        return 999999
    return opt


class kidpy:
    def __init__(self):
        # Pull config
        config = configparser.ConfigParser()
        config.read("generalConfig.conf")
        self.__redis_host = config["REDIS"]["host"]
        self.__customWaveform = config["DSP"]["customWaveform"]
        self.__customSingleTone = config["DSP"]["singleToneFrequency"]
        self.__saveData = config["DATA"]["saveFolder"]
        self.__ValonPorts = config["VALON"]["valonSerialPorts"].split(",")
        self.__valon_RF1_SYS2 = config["VALON"]["rfsoc1System2"]
        self.__valon_RF1_SYS1 = config["VALON"]["rfsoc1System1"]

        # setup redis
        self.r = redis.Redis(self.__redis_host)
        self.p = self.r.pubsub()
        self.p.subscribe("ping")
        time.sleep(1)
        if self.p.get_message()["data"] != 1:
            print("Failed to Subscribe to redis Ping Channel")
            exit()
        self.p.subscribe("picard_reply")
        time.sleep(1)
        if self.p.get_message()["data"] != 2:
            print("Failed to Subscribe redis picard_reply channel")
            exit()

        # check that the rfsoc is running redisControl.py
        os.system("clear")
        if not checkBlastCli(self.r, self.p):
            exit()

        # Differentiate 5009's connected to the system
        self.valon = valon5009.Synthesizer("/dev/IF1System1LO")
        self.valon.set_frequency(valon5009.SYNTH_B, default_f_center)
        # for v in self.__ValonPorts:
        #    self.valon = valon5009.Synthesizer(v.replace(' ', ''))

        self.__udp = udpcap.udpcap()
        self.current_waveform = []
        self.current_amplitude = []
        caption1 = "\n\t\033[95mKID-PY2 RFSoC Readout\033[95m"
        self.captions = [caption1]

        self.__main_opts = [
            "Upload firmware",
            "Initialize system & UDP conn",
            "Write test comb (single or multitone)",
            "Write stored comb from config file",
            "I <-> Q Phase offset",
            "Take Raw Data",
            "LO Sweep",
            "Exit",
            "ONR kidpy",
            "Plot accum sample",
        ]

    def get_tone_list(self):
        lo_freq = valon5009.Synthesizer.get_frequency(self.valon, valon5009.SYNTH_B)
        tones = lo_freq * 1.0e6 + np.asarray(self.get_last_flist())
        return tones

    def get_last_flist(self):
        log = logger.getChild("kidpy.get_last_flist")
        cmd = json.dumps({"cmd": "get_last_flist", "args": []})
        self.r.publish("picard", cmd)
        status, data = wait_for_reply(self.p, "get_last_flist", 3)
        if status:
            return np.array(data)
        else:
            log.error("The rfsoc didn't return back our data")
            return None

    def get_last_alist(self):
        log = logger.getChild("kidpy.get_last_alist")
        cmd = json.dumps({"cmd": "get_last_alist", "args": []})
        self.r.publish("picard", cmd)
        status, data = wait_for_reply(self.p, "get_last_alist", 2)
        if status:
            return np.array(data)
        else:
            log.error("The rfsoc didn't return back our data")
            return None

    def main_opt(self):
        log = logger.getChild(__name__)
        """
        Main user interface routing

        r : redis Server instance
        p : redis.pubsub instance
        udp : udpcap object instance
        """
        while 1:
            conStatus = testConnection(self.r)
            if conStatus:
                print("\033[0;36m" + "\r\nConnected" + "\033[0m")
            else:
                print(
                    "\033[0;31m"
                    + "\r\nCouldn't connect to redis-server double check it's running and the generalConfig is correct"
                    + "\033[0m"
                )
            opt = menu(self.captions, self.__main_opts)
            if conStatus == False:
                resp = input(
                    "Can't connect to redis server, do you want to continue anyway? [y/n]: "
                )
                if resp != "y":
                    exit()
            if opt == 999999:
                pass
            if opt == 0:  # upload firmware
                os.system("clear")
                cmd = {"cmd": "ulBitstream", "args": []}
                cmdstr = json.dumps(cmd)
                self.r.publish("picard", cmdstr)
                self.r.set("status", "busy")
                print("Waiting for the RFSOC to upload it's bitstream...")
                if wait_for_free(self.r, 0.75, 25):
                    print("Done")

            if opt == 1:  # Init System & UDP conn.
                os.system("clear")
                print("Initializing System and UDP Connection")
                cmd = {"cmd": "initRegs", "args": []}
                cmdstr = json.dumps(cmd)
                self.r.publish("picard", cmdstr)
                if wait_for_free(self.r, 0.5, 5):
                    print("Done")

            if opt == 2:  # Write test comb
                prompt = input("Full test comb? y/n ")
                os.system("clear")
                if prompt == "y":
                    print("Waiting for the RFSOC to finish writing the full comb")
                    write_fList(self, [], [])
                else:
                    print(
                        "Waiting for the RFSOC to write single {} MHz Tone".format(
                            float(self.__customSingleTone) / 1e6
                        )
                    )
                    write_fList(self, [float(self.__customSingleTone)], [])

            if opt == 3:  # write stored comb
                os.system("clear")
                # not used

            if opt == 4:
                print("Not Implemented")

            if opt == 5:
                t = 0
                try:
                    t = int(input("How many seconds of data?: "))
                    print(t)
                except ValueError:
                    print("Error, not a valid Number")
                except KeyboardInterrupt:
                    return

                if t <= 0:
                    print("Can't sample 0 seconds")
                else:
                    os.system("clear")
                    print("Binding Socket")
                    self.__udp.bindSocket()
                    print("Capturing packets")
                    fname = (
                        self.__saveData
                        + "kidpyCaptureData{0:%Y%m%d%H%M%S}.h5".format(
                            datetime.datetime.now()
                        )
                    )
                    print(fname)
                    if t < 60:
                        self.__udp.shortDataCapture(fname, 488 * t)
                    else:
                        self.__udp.LongDataCapture(fname, 488 * t)
                    print("Releasing Socket")
                    self.__udp.release()

            if opt == 6:  # Lo Sweep
                # valon should be connected and differentiated as part of bringing kidpy up.
                os.system("clear")
                print("LO Sweep")
                sweeps.loSweep(
                    self.valon,
                    self.__udp,
                    self.get_last_flist(),
                    f_center=default_f_center,
                    freq_step=0,
                )

                # plot result
                sweeps.plot_sweep("./s21.npy")

            if opt == 7:  # get system state
                exit()

            if opt == 8:  # ONR version of kidpy
                if onr_flag:
                    onr_loop = True
                    while onr_loop:
                        onr_caption = [
                            "\n\t\033[95mKID-PY2 RFSoC Readout (ONR Version)\033[95m"
                        ]
                        onr_options = [
                            "Write Custom Tone List",
                            "Standard Calibration LO Sweep",
                            "Stream Data to File",
                            "Get Cooridinates",
                            "Set AZ Position",
                            "Set EL Position",
                            "Motor Test for Data Acquisition",
                            "Exit",
                            "Tone Powers",
                            "LO Sweep to Calibrate Readout Power"
                        ]
                        onr_opt = menu(onr_caption, onr_options)

                        if onr_opt == 0:  # write stored comb
                            os.system("clear")

                            # see if the user wants the default list or something different:
                            tone_file = (
                                input(
                                    "What is the tone file you would like to load (default is params/Default_tone_list.npy)"
                                )
                                or "params/Default_tone_list.npy"
                            )
                            freqfile = np.load(tone_file)
                            fList = np.ndarray.tolist(freqfile)
                            aList = []
                            # aList = np.ndarray.tolist(np.load(amplitude_file)) # doesnt exist yet...

                            print(
                                "Waiting for the RFSOC to finish writing the custom frequency list"
                            )
                            write_fList(self, fList, aList)

                        if onr_opt == 1:  # Run standard calibration LO sweep
                            # see if the user wants to shift all the tones (e.g., due to change in loading)
                            self.valon.set_frequency(2, default_f_center)
                            chan_name = 'rfsoc2'
                            tone_shift = (
                                input(
                                    "How many kHz to shift the tones in the band center before the LO sweep (default is 0)"
                                )
                                or 0
                            )
                            if tone_shift != 0:
                                lo_freq = valon5009.Synthesizer.get_frequency(
                                    self.valon, valon5009.SYNTH_B
                                )
                                current_tone_list = self.get_tone_list()
                                fList = np.ndarray.tolist(
                                    current_tone_list
                                    + float(tone_shift)
                                    * current_tone_list
                                    / np.median(current_tone_list)
                                    * 1.0e3
                                    - lo_freq * 1.0e6
                                )
                                print(
                                    "Waiting for the RFSOC to finish writing the updated frequency list"
                                )
                                fAmps = self.get_last_alist()
                                write_fList(self, fList, np.ndarray.tolist(fAmps))
#                                write_fList(self, fList, [])

                            # first the low resolution initial sweep
                            os.system("clear")
                            print(
                                "Taking initial sweep with df = 1 kHz and Deltaf = 100 kHz"
                            )
                            savefile = onrkidpy.get_filename(
                                type="LO", chan_name=chan_name
                            )
                            sweeps.loSweep(
                                self.valon,
                                self.__udp,
                                self.get_last_flist(),
                                valon5009.Synthesizer.get_frequency(
                                    self.valon, valon5009.SYNTH_B
                                ),
                                N_steps=200,
                                freq_step=0.001,
                                savefile=savefile,
                            )

                            # then fit the resonances from that sweep
                            fit_f0, fit_qi, fit_qc = fit_lo.main(
                                self.get_tone_list(),
                                savefile + ".npy",
                                quickPlot=True,
                                printFlag=True,
                            )
                            adjust_tones = (
                                input(
                                    "Manually adjust any of the fitted f0 values (y/n)?"
                                )
                                or "n"
                            )
                            if adjust_tones == "y":
                                keepgoing = "y"
                                while keepgoing == "y":
                                    adjust_index = int(
                                        input("Index of tone to adjust:  ")
                                    )
                                    freq_adjust = float(input("Frequency (in MHz):  "))
                                    fit_f0[adjust_index] = freq_adjust * 1.0e6
                                    keepgoing = (
                                        input("Adjust another tone (y/n, default is n)?") or "n"
                                    )
                            new_tone_list = (
                                fit_f0
                                - valon5009.Synthesizer.get_frequency(
                                    self.valon, valon5009.SYNTH_B
                                )
                                * 1.0e6
                            )
                            write_new_list = (
                                input("Write new list of tones (y/n, default is n)?")
                                or 'n'
                            )
                            if write_new_list == 'y':
                                fAmps = self.get_last_alist()
                                write_fList(self, np.ndarray.tolist(new_tone_list), np.ndarray.tolist(fAmps))
#                                write_fList(self, np.ndarray.tolist(new_tone_list), [])
                                np.save(
                                    onrkidpy.get_filename(
                                        type="TONELIST", chan_name=chan_name
                                    ),
                                    new_tone_list,
                                )
                            plt.close("all")

                            second_sweep = (input('Perform a second sweep centered on resonators (y/n, default = n)') or 'n')
                            if second_sweep == 'y':
                                savefile = onrkidpy.get_filename(
                                type="LO", chan_name=chan_name)
                                sweeps.loSweep(
                                self.valon,
                                self.__udp,
                                self.get_last_flist(),
                                valon5009.Synthesizer.get_frequency(
                                    self.valon, valon5009.SYNTH_B
                                ),
                                N_steps=200,
                                freq_step=0.001,
                                savefile=savefile,)

                        if onr_opt == 2:  # Stream data to file
                            t = int(input("How many seconds of data?: ")) or 0
                            os.system("clear")
                            rfsocfile = (
                                onrkidpy.get_filename(type="TOD", chan_name="channame")
                                + ".h5"
                            )
                            rfsocfile = rfsocfile.replace("channame", "rfsoc2")
                            # Populate the rfchannel with all the relevent details
                            bb = self.get_last_flist()
                            rfsoc2 = data_handler.RFChannel(
                                rfsocfile,
                                "192.168.5.40",
                                bb,
                                self.get_last_alist(),
                                port=4096,
                                name="rfsoc2",
                                n_tones=len(bb),
                                attenuator_settings=np.array([20.0, 10.0]),
                                tile_number=2,
                                rfsoc_number=2,
                                lo_sweep_filename=data_handler.get_last_lo("rfsoc2"),
                                lo_freq=self.valon.get_frequency(valon5009.SYNTH_B)*1e6
                            )
                            udp2.capture(
                                 [rfsoc2],
                                 time.sleep,
                                 t
                            )
                            yymmdd = onrkidpy.get_yymmdd()
                            setnum = rfsocfile[-7:-3]
                            onrp.create_processed_file(yymmdd,setnum,azel=False)
#                            onrn.main(yymmdd,setnum,'Device_aSi1_Channel2')

#                             os.system("clear")
#                             self.__udp.bindSocket()
#                             savefile = (
#                                 onrkidpy.get_filename(type="TOD", chan_name="rfsoc2")
#                                 + ".h5"
#                             )
#                             if t < 60:
#                                 self.__udp.shortDataCapture(savefile, 488 * t)
#                             else:
#                                 self.__udp.LongDataCapture(savefile, 488 * t)
#                             self.__udp.release()

                        if onr_opt == 3:  # Test a telescope function
                            motor.init_test()
                            motor.AZ_Ser_Pos()
                            print("The AZ position is: ", motor.pfb)
                            motor.EL_Ser_Pos()
                            print("The EL position is: ", motor.pos)

                        if onr_opt == 4:
                            motor.init_test()
                            pfb = motor.pfb
                            print("Az Position is: ", pfb)
                            az_set_pos_req = float(
                                input(
                                    "What position do you want to set the motor (-180.000 to 180.000 degrees)?"
                                )
                            )
                            az_set_pos = az_set_pos_req
                            if az_set_pos > 180000 or az_set_pos < -180000:
                                print(
                                    "This position is outside the limits of the Telescope!"
                                )
                            else:
                                motor.setAZposition(az_set_pos)
                            print("The AZ position is: ", motor.pfb)

                        if onr_opt == 5:
                            try:
                                motor.init_test()
                                pos = motor.pos
                                print("El Position is: ", pos)
                                el_set_pos = float(
                                    input(
                                        "What position do you want to set the motor (Degrees)?"
                                    )
                                )
                                motor.setELposition(el_set_pos)
                                print("The EL position is: ", motor.pos)
                            except:
                                motor.set_ao_zero()
                                print(
                                    "\033[93m UnboundLocalError: DAQ could not be initialized: Check comm port and power supply\033[0m"
                                )

                        if onr_opt == 6:
                            # then collect the KID data
                            os.system("clear")
                            motor.init_test()
                            rfsocfile = (
                                onrkidpy.get_filename(type="TOD", chan_name="channame")
                                + ".h5"
                            )
                            telefile = rfsocfile.replace('TOD', 'AZEL')
                            telefile = telefile.replace("_channame", "")
                            rfsocfile = rfsocfile.replace("channame", "rfsoc2")
                            # Populate the rfchannel with all the relevent details
                            bb = self.get_last_flist()
                            rfsoc2 = data_handler.RFChannel(
                                rfsocfile,
                                "192.168.5.40",
                                bb,
                                self.get_last_alist(),
                                port=4096,
                                name="rfsoc2",
                                n_tones=len(bb),
                                attenuator_settings=np.array([20.0, 10.0]),
                                tile_number=2,
                                rfsoc_number=2,
                                lo_sweep_filename=data_handler.get_last_lo("rfsoc2"),
                                lo_freq=self.valon.get_frequency(valon5009.SYNTH_B)*1e6
                            )
#                             udp2.capture(
#                                 [rfsoc2],
#                                 time.sleep,
#                                 10
#                             )
                            udp2.capture(
                                [rfsoc2],
                                motor.AZ_scan_mode,
                                -5.0,
                                5.0,
                                telefile,
                                n_repeats=2,
                                position_return=True,
                            )
                            yymmdd = onrkidpy.get_yymmdd()
                            setnum = rfsocfile[-7:-3]
                            onrp.create_processed_file(yymmdd,setnum)
                            onrm.create_map(yymmdd,setnum)

                        if onr_opt == 7:  # Exit
                            onr_loop = False

                        if onr_opt == 8:  # Tone Powers
                            fList = self.get_last_flist()
                            max_power_file = input('Filename with max power values? e.g., Device_aSi1_Channel2 (default is uniform power)') or ''
                            if max_power_file != '':
                                power_dB = np.load(onr_repo_dir + '/params/' + max_power_file + '_max_readout_power_dB.npy')
                                fAmps = np.exp(power_dB/10.)
                            else:
                                fAmps = np.ones(np.size(fList))
                            write_fList(
                                self, np.ndarray.tolist(fList), np.ndarray.tolist(fAmps)
                            )
                            
                        if onr_opt == 9:  # LO Sweep to calibrate readout power
                            # see if the user wants to shift all the tones (e.g., due to change in loading)
                            atten_out = (
                                input(
                                    "What is the attenuation of the IF output (in dB)?"))
                            self.valon.set_frequency(2, default_f_center)
                            chan_name = 'rfsoc2'
                            lo_freq = valon5009.Synthesizer.get_frequency(
                                self.valon, valon5009.SYNTH_B)

                            # first the low resolution initial sweep
                            os.system("clear")
                            print(
                                "Taking initial sweep with df = 1 kHz and Deltaf = 100 kHz"
                            )
                            savefile = onrkidpy.get_filename(
                                type="LO", chan_name=chan_name
                            )
                            sweeps.loSweep(
                                self.valon,
                                self.__udp,
                                self.get_last_flist(),
                                valon5009.Synthesizer.get_frequency(
                                    self.valon, valon5009.SYNTH_B
                                ),
                                N_steps=200,
                                freq_step=0.001,
                                savefile=savefile,
                            )

                            # then fit the resonances from that sweep
                            fit_f0, fit_qi, fit_qc = fit_lo.main(
                                self.get_tone_list(),
                                savefile + ".npy",
                                quickPlot=False,
                                printFlag=False,
                            )
                            np.save(onrkidpy.get_filename(type='attenuator',attenuation=atten_out), fit_f0)

                        if onr_opt == 10:
                            sweeps.plot_sweep_hdf(data_handler.get_last_rdf("rfsoc2"))

                else:
                    print("ONR repository does not exist")

            if opt == 9:
                f = data_handler.RawDataFile(data_handler.get_last_rdf("rfsoc2"), 'r')
                i = f.adc_i[:].T[10]
                q = f.adc_q[:].T[10]
                print(f"{i.shape}")
                mag = np.sqrt(i**2 + q**2)
                y = 10 * np.log10(mag / np.max(mag))
                plt.plot(y)
                plt.title("Accum (dB)")
                plt.grid()
                plt.show()
            return 0


def main():
    k = kidpy()
    try:
        while 1:
            k.main_opt()
    except Exception as e:
        raise e


if __name__ == "__main__":
    main()
