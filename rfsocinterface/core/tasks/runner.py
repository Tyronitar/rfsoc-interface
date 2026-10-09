"""Interface between the manager and the backend that runs in a separate thread."""

from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID

from PySide6.QtCore import QObject, Signal

from .backend import BackendUpdate, TaskBackend
from .tasks import Task


class CommandType(Enum):
    """Type of message to send to a backend."""

    START = auto()
    CANCEL = auto()
    TERMINATE = auto()
    STOP = auto()


@dataclass(frozen=True)
class BackendCommand:
    """A command issued to a manager's backend."""

    kind: CommandType
    task_id: UUID | None = None
    task: Task | None = None


class BackendRunner(QObject):
    """Execute backend operations outside the GUI thread."""

    updated = Signal(object)
    command_failed = Signal(object, object, str, str)
    command_succeeded = Signal(object, object)
    stopped = Signal()
    fatal_error = Signal(str, str)

    def __init__(
        self,
        backend: TaskBackend,
        poll_interval: float = 0.03,
        parent: QObject | None = None,
    ):
        """Initialize a BackendRunner."""
        super().__init__(parent)

        self.backend = backend
        self.poll_interval = poll_interval

        self._commands: queue.Queue[BackendCommand] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        """Start the BackendRunner's polling thread."""
        if self._thread is not None:
            raise RuntimeError('BackendRunner already started')

        self._thread = threading.Thread(
            target=self._run,
            name='TaskBackendRunner',
            daemon=False,
        )
        self._thread.start()

    def submit(self, task: Task) -> None:
        """Submit a task to the backend."""
        self._enqueue(BackendCommand(CommandType.START, task.id, task))

    def cancel(self, task_id: UUID) -> None:
        """Cancel execution of a task."""
        self._enqueue(BackendCommand(CommandType.CANCEL, task_id))

    def terminate(self, task_id: UUID) -> None:
        """Forceibly terminate execution of a task."""
        self._enqueue(BackendCommand(CommandType.TERMINATE, task_id))

    def _enqueue(self, command: BackendCommand) -> None:
        """Add a command to the queue to be processed."""
        if self._stopping:
            raise RuntimeError('BackendRunner is stopping')
        self._commands.put(command)

    def request_stop(self) -> None:
        """Request that the BackendRunner end it's polling thread."""
        if not self._stopping:
            self._stopping = True
            self._commands.put(BackendCommand(CommandType.STOP))

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for shutdown. Call only when blocking is acceptable."""
        if self._thread is None:
            return True

        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _execute(self, command: BackendCommand) -> None:
        """Pass a command to the backend for execution."""
        match command.kind:
            case CommandType.START:
                assert command.task is not None
                self.backend.start(command.task)
            case CommandType.CANCEL:
                assert command.task_id is not None
                self.backend.cancel(command.task_id)
            case CommandType.TERMINATE:
                assert command.task_id is not None
                self.backend.terminate(command.task_id)
            case _:
                raise ValueError(f'Unexpected command: {command.kind}')

        self.command_succeeded.emit(command.task_id, command.kind)

    def _run(self) -> None:
        """Wrapper around run loop for handling backend errors."""
        try:
            self._run_loop()
        except BaseException as exc:  # noqa: BLE001
            self.fatal_error.emit(
                f'{type(exc).__name__}: {exc}',
                traceback.format_exc(),
            )
        finally:
            try:
                self.backend.close()
            except BaseException as exc:  # noqa: BLE001
                self.fatal_error.emit(
                    f'Backend cleanup failed: {exc}',
                    traceback.format_exc(),
                )
            finally:
                self.stopped.emit()

    def _run_loop(self) -> None:
        """Core loop for handling communications."""
        try:
            while True:
                # Wait briefly for a command. This also determines
                # the normal polling interval.
                try:
                    command = self._commands.get(timeout=self.poll_interval)
                except queue.Empty:
                    command = None

                if command is not None:
                    if command.kind == CommandType.STOP:
                        break

                    try:
                        self._execute(command)
                    except Exception as exc:  # noqa: BLE001
                        self.command_failed.emit(
                            command.kind,
                            command.task_id,
                            f'{type(exc).__name__}: {exc}',
                            traceback.format_exc(),
                        )

                # Drain additional commands without waiting.
                # Bound the batch so polling cannot be starved.
                for _ in range(99):
                    try:
                        command = self._commands.get_nowait()
                    except queue.Empty:
                        break

                    if command.kind == CommandType.STOP:
                        return

                    try:
                        self._execute(command)
                    except Exception as exc:  # noqa: BLE001
                        self.command_failed.emit(
                            command.kind,
                            command.task_id,
                            f'{type(exc).__name__}: {exc}',
                            traceback.format_exc(),
                        )

                update: BackendUpdate = self.backend.poll()

                if update.events or update.exited_workers:
                    self.updated.emit(update)

        finally:
            try:
                self.backend.close()
            finally:
                self.stopped.emit()
