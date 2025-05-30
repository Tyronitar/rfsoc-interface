"""Common utility functions for use throughout the project."""

import functools
import time
from collections.abc import Callable
from typing import Any

from numbers import Number

import numpy as np
import pytest


__all__ = [
    'assert_equal',
    'assert_close',
    'catch_exits',
    'sleep_and_raise',
    'assert_equal_dict',
    'assert_less_than',
    'assert_greater_than',
]


def assert_equal_dict(result: dict, expected: dict) -> bool:
    """Return whether two dictionaries are equal."""
    try:
        vals = (all_close(result[k], expected[k]) for k in expected)
    except KeyError:
        # assert False
        pytest.fail('Dictionaries do not contain the same keys')
    assert all(list(vals))


def assert_equal(result: Any, expected: Any) -> None:
    """Assert the two inputs are equivalent."""
    if isinstance(result, dict) and isinstance(expected, dict):
        assert_equal_dict(result, expected)
        return
    np.testing.assert_equal(result, expected)
    # assert np.array_equal(result, expected)


def all_close(result: Any, expected: Any, err: float = 1e-3) -> bool:
    """Check whether two numbers are close to equal, within some error bound."""
    if isinstance(result, Number | np.ndarray) and isinstance(
        expected, Number | np.ndarray
    ):
        return np.allclose(result, expected, atol=err)
    if (
        isinstance(result, list | np.ndarray)
        and isinstance(expected, list | np.ndarray)
        and len(result) > 0
        and isinstance(result[0], Number)
    ):
        return np.allclose(result, expected, atol=err)
    assert_equal(result, expected)
    return True


def assert_close(result: Any, expected: Any, err: float = 1e-3) -> None:
    """Assert two numbers are close to equal, within some error bound."""
    if isinstance(result, Number | np.ndarray) and isinstance(
        expected, Number | np.ndarray
    ):
        np.testing.assert_allclose(result, expected, atol=err)
        # assert np.allclose(n1, n2, rtol=err)
    elif (
        isinstance(result, list | np.ndarray)
        and isinstance(expected, list | np.ndarray)
        and len(result) > 0
        and isinstance(result[0], Number)
    ):
        # assert np.allclose(n1, n2, rtol=err)
        np.testing.assert_allclose(result, expected, atol=err)
    else:
        assert_equal(result, expected)


def assert_less_than(n1: Any, n2: Any):
    """Assert n1 is less than n2 at all points."""
    np.testing.assert_array_less(n1, n2)


def assert_greater_than(n1: Any, n2: Any):
    """Assert n1 is less than n2 at all points."""
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
