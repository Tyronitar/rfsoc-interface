"""Worker backend implementations."""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import traceback
import typing
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Protocol
from uuid import UUID

from rfsocinterface.core.tasks.tasks import (
    Cancelled,
    Failed,
    Started,
    Succeeded,
    Task,
    TaskCancelled,
    TaskContext,
    TaskEvent,
    TerminalEvent,
)


@dataclass(frozen=True)
class WorkerExit:
    """Information describing a worker's exit conditions."""

    exit_code: int | None
    termination_requested: bool = False


@dataclass
class BackendUpdate:
    """Structured information containing the state of the backend and its workers."""

    events: list[TaskEvent]
    """Events since the last poll."""

    exited_workers: dict[UUID, WorkerExit]
    """Workers that exited without reporting an outcome."""


class TaskBackend(Protocol):
    """Class handling worker creation and task execution."""

    def start(self, task: Task) -> None:
        """Start executing a task."""
        ...

    def cancel(self, task_id: UUID) -> None:
        """Request cancellation of a running task."""
        ...

    def terminate(self, task_id: UUID) -> None:
        """Forcefully terminate a running task."""
        ...

    def poll(self, limit: int = 100) -> BackendUpdate:
        """Retrieve task events and backend-generated events."""
        ...

    def close(self) -> None:
        """Release backend resources."""
        ...


@dataclass
class MultiprocessingWorkerHandle:
    """Handle containing a worker's information (i.e. process, connection, etc.)."""

    process: mp.Process
    """The process this worker is operating on."""

    cancel_event: mp.Event
    """Event to trigger cancellation."""

    conn: Connection
    """Connection to send events to the backend."""

    termination_requested: bool = False
    """Whether termination was requested for this task."""

    terminal_received: bool = False
    """Whether the worker's terminal event was received."""

    channel_closed: bool = False
    """Whether the worker's connection has been closed."""

    def is_alive(self) -> bool:
        """Whether the process is still alive."""
        return self.process.is_alive()

    def cancel(self) -> None:
        """Trigger this worker's cancel event."""
        self.cancel_event.set()


def multiprocessing_worker_entry(
    task: Task, cancel_event: mp.Event, event_conn: Connection
) -> None:
    """Entry point for a worker to execute a task from a MultiprocessingBackend."""
    context = TaskContext(
        task.id,
        send_event=event_conn.send,
        is_cancelled=cancel_event.is_set,
    )
    try:
        context.check_cancelled()
        event_conn.send(Started(task.id))

        kwargs = dict(task.kwargs)
        if task.with_context:
            if 'context' in kwargs:
                raise ValueError('context is reserved when with_context=True')  # noqa: TRY301
            kwargs['context'] = context

        result = task.target(*task.args, **kwargs)
        context.check_cancelled()

        event_conn.send(Succeeded(task.id, result))
    except TaskCancelled:
        event_conn.send(Cancelled(task.id))
    except Exception as exc:  # noqa: BLE001
        with contextlib.suppress(OSError, BrokenPipeError):
            event_conn.send(
                Failed(task.id, f'{type(exc).__name__}: {exc}', traceback.format_exc())
            )
    finally:
        event_conn.close()


class MultiprocessingBackend:
    """TaskBackend implementation using multiprocessing."""

    def __init__(self) -> None:
        """Initialize a MultiprocessingBackend."""
        self.context = mp.get_context('spawn')
        self.workers: dict[UUID, MultiprocessingWorkerHandle] = {}

    @typing.override
    def start(self, task: Task) -> None:
        if task.id in self.workers:
            raise ValueError(f'Duplicate task ID: {task.id}')

        cancel_event = self.context.Event()
        recv_conn, send_conn = self.context.Pipe(duplex=False)

        process = self.context.Process(
            target=multiprocessing_worker_entry,
            args=(task, cancel_event, send_conn),
            name=task.name,
        )

        try:
            process.start()
        except:
            process.close()
            send_conn.close()
            recv_conn.close()
            raise
        else:
            send_conn.close()

        self.workers[task.id] = MultiprocessingWorkerHandle(
            process=process,
            cancel_event=cancel_event,
            conn=recv_conn,
        )

    @typing.override
    def cancel(self, task_id: UUID) -> None:
        self.workers[task_id].cancel_event.set()

    @typing.override
    def terminate(self, task_id: UUID) -> None:
        handle = self.workers[task_id]
        handle.termination_requested = True
        if handle.process.is_alive():
            handle.process.terminate()

    @typing.override
    def poll(self, limit: int = 100) -> BackendUpdate:
        events: list[TaskEvent] = []
        exited_workers: dict[UUID, WorkerExit] = {}

        for task_id, handle in list(self.workers.items()):
            conn = handle.conn

            while len(events) < limit and not handle.channel_closed:
                # Consume the worker's remaining events
                try:
                    if not conn.poll(0):
                        break
                    event = conn.recv()
                except EOFError:
                    # Pipe is closed
                    handle.channel_closed = True
                    break
                except (OSError, ConnectionError):
                    # Pipe is broken
                    handle.channel_closed = True
                    break

                events.append(event)
                if isinstance(event, TerminalEvent.__value__):
                    handle.terminal_received = True

            exit_code = handle.process.exitcode

            # Keep the worker until its channel is fully drained.
            if exit_code is None or not handle.channel_closed:
                continue

            if not handle.terminal_received:
                # The worker process has exited or the pipe has been closed but we
                # haven't seen a TerminalEvent yet, so something went wrong.
                exited_workers[task_id] = WorkerExit(
                    exit_code=exit_code,
                    termination_requested=handle.termination_requested,
                )

            # We're done with the worker, so clean up resources
            self.reap(task_id)

        return BackendUpdate(events, exited_workers)

    def reap(self, task_id: UUID, timeout: float = 0) -> None:
        """Clean up resources of and remove references to a completed worker."""
        handle = self.workers.pop(task_id, None)
        if handle is not None:
            handle.process.join(timeout=timeout)
            handle.conn.close()
            handle.process.close()

    @typing.override
    def close(self) -> None:
        for handle in self.workers.values():
            if handle.is_alive():
                handle.cancel()
        for handle in self.workers.values():
            handle.process.join(timeout=1)
            if handle.process.is_alive():
                handle.process.terminate()
                handle.process.join()
            handle.conn.close()
            handle.process.close()
        self.workers.clear()
