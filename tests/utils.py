"""Common utility functions for use throughout the project."""

import functools
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

__all__ = [
    'assert_close',
    'assert_equal',
    'assert_greater_than',
    'assert_less_than',
    'catch_exits',
    'sleep_and_raise',
]


def assert_equal(result: Any, expected: Any) -> None:
    """Assert the two inputs are equivalent."""
    np.testing.assert_equal(result, expected)


def assert_close(result: Any, expected: Any, err: float = 1e-3) -> None:
    """Assert two numbers are close to equal, within some error bound."""
    np.testing.assert_allclose(result, expected, atol=err)


def assert_less_than(n1: Any, n2: Any):
    """Assert n1 is less than n2 at all points."""
    np.testing.assert_array_less(n1, n2)


def assert_greater_than(n1: Any, n2: Any):
    """Assert n1 is greater than n2 at all points."""
    np.testing.assert_array_less(n2, n1)


def catch_exits(func: Callable) -> Callable:
    """Wrapper to catch and silence exit calls."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with pytest.raises(SystemExit) as exc_info:
            func(*args, **kwargs)
        assert exc_info.value.code == 0

    return wrapper


def sleep_and_raise(n: int):
    """Sleep for some time and the raise an error."""
    time.sleep(n)
    raise RuntimeError('expected raise')
