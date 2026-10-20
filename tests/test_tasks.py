"""Tests for running backend tasks."""

import os
import time
import typing
from collections.abc import Callable, Generator
from multiprocessing import Event
from uuid import uuid4

import numpy as np
import pytest
from PySide6.QtCore import SignalInstance

from rfsocinterface.core.tasks import (
    TERMINAL_STATUSES,
    BackendUpdate,
    CancellationPolicy,
    MultiprocessingBackend,
    ReceiverStatus,
    ReceiverUpdate,
    Task,
    TaskCancelled,
    TaskManager,
    TaskRecord,
    TaskStatus,
)
from rfsocinterface.core.tasks.context import TaskContext


def check_record(
    status: TaskStatus, result=None, progress=None, error=None, worker_exited=False
):
    """Factory for creating record checkers."""

    def wrapper(record: TaskRecord):
        """Check that the record has the expected values."""
        return (
            record.status == status
            and record.result == result
            and record.progress == progress
            and record.error == error
            and record.worker_exited == worker_exited
        )

    return wrapper


def get_signals_success(
    manager: TaskManager,
    result=None,
) -> tuple[list[SignalInstance], list[Callable]]:
    """Get the appropriate signals and callbacks for a succesful task.

    We expect four updates:
        1. Initial update (PENDING)
        2. Task start (RUNNING)
        3. Task finish (SUCCESS)
        4. Cleanup finished (//, worker_exited=True)
    """
    status_checkers = [
        check_record(TaskStatus.PENDING),
        check_record(TaskStatus.RUNNING),
        check_record(TaskStatus.SUCCEEDED, result=result),
        check_record(TaskStatus.SUCCEEDED, result=result, worker_exited=True),
    ]
    signals = [manager.changed] * len(status_checkers)
    return signals, status_checkers


def get_signals_cancel(
    manager: TaskManager,
) -> tuple[tuple[list[SignalInstance], list[Callable]]]:
    """Get the appropriate signals and callbacks for a canceled task.

    We expect two updates before canceling:
        1. Initial update (PENDING)
        2. Task start (RUNNING)
    And we expect three updates after canceling:
        1. Cancel requested (CANCELLING)
        2. Cancel finished (CANCELLED)
        3. Cleanup finished (//, worker_exited=True)
    """
    # Split statuses into before and after the cancel
    status_checkers_pre = [
        check_record(TaskStatus.PENDING),
        check_record(TaskStatus.RUNNING),
    ]
    status_checkers_post = [
        check_record(TaskStatus.CANCELLING),
        check_record(TaskStatus.CANCELLED),
        check_record(TaskStatus.CANCELLED, worker_exited=True),
    ]
    signals_pre = [manager.changed] * len(status_checkers_pre)
    signals_post = [manager.changed] * len(status_checkers_post)
    return (
        (signals_pre, status_checkers_pre),
        (signals_post, status_checkers_post),
    )


def get_signals_fail(
    manager: TaskManager,
    exc: Exception,
) -> tuple[list[tuple[SignalInstance, str]], list[Callable]]:
    """Get the appropriate signals and callbacks for a failed task.

    We expect four updates:
        1. Initial update (PENDING)
        2. Task start (RUNNING)
        3. Task failure (FAILED, with error)
        4. Cleanup finished (//, worker_exited=True)
    """
    error = f'{type(exc).__name__}: {exc}'
    status_checkers = [
        check_record(TaskStatus.PENDING),
        check_record(TaskStatus.RUNNING),
        check_record(TaskStatus.FAILED, error=error),
        check_record(TaskStatus.FAILED, error=error, worker_exited=True),
    ]
    signals = [manager.changed] * len(status_checkers)
    return signals, status_checkers


@pytest.fixture
def manager(qtbot) -> Generator[TaskManager, None, None]:
    """Fixture for creating a TaskManager and handling cleanup."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.2)
    manager = TaskManager(backend)

    yield manager

    manager.close()

    qtbot.waitUntil(
        lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
        timeout=5000,
    )


def wait_for_task(qtbot, manager, task_id, timeout=5000):
    """Wait for a task's worker to exit."""
    qtbot.waitUntil(
        lambda: manager.records[task_id].worker_exited,
        timeout=timeout,
    )
    return manager.records[task_id]


#
# Example tasks for testing
#


def sum_task(x: float, y: float) -> float:
    """Return the sum of two numbers."""
    return x + y


def exception_task():
    """Task that raises an exception."""
    raise RuntimeError('Expected failure')


def crash_task():
    """Task that crashes 'unexpectedly'.

    `os._exit` bypasses normal Python exception handling, so useful for testing worker
    exit reconciliation.
    """
    os._exit(17)


def unpickleable_result_task():
    """Return an unpickleable result, which results in an IPC failure."""
    return lambda x: x


def long_running_task():
    """Task that just runs for a whilem for testing termination."""
    time.sleep(30)


def sleep_task(duration: int, context: TaskContext | None = None):
    """Sleep for the given duration, adn respect context."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < duration:
        if context.is_cancelled():
            raise TaskCancelled
    return True


def large_transfer_task(event: Event):
    """Task that transfers a large amount of data."""
    arr = np.zeros((10000, 1000), dtype=np.float64)
    event.set()  # Signal that the result is ready to be written
    return arr


#
# Final state tests
#


@pytest.mark.integration
def test_normal_task_success(qtbot, manager):
    """Test that a task succeeds under normal circumstances and cleanup is handled."""
    task = Task(
        target=sum_task,
        args=(1, 1),
    )
    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.SUCCEEDED
    assert record.worker_exited
    assert record.result == 2


@pytest.mark.integration
def test_cooperative_cancel(qtbot, manager):
    """Test that cooperative cancel works properly."""
    task = Task(
        target=sleep_task,
        args=(5,),
        with_context=True,
        cancellation_policy=CancellationPolicy.COOPERATIVE,
    )

    manager.submit(task)

    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )
    manager.cancel(task.id)

    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.CANCELLED
    assert record.worker_exited
    assert record.result is None


@pytest.mark.integration
def test_cooperative_cancel_after_exit(qtbot, manager):
    """Test that cancelling after completion does nothing."""
    # backend = MultiprocessingBackend(ipc_failure_grace=0.01)
    # manager = TaskManager(backend)

    task = Task(
        target=sleep_task,
        args=(0.1,),
        with_context=True,
        cancellation_policy=CancellationPolicy.COOPERATIVE,
    )

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.SUCCEEDED
    assert record.worker_exited
    assert record.result is True

    # Cancel after finishing should be ignored
    with qtbot.assertNotEmitted(manager.changed, wait=100):
        manager.cancel(task.id)


@pytest.mark.integration
def test_forced_termination(qtbot, manager):
    """Test that a task can be forcibly terminated."""
    task = Task(
        target=long_running_task,
        cancellation_policy=CancellationPolicy.TERMINATE,
    )

    manager.submit(task)

    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )
    manager.cancel(task.id)
    record = wait_for_task(qtbot, manager, task.id)
    assert record.status == TaskStatus.CANCELLED
    assert record.worker_exited
    assert task.id not in manager.backend.workers


@pytest.mark.integration
def test_task_exception(qtbot, manager):
    """Test case of task raising an exception."""
    task = Task(target=exception_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.FAILED
    assert 'expected failure' in record.error.lower()
    assert record.result is None


@pytest.mark.integration
def test_worker_crash(qtbot, manager):
    """Test case where worker crashes without sending a terminal status."""
    task = Task(target=crash_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.FAILED
    assert '17' in record.error
    assert record.worker_exited
    assert task.id not in manager.backend.workers


@pytest.mark.integration
def test_unpickleable_result(qtbot, manager):
    """Test that failure to serialize a result results in a task failure."""
    task = Task(target=unpickleable_result_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.FAILED
    assert record.worker_exited
    assert 'pickle' in record.error.lower() or 'attribute' in record.error.lower()


@pytest.mark.integration
def test_worker_failure_is_isolated(qtbot, manager):
    """With multiple tasks, test that failures are isolated."""
    failed_task = Task(target=crash_task)
    successful_task = Task(target=sum_task, args=(10, 20))

    manager.submit(failed_task)
    manager.submit(successful_task)

    failed = wait_for_task(qtbot, manager, failed_task.id)
    succeeded = wait_for_task(qtbot, manager, successful_task.id)

    assert failed.status == TaskStatus.FAILED
    assert succeeded.status == TaskStatus.SUCCEEDED
    assert succeeded.result == 30
    assert failed.worker_exited
    assert succeeded.worker_exited


#
# IPC Failure Tests
#
class FakeWorkerHandle:
    """Fake WorkerHandle for testing IPC failure."""

    def __init__(self):
        """Initialize FakeWorkerHandle."""
        self.id = uuid4()
        self.receiver_error = None
        self.ipc_failure_at = None
        self._alive = True

    def is_alive(self) -> bool:
        """Whether the worker is alive."""
        return self._alive

    def cancel(self):
        """Simulate canceling the worker."""
        self._alive = False


@pytest.mark.integration
def test_receiver_error(qtbot, manager):
    """Test that an error from the receiver is handled correctly."""
    task = Task(
        target=long_running_task,
        cancellation_policy=CancellationPolicy.TERMINATE,
    )

    manager.submit(task)

    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )

    # Simulate a receiver failure.
    manager.backend._received.put(  # noqa: SLF001
        ReceiverUpdate(
            task_id=task.id,
            status=ReceiverStatus.ERROR,
            error='Simulated deserialization failure',
        )
    )

    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.FAILED,
        timeout=5000,
    )

    assert 'Simulated deserialization failure' in (manager.records[task.id].error)


@pytest.mark.smoke
def test_receiver_failure_handling():
    """Test that the backend's receiver failure handling works."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.2)
    handle = FakeWorkerHandle()
    backend.workers[handle.id] = handle
    t0 = time.monotonic()
    event = backend._handle_receiver_failure(handle.id, 'Simulated IPC failure')  # noqa: SLF001

    assert 'Simulated IPC failure' in handle.receiver_error
    assert handle.ipc_failure_at > t0
    assert not handle.is_alive()
    assert event.error == handle.receiver_error


@pytest.mark.slow
@pytest.mark.integration
def test_terminate_during_transfer(qtbot, manager):
    """Test termination of a worker while writing its result."""
    event = manager.backend.context.Event()
    task = Task(
        target=large_transfer_task,
        args=(event,),
        cancellation_policy=CancellationPolicy.TERMINATE,
    )
    manager.submit(task)
    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )

    # Kill the worker while it's writing its large result
    event.wait()
    manager.runner.backend.workers[task.id].process.terminate()

    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.FAILED
    assert 'worker exited' in record.error.lower()
    assert 'without reporting a terminal outcome' in record.error.lower()
    assert record.worker_exited


#
# Cancellation Race Tests
#


def synchronized_task(event: Event):
    """Task that waits for a synchronization event."""
    event.wait()
    return True


@pytest.mark.integration
def test_immediate_cancel(qtbot, manager):
    """Test cancelling immediately after submitting a task."""
    task = Task(
        target=long_running_task,
        cancellation_policy=CancellationPolicy.TERMINATE,
    )
    manager.submit(task)
    manager.cancel(task.id)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.CANCELLED


@pytest.mark.integration
def test_cancel_near_completion(qtbot, manager):
    """Test that canceling near the end of the task doesn't cause problems."""
    event = manager.backend.context.Event()
    task = Task(
        target=synchronized_task,
        args=(event,),
        cancellation_policy=CancellationPolicy.TERMINATE,
    )
    manager.submit(task)
    qtbot.waitUntil(
        lambda: manager.records[task.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )
    event.set()
    manager.cancel(task.id)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)

    # Whether the task finishes or is canceled first is non-deterministic
    assert record.status in TERMINAL_STATUSES
    assert record.worker_exited
    if record.status == TaskStatus.SUCCEEDED:
        assert record.result is True
    else:
        assert record.result is None


# Runner isolation tests
class FailingStartBackend:
    """Backend that fails on starting a task."""

    @typing.override
    def start(self, task):
        raise RuntimeError('Simulated startup failure')

    @typing.override
    def cancel(self, task_id):
        pass

    @typing.override
    def terminate(self, task_id):
        pass

    @typing.override
    def poll(self, limit=100):
        return BackendUpdate([], {})

    @typing.override
    def close(self):
        return True


class PollFailureBackend:
    """Backend that fails on poll."""

    @typing.override
    def start(self, task):
        pass

    @typing.override
    def cancel(self, task_id):
        pass

    @typing.override
    def terminate(self, task_id):
        pass

    @typing.override
    def poll(self, limit=100):
        raise RuntimeError('Simulated poll failure')

    @typing.override
    def close(self):
        return True


@pytest.mark.integration
def test_start_failure(qtbot):
    """Test that backend start failures are handled properly by the runner."""
    manager = TaskManager(FailingStartBackend())
    task = Task(target=sum_task, args=(1, 2))

    try:
        manager.submit(task)

        qtbot.waitUntil(
            lambda: manager.records[task.id].status == TaskStatus.FAILED,
            timeout=2000,
        )

        assert 'Simulated startup failure' in manager.records[task.id].error
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
            timeout=2000,
        )


@pytest.mark.integration
def test_poll_failure(qtbot):
    """Test that poll raising an issue is handled properly."""
    manager = TaskManager(PollFailureBackend())
    task = Task(target=sum_task, args=(1, 2))

    try:
        manager.submit(task)
        qtbot.waitSignal(manager.runner.fatal_error, timeout=5000)
        qtbot.waitUntil(
            lambda: manager.records[task.id].status == TaskStatus.UNKNOWN,
            timeout=2000,
        )
        assert 'Simulated poll failure' in manager.records[task.id].error
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
            timeout=2000,
        )
