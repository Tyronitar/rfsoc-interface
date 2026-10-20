"""Code for providing context to tasks and."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from rfsocinterface.core.tasks.task import (
    Message,
    Progress,
    SubtaskProgress,
    SubtasksDefined,
    TaskCancelled,
    TaskEvent,
)


# TODO: Implement handling for sending pickled figures to the main process.
# def show_plot(self, figure: Figure) -> None:
#     self.emit('plot', figure)
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


@dataclass
class _SubtaskState:
    name: str
    weight: float
    path: tuple[str, ...]
    fraction: float = 0.0


class SubtaskContext:
    """Context for a subtask.

    Reports progress updates to its parent.
    """

    def __init__(
        self,
        parent: TaskContext,
        state: _SubtaskState,
        update: Callable[[], None],
    ):
        """Initialize a SubtaskContext."""
        self.parent = parent
        self.state = state
        self._update = update

    def progress(
        self,
        value: float,
        *,
        minimum: float = 0,
        maximum: float = 100,
        label: str | None = None,
    ) -> None:
        """Send the subtask's progress to the main process."""
        if maximum <= minimum:
            raise ValueError('maximum must exceed minimum')

        fraction = (value - minimum) / (maximum - minimum)
        self.state.fraction = max(0.0, min(1.0, fraction))

        self.parent._send_event(  # noqa: SLF001
            SubtaskProgress(
                task_id=self.parent.task_id,
                path=self.state.path,
                value=value,
                minimum=minimum,
                maximum=maximum,
                label=label,
            )
        )

        self._update()

    def check_cancelled(self) -> None:
        """Return whether the subtask's parent has started cancellation."""
        self.parent.check_cancelled()

    def is_cancelled(self) -> bool:
        """Check if the subtask's parent has been cancelled."""
        return self.parent.is_cancelled()

    def emit(self, kind: str, payload: object) -> None:
        """Send a message to the main process."""
        self.parent.emit(kind, payload)


class TaskProgress:
    """Helper for managing subtasks and progress updates."""

    def __init__(
        self,
        context: TaskContext,
        subtasks: list[tuple[str, float]],
    ):
        """Initialize a TaskProgress."""
        self.context = context
        self.states = [
            _SubtaskState(
                name=name,
                weight=weight,
                path=(str(i),),
            )
            for i, (name, weight) in enumerate(subtasks)
        ]

        if not self.states:
            raise ValueError('At least one subtask is required')

        if any(s.weight <= 0 for s in self.states):
            raise ValueError('Weights must be positive')

        self.total_weight = sum(s.weight for s in self.states)

        self.context._send_event(  # noqa: SLF001
            SubtasksDefined(
                task_id=context.task_id,
                subtasks=tuple(
                    (
                        state.path,  # Stable path/identifier
                        state.name,
                        state.weight,
                    )
                    for state in self.states
                ),
            )
        )

    def _update(self) -> None:
        """Update the progress accounting for subtasks."""
        overall = (
            sum(state.weight * state.fraction for state in self.states)
            / self.total_weight
        )

        self.context.progress(
            overall,
            minimum=0,
            maximum=1,
        )

    @contextmanager
    def subtask(self, index: int) -> Generator[SubtaskContext, None, None]:
        """Create the context for a subtask."""
        state = self.states[index]

        subcontext = SubtaskContext(
            parent=self.context,
            state=state,
            update=self._update,
        )

        self.context.check_cancelled()
        subcontext.progress(0, minimum=0, maximum=1)

        try:
            yield subcontext
        except BaseException:  # noqa: TRY203
            raise
        else:
            # Successful completion counts as 100%, even if
            # the routine never explicitly reported progress.
            subcontext.progress(1, minimum=0, maximum=1)
            self._update()
