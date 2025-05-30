import socket
from turtle import pd
import numpy as np
import matplotlib.pyplot as plt
from time import sleep
import time
from scipy import signal
import h5py
import multiprocessing as mproc

DEFAULT_UDP_IP = "192.168.5.40"
DEFAULT_UDP_PORT = 4096


def ldcHelper(queue, filename, nPackets):

    """
    ldcHelper is a helper method intended to be used in the udpcap.LongDataCapture method.
    This method runs asynchronously to udpcap.LongDataCapture in order to seperate 
    the array copy and i/o writing phases of data capture.

     **** This should not be used for any purpose. ****
    
    queue : multiprocessing.manager.queue
        Data Queue we are sourceing data from
    
    dIn : numpy.array
        Numpy array that shall be copied into the h5p5 dataset
    """
    print("ldc helper internal function was called")
    dFile = h5py.File(filename, 'w')
    data = dFile.create_dataset("PACKETS",(2052, nPackets), dtype=h5py.h5t.NATIVE_INT32, chunks=True,
                                maxshape=(None, None))
    active = True
    while active:
        rawData = queue.get()
        # print("rawdata {}".format(rawData))
        if rawData is not None:
            d, c = rawData
            data[:, c] = d
        else:
            active = False
            dFile.flush()
    dFile.close()


class udpcap():
    def __init__(self, UDP_IP = DEFAULT_UDP_IP, UDP_PORT = DEFAULT_UDP_PORT):
        self.UDP_IP = UDP_IP
        self.UDP_PORT = UDP_PORT
        print(self.UDP_IP)
        print(self.UDP_PORT)


    def bindSocket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.UDP_IP,self.UDP_PORT))


    def parse_packet(self):
        data = self.sock.recv(8208 * 1)
        if len(data) <  8000:
            print("invalid packet recieved")
            return
        datarray = bytearray(data)
        
        # now allow a shift of the bytes
        spec_data = np.frombuffer(datarray, dtype = '<i')
        # offset allows a shift in the bytes
        return spec_data # int32 data type


    def capture_packets(self, N_packets):
        """
        DEPRECATED
        """
        packets = np.zeros(shape=(2052,N_packets))
        #packets = np.zeros(shape=(2051,N_packets))
        counter = 0
        for i in range(N_packets):
            data_2 = self.parse_packet()
            packets[:,i] = data_2 
            if i%488 == 0:
                print("{}/{} captured ({:.3f}% Complete)".format(i, N_packets, 
                    (N_packets/488)*100.0))
        return packets


    def LongDataCapture(self, fname, nPackets):
        """
        Captures packets for extended periods of time utilzing pythons Multiprocessing library
        fname : string
            file name / path where data shall be exported
        nPackets : int
            Number of packets to save
        """
        try:
            print("capture {} packets".format(nPackets))
            print("Begin Capture")
            
            # enter while loop
            
            manager = mproc.Manager()
            pool = manager.Pool(1)
            queue = manager.Queue()
            
            pool.apply_async(ldcHelper, (queue, fname, nPackets))
            count = 0
            while count < nPackets:
                packet = self.parse_packet()
                if packet is None:
                    continue
                queue.put((packet, count))
                count = count + 1
                if count > 0 and count % 488 == 0:
                    print("{}/{} captured ({:.2f}% Complete)".format(count, nPackets, ((count/nPackets)*100.0)))
            # create helper process
            # capture n packets 
                # Dispatch helper process to dump data into hdf5 dataset
            # continue to capture n packets, never interrupting datataking
        
        except TypeError:
            print("Type error occured")
            return False

        except KeyboardInterrupt:
            print("Interrupted Data Capture")
            return False
        return True


    def shortDataCapture(self, fname, nPackets):
        """
        Performes sub 60 seconds data captures using only memory. 
        Data is then transferred to a file after the collection is complete.
        N : int
            Number of packets to save
        fname : string
            file name / path
        """

        assert nPackets < 488*60, "METHOD NOT INTENDED FOR LONG DATA CAPTURES > 488 packets per second * 60 seconds"
        pData = np.zeros((2052, nPackets))
        try:
            print("capture {} packets".format(nPackets))
            dFile = h5py.File(fname, 'w')
            pkts = dFile.create_dataset("PACKETS",(2052, nPackets), dtype=h5py.h5t.NATIVE_INT32, chunks=True, maxshape=(None, None))
            time_stamp = dFile.create_dataset("TIME", (nPackets), dtype=h5py.h5t.NATIVE_FLOAT, chunks=True, maxshape=(None))
            print("Begin Capture")
            for i in range(nPackets):
                pData[:, i] = self.parse_packet()
                time_stamp[i] = time.time()
                if i > 0 and i % 488 == 0:
                    print("{}/{} captured ({:.2f}% Complete)".format(i, nPackets, ((i/nPackets)*100.0)))
            pkts[...] = pData
            dFile.close()
        except Exception as errorE:
            raise(errorE)
        return True

    def release(self):
        self.sock.close()



