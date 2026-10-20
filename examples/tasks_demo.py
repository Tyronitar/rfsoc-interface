"""Demo for demonstrating background tasks in a GUI application."""
from __future__ import annotations

import multiprocessing as mp
import sys
import time
from uuid import UUID

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


from rfsocinterface.core.tasks import (
    MultiprocessingBackend,
    TaskManager,
    TaskRecord,
    TaskProgress,
    CancellationPolicy,
    Task,
    TaskStatus,
)
from rfsocinterface.gui.widgets import TaskProgressWidget


def example_job(seconds: int, *, context):
    for i in range(seconds):
        context.check_cancelled()
        time.sleep(1)
        context.progress(
            i + 1, minimum=0, maximum=seconds, label=f'Step {i + 1}/{seconds}'
        )
    context.emit('plot_request', {'x': [0, 1, 2], 'y': [0, 1, 4]})
    return f'Processed {seconds} steps'

def example_composite_job(seconds: int, subtasks: int, *, context):
    progress = TaskProgress(
        context,
        subtasks=[
            (f'wait_{i}', 1.0) for i in range(subtasks)
        ],
    )
    for i in range(subtasks):
        context.check_cancelled()
        with progress.subtask(i) as subcontext:
            example_job(int(seconds / subtasks), context=subcontext)
    return f'Processed {seconds} steps'



def example_job_contextless(seconds: int):
    for i in range(seconds):
        time.sleep(1)
    return f'Processed {seconds} steps'


class TaskRow(QWidget):
    def __init__(
        self, manager: TaskManager, task_id, cancellation_policy: CancellationPolicy
    ):
        super().__init__()
        self.manager = manager
        self.task_id = task_id
        self.cancellation_policy = cancellation_policy
        self.label = QLabel()
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)

        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel)
        layout = QHBoxLayout(self)
        layout.addWidget(self.label, 2)
        layout.addWidget(self.bar, 3)
        layout.addWidget(self.cancel_button)

    def cancel(self):
        self.manager.cancel(self.task_id)

    def update_record(self, record: TaskRecord):
        if record.task.id != self.task_id:
            return
        self.label.setText(
            f'{record.task.name}: {record.status.name}'
            + (
                f' — {record.progress.label}'
                if record.progress and record.progress.label
                else ''
            )
        )
        if record.progress and record.progress.value is not None:
            p = record.progress
            self.bar.setRange(0, 1000)
            minimum = p.minimum if p.minimum is not None else 0
            maximum = p.maximum if p.maximum is not None else 1
            ratio = (
                (p.value - minimum) / (maximum - minimum) if maximum > minimum else 0
            )
            self.bar.setValue(max(0, min(1000, round(ratio * 1000))))
        elif record.status in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED):
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000)

        if record.status == TaskStatus.CANCELLED:
            self.bar.setFormat('Canceled')
            self.bar.setStyleSheet("""
                QProgressBar {
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #8c8c8c;
                }
            """)

        self.cancel_button.setEnabled(
            record.status
            not in (
                TaskStatus.CANCELLING,
                TaskStatus.SUCCEEDED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            )
            and record.task.cancellation_policy != CancellationPolicy.DISABLED
        )


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Background task demo')
        self.resize(750, 350)
        self.manager = TaskManager(MultiprocessingBackend(ipc_failure_grace=0.25))
        self.rows: dict[UUID, TaskProgressWidget] = {}
        layout = QVBoxLayout(self)
        add_button = QPushButton('Start 10-second task')
        add_button.clicked.connect(self.create_task)
        layout.addWidget(add_button)
        self.tasks_layout = QVBoxLayout()
        layout.addLayout(self.tasks_layout)
        layout.addStretch()
        self.manager.changed.connect(self.on_changed)
        self.manager.event_received.connect(self.on_event)

    def create_task(self):
        i = len(self.rows.values())
        match i % 3:
            case 0:
                task = Task(
                    target=example_job,
                    args=(10,),
                    name='With context',
                    with_context=True,
                    cancellation_policy=CancellationPolicy.COOPERATIVE,
                )
            case 1:
                task = Task(
                    target=example_job_contextless,
                    args=(10,),
                    name='No context',
                    with_context=False,
                    cancellation_policy=CancellationPolicy.TERMINATE,
                )
            case _:
                task = Task(
                    target=example_job_contextless,
                    args=(10,),
                    name='Cancel disabled',
                    with_context=False,
                    cancellation_policy=CancellationPolicy.DISABLED,
                )
        self.add_task(task)

    def add_task(self, task: Task):
        row = TaskRow(self.manager, task.id, task.cancellation_policy)
        row = TaskProgressWidget(self.manager, task.id, parent=self)
        self.rows[task.id] = row
        self.tasks_layout.addWidget(row)
        self.manager.submit(task)

    def on_changed(self, record: TaskRecord):
        row = self.rows.get(record.task.id)
        if row is not None:
            if record.status == TaskStatus.FAILED:
                print(f'Task failed: {record.error}\n{record.traceback}')
            row.update_record(record)

    def on_event(self, event):
        if event.kind == 'plot_request':
            print('Received plot request:', event.payload)
            # Construct a matplotlib FigureCanvasQTAgg here in the GUI thread.
        elif event.kind == 'plot':
            # dialog = show_figure(event.data, parent=main_window)

            # Retain a reference so the dialog stays alive.
            # main_window.plot_dialogs.append(dialog)
            ...

    def closeEvent(self, event):
        self.manager.close()
        self.manager.runner.wait()
        super().closeEvent(event)


if __name__ == '__main__':
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    window.add_task(
        Task(
            target=example_composite_job,
            args=(15, 3),
            cancellation_policy=CancellationPolicy.COOPERATIVE,
            with_context=True,
        )

    )
    sys.exit(app.exec())
