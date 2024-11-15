from PySide6.QtWidgets import QDialog, QWidget, QApplication, QProgressDialog
from PySide6.QtCore import Signal, Qt
from typing import Callable, Any

from rfsocinterface.ui.progress_bar_ui import Ui_Dialog
from rfsocinterface.utils import Job, P, JobQueue, SequentialJobQueue


class ProgressBarDialog(QProgressDialog):
    incrementSignal = Signal(int)

    def __init__(self,
                 labelText: str,
                 cancelButtonText: str,
                 minimum: int,
                 maximum: int,
                 max_threads: int=1,
                 parent: QWidget | None=None,
                 flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(
            labelText,
            cancelButtonText,
            minimum,
            maximum,
            parent=parent,
            flags=flags)
        # self.setupUi(self)
        self.setAutoClose(False)
        self.reset()
        self.job_queue = JobQueue(max_threads=max_threads)
        self.incrementSignal.connect(self.increment)
        self.canceled.connect(self.job_queue.cancel)
    
    # def reset(self):
    #     self.total_tasks = 0
    #     self._completed_tasks = 0
    #     self.progressBar.setValue(0)
    
    def add_job(self, func: Callable[P, None], *args: P.args, use_main_thread=False, start_message: str='', **kwargs: P.kwargs):
        job = Job(func, *args, **kwargs)
        job.updateProgress.connect(self.increment)
        job.set_start_message(start_message)
        # job.finishWork.connect(self.worker_finished, job)
        self.job_queue.add_job(job, use_main_thread=use_main_thread)
        job.started.connect(self.worker_started)

    def worker_started(self, message: str):
        if message:
            self.setLabelText(message)
    
    # def start_next(self):
    #     worker = self.job_queue.pop()
    #     worker.start()

    def start(self):
        try:
            self.job_queue.run_all()
        except KeyboardInterrupt as e:
            print(e)

        # for worker in self.job_queue:
        #     worker.start()
    
    def increment(self, new_max: int):
        if new_max > 0:
            self.setMaximum(new_max)
            self.reset()
        else:
            self.setValue(self.value() + 1)

class SequentialProgressBarDialog(ProgressBarDialog):

    allFinished = Signal()

    def __init__(self,
                 labelText: str,
                 cancelButtonText: str,
                 minimum: int,
                 maximum: int,
                 parent: QWidget | None=None,
                 flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(
            labelText,
            cancelButtonText,
            minimum,
            maximum,
            max_threads=1,
            parent=parent,
            flags=flags,
        )
        # self.job_queue = SequentialJobQueue()
        # self.job_queue.allFinished.connect(self.allFinished.emit)
        # self.job_queue.allFinished.connect(lambda: print('jobs done'))
        # self.canceled.connect(self.job_queue.cancel)
    
    def get_result(self, idx: int) -> Any:
        return self.job_queue.results[idx]