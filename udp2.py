"""
Overview
________

udp2 is the Next iteration of udpcap. Here, we want to facilitate the process of pulling data
from multiple channels from multiple RFSOC's in a multiprocessing environment. 
Unlike udpcap, udp2 utilizes the hdf5 obervation file format defined by data_handler.

.. note::
    A key part of python multiprocessing library is 'pickling'. This is a funny name to describe object serialization. Essentially, our code needs
    to be convertable into a stream of bytes that can be passed intoa new python interpreter process.
    Certain typs of variables such as h5py objects or sockets can't be pickled. We therefore have to create the h5py/socket objects we need post-pickle. 

:Authors: Cody Roberson
:Date: 2023-08-02
:Version: 2.0.1

"""
import ctypes
import logging
import numpy as np
import socket

from data_handler import RFChannel
from data_handler import RawDataFile
from data_handler import get_last_lo
import socket
import time
import multiprocessing as mp

RED='\033[0;31m'
NC='\033[0m' # No Color

logger = logging.getLogger(__name__)

def __data_writer_process(dataqueue, chan: RFChannel, runFlag):
    """
    Creates a RawDataFile and populates it with data that is passed to it through
    the dataqueue parameter. This function runs indefinitely until
    None is passed through the queue by its partner data_collector_process.

    Data is handled in bursts and the data is chunked allowing us to collect an indefinite amount of data.
    """
    log = logger.getChild(__name__)
    log.debug(f"began data writer process <{chan.name}>")

    # Create HDF5 Datafile and populate various fields
    try:
        raw = RawDataFile(chan.raw_filename, 'w')
        raw.format(chan.n_sample, chan.n_tones, chan.n_fftbins)
        raw.set_global_data(chan)
    except Exception as e:
        errorstr = RED+str(e)+NC
        log.exception(errorstr)
        return
        # raise e
    # Pass in the last LO sweep here
    if chan.lo_sweep_filename == "":
        raw.append_lo_sweep(get_last_lo(chan.name))
    else:
        raw.append_lo_sweep(chan.lo_sweep_filename)

    while True:
        # we're done if the queue closes or we don't get any day within 5 seconds
        try:
            obj = dataqueue.get(True, 5)
        except Exception as e:
            obj = None
        if obj is None:
            log.debug(f"obj is None <{chan.name}>")
            break
        t1 = time.perf_counter_ns()
        log.debug(f"Received a queue object<{chan.name}>")
        # re-Allocate Dataset
        indx, adci, adcq, timestamp = obj
        raw.resize(indx)
        log.debug("resized")
        # Get Data
        raw.adc_i[:, indx - 488 : indx] = adci
        raw.adc_q[:, indx - 488 : indx] = adcq
        raw.timestamp[indx - 488 : indx] = timestamp
        raw.n_sample[0] = indx
        t2 = time.perf_counter_ns()
        log.debug(f"Parsed in this loop's data <{chan.name}>")
        log.debug(f"Data Writer deltaT = {(t2-t1)*1e-6} ms for <{chan.name}>")

    raw.close()
    log.debug(f"Queue closed, closing file and exiting for <{chan.name}>")
    #log.warning("Keyboard Interrupt Caught. This terminates processes that may be writing to a file. Expect possible hdf5 data corruption")

def __data_collector_process(dataqueue, chan: RFChannel, runFlag):
    """
    Creates a socket connection and collects udp data. Said data is put in a tuple and
    passed to it's partner data writer process through the queue. When collection ends, None is possed into the
    queue to signal that further data will not be passed.

    Data is handed off to the writer in chunks of 488 which allows us to run more efficiently as well as collect data indefinitely.

    """
    import time
    log = logger.getChild(__name__)
    log.debug(f"began data collector process <{chan.name}>")
    # Creae Socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((chan.ip, chan.port))
        s.settimeout(10)
    except Exception as e:
        dataqueue.put(None)
        errorstr = RED+str(e)+NC
        log.exception(errorstr)
        return
    # log.debug(f"Socket bound - <{chan.name}>")
    # Take Data
    idx = 488
    i = np.zeros((1024, 488))
    q = np.zeros((1024, 488))
    ts = np.zeros(488)
    log.debug(f"runflag is {runFlag.value}")

    while runFlag.value:
        t1 = time.perf_counter_ns()
        try:
            i[...] = 0
            q[...] = 0
            ts[...] = 0
            for k in range(488):
                data = s.recv(8208 * 1)
                datarray = bytearray(data)
                spec_data = np.frombuffer(datarray, dtype = '<i')
                i[:, k] = spec_data[0::2][0:1024]
                q[:, k] = spec_data[1::2][0:1024]
                ts[k] = time.time()
            dataqueue.put((idx, i, q, ts))
            # log.info(f"<{chan.name}> rx 488 pkts")
        except TimeoutError:
            log.warning(f"Timed out waiting for data <{chan.name}>")
            break
        idx = idx + 488
        t2 = time.perf_counter_ns()
        log.debug(f"datacollector deltaT = {(t2-t1)*1e-6} ms")
    log.debug(f"exited while loop, putting None in dataqueue for <{chan.name}> ")
    dataqueue.put(None)
    s.close()
    return

def exceptionCallback(e: Exception):
    log = logger.getChild(__name__)
    log.error(str(e))
    raise e


def capture(channels: list, fn=None, *args, **kwargs):
    """
    Begins the capture of readout data. For each channel provided, a pair of downstream processes are created
    to capture and save data. Due to the fact that the main thread isn't handling data means that it's relatively free to run some other job.

    Two possibilites can occur
    - A function is provided to capture()

      - After capture() starts its downstream data processes, it executes
        fn() and passes in arbitrary arguments. Once fn returns,
        the datacapture processes are then closed down.

    - No function is provided

      - Capture will sleep() for 10 seconds and then end the data capture.

    :param List(data_handler.RFChannel) channels: RF channels to capture data from

    :param callable fn: Pass in a funtion to call during capture.

        .. DANGER::
            The provided function should not hang indefinitely and returned data is ignored.

    :param any args: args to pass into the provided function

    :param any kwargs: keywords to pass onto the function

    :return: None

    Example
    -------
    The following spawns a data read/writer pair for rfsoc and waits 30 seconds.

    .. code::
        
        # Example 1 Usage
        bb = self.get_last_flist()
        rfsoc1 = data_handler.RFChannel(savefile, "192.168.5.40", 
                                        4096, "rfsoc1", baseband_freqs=bb,
                                        tone_powers=self.get_last_alist(), 
                                        n_resonator=len(bb), attenuator_settings=np.array([20.0, 10.0]),
                                        tile_number=1, rfsoc_number=1, 
                                        lo_sweep_filename=data_handler.get_last_lo("rfsoc1"))
        rfsoc2 = data_handler.RFChannel(savefile, "192.168.6.40", 
                                        4096, "rfsoc1", baseband_freqs=bb,
                                        tone_powers=self.get_last_alist(), 
                                        n_resonator=len(bb), attenuator_settings=np.array([20.0, 10.0]),
                                        tile_number=1, rfsoc_number=1, 
                                        lo_sweep_filename=data_handler.get_last_lo("rfsoc1"))
        
        udp2.capture([rfsoc1, rfsoc2], time.sleep, 30)

        # Example 2 usage
        udp2.capture([rfsoc1],motor.AZ_scan_mode,0.0,10.0,savefile,n_repeats=2,position_return=True)
        
    """
    log = logger.getChild(__name__)

    if channels is None or len(channels) == 0:
        log.warning("Specified list of rfsoc connections is empy/None")
        return

    # setup process pool.
    manager = mp.Manager()
    pool = mp.Pool()

    log.info("Starting Capture Processes")
    runFlag = manager.Value(ctypes.c_bool, True)

    for chan in channels:
        dataqueue = manager.Queue()
        pool.apply_async(
            __data_writer_process,
            (dataqueue, chan, runFlag),
            error_callback=exceptionCallback,
        )
        log.debug(f"Spawned data collector process: {chan.name}")
        pool.apply_async(
            __data_collector_process,
            (dataqueue, chan, runFlag),
            error_callback=exceptionCallback,
        )
        log.debug(f"Spawned data writer process: {chan.name}")

    pool.close()
    log.info("Waiting on capture to complete")
    if not fn is None:
        try:
            fn(*args, **kwargs)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
        except Exception as e:
            log.error("While calling fn, an exception occured")
            errorstr = RED+str(e)+NC
            log.exception(errorstr)
            pool.terminate()
            pool.join()
    else:
        log.debug("No function provided, defaulting to a 2 second collection")
        time.sleep(2)
    log.info("Ending Data Capture; Waiting for child processes to finish...")
    runFlag.value = False
    try:
        pool.join()
    except KeyboardInterrupt:
        errorstr = RED+str(e)+NC
        log.exception(errorstr)
        pool.terminate()
        pool.join()
        return
    log.info("Capture finished")


if __name__ == "__main__":
    """
    Test routine. Used insitu of a connected RFSOC. For testing, several terminals were opened
    and each of them would run udp_sender in order to simulate incomming data.
    ..code:: bash
        python udp_sender 4096
    """
    __LOGFMT = (
        "%(asctime)s|%(levelname)s|%(filename)s|%(lineno)d|%(funcName)s|%(message)s"
    )
    logging.basicConfig(format=__LOGFMT, level=logging.DEBUG)
    __logh = logging.FileHandler("./udp2.log")
    logging.root.addHandler(__logh)
    logger.log(100, __LOGFMT)
    __logh.flush()
    __logh.setFormatter(logging.Formatter(__LOGFMT))

    log = logger.getChild(__name__ + ".__main__ test block")
    # # lets test this thing, shall we?
    # rfsoc = data_handler.RFChannel(
    #     "./rfsoc1_fakedata.h5", "127.0.0.1", 4096, "Stuffed Crust Pizza", 488, 1024, 1
    # )
    # rfsoc2 = data_handler.RFChannel(
    #     "./rfsoc2_fakedata.h5", "127.0.0.1", 4097, "Salad", 488, 1024, 1
    # )
    # start = time.perf_counter_ns()
    # capture([rfsoc, rfsoc2], time.sleep, 10)  # wait 10 seconds
    # stop = time.perf_counter_ns()
    # log.info(f"capture runtime --> {(stop-start) * 1e-6} ms")
