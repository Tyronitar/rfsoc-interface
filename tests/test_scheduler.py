"""Deterministic scheduling tests for TaskManager."""

from __future__ import annotations

import threading
import typing
from collections import deque
from dataclasses import replace
from uuid import UUID

import pytest

from rfsocinterface.core.tasks.backend import BackendUpdate, WorkerExit
from rfsocinterface.core.tasks.manager import TaskManager
from rfsocinterface.core.tasks.task import (
    CancellationPolicy,
    Cancelled,
    Failed,
    Started,
    Succeeded,
    Task,
    TaskStatus,
)


def unused_target():
    """Fake backend never calls the task target."""


class ControlledBackend:
    """A thread-safe fake backend whose worker events are controlled by tests.

    BackendRunner calls start/cancel/terminate/poll/close in its own thread.
    Tests call succeed/fail/exit from the GUI/test thread.
    """

    def __init__(self):
        """Initialize a ControlledBackend."""
        self._lock = threading.Lock()
        self._pending = deque()
        self._started: dict[UUID, Task] = {}
        self._start_order: list[UUID] = []
        self._cancelled: list[UUID] = []
        self._terminated: list[UUID] = []
        self._fail_start: set[UUID] = set()

    @property
    def start_order(self) -> list[UUID]:
        """Tasks in order of being started."""
        with self._lock:
            return list(self._start_order)

    @property
    def cancelled(self) -> list[UUID]:
        """Tasks that have been cancelled."""
        with self._lock:
            return list(self._cancelled)

    def fail_next_start(self, task_id: UUID) -> None:
        """Make the next call to start for the task fail."""
        with self._lock:
            self._fail_start.add(task_id)

    @typing.override
    def start(self, task: Task) -> None:
        with self._lock:
            if task.id in self._fail_start:
                self._fail_start.remove(task.id)
                raise RuntimeError('Simulated startup failure')
            if task.id in self._started:
                raise AssertionError(f'Duplicate start: {task.id}')
            self._started[task.id] = task
            self._start_order.append(task.id)
            self._pending.append(BackendUpdate([Started(task.id)], {}))

    @typing.override
    def cancel(self, task_id: UUID) -> None:
        with self._lock:
            if task_id not in self._started:
                raise KeyError(task_id)
            self._cancelled.append(task_id)

    @typing.override
    def terminate(self, task_id: UUID) -> None:
        with self._lock:
            if task_id not in self._started:
                raise KeyError(task_id)
            self._terminated.append(task_id)

    @typing.override
    def poll(self, limit: int = 100) -> BackendUpdate:
        with self._lock:
            events = []
            exits = {}
            # Drain bounded updates, preserving their order.
            for _ in range(min(limit, len(self._pending))):
                update = self._pending.popleft()
                events.extend(update.events)
                exits.update(update.exited_workers)
            return BackendUpdate(events, exits)

    @typing.override
    def close(self) -> bool:
        # This fake has no real workers or OS resources.
        return True

    def _emit(self, event) -> None:
        """Add an event to the queue."""
        with self._lock:
            assert event.task_id in self._started, 'Task was not started'
            self._pending.append(BackendUpdate([event], {}))

    def succeed(self, task_id: UUID, result=None) -> None:
        """Mark a task as succeeded."""
        self._emit(Succeeded(task_id, result))

    def fail(self, task_id: UUID, error='Simulated failure') -> None:
        """Mark a task as failed."""
        self._emit(Failed(task_id, error, 'Simulated traceback'))

    def finish_cancelled(self, task_id: UUID) -> None:
        """Mark a task as cancelled."""
        self._emit(Cancelled(task_id))

    def exit(self, task_id: UUID, exit_code=0) -> None:
        """Independently simulate confirmed process exit and cleanup."""
        with self._lock:
            assert task_id in self._started
            del self._started[task_id]
            self._pending.append(
                BackendUpdate([], {task_id: WorkerExit(exit_code=exit_code)})
            )


@pytest.fixture
def rig(qtbot):  # noqa: ARG001
    """Fixture for scheduler tests and cleanup."""
    backend = ControlledBackend()
    manager = TaskManager(backend, max_workers=2)
    yield manager, backend
    manager.close()
    assert manager.runner.wait(timeout=5), 'Backend runner did not stop'


def task(*, depends_on=(), resources=(), policy=CancellationPolicy.COOPERATIVE):
    """Construct a dummy task for scheduling tests."""
    return Task(
        target=unused_target,
        depends_on=frozenset(depends_on),
        resources=frozenset(resources),
        cancellation_policy=policy,
    )


def wait_started(qtbot, backend, task_id):
    """Wait for the backend to report task starting."""
    qtbot.waitUntil(lambda: task_id in backend.start_order, timeout=3000)


def wait_status(qtbot, manager, task_id, status):
    """Wait for the task to have the desired status."""
    qtbot.waitUntil(
        lambda: manager.records[task_id].status == status,
        timeout=3000,
    )


def complete(qtbot, manager, backend, task_id, result=None):
    """Mark a task as succeeded."""
    backend.succeed(task_id, result)
    wait_status(qtbot, manager, task_id, TaskStatus.SUCCEEDED)
    backend.exit(task_id)
    qtbot.waitUntil(lambda: manager.records[task_id].worker_exited, timeout=3000)


@pytest.mark.integration
def test_independent_tasks_start_concurrently(qtbot, rig):
    """Test that independent tasks start independently."""
    manager, backend = rig
    a = task(resources={'file:A'})
    b = task(resources={'file:B'})
    manager.submit(a)
    manager.submit(b)
    qtbot.waitUntil(lambda: len(backend.start_order) == 2, timeout=3000)
    assert set(backend.start_order) == {a.id, b.id}


@pytest.mark.integration
def test_same_resource_serializes_until_worker_exit(qtbot, rig):
    """Tasks that use the same resource cannot overlap."""
    manager, backend = rig
    a = task(resources={'file:A'})
    b = task(resources={'file:A'})
    manager.submit(a)
    manager.submit(b)
    wait_started(qtbot, backend, a.id)
    assert b.id not in backend.start_order

    backend.succeed(a.id)
    wait_status(qtbot, manager, a.id, TaskStatus.SUCCEEDED)
    assert b.id not in backend.start_order, 'Lock released before process exit'

    backend.exit(a.id)
    wait_started(qtbot, backend, b.id)
    assert backend.start_order == [a.id, b.id]


@pytest.mark.integration
def test_dependency_waits_for_success_and_exit(qtbot, rig):
    """Dependent tasks wait for success and worker exit."""
    manager, backend = rig
    a = task()
    b = task(depends_on={a.id})
    manager.submit(a)
    manager.submit(b)
    wait_started(qtbot, backend, a.id)
    assert b.id not in backend.start_order

    backend.succeed(a.id)
    wait_status(qtbot, manager, a.id, TaskStatus.SUCCEEDED)
    assert b.id not in backend.start_order

    backend.exit(a.id)
    wait_started(qtbot, backend, b.id)


@pytest.mark.integration
@pytest.mark.parametrize('outcome', ['failed', 'cancelled'])
def test_unsuccessful_dependency_skips_descendants(qtbot, rig, outcome):
    """Check that unsuccessful dependencies result in workers skipping."""
    manager, backend = rig
    a = task()
    b = task(depends_on={a.id})
    c = task(depends_on={b.id})
    manager.submit(a)
    manager.submit(b)
    manager.submit(c)
    wait_started(qtbot, backend, a.id)

    if outcome == 'failed':
        backend.fail(a.id)
        wait_status(qtbot, manager, a.id, TaskStatus.FAILED)
    else:
        backend.finish_cancelled(a.id)
        wait_status(qtbot, manager, a.id, TaskStatus.CANCELLED)
    backend.exit(a.id)
    wait_status(qtbot, manager, b.id, TaskStatus.SKIPPED)
    wait_status(qtbot, manager, c.id, TaskStatus.SKIPPED)
    assert b.id not in backend.start_order
    assert c.id not in backend.start_order


@pytest.mark.integration
def test_multiple_resources_are_acquired_atomically(qtbot, rig):
    """Check that all resource locks are acquired before dispatch."""
    manager, backend = rig
    a = task(resources={'file:A'})
    b = task(resources={'file:A', 'file:B'})
    c = task(resources={'file:B'})
    manager.submit(a)
    manager.submit(b)
    manager.submit(c)
    qtbot.waitUntil(lambda: len(backend.start_order) == 2, timeout=3000)
    assert set(backend.start_order) == {a.id, c.id}
    assert b.id not in backend.start_order

    complete(qtbot, manager, backend, a.id)
    assert b.id not in backend.start_order  # B is still owned by C.
    complete(qtbot, manager, backend, c.id)
    wait_started(qtbot, backend, b.id)


@pytest.mark.integration
def test_max_workers_limit(qtbot, rig):
    """`max_workers` is respected."""
    manager, backend = rig  # max_workers=2
    a, b, c = task(), task(), task()
    for t in (a, b, c):
        manager.submit(t)
    qtbot.waitUntil(lambda: len(backend.start_order) == 2, timeout=3000)
    assert c.id not in backend.start_order
    complete(qtbot, manager, backend, a.id)
    wait_started(qtbot, backend, c.id)


@pytest.mark.integration
def test_start_failure_releases_resources(qtbot, rig):
    """Failing start releases resources."""
    manager, backend = rig
    a = task(resources={'file:A'})
    b = task(resources={'file:A'})
    backend.fail_next_start(a.id)
    manager.submit(a)
    manager.submit(b)
    wait_status(qtbot, manager, a.id, TaskStatus.FAILED)
    wait_started(qtbot, backend, b.id)
    assert not manager.records[a.id].worker_exited  # No worker was ever created.


@pytest.mark.integration
def test_cancel_queued_task_never_starts(qtbot, rig):
    """Cancelling a queued task ensures it never starts."""
    manager, backend = rig
    a = task(resources={'file:A'})
    b = task(resources={'file:A'})
    manager.submit(a)
    manager.submit(b)
    wait_started(qtbot, backend, a.id)
    manager.cancel(b.id)
    wait_status(qtbot, manager, b.id, TaskStatus.CANCELLED)
    complete(qtbot, manager, backend, a.id)
    assert b.id not in backend.start_order
    assert b.id not in backend.cancelled


@pytest.mark.integration
def test_unknown_dependency_is_rejected(rig):
    """Reject invalid dependencies."""
    manager, _ = rig
    with pytest.raises(ValueError, match=r'dependenc|unknown|missing'):
        manager.submit(task(depends_on={UUID(int=123)}))


@pytest.mark.integration
def test_self_dependency_is_rejected(rig):
    """A task cannot depend on itself."""
    manager, _ = rig
    a = task()
    a = replace(a, depends_on=frozenset({a.id}))
    with pytest.raises(ValueError, match=r'depend|itself|cycle'):
        manager.submit(a)
