from typing import Callable
import time

import pytest
from rfsocinterface.core.pool import QThreadJobPool, QProcessJobPool

from tests.utils import assert_equal

# First 40 Fibonacci numbers
FIBONACCI = [
    0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597,
    2584, 4181, 6765, 10946, 17711, 28657, 46368, 75025, 121393, 196418, 317811,
    514229, 832040, 1346269, 2178309, 3524578, 5702887, 9227465, 14930352,
    24157817, 39088169, 63245986,
]

def fibonacci(n: int, progress_callback: Callable=None):
    if progress_callback is not None:
        progress_callback()
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def fail_on_four(n: int):
    if n == 4:
        raise ValueError('Four is unlucky')
    return n

#
# QThreadJobPool Tests
#

def test_qthread_job_pool(qtbot):
    n_tasks = 30
    pool = QThreadJobPool()
    # Check that signals are being emitted
    with qtbot.waitSignals([pool.job_finished, pool.progress, pool.result] * n_tasks):
        future = pool.map(fibonacci, range(n_tasks))
    assert_equal(list(future.result()), FIBONACCI[:n_tasks])


def test_qthread_job_pool_cancel(qapp):
    n_tasks = 25
    pool = QThreadJobPool(max_workers=3)
    future = pool.map(fibonacci, range(n_tasks))
    pool.shutdown(wait=True)
    assert future.cancelled()  # Job is canceled before it can be finished


def test_qthread_job_pool_exception(qtbot):
    n_tasks = 10
    pool = QThreadJobPool()
    # Check that signals are being emitted
    expected_signals = [(pool.job_finished, 'job_finished')] * n_tasks \
        + [(pool.result, 'result')] * (n_tasks - 1) \
        + [(pool.error, 'error')]
    with qtbot.waitSignals(expected_signals):
        future = pool.map(fail_on_four, range(n_tasks))
    pool.close()
    pool.join()
    with pytest.raises(ValueError, match='Four is unlucky'):
        print(future.exception())
        raise future.exception()

#
# QProcessJobPool Tests
#

def test_qprocess_job_pool(qtbot):
    n_tasks = 30
    pool = QProcessJobPool(max_workers=4)
    # Check that signals are being emitted
    with qtbot.waitSignals([pool.job_finished, pool.progress, pool.result] * n_tasks):
        future = pool.map(fibonacci, range(n_tasks))
    assert_equal(list(future.result()), FIBONACCI[:n_tasks])


def test_qprocess_job_pool_cancel(qapp):
    n_tasks = 50
    pool = QProcessJobPool(max_workers=3)
    future = pool.map(fibonacci, range(n_tasks))
    pool.shutdown(wait=True)
    assert future.cancelled()  # Job is canceled before it can be finished

def test_qprocess_job_pool_exception(qtbot):
    n_tasks = 10
    pool = QProcessJobPool(max_workers=2)
    # Check that signals are being emitted
    expected_signals = [(pool.job_finished, 'job_finished')] * n_tasks \
        + [(pool.result, 'result')] * (n_tasks - 1) \
        + [(pool.error, 'error')]
    with qtbot.waitSignals(expected_signals):
        future = pool.map(fail_on_four, range(n_tasks))
    pool.close()
    pool.join()
    with pytest.raises(ValueError, match='Four is unlucky'):
        print(future.exception())
        raise future.exception()