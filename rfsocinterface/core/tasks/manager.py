"""Task creation and orchestration handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot

from rfsocinterface.core.tasks.backend import BackendUpdate, TaskBackend
from rfsocinterface.core.tasks.runner import BackendCommandType, BackendRunner
from rfsocinterface.core.tasks.task import (
    TERMINAL_STATUSES,
    CancellationPolicy,
    Cancelled,
    Failed,
    IPCFailed,
    Message,
    Progress,
    Started,
    SubtaskProgress,
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
    subtask_progress: dict[tuple[str, ...], SubtaskProgress] = field(
        default_factory=dict
    )
    result: Any = None
    error: str | None = None
    traceback: str | None = None
    worker_exited: bool = False


class TaskManager(QObject):
    """Widget for tracking task state and communicating with the GUI."""

    changed = Signal(object)
    event_received = Signal(object)

    def __init__(
        self,
        backend: TaskBackend,
        max_workers: int = 4,
        parent: QObject | None = None,
    ):
        """Initialize a TaskManager."""
        super().__init__(parent)

        self.backend = backend
        self.records: dict[UUID, TaskRecord] = {}

        self._stopping = False
        self._active: set[UUID] = set()
        self._resource_owners: dict[str, UUID] = {}
        self.max_workers = max_workers

        self.runner = BackendRunner(backend)
        self.runner.updated.connect(self._handle_update)
        self.runner.command_failed.connect(self._command_failed)
        self.runner.command_succeeded.connect(self._command_succeeded)
        self.runner.fatal_error.connect(self._handle_fatal_error)
        self.runner.start()

    def _validate_dependencies(self, task: Task) -> None:
        """Check that a task's dependencies are valid."""
        if task.id in task.depends_on:
            raise ValueError('A task cannot depend on itself')

        missing = task.depends_on - self.records.keys()

        if missing:
            raise ValueError(f'Task has unknown dependencies: {missing}')

    def submit(self, task: Task) -> UUID:
        """Submit a task to the manager."""
        if task.id in self.records:
            raise ValueError('Duplicate task ID')

        self._validate_dependencies(task)

        record = TaskRecord(task)
        self.records[task.id] = record

        self.changed.emit(record)
        self._schedule()

        return task.id

    def _dependencies_succeeded(self, task: Task) -> bool:
        """Check if all of a task's dependencies succeeded."""
        return all(
            self.records[dep_id].status == TaskStatus.SUCCEEDED
            and self.records[dep_id].worker_exited
            for dep_id in task.depends_on
        )

    def _resources_available(self, task: Task) -> bool:
        """Check that a task's required resources are available."""
        return all(resource not in self._resource_owners for resource in task.resources)

    def _acquire_resources(self, task: Task) -> None:
        """Assign resource ownership of the task."""
        for resource in task.resources:
            self._resource_owners[resource] = task.id

    def _release_resources(self, task: Task) -> None:
        """Free ownership of this task's resources after completion."""
        for resource in task.resources:
            if self._resource_owners.get(resource) == task.id:
                del self._resource_owners[resource]

    def _schedule(self) -> None:
        """Schedule submitted tasks for execution."""
        if self._stopping:
            return

        # Propagate failed dependencies
        for record in self.records.values():
            if record.status != TaskStatus.PENDING:
                continue

            dependencies = [self.records[dep_id] for dep_id in record.task.depends_on]

            if any(
                dep.status
                in {
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.SKIPPED,
                }
                for dep in dependencies
            ):
                record.status = TaskStatus.SKIPPED
                record.error = 'A dependency did not succeed'
                self.changed.emit(record)

        # Dispatch ready tasks
        for record in self.records.values():
            if len(self._active) >= self.max_workers:
                break

            if record.status != TaskStatus.PENDING:
                continue

            task = record.task

            if not self._dependencies_succeeded(task):
                continue

            if not self._resources_available(task):
                continue

            self._acquire_resources(task)
            self._active.add(task.id)
            record.status = TaskStatus.STARTING
            self.changed.emit(record)

            try:
                self.runner.submit(task)
            except Exception:
                self._active.remove(task.id)
                self._release_resources(task)
                raise

    def cancel(self, task_id: UUID):
        """Cancel a task."""
        record = self.records[task_id]
        match record.status:
            # Ignore for tasks that have already completed
            case (
                TaskStatus.CANCELLED
                | TaskStatus.SUCCEEDED
                | TaskStatus.FAILED
                | TaskStatus.SKIPPED
            ):
                return
            # Ignore duplicate requests
            case TaskStatus.CANCELLING:
                return
            # Cancel pending tasks locally without contacting the backend
            case TaskStatus.PENDING:
                if record.task.cancellation_policy == CancellationPolicy.DISABLED:
                    return
                record.status = TaskStatus.CANCELLED
                self.changed.emit(record)
                self._schedule()
                return
            # Send cancellation request to the backend to handle for starting tasks
            case TaskStatus.STARTING:
                self.runner.cancel(task_id)
                record.status = TaskStatus.CANCELLING
                self.changed.emit(record)
            # Cancel a running task according to its policy
            case TaskStatus.RUNNING:
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
                case SubtaskProgress():
                    record.subtask_progress[event.path] = event
                case Succeeded():
                    record.status = TaskStatus.SUCCEEDED
                    record.result = event.result
                case Failed():
                    record.status = TaskStatus.FAILED
                    record.error = event.error
                    record.traceback = event.traceback
                case Cancelled():
                    record.status = TaskStatus.CANCELLED
                case IPCFailed():
                    if record.status not in TERMINAL_STATUSES:
                        record.status = TaskStatus.FAILED
                    record.error = event.error

            self.changed.emit(record)

        # Handle workers that have exited and been cleaned up by the backend
        for task_id, exit_info in updates.exited_workers.items():
            record = self.records.get(task_id)

            if record is None:
                continue

            record.worker_exited = True

            if record.status not in TERMINAL_STATUSES:
                if exit_info.receiver_error:
                    record.status = TaskStatus.FAILED
                    record.error = f'IPC failure: {exit_info.receiver_error}'
                elif exit_info.termination_requested:
                    record.status = TaskStatus.CANCELLED
                else:
                    record.status = TaskStatus.FAILED
                    record.error = (
                        f'Worker exited with code {exit_info.exit_code} '
                        'without reporting a terminal outcome'
                    )
            self.changed.emit(record)

        # Release resources
        for task_id in updates.exited_workers:
            if task_id in self._active:
                self._active.remove(task_id)
                self._release_resources(self.records[task_id].task)

        # Schedule tasks if resources are available
        self._schedule()

    @Slot(object, object, str, str)
    def _command_failed(
        self, command: BackendCommandType, task_id: UUID, error: str, traceback: str
    ):
        """Handle failed commands sent to the runner."""
        record = self.records.get(task_id)

        if record is None or record.status in TERMINAL_STATUSES:
            return

        match command:
            case BackendCommandType.START:
                record.status = TaskStatus.FAILED
                record.error = error
                record.traceback = traceback
                self._active.discard(task_id)
                self._release_resources(record.task)
            case BackendCommandType.CANCEL | BackendCommandType.TERMINATE:
                # TODO: Report cancellation error to the GUI
                record.error = error
                record.traceback = traceback

        self.changed.emit(record)
        self._schedule()

    @Slot(str, str)
    def _handle_fatal_error(self, error: str, traceback: str):
        """Handle fatal errors reported by the runner."""
        # TODO: Mark affected tasks as failed or indicate unknown execution state
        for record in self.records.values():
            if record.worker_exited:
                continue

            if record.status not in TERMINAL_STATUSES:
                # Backend crashed before verfiying that the task was completed
                record.status = TaskStatus.UNKNOWN

            record.error = f'Backend failure: {error}'
            record.traceback = traceback
            self.changed.emit(record)

    @Slot(object, object)
    def _command_succeeded(self, task_id: UUID, command: BackendCommandType):
        """Hook for acknowledging command completion."""
        # TODO: Add some acknowledgment logic if desired.

    def close(self) -> None:
        """Close the manager and do the necessary cleanup."""
        self._stopping = True
        self.runner.request_stop()
