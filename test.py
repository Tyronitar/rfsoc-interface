import time
from concurrent.futures import Future, CancelledError
from threading import current_thread
from typing import Callable, Iterable

from PySide6.QtWidgets import QMainWindow, QPushButton, QApplication
from PySide6.QtCore import Qt

from rfsocinterface.gui.widgets.progress_bar import JobProgressDialog
from rfsocinterface.core.utils import print_future_result

def square(n: int) -> int:
    return n ** 2

def counting(n: int, progress_callback: Callable | None=None):
    if progress_callback is not None:
        progress_callback()
    time.sleep(0.05)
    return n

class Window(QMainWindow):
    def __init__(self, total: int, parent = None):
        super().__init__(parent)
        self.count = 0
        self.total = total

        butt = QPushButton(self)
        butt.setText('Push Me!')
        butt.clicked.connect(self.on_push)
        self.setCentralWidget(butt)
    
    def on_push(self):
        self.d = JobProgressDialog(
            labelText='Counting...',
            cancelButtonText='Cancel',
            minimum=0,
            maximum=self.total,
            max_workers=4,
            parent=self,
        )
        self.d.setModal(True)
        # d.setValue(0)
        self.d.show()
        future = self.d.map(counting, range(self.total))
        future.add_done_callback(print_future_result)
        # d.canceled.connect(d.close)

if __name__ == '__main__':
    app = QApplication()
    win = Window(total=100)
    win.show()
    app.exec()
