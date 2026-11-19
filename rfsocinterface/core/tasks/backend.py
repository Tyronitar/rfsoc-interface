"""Worker backend implementations."""

from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import queue
import time
import traceback
import typing
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from multiprocessing.connection import Connection
from threading import Event, Thread
from time import monotonic
from typing import Protocol
from uuid import UUID

from rfsocinterface.core.tasks.context import MainTaskContext
from rfsocinterface.core.tasks.task import (
    CancellationPolicy,
    Cancelled,
    Failed,
    IPCFailed,
    Started,
    Succeeded,
    Task,
    TaskCancelled,
    TaskEvent,
    TerminalEvent,
)

_logger = logging.getLogger(__name__)


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
    """Workers that have succesfully been cleaned up by the backend."""


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

    def close(self) -> bool:
        """Release backend resources and return whether cleanup is complete."""


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

    cancellation_policy: CancellationPolicy
    """How this worker should handle cancellation. Inherited from the task."""

    termination_requested: bool = False
    """Whether termination was requested for this task."""

    terminal_received: bool = False
    """Whether the worker's terminal event was received."""

    channel_closed: bool = False
    """Whether the worker's connection has been closed."""

    receiver_error: str | None = None
    """Error concerning the receiver thread."""

    ipc_failure_at: float | None = None
    """The time that IPC failure was detected, if it did."""

    def is_alive(self) -> bool:
        """Whether the process is still alive."""
        return self.process.is_alive()

    def cancel(self) -> None:
        """Trigger this worker's cancel event."""
        self.cancel_event.set()


def execute_task(
    task: Task,
    send_event: Callable[[TaskEvent], None],
    is_cancelled: Callable[[], bool],
) -> None:
    """Execute a task, reporting its lifecycle events through `send_event`.

    Shared by all backends so that every worker reports the same sequence of events.
    Cancellation is only honored before the target starts or when the target raises
    `TaskCancelled`. A target that returns normally is reported as `Succeeded`, even if
    cancellation was requested after it could last react.
    """
    context = MainTaskContext(
        task.id,
        send_event=send_event,
        is_cancelled=is_cancelled,
    )
    try:
        context.check_cancelled()
        send_event(Started(task.id))

        kwargs = dict(task.kwargs)
        if task.with_context:
            if 'context' in kwargs:
                raise ValueError('context is reserved when with_context=True')
            kwargs['context'] = context

        result = task.target(*task.args, **kwargs)
        send_event(Succeeded(task.id, result))
    except TaskCancelled:
        send_event(Cancelled(task.id))
    except Exception as exc:  # noqa: BLE001
        with contextlib.suppress(OSError, BrokenPipeError):
            send_event(
                Failed(task.id, f'{type(exc).__name__}: {exc}', traceback.format_exc())
            )


def multiprocessing_worker_entry(
    task: Task, cancel_event: mp.Event, event_conn: Connection
) -> None:
    """Entry point for a worker to execute a task from a MultiprocessingBackend."""
    try:
        execute_task(task, event_conn.send, cancel_event.is_set)
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
            if not isinstance(event, TaskEvent):
                raise TypeError(
                    f'Invalid event type: "{type(event).__name__}"',
                )
            if event.task_id != task_id:
                raise ValueError(
                    f'Event task ID mismatch: expected {task_id}, received {event.id}.',
                )
            _logger.debug(
                f'Received event of type {event.__class__.__name__} from task '
                f'{event.task_id}'
            )
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
        _logger.debug(f'Closed communication channel with task {task_id}')
    except Exception as exc:
        updates.put(
            ReceiverUpdate(
                task_id=task_id,
                status=ReceiverStatus.ERROR,
                error=f'{type(exc).__name__}: {exc}',
            )
        )
        _logger.exception('Encountered exception in receiver thread')


class MultiprocessingBackend:
    """TaskBackend implementation using multiprocessing."""

    def __init__(self, ipc_failure_grace: float = 2.0) -> None:
        """Initialize a MultiprocessingBackend."""
        self.context = mp.get_context('spawn')
        self.workers: dict[UUID, MultiprocessingWorkerHandle] = {}
        self._received: queue.Queue[ReceiverUpdate] = queue.Queue()
        # Fallback for broken communication channels
        self.ipc_failure_grace = ipc_failure_grace

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
            _logger.exception('Error encountered when starting worker process')
            raise
        else:
            send_conn.close()
            _logger.debug(
                f'Succesfully started worker process {process.pid} for task {task.id}'
            )

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
            cancellation_policy=task.cancellation_policy,
        )
        try:
            receiver.start()
        except BaseException:
            handle = self.workers.pop(task.id)

            try:
                if handle.process.is_alive():
                    handle.process.terminate()

                handle.process.join()
            finally:
                handle.conn.close()
                handle.process.close()

            _logger.exception('Error encountered when starting receiver')
            raise
        else:
            _logger.debug(f'Succesfully started receiver for task {task.id}')

    @typing.override
    def cancel(self, task_id: UUID) -> None:
        self.workers[task_id].cancel_event.set()
        _logger.debug(f'Set cancel event for task {task_id}')

    @typing.override
    def terminate(self, task_id: UUID) -> None:
        handle = self.workers[task_id]
        handle.termination_requested = True
        if handle.process.is_alive():
            handle.process.terminate()
        _logger.debug(f'Foricbly terminated task {task_id}')

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

            match update.status:
                case ReceiverStatus.EVENT:
                    # Process the event
                    event = update.event
                    if event is None:
                        continue
                    events.append(event)
                    if isinstance(event, TerminalEvent.__value__):
                        handle.terminal_received = True
                case ReceiverStatus.EOF:
                    # Pipe is closed
                    handle.channel_closed = True
                case ReceiverStatus.ERROR:
                    # Receiver encountered an issue while calling recv(). The
                    # communication channel is no longer usable
                    events.append(
                        self._handle_receiver_failure(
                            update.task_id,
                            update.error or 'Unknown IPC error',
                        )
                    )

        # Handle recovery from any IPC failures
        now = monotonic()
        for task_id, handle in self.workers.items():
            if handle.ipc_failure_at is None:
                continue

            if not handle.process.is_alive():
                continue

            elapsed = now - handle.ipc_failure_at

            if elapsed >= self.ipc_failure_grace:
                msg = (
                    f'Worker for task {task_id} took too long to recover '
                    'from IPC failure. '
                )
                # Worker took too long to cancel after the issue. Force terminate it.
                if handle.cancellation_policy == CancellationPolicy.TERMINATE:
                    handle.process.terminate()
                    msg += 'Forcibly terminated worker per cancellation policy.'
                else:
                    # Otherwise, keep supervision of the worker until it exits
                    msg += 'Keeping supervision until worker exits.'
                _logger.debug(msg)

        # Reconcile worker process exits.
        for task_id, handle in list(self.workers.items()):
            exit_code = handle.process.exitcode

            # Do not reap until the receiver has finished.
            #
            # This also ensures that all previously received events
            # have been processed, since they share one FIFO queue.
            if (
                exit_code is None
                or not handle.channel_closed
                or handle.receiver.is_alive()
            ):
                continue

            exited_workers[task_id] = WorkerExit(
                exit_code=exit_code,
                termination_requested=handle.termination_requested,
                receiver_error=handle.receiver_error,
            )

            # We're done with the worker, so clean up resources
            self.reap(task_id)

        return BackendUpdate(events, exited_workers)

    def _handle_receiver_failure(
        self,
        task_id: UUID,
        error: str,
    ) -> IPCFailed:
        """Handle receiver communication errors."""
        handle = self.workers[task_id]

        handle.channel_closed = True
        handle.receiver_error = error
        handle.ipc_failure_at = monotonic()

        if handle.is_alive():
            handle.cancel()

        return IPCFailed(task_id, error)

    def reap(self, task_id: UUID):
        """Clean up resources of and remove references to a completed worker."""
        handle = self.workers[task_id]

        if handle.process.exitcode is None:
            raise RuntimeError('Cannot reap a running worker')
        if handle.receiver.is_alive():
            raise RuntimeError('Cannot reap a worker with an active receiver')

        handle.receiver.join(timeout=0)
        handle.process.join(timeout=0)
        handle.conn.close()
        handle.process.close()
        del self.workers[task_id]
        _logger.debug(f'Cleaned up resources for task {task_id}')

    @typing.override
    def close(self) -> bool:
        # Request cooperative cancellation. Tasks with cancellation disabled are left
        # to run to completion.
        for handle in self.workers.values():
            if (
                handle.is_alive()
                and handle.cancellation_policy != CancellationPolicy.DISABLED
            ):
                handle.cancel()

        # Give workers an opportunity to finish cleanup.
        deadline = monotonic() + self.ipc_failure_grace
        while monotonic() < deadline:
            if all(not h.is_alive() for h in self.workers.values()):
                break
            time.sleep(2e-2)

        # Forcefully stop workers that did not exit.
        for handle in self.workers.values():
            if (
                handle.process.is_alive()
                and handle.cancellation_policy == CancellationPolicy.TERMINATE
            ):
                handle.process.terminate()

        # Join exited worker processes
        for handle in self.workers.values():
            if handle.process.exitcode is not None:
                handle.process.join(timeout=0)

        self.reap_finished_workers()
        done = not self.workers
        if done:
            _logger.debug('Completed cleanup of MultiprocessingBackend')
        return done

    def reap_finished_workers(self):
        """Close IPC resources and reap receiver threads for finished workers."""
        for task_id, handle in list(self.workers.items()):
            # Check channel closed, as that's only assigned in poll. So we won't reap
            # before the final WorkerExit is processed and sent to the manager
            if (
                handle.channel_closed
                and not handle.is_alive()
                and not handle.receiver.is_alive()
            ):
                self.reap(task_id)

    def active_workers(self) -> int:
        """Return the number of workers still alive."""
        return len(self.workers)


@dataclass
class ThreadingWorkerHandle:
    """Handle containing a worker thread's information."""

    thread: Thread
    """The thread this worker is executing on."""

    cancel_event: Event
    """Event to trigger cancellation."""

    cancellation_policy: CancellationPolicy
    """How this worker should handle cancellation. Inherited from the task."""

    termination_requested: bool = False
    """Whether termination was requested for this task."""

    terminal_received: bool = False
    """Whether the worker's terminal event was received."""

    finished: bool = False
    """Whether the worker has sent its final message (i.e. no more events will come)."""

    exit_code: int | None = None
    """0 if the worker exited normally, 1 if an exception escaped it."""

    worker_error: str | None = None
    """Exception that escaped the worker, if any."""

    abandoned: bool = False
    """Whether the backend gave up waiting for this thread during shutdown."""

    def is_alive(self) -> bool:
        """Whether the thread is still alive."""
        return self.thread.is_alive()

    def cancel(self) -> None:
        """Trigger this worker's cancel event."""
        self.cancel_event.set()


def threading_worker_entry(
    task: Task, cancel_event: Event, updates: queue.Queue[ReceiverUpdate]
) -> None:
    """Entry point for a worker to execute a task from a ThreadingBackend.

    Events are placed directly on the backend's shared queue. An EOF update is always
    sent last, so every event from this worker precedes it in the queue.
    """
    error: str | None = None

    def send_event(event: TaskEvent) -> None:
        updates.put(ReceiverUpdate(task.id, ReceiverStatus.EVENT, event=event))

    try:
        execute_task(task, send_event, cancel_event.is_set)
    except BaseException as exc:  # Anything execute_task didn't handle
        error = f'{type(exc).__name__}: {exc}'
        _logger.exception(f'Unhandled exception in worker thread for task {task.id}')
    finally:
        updates.put(
            ReceiverUpdate(
                task.id,
                ReceiverStatus.ERROR if error else ReceiverStatus.EOF,
                error=error,
            )
        )


class ThreadingBackend:
    """TaskBackend implementation using threads.

    Tasks share the main process's memory, so arguments and results are not pickled
    and there is no IPC to fail. The tradeoffs are that CPU-bound tasks are serialized
    by the GIL and that threads cannot be forcibly terminated:

    - `terminate` sets the task's cancel event and marks termination as requested, but
      the task keeps running until it checks for cancellation or returns. Its worker
      slot and resources remain held until then.
    - `close` waits `shutdown_grace` seconds for workers to exit. Workers with
      `CancellationPolicy.TERMINATE` still running after that are abandoned (they are
      daemon threads, so they won't block interpreter exit). All other workers are
      waited on until they finish.
    """

    def __init__(self, shutdown_grace: float = 2.0) -> None:
        """Initialize a ThreadingBackend."""
        self.workers: dict[UUID, ThreadingWorkerHandle] = {}
        self._received: queue.Queue[ReceiverUpdate] = queue.Queue()
        self.shutdown_grace = shutdown_grace
        self._close_deadline: float | None = None

    @typing.override
    def start(self, task: Task) -> None:
        if task.id in self.workers:
            raise ValueError(f'Duplicate task ID: {task.id}')

        cancel_event = Event()
        thread = Thread(
            target=threading_worker_entry,
            args=(task, cancel_event, self._received),
            name=f'TaskWorker-{task.name}-{task.id}',
            daemon=True,  # Allows interpreter exit if a worker must be abandoned
        )

        self.workers[task.id] = ThreadingWorkerHandle(
            thread=thread,
            cancel_event=cancel_event,
            cancellation_policy=task.cancellation_policy,
        )
        try:
            thread.start()
        except BaseException:
            del self.workers[task.id]
            _logger.exception('Error encountered when starting worker thread')
            raise
        _logger.debug(f'Succesfully started worker thread for task {task.id}')

    @typing.override
    def cancel(self, task_id: UUID) -> None:
        self.workers[task_id].cancel()
        _logger.debug(f'Set cancel event for task {task_id}')

    @typing.override
    def terminate(self, task_id: UUID) -> None:
        # Threads cannot be killed, so this is the strongest request available.
        handle = self.workers[task_id]
        handle.termination_requested = True
        handle.cancel()
        _logger.debug(
            f'Requested termination of task {task_id}; threads cannot be forcibly '
            'stopped, so it will exit at its next cancellation check'
        )

    @typing.override
    def poll(self, limit: int = 100) -> BackendUpdate:
        events: list[TaskEvent] = []
        exited_workers: dict[UUID, WorkerExit] = {}

        for _ in range(limit):
            try:
                update = self._received.get_nowait()
            except queue.Empty:
                break

            handle = self.workers.get(update.task_id)

            # Unknown, or an abandoned worker that's still producing events
            if handle is None:
                continue

            match update.status:
                case ReceiverStatus.EVENT:
                    event = update.event
                    if event is None:
                        continue
                    events.append(event)
                    if isinstance(event, TerminalEvent.__value__):
                        handle.terminal_received = True
                case ReceiverStatus.EOF:
                    handle.finished = True
                    handle.exit_code = 0
                case ReceiverStatus.ERROR:
                    handle.finished = True
                    handle.exit_code = 1
                    handle.worker_error = update.error

        # Reconcile worker exits. The final update is sent from the thread's `finally`
        # block, so the thread may still be alive for an instant afterward.
        for task_id, handle in list(self.workers.items()):
            if handle.abandoned:
                exited_workers[task_id] = WorkerExit(
                    exit_code=None,
                    termination_requested=True,
                    receiver_error=None,
                )
                del self.workers[task_id]
                _logger.debug(f'Released abandoned worker for task {task_id}')
                continue

            if not handle.finished or handle.thread.is_alive():
                continue

            exited_workers[task_id] = WorkerExit(
                exit_code=handle.exit_code,
                termination_requested=handle.termination_requested,
                receiver_error=handle.worker_error,
            )
            self.reap(task_id)

        return BackendUpdate(events, exited_workers)

    def reap(self, task_id: UUID) -> None:
        """Remove references to a completed worker."""
        handle = self.workers[task_id]

        if handle.thread.is_alive():
            raise RuntimeError('Cannot reap a running worker')

        handle.thread.join(timeout=0)
        del self.workers[task_id]
        _logger.debug(f'Cleaned up resources for task {task_id}')

    @typing.override
    def close(self) -> bool:
        # Called repeatedly by the runner until it returns True, interleaved with
        # poll(), so this must not block for long.
        if self._close_deadline is None:
            for handle in self.workers.values():
                if (
                    handle.is_alive()
                    and handle.cancellation_policy != CancellationPolicy.DISABLED
                ):
                    handle.cancel()
            self._close_deadline = monotonic() + self.shutdown_grace

        if monotonic() >= self._close_deadline:
            for task_id, handle in self.workers.items():
                if (
                    not handle.abandoned
                    and handle.is_alive()
                    and handle.cancellation_policy == CancellationPolicy.TERMINATE
                ):
                    handle.abandoned = True
                    _logger.warning(
                        f'Abandoning worker thread for task {task_id}, which did not '
                        'exit within the shutdown grace period'
                    )

        # Workers are removed by poll(), so their WorkerExit reaches the manager.
        done = not self.workers
        if done:
            _logger.debug('Completed cleanup of ThreadingBackend')
        return done

    def active_workers(self) -> int:
        """Return the number of workers still tracked."""
        return len(self.workers)
