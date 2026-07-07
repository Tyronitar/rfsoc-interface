import pdb

from rfsocinterface.core.data import *
from rfsocinterface.analysis import *

if __name__ == '__main__':

    old_beammap = ProcessedData.load('20260521', 1010, mode='r')
    new_beammap = ProcessedData.load('20260617', 1001, mode='r')

    pdb.set_trace()


