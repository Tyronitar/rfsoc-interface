
from rfsocinterface.core.data import *
from rfsocinterface.core.losweep import PowerSweepData


if __name__ == '__main__':
    sweep = PowerSweepData.from_h5('/data/20260427/20260427_Device_aSi1_Channel2_telescope_275mK_20260325_with_offres_Power_Sweep_hour16p3117.h5')
    sweep.find_optimal_readout_power()