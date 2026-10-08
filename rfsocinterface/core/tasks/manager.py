"""Task creation and orchestration handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PySide6.QtCore import QObject, QTimer, Signal

from rfsocinterface.core.tasks.backend import TaskBackend
from rfsocinterface.core.tasks.tasks import (
    TERMINAL_STATUSES,
    CancellationPolicy,
    Cancelled,
    Failed,
    Message,
    Progress,
    Started,
    Succeeded,
    Task,
    TaskStatus,
)


@dataclass
class TaskRecord:
    """A record of a task and its current state."""

    task: Task
    status: TaskStatus = TaskStatus.PENDING
    progress: Progress | None = None
    result: Any = None
    error: str | None = None
    traceback: str | None = None


class TaskManager(QObject):
    """Widget for tracking task state and communicating with the GUI."""

    changed = Signal(object)
    event_received = Signal(object)

    def __init__(
        self,
        backend: TaskBackend,
        parent: QObject | None = None,
    ):
        """Initialize a TaskManager."""
        super().__init__(parent)

        self.backend = backend
        self.records: dict[UUID, TaskRecord] = {}

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def submit(self, task: Task) -> UUID:
        """Submit a task to the manager."""
        if task.id in self.records:
            raise ValueError('Duplicate task ID')
        record = TaskRecord(task)
        self.backend.start(task)
        self.records[task.id] = record
        self.changed.emit(record)
        return task.id

    def cancel(self, task_id: UUID) -> None:
        """Cancel a currently executing task."""
        record = self.records[task_id]
        if record.status in TERMINAL_STATUSES:
            return
        match record.task.cancellation_policy:
            case CancellationPolicy.COOPERATIVE:
                self.backend.cancel(task_id)
                record.status = TaskStatus.CANCELLING
                self.changed.emit(record)
            case CancellationPolicy.TERMINATE:
                self.terminate(task_id)
            case CancellationPolicy.DISABLED:
                return

    def terminate(self, task_id: UUID) -> None:
        """Forcibly terminate a currently executing task."""
        record = self.records[task_id]
        if record.status not in TERMINAL_STATUSES:
            self.backend.terminate(task_id)
            # Termination is not guaranteed to be immediate; _poll reconciles exit.
            record.status = TaskStatus.CANCELLING
            self.changed.emit(record)

    def _poll(self) -> None:
        """Check for and handle updates from existing tasks."""
        updates = self.backend.poll()

        for event in updates.events:
            record = self.records.get(event.task_id)

            if record is None or record.status in TERMINAL:
                continue

            if isinstance(event, Started):
                if record.status != TaskStatus.CANCELLING:
                    record.status = TaskStatus.RUNNING

            elif isinstance(event, Progress):
                record.progress = event

            elif isinstance(event, Message):
                self.event_received.emit(event)

            elif isinstance(event, Succeeded):
                record.status = TaskStatus.SUCCEEDED
                record.result = event.result

            elif isinstance(event, Failed):
                record.status = TaskStatus.FAILED
                record.error = event.error
                record.traceback = event.traceback

            elif isinstance(event, Cancelled):
                record.status = TaskStatus.CANCELLED

            self.changed.emit(record)

        # Workers that exited without reporting a terminal outcome.
        for task_id, exit_info in updates.exited_workers.items():
            record = self.records.get(task_id)

            if record is None or record.status in TERMINAL_STATUSES:
                continue

            if exit_info.termination_requested:
                record.status = TaskStatus.CANCELLED
            else:
                record.status = TaskStatus.FAILED
                record.error = (
                    f'Worker exited with code {exit_info.exit_code} '
                    'without reporting a result'
                )

            self.changed.emit(record)

    def close(self) -> None:
        """Close the manager and do the necessary cleanup."""
        self.timer.stop()
        self.backend.close()
