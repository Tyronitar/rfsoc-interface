from pathlib import Path

from rfsocinterface.core.utils import get_params_file_template
from rfsocinterface.core.params import RFSoCParameters
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
    # filename = '/data/20260513/20260513_Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour15p0019.h5'
    # # filename = '/data/20260515/20260515_Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour11p7350.h5'
    # sweep = PowerSweepData.load(filename)
    # pdb.set_trace()
    # counter = Counter()
    # sweep.fit(callback=counter.increment)
    # pdb.set_trace()
    # sweep.find_optimal_readout_power()

    # sweep_file = '/data/20260513/20260513_Device_aSi1_Channel2_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour15p0019.h5'
    # tile_name = 'Device_aSi1_Channel2_telescope_275mK_20260513_with_offres_and_max_power'
    # sweep_file = '/data/20260515/20260515_Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power_Power_Sweep_hour11p7350.h5'
    # tile_name = 'Device_aSi2_Channel3_telescope_275mK_20260511_with_offres_and_max_power'

    # sweep = PowerSweepData.load(sweep_file)
    # sweep.fit_f0()  # Fit resonances if they haven't yet
    # sweep.save_as(sweep_file)
    # sweep.find_optimal_readout_power(bad_power_cutoff_percentile=0.5, pdf_filename=f'max_power_{tile_name}.pdf')
    # sweep.save_as(sweep_file)

    # pdb.set_trace()
    # sweep.save_to_params_file(tile_name)

    sweep_file = '/data/20261020/20261020_Device_aSi3_Channel4_Power_Sweep_hour09p9742.h5'
    sweep = PowerSweepData.load(sweep_file)
    sweep.find_optimal_readout_power()
    sweep.save()
    # sweep.plot()

    # sweep.save_to_params_file('Device_aSi3_Channel4_with_max_power')
    # params = RFSoCParameters.from_tile_name('Device_aSi3_Channel4_with_max_power')
    # pdb.set_trace()