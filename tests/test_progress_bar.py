import pytest
from pathlib import Path
from rfsocinterface.utils import JobQueue, SequentialJobQueue
from rfsocinterface.losweep import LoSweepData
import time
from PySide6.QtCore import SignalInstance
import numpy as np
import onrkidpy

def slow_job(n: int, signal: SignalInstance):
    for _ in range(n):
        time.sleep(0.1)
        signal.emit()

class Counter:
    def __init__(self):
        self.count = 0
    
    def __call__(self):
        self.count += 1

# def test_job_queue():
#     q = JobQueue()
#     q.add_job(slow_job, 10)
#     job, _ = q.queue[0]
#     cntr = Counter()
#     job.updateProgress.connect(cntr)
#     q.run_all()
#     assert cntr.count == 10

def test_parallel_fit():
    chan_name = 'rfsoc2'
    savefile = onrkidpy.get_filename(
        type="LO", chan_name=chan_name
    )
    sweep_file = '20240822_rfsoc2_LO_Sweep_hour16p3294.npy'
    tone_list = 'Default_tone_list.npy'
    chanmask = 'chanmask.npy'
    savefile = Path(savefile).name
    sweep_data = LoSweepData.from_file(tone_list, sweep_file, chanmask)

    q = SequentialJobQueue()
    for i_chan in np.argwhere(sweep_data.chanmask == 1):
        i: int = i_chan[0]
        resonator = sweep_data.resonator_data[i]
        q.add_job(resonator.fit, sweep_data.df)
    
    q.run_all()
    for i, (f0, qc, qi) in enumerate(q.results):
        sweep_data.fit_f0[i] = f0
        sweep_data.fit_qc[i] = qc
        sweep_data.fit_qi[i] = qi

        diff = resonator.difference
        if np.abs(diff) > sweep_data.diff_to_flag[i]:
            resonator.flagged = True
            print(
                'tone index =',
                f'{i:4d}',
                '|| new tone =',
                f'{sweep_data.fit_f0[i] * 1.0e-6:9.5f}',
                '|| old tone =',
                f'{sweep_data.tone_list[i] * 1.0e-6:9.5f}',
                '|| difference (kHz) =',
                f'{diff:+5.3f}',
            )
    assert False


    