"""Tests for running backend tasks."""

import os
import time
from collections.abc import Callable, Generator

import pytest
from PySide6.QtCore import SignalInstance

from rfsocinterface.core.tasks import (
    CancellationPolicy,
    MultiprocessingBackend,
    Task,
    TaskContext,
    TaskManager,
    TaskRecord,
    TaskStatus,
)


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
            break
    return True


#
# Final state tests
#


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
    assert record.result == 2  # noqa: PLR2004


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


def test_task_exception(qtbot, manager):
    """Test case of task raising an exception."""
    task = Task(target=exception_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id, timeout=5000)
    assert record.status == TaskStatus.FAILED
    assert 'expected failure' in record.error.lower()
    assert record.result is None


def test_worker_crash(qtbot, manager):
    """Test case where worker crashes without sending a terminal status."""
    task = Task(target=crash_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.FAILED
    assert '17' in record.error
    assert record.worker_exited
    assert task.id not in manager.backend.workers


def test_unpickleable_result(qtbot, manager):
    """Test that failure to serialize a result results in a task failure."""
    task = Task(target=unpickleable_result_task)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.FAILED
    assert record.worker_exited
    assert 'pickle' in record.error.lower() or 'attribute' in record.error.lower()


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
    assert succeeded.result == 30  # noqa: PLR2004
    assert failed.worker_exited
    assert succeeded.worker_exited
