"""Task creation and orchestration handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot

from rfsocinterface.core.tasks.backend import BackendUpdate, TaskBackend
from rfsocinterface.core.tasks.runner import BackendRunner, CommandType
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

        self.runner = BackendRunner(backend)
        self.runner.updated.connect(self._handle_update)
        self.runner.command_failed.connect(self._command_failed)
        self.runner.command_succeeded.connect(self._command_succeeded)
        self.runner.start()

    def submit(self, task: Task):
        """Submit a task to the manager."""
        if task.id in self.records:
            raise ValueError('Duplicate task ID')
        record = TaskRecord(task)
        self.runner.submit(task)
        self.records[task.id] = record
        self.changed.emit(record)

    def cancel(self, task_id: UUID):
        """Cancel a currently executing task."""
        record = self.records[task_id]
        if record.status in TERMINAL_STATUSES:
            return
        match record.task.cancellation_policy:
            case CancellationPolicy.COOPERATIVE:
                self.runner.cancel(task_id)
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
            self.runner.terminate(task_id)
            record.status = TaskStatus.CANCELLING
            self.changed.emit(record)

    @Slot(object)
    def _handle_update(self, updates: BackendUpdate):
        """Check for and handle updates from existing tasks."""
        for event in updates.events:
            record = self.records.get(event.task_id)

            if record is None:
                continue

            # Presevre message events, even if the task has already reached a terminal
            # state
            if isinstance(event, Message):
                self.event_received.emit(event)
                continue

            if record.status in TERMINAL_STATUSES:
                continue

            match event:
                case Started():
                    if record.status != TaskStatus.CANCELLING:
                        record.status = TaskStatus.RUNNING
                case Progress():
                    record.progress = event
                case Succeeded():
                    record.status = TaskStatus.SUCCEEDED
                    record.result = event.result
                case Failed():
                    record.status = TaskStatus.FAILED
                    record.error = event.error
                    record.traceback = event.traceback
                case Cancelled():
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

    @Slot(object, str, str)
    def _command_failed(
        self, command: CommandType, task_id: UUID, error: str, traceback: str
    ):
        """Handle failed commands sent to the runner."""
        record = self.records.get(task_id)

        if record is None or record.status in TERMINAL_STATUSES:
            return

        match command:
            case CommandType.START:
                record.status = TaskStatus.FAILED
                record.error = error
                record.traceback = traceback
            case CommandType.CANCEL | CommandType.TERMINATE:
                # TODO: Report cancellation error to the GUI
                record.error = error
                record.traceback = traceback

        self.changed.emit(record)

    @Slot(object, object)
    def _command_succeeded(self, task_id: UUID, command: CommandType):
        """Hook for acknowledging command completion."""
        # TODO: Add some acknowledgment logic if desired.

    def close(self) -> None:
        """Close the manager and do the necessary cleanup."""
        self.runner.request_stop()
