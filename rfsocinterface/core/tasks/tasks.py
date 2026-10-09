"""Abstraction of background tasks to be completed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4


class TaskStatus(Enum):
    """Status of a task."""

    PENDING = auto()
    """Task has not statred yet."""

    RUNNING = auto()
    """Task is currently executing."""

    CANCELLING = auto()
    """Task is in the process of handling cancellation."""

    # Terminal Statuses
    SUCCEEDED = auto()
    """Task has completed execution succesfully.."""

    FAILED = auto()
    """Task failed execution due to an exception."""

    CANCELLED = auto()
    """Task has finished handling cancellation."""


TERMINAL_STATUSES = {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
type TerminalEvent = Succeeded | Failed | Cancelled


class CancellationPolicy(Enum):
    """Policy dictating how a task handles early stopping."""

    COOPERATIVE = auto()
    """The manager should set the task's cancellation event and the worker will handle.

    Use for tasks that should not be stopped mid execution (e.g. file writes,
    telescope motion). Worker is expected to handle cleanup during signal handling.
    Requires `Task.with_context == True`, as the cancel signal would not be received
    otherwise.
    """

    TERMINATE = auto()
    """The manager is safe to terminate the process in the middle of execution.

    Cleanup is not guaranteed, so only use in functions where cleanup is not essential.
    """

    DISABLED = auto()
    """The task can not be interrupted by the manager.

    Cleanup is guaranteed if the target is executed normally. This is the default for
    new tasks.
    """


@dataclass(frozen=True)
class Task:
    """Wrapper for a task to be completed in the background and relevant information.

    Attributes:
        target: The target callable to execute.
        args: Positional arguments to pass to the target callable.
        kwargs: Keyword arguments to pass to the target callable.
        name: Identifier for this task. Defaults to 'Task'.
        with_context: Whether to use context with this task for (e.g. progress updates).
            If True, then `target` must accept the keyword argument `context`.
        id: Uniqiue identifier for this task.
        cancellation_policy: How this task should handle cancellation. Defaults to
            `CancellationPolicy.Disabled`.
    """

    target: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    name: str = 'Task'
    with_context: bool = False
    id: UUID = field(default_factory=uuid4)
    cancellation_policy: CancellationPolicy = CancellationPolicy.DISABLED


@dataclass(frozen=True)
class TaskEvent:
    """An event containing information about the execution of a task."""

    task_id: UUID


@dataclass(frozen=True)
class Started(TaskEvent):
    """Event indicating the beginning of execution."""


@dataclass(frozen=True)
class Progress(TaskEvent):
    """Event indicating values for progress bars.

    Attributes correspond to the values of a QProgressBar.
    """

    value: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    label: str | None = None


@dataclass(frozen=True)
class Message(TaskEvent):
    """Message to communicate to the main process."""

    kind: str
    payload: Any


@dataclass(frozen=True)
class Succeeded(TaskEvent):
    """Event indicating that a task has succesfully executed."""

    result: Any


@dataclass(frozen=True)
class Failed(TaskEvent):
    """Event indicating that a task has failed due to an exception."""

    error: str
    traceback: str


@dataclass(frozen=True)
class Cancelled(TaskEvent):
    """Event indicating that a task has finished cancelling."""


@dataclass(frozen=True)
class IPCFailed(TaskEvent):
    """Event indicating that IPC has failed."""

    error: str


class TaskCancelled(Exception):  # noqa: N818
    """Exception raised to signal a task to interrupt its execution."""


class TaskContext:
    """Backend-independent interface for reporting progress and checking status."""

    def __init__(
        self,
        task_id: UUID,
        send_event: Callable[[TaskEvent], None],
        is_cancelled: Callable[[], bool],
    ):
        """Initialize a TaskContext."""
        self.task_id = task_id
        self._send_event = send_event
        self._is_cancelled = is_cancelled

    def emit(self, kind: str, payload: Any) -> None:
        """Send a message to the main process."""
        self._send_event(Message(self.task_id, kind, payload))

    def progress(
        self,
        value: float | None = None,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        label: str | None = None,
    ) -> None:
        """Send the task's progress to the main process."""
        self._send_event(Progress(self.task_id, value, minimum, maximum, label))

    def is_cancelled(self) -> bool:
        """Return whether the task has started cancellation."""
        return self._is_cancelled()

    def check_cancelled(self) -> None:
        """Check if the task has been cancelled."""
        if self.is_cancelled():
            raise TaskCancelled

    # TODO: Implement handling for sending pickled figures to the main process.
    # def show_plot(self, figure: Figure) -> None:
    #     self.emit('plot', figure)
