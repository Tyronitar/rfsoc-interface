from PySide6.QtWidgets import QDialog, QWidget, QApplication, QProgressDialog
from PySide6.QtCore import Signal, Qt
from typing import Callable, Any

from rfsocinterface.ui.progress_bar_ui import Ui_Dialog
from rfsocinterface.utils import Job, P, JobQueue, SequentialJobQueue


class ProgressBarDialog(QProgressDialog):
    incrementSignal = Signal()

    def __init__(self, max_threads: int=1, parent: QWidget | None=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        # self.setupUi(self)
        self.reset()
        self.job_queue = JobQueue(max_threads=max_threads)
        self.incrementSignal.connect(self.increment)
    
    # def reset(self):
    #     self.total_tasks = 0
    #     self._completed_tasks = 0
    #     self.progressBar.setValue(0)
    
    def add_job(self, func: Callable[P, None], *args: P.args, num_tasks: int=1, use_main_thread=False, start_message: str='', **kwargs: P.kwargs):
        job = Job(func, *args, **kwargs)
        job.updateProgress.connect(self.increment)
        job.set_start_message(start_message)
        # job.finishWork.connect(self.worker_finished, job)
        self.job_queue.add_job(job, use_main_thread=use_main_thread)
        job.started.connect(self.worker_started)
        self.setMaximum(num_tasks)
        # self.total_tasks += num_tasks
    
    def worker_finished(self, message: str):
        if message:
            self.setLabelText(message)
            # self.label.setText(message)

    def worker_started(self, message: str):
        if message:
            self.setLabelText(message)
            # self.label.setText(message)
    
    def completed(self) -> bool:
        return self._completed_tasks >= self.total_tasks
    
    # def start_next(self):
    #     worker = self.job_queue.pop()
    #     worker.start()

    def start(self):
        self.job_queue.run_all()
        # for worker in self.job_queue:
        #     worker.start()
    
    def set_total_tasks(self, total: int):
        self.total_tasks = total
    
    def increment(self):
        self.setValue(self.value() + 1)
        # if self._completed_tasks < self.total_tasks:
        #     self._completed_tasks += 1
        #     self.progressBar.setValue(int((self._completed_tasks / self.total_tasks) * 100))

class SequentialProgressBarDialog(ProgressBarDialog):

    allFinished = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(max_threads=1, parent=parent)
        self.job_queue = SequentialJobQueue()
        self.job_queue.allFinished.connect(self.allFinished.emit)
        self.job_queue.allFinished.connect(lambda: print('jobs done'))
    
    def get_result(self, idx: int) -> Any:
        return self.job_queue.results[idx]