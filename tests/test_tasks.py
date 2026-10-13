"""Tests for running backend tasks."""

import time
from collections.abc import Callable

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


def add_task(x: float, y: float) -> float:
    """Task adding two numbers together."""
    return x + y


def exception_task():
    """Task that raises an exception."""
    raise RuntimeError('Expected failure')


def sleep_task(duration: int, context: TaskContext | None = None):
    """Sleep for the given duration, adn respect context."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < duration:
        if context.is_cancelled():
            break
    return True


def test_normal_task_success(qtbot):
    """Test that a task succeeds under normal circumstances and cleanup is handled."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.01)
    manager = TaskManager(backend)

    task = Task(
        target=add_task,
        args=(1, 1),
        # with_context=True,
    )

    signals, checkers = get_signals_success(manager, result=2)

    try:
        with qtbot.waitSignals(
            signals, order='strict', check_params_cbs=checkers, timeout=5000
        ):
            manager.submit(task)
    finally:
        with qtbot.waitSignal(manager.runner.stopped, timeout=5000):
            manager.close()
            manager.runner.wait()


def test_cooperative_cancel(qtbot):
    """Test that cooperative cancel works properly."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.01)
    manager = TaskManager(backend)

    task = Task(
        target=sleep_task,
        args=(5,),
        with_context=True,
        cancellation_policy=CancellationPolicy.COOPERATIVE,
    )

    (signals_pre, checkers_pre), (signals_post, checkers_post) = get_signals_cancel(
        manager
    )

    try:
        with qtbot.waitSignals(
            signals_pre, order='strict', check_params_cbs=checkers_pre, timeout=5000
        ):
            manager.submit(task)
        with qtbot.waitSignals(
            signals_post, order='strict', check_params_cbs=checkers_post, timeout=5000
        ):
            manager.cancel(task.id)
    finally:
        with qtbot.waitSignal(manager.runner.stopped, timeout=5000):
            manager.close()
            manager.runner.wait()


def test_cooperative_cancel_after_exit(qtbot):
    """Test that cancelling after completion does nothing."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.01)
    manager = TaskManager(backend)

    task = Task(
        target=sleep_task,
        args=(1,),
        with_context=True,
        cancellation_policy=CancellationPolicy.COOPERATIVE,
    )

    signals, checkers = get_signals_success(manager, result=True)

    try:
        with qtbot.waitSignals(
            signals, check_params_cbs=checkers, order='strict', timeout=5000
        ):
            manager.submit(task)
        # Cancel after finishing should be ignored
        with qtbot.assertNotEmitted(manager.changed, wait=100):
            manager.cancel(task.id)
    finally:
        with qtbot.waitSignal(manager.runner.stopped, timeout=5000):
            manager.close()
            manager.runner.wait()


def test_task_exception(qtbot):
    """Test case of task raising an exception."""
    backend = MultiprocessingBackend(ipc_failure_grace=0.01)
    manager = TaskManager(backend)

    task = Task(target=exception_task)

    signals, checkers = get_signals_fail(manager, RuntimeError('Expected failure'))

    try:
        with qtbot.waitSignals(
            signals, check_params_cbs=checkers, order='strict', timeout=1000
        ):
            manager.submit(task)
    finally:
        with qtbot.waitSignal(manager.runner.stopped, timeout=5000):
            manager.close()
            manager.runner.wait()
