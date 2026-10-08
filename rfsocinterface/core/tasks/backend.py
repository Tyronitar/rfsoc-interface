"""Worker backend implementations."""

from __future__ import annotations

import multiprocessing as mp
import queue
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

    result_conn: Connection
    """Connection to send the execution result to the backend."""

    termination_requested: bool = False
    """Whether termination was requested for this task."""

    terminal_received: bool = False
    """Whether the worker's terminal event was received."""

    def is_alive(self) -> bool:
        """Whether the process is still alive."""
        return self.process.is_alive()

    def cancel(self) -> None:
        """Trigger this worker's cancel event."""
        self.cancel_event.set()


def multiprocessing_worker_entry(
    task: Task, out_queue: mp.Queue, cancel_event: mp.Event, result_conn: Connection
) -> None:
    """Entry point for a worker to execute a task from a MultiprocessingBackend."""
    context = TaskContext(
        task.id,
        send_event=out_queue.put,
        is_cancelled=cancel_event.is_set,
    )
    try:
        context.check_cancelled()
        out_queue.put(Started(task.id))

        kwargs = dict(task.kwargs)
        if task.with_context:
            if 'context' in kwargs:
                raise ValueError('context is reserved when with_context=True')  # noqa: TRY301
            kwargs['context'] = context

        result = task.target(*task.args, **kwargs)
        context.check_cancelled()

        result_conn.send(Succeeded(task.id, result))
    except TaskCancelled:
        result_conn.send(Cancelled(task.id))
    except Exception as exc:  # noqa: BLE001
        result_conn.send(
            Failed(task.id, f'{type(exc).__name__}: {exc}', traceback.format_exc())
        )
    finally:
        result_conn.close()


class MultiprocessingBackend:
    """TaskBackend implementation using multiprocessing."""

    def __init__(self) -> None:
        """Initialize a MultiprocessingBackend."""
        self.context = mp.get_context('spawn')
        self.events = self.context.Queue()
        self.workers: dict[UUID, MultiprocessingWorkerHandle] = {}

    @typing.override
    def start(self, task: Task) -> None:
        if task.id in self.workers:
            raise ValueError(f'Duplicate task ID: {task.id}')

        cancel_event = self.context.Event()
        parent_conn, child_conn = self.context.Pipe(duplex=False)

        process = self.context.Process(
            target=multiprocessing_worker_entry,
            args=(task, self.events, cancel_event, child_conn),
            name=task.name,
        )

        try:
            process.start()
        except:
            process.close()
            child_conn.close()
            raise

        child_conn.close()

        self.workers[task.id] = MultiprocessingWorkerHandle(
            process=process,
            cancel_event=cancel_event,
            result_conn=parent_conn,
        )

    @typing.override
    def cancel(self, task_id: UUID) -> None:
        self.workers[task_id].cancel_event.set()

    @typing.override
    def terminate(self, task_id: UUID) -> None:
        handle = self.workers[task_id]
        handle.termination_requested = True
        handle.process.terminate()

    @typing.override
    def poll(self, limit: int = 100) -> BackendUpdate:
        messages: list[TaskEvent] = []
        exited_workers: dict[UUID, WorkerExit] = {}

        # Retrieve ordinary task events (progress, messages, etc.).
        for _ in range(limit):
            try:
                messages.append(self.events.get_nowait())
            except queue.Empty:
                break

        # Retrieve terminal outcomes and detect unexpected worker exits.
        for task_id, handle in list(self.workers.items()):
            conn = handle.result_conn
            exit_code = handle.process.exitcode

            terminal_event = None
            # A pipe can contain a result even after the process exits.
            try:
                if conn.poll():
                    terminal_event = conn.recv()
            except (EOFError, OSError):
                pass

            if terminal_event is not None:
                messages.append(terminal_event)
                handle.terminal_received = True

            if exit_code is None:
                # The worker sent its result before fully exiting.
                # Keep the handle until the process has actually exited.
                continue

            if not handle.terminal_received:
                # Worker exited without reporting a terminal outcome.
                exited_workers[task_id] = WorkerExit(
                    exit_code=exit_code,
                    termination_requested=handle.termination_requested,
                )

            handle.process.join(timeout=0)
            conn.close()
            del self.workers[task_id]

        return BackendUpdate(
            events=messages,
            exited_workers=exited_workers,
        )

    @typing.override
    def reap(self, task_id: UUID) -> None:
        handle = self.workers.pop(task_id, None)
        if handle is not None:
            handle.process.join(timeout=0)

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
            handle.result_conn.close()
        self.workers.clear()
        self.events.close()
        self.events.join_thread()
