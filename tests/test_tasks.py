"""Tests for running backend tasks."""

import os
import threading
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
    Message,
    MultiprocessingBackend,
    Progress,
    ReceiverStatus,
    ReceiverUpdate,
    Task,
    TaskCancelled,
    TaskManager,
    TaskRecord,
    TaskStatus,
    ThreadingBackend,
)
from rfsocinterface.core.tasks.context import TaskContext, TaskProgress


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


@pytest.fixture(params=['multiprocessing', 'threading'])
def manager(request, qtbot) -> Generator[TaskManager, None, None]:
    """Fixture for creating a TaskManager with each backend and handling cleanup."""
    if request.param == 'multiprocessing':
        backend = MultiprocessingBackend(ipc_failure_grace=0.2)
    else:
        backend = ThreadingBackend(shutdown_grace=0.2)
    manager = TaskManager(backend)

    yield manager

    manager.close()

    qtbot.waitUntil(
        lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
        timeout=5000,
    )


def make_event(manager: TaskManager):
    """Create an event that can be shared with the manager's workers."""
    if isinstance(manager.backend, ThreadingBackend):
        return threading.Event()
    return manager.backend.context.Event()


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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
def test_terminate_context_aware_task(qtbot, manager):
    """Test terminating a TERMINATE-policy task that checks for cancellation.

    Multiprocessing kills the process; threading stops at the next cancellation check.
    Both should end CANCELLED.
    """
    task = Task(
        target=sleep_task,
        args=(30,),
        with_context=True,
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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
    crash = (
        exception_task if isinstance(manager.backend, ThreadingBackend) else crash_task
    )
    failed_task = Task(target=crash)
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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
@pytest.mark.parametrize('manager', [('multiprocessing')], indirect=['manager'])
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
    event = make_event(manager)
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
        # Keep the blocker alive (and actually wait) until fatal_error arrives.
        # Discarding it can leave a queued call pointing at a freed object.
        with qtbot.waitSignal(manager.runner.fatal_error, timeout=5000):
            manager.submit(task)
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


#
# Threading shutdown tests
#


def blocking_task(release: threading.Event):
    """Task that ignores cancellation and blocks until released."""
    release.wait()
    return True


@pytest.mark.integration
def test_threading_close_abandons_stuck_terminate_task(qtbot):
    """Test that close() abandons a stuck TERMINATE thread after the grace period."""
    release = threading.Event()
    backend = ThreadingBackend(shutdown_grace=0.2)
    manager = TaskManager(backend)
    task = Task(
        target=blocking_task,
        args=(release,),
        cancellation_policy=CancellationPolicy.TERMINATE,
    )

    try:
        manager.submit(task)
        qtbot.waitUntil(
            lambda: manager.records[task.id].status == TaskStatus.RUNNING,
            timeout=5000,
        )
        thread = backend.workers[task.id].thread

        manager.close()
        qtbot.waitUntil(
            lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
            timeout=5000,
        )

        # The runner shut down even though the worker thread is still running
        assert thread.is_alive()
        assert not backend.workers

        record = wait_for_task(qtbot, manager, task.id)
        assert record.status == TaskStatus.CANCELLED
        assert record.result is None
    finally:
        release.set()

    # Events from the abandoned thread are ignored once it finishes
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert backend.poll().events == []
    assert manager.records[task.id].status == TaskStatus.CANCELLED


def make_backend(kind: str):
    """Create a backend by name."""
    if kind == 'multiprocessing':
        return MultiprocessingBackend(ipc_failure_grace=0.2)
    return ThreadingBackend(shutdown_grace=0.2)


def gated_task(release: Event, context: TaskContext) -> bool:
    """Ignore cancellation, block until released, and report if cancel was seen."""
    release.wait()
    return context.is_cancelled()


@pytest.mark.integration
@pytest.mark.parametrize('kind', ['multiprocessing', 'threading'])
def test_close_does_not_cancel_disabled_task(qtbot, kind):
    """Test that close() neither cancels nor abandons a task with cancel disabled."""
    backend = make_backend(kind)
    manager = TaskManager(backend)
    release = make_event(manager)
    task = Task(target=gated_task, args=(release,), with_context=True)

    try:
        manager.submit(task)
        qtbot.waitUntil(
            lambda: manager.records[task.id].status == TaskStatus.RUNNING,
            timeout=5000,
        )

        manager.close()
        # Well past the grace period, the runner should still be waiting
        qtbot.wait(500)
        assert manager.runner._thread.is_alive()  # noqa: SLF001
        assert task.id in backend.workers
    finally:
        release.set()

    qtbot.waitUntil(
        lambda: not manager.runner._thread.is_alive(),  # noqa: SLF001
        timeout=5000,
    )
    record = wait_for_task(qtbot, manager, task.id)
    assert record.status == TaskStatus.SUCCEEDED
    assert record.result is False, 'Cancel event was set on a DISABLED task'


#
# Cancellation that arrives too late
#


@pytest.mark.integration
def test_cooperative_task_finishing_after_cancel_succeeds(qtbot, manager):
    """A task that returns before reacting to cancellation is reported as succeeded.

    Its pending dependents are cancelled regardless.
    """
    release = make_event(manager)
    a = Task(
        target=gated_task,
        args=(release,),
        with_context=True,
        cancellation_policy=CancellationPolicy.COOPERATIVE,
    )
    b = Task(target=sum_task, args=(1, 2), depends_on=frozenset({a.id}))
    c = Task(target=sum_task, args=(3, 4), depends_on=frozenset({b.id}))
    for t in (a, b, c):
        manager.submit(t)

    qtbot.waitUntil(
        lambda: manager.records[a.id].status == TaskStatus.RUNNING,
        timeout=5000,
    )
    manager.cancel(a.id)
    assert manager.records[a.id].status == TaskStatus.CANCELLING
    assert manager.records[b.id].status == TaskStatus.CANCELLED
    assert manager.records[c.id].status == TaskStatus.CANCELLED

    # Release only once the request has actually reached the worker
    qtbot.waitUntil(manager.backend.workers[a.id].cancel_event.is_set, timeout=5000)
    release.set()
    record = wait_for_task(qtbot, manager, a.id)
    assert record.status == TaskStatus.SUCCEEDED
    assert record.result is True, 'Task should have seen the cancel request'
    assert manager.records[b.id].status == TaskStatus.CANCELLED
    assert manager.records[c.id].status == TaskStatus.CANCELLED
    assert not manager.records[b.id].worker_exited, 'Dependent should never start'


#
# Context event tests
#


def progress_task(context: TaskContext) -> str:
    """Report progress and ETA updates, then finish."""
    context.eta(10.0)
    for value in (0, 5, 10):
        context.progress(value, minimum=0, maximum=10, label=f'step {value}')
    context.eta(0.0)
    return 'done'


def message_task(context: TaskContext) -> None:
    """Emit messages of different kinds and payload types."""
    context.emit('status', 'hello')
    context.emit('data', {'x': [1, 2, 3]})
    context.emit('status', 'goodbye')


def subtask_task(context: TaskContext) -> bool:
    """Run two weighted subtasks that report their own progress and ETA."""
    progress = TaskProgress(context, [('load', 1.0), ('fit', 3.0)])
    with progress.subtask(0) as sub:
        sub.progress(50, maximum=100, label='loading')
        sub.eta(1.5)
        sub.emit('subtask', 'from load')
    with progress.subtask(1) as sub:
        sub.progress(1, minimum=0, maximum=2)
    return True


def failing_subtask_task(context: TaskContext) -> None:
    """Fail partway through the first of two subtasks."""
    progress = TaskProgress(context, [('first', 1.0), ('second', 1.0)])
    with progress.subtask(0) as sub:
        sub.progress(25)
        raise ValueError('Subtask failed')
    with progress.subtask(1):
        pass


def collect_changes(manager: TaskManager, task_id, attr: str) -> list:
    """Record a task's `attr` each time it changes, in the order changes arrive."""
    seen = []

    def on_changed(record: TaskRecord):
        if record.task.id != task_id:
            return
        value = getattr(record, attr)
        if value is not None and (not seen or seen[-1] != value):
            seen.append(value)

    manager.changed.connect(on_changed)
    return seen


@pytest.mark.integration
def test_progress_and_eta_events(qtbot, manager):
    """Test that progress and ETA updates reach the task record in order."""
    task = Task(target=progress_task, with_context=True)
    progress_seen = collect_changes(manager, task.id, 'progress')
    eta_seen = collect_changes(manager, task.id, 'eta')

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.SUCCEEDED
    assert record.result == 'done'
    assert [p.value for p in progress_seen] == [0, 5, 10]
    assert [p.label for p in progress_seen] == ['step 0', 'step 5', 'step 10']
    assert record.progress == Progress(task.id, 10, 0, 10, 'step 10')
    assert eta_seen == [10.0, 0.0]
    assert record.eta == 0.0


@pytest.mark.integration
def test_message_events(qtbot, manager):
    """Test that messages are forwarded through event_received, in order."""
    task = Task(target=message_task, with_context=True)
    messages = []
    manager.event_received.connect(messages.append)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.SUCCEEDED
    assert all(isinstance(m, Message) and m.task_id == task.id for m in messages)
    assert [(m.kind, m.payload) for m in messages] == [
        ('status', 'hello'),
        ('data', {'x': [1, 2, 3]}),
        ('status', 'goodbye'),
    ]


@pytest.mark.integration
def test_subtask_events(qtbot, manager):
    """Test subtask definition, timing, progress, ETA, and weighted overall progress."""
    task = Task(target=subtask_task, with_context=True)
    overall_seen = collect_changes(manager, task.id, 'progress')
    messages = []
    manager.event_received.connect(messages.append)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.SUCCEEDED, record.error
    assert record.result is True

    load, fit = record.subtasks[('0',)], record.subtasks[('1',)]
    assert set(record.subtasks) == {('0',), ('1',)}
    assert (load.name, load.weight) == ('load', 1.0)
    assert (fit.name, fit.weight) == ('fit', 3.0)

    # Both ran, one after the other
    assert load.start_time <= load.end_time <= fit.start_time <= fit.end_time
    assert not load.is_active
    assert not fit.is_active

    # Completing a subtask counts as 100%, regardless of what it last reported
    assert load.progress.value == 1
    assert fit.progress.value == 1
    assert load.eta == 1.5
    assert fit.eta is None

    # Overall progress is weighted: load is 1/4 of the total, fit 3/4
    values = [p.value for p in overall_seen]
    assert values == sorted(values), 'Overall progress went backwards'
    assert values[-1] == pytest.approx(1.0)
    assert pytest.approx(0.125) in values  # load at 50%
    assert pytest.approx(0.25) in values  # load done
    assert pytest.approx(0.625) in values  # fit at 50%

    assert [(m.kind, m.payload) for m in messages] == [('subtask', 'from load')]


@pytest.mark.integration
def test_subtask_failure_events(qtbot, manager):
    """Test that a failing subtask still reports finishing and later ones never run."""
    task = Task(target=failing_subtask_task, with_context=True)

    manager.submit(task)
    record = wait_for_task(qtbot, manager, task.id)

    assert record.status == TaskStatus.FAILED
    assert 'Subtask failed' in record.error

    first, second = record.subtasks[('0',)], record.subtasks[('1',)]
    assert first.start_time is not None
    assert first.end_time is not None
    assert first.progress.value == 25  # No automatic completion on failure
    assert second.start_time is None
    assert second.progress is None
