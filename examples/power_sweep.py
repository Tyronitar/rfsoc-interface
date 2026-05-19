
from rfsocinterface.core.data import *
from rfsocinterface.core.sweeps import PowerSweepData
import pdb

class Counter:
    def __init__(self):
        self.count = 0
    
    def increment(self):
        self.count += 1
        print(self.count)

if __name__ == '__main__':
    filename = '/data/20260513/20260513_Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour15p0019.h5'
    # filename = '/data/20260515/20260515_Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour11p7350.h5'
    sweep = PowerSweepData.load(filename)
    pdb.set_trace()
    counter = Counter()
    sweep.fit(callback=counter.increment)
    pdb.set_trace()
    sweep.find_optimal_readout_power()