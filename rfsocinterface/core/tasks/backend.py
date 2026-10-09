"""Worker backend implementations."""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import queue
import traceback
import typing
from dataclasses import dataclass
from enum import Enum, auto
from multiprocessing.connection import Connection
from threading import Thread
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
    receiver_error: str | None = None


@dataclass
class BackendUpdate:
    """Structured information containing the state of the backend and its workers."""

    events: list[TaskEvent]
    """Events since the last poll."""

    exited_workers: dict[UUID, WorkerExit]
    """Workers that exited without reporting an outcome."""


class ReceiverStatus(Enum):
    """Object indicating a receiver thread's status."""

    EVENT = auto()
    EOF = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ReceiverUpdate:
    """Message showing the current state of a receiver thread."""

    task_id: UUID
    status: ReceiverStatus
    event: TaskEvent | None = None
    error: str | None = None


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

    receiver: Thread
    """Thread responsible for deserialzing messages from the worker. This happens before
    the backend handles the message to avoid slow deserialization blocking.
    """

    termination_requested: bool = False
    """Whether termination was requested for this task."""

    terminal_received: bool = False
    """Whether the worker's terminal event was received."""

    channel_closed: bool = False
    """Whether the worker's connection has been closed."""

    receiver_error: str | None = None
    """Error concerning the receiver thread."""

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


def receive_worker_events(
    task_id: UUID,
    conn: Connection,
    updates: queue.Queue[ReceiverUpdate],
) -> None:
    """Receive and deserialize events from one worker."""
    try:
        while True:
            event = conn.recv()
            updates.put(
                ReceiverUpdate(
                    task_id=task_id,
                    status=ReceiverStatus.EVENT,
                    event=event,
                )
            )
    except EOFError:
        updates.put(
            ReceiverUpdate(
                task_id=task_id,
                status=ReceiverStatus.EOF,
            )
        )
    except Exception as exc:  # noqa: BLE001
        updates.put(
            ReceiverUpdate(
                task_id=task_id,
                status=ReceiverStatus.ERROR,
                error=f'{type(exc).__name__}: {exc}',
            )
        )


class MultiprocessingBackend:
    """TaskBackend implementation using multiprocessing."""

    def __init__(self) -> None:
        """Initialize a MultiprocessingBackend."""
        self.context = mp.get_context('spawn')
        self.workers: dict[UUID, MultiprocessingWorkerHandle] = {}
        self._received: queue.Queue[ReceiverUpdate] = queue.Queue()

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

        # Create thread for receiving messages from the worker process
        receiver = Thread(
            target=receive_worker_events,
            args=(task.id, recv_conn, self._received),
            name=f'TaskReceiver-{task.id}',
            daemon=True,  # Failsafe for if it gets stuck inside a recv() call
        )

        self.workers[task.id] = MultiprocessingWorkerHandle(
            process=process,
            cancel_event=cancel_event,
            conn=recv_conn,
            receiver=receiver,
        )
        try:
            receiver.start()
        except:
            self.terminate(task.id)
            self.reap(task.id)
            raise

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

        # Process notifications from receiver threads.
        for _ in range(limit):
            try:
                update = self._received.get_nowait()
            except queue.Empty:
                break

            handle = self.workers.get(update.task_id)

            if handle is None:
                continue

            if update.status == ReceiverStatus.EVENT:
                # Process the event
                event = update.event
                if event is None:
                    continue
                events.append(event)
                if isinstance(event, TerminalEvent.__value__):
                    handle.terminal_received = True
            elif update.status == ReceiverStatus.EOF:
                # Pipe is closed
                handle.channel_closed = True
            elif update.status == ReceiverStatus.ERROR:
                # Receiver encountered an issue while calling recv()
                handle.channel_closed = True
                handle.receiver_error = update.error

        # Reconcile worker process exits.
        for task_id, handle in list(self.workers.items()):
            exit_code = handle.process.exitcode

            # Do not reap until the receiver has finished.
            #
            # This also ensures that all previously received events
            # have been processed, since they share one FIFO queue.
            if exit_code is None or not handle.channel_closed:
                continue

            if not handle.terminal_received:
                # The worker process has exited or the pipe has been closed but we
                # haven't seen a TerminalEvent yet, so something went wrong.
                exited_workers[task_id] = WorkerExit(
                    exit_code=exit_code,
                    termination_requested=handle.termination_requested,
                    receiver_error=handle.receiver_error,
                )

            # We're done with the worker, so clean up resources
            self.reap(task_id)

        return BackendUpdate(events, exited_workers)

    def reap(
        self, task_id: UUID, process_timeout: float = 0, receiver_timeout: float = 0
    ) -> None:
        """Clean up resources of and remove references to a completed worker."""
        handle = self.workers.pop(task_id, None)
        if handle is not None:
            handle.receiver.join(timeout=process_timeout)
            handle.process.join(timeout=receiver_timeout)
            handle.conn.close()
            handle.process.close()

    @typing.override
    def close(self) -> None:
        # Request cooperative cancellation
        for handle in self.workers.values():
            if handle.is_alive():
                handle.cancel()

        # Give workers an opportunity to finish cleanup.
        for handle in self.workers.values():
            handle.process.join(timeout=1)

        # Forcefully stop workers that did not exit.
        for handle in self.workers.values():
            if handle.process.is_alive():
                handle.process.terminate()

        # Close IPC resources and reap receiver threads.
        for task_id in self.workers:
            # A partial message may leave recv() blocked on some
            # platforms. Do not wait indefinitely for receiver.
            self.reap(task_id, receiver_timeout=0.5)

        self.workers.clear()
