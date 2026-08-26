"""Common utility functions for use throughout the project."""

import functools
import time
import typing
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from rfsocinterface.core.data import (
    DataRoutine,
    ProcessedData,
    RoutineResult,
)

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


# ruff: disable[ARG002]


class SingleInputRoutine(DataRoutine):
    @typing.override
    def _run(self, pdata, inputs):
        test_group = pdata.create_group('tests')
        res = test_group.create_dataset('result', shape=(2, 10), dtype=np.float64)
        res[:] = np.random.default_rng(2).random((2, 10))
        pdata.get_data_gain_phase(0)[:] = 0
        del pdata['channels/channel_000/time_ordered_data/data_IQ']

        return RoutineResult(
            created={'input': ('tests', 'tests/result')},
            modified={
                'input': ('channels/channel_000/time_ordered_data/data_gain_phase',)
            },
            deleted={'input': ('channels/channel_000/time_ordered_data/data_IQ',)},
            value=res[:],
        )


class MultiInputRoutine(DataRoutine):
    max_inputs = 2
    map_over_inputs = False

    @typing.override
    def _inputs(self, x: ProcessedData, y: ProcessedData):
        return {
            'x': {
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            },
            'y': {
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            },
        }

    @typing.override
    def _run(self, x: ProcessedData, y: ProcessedData, inputs):
        test_group_x = x.create_group('tests')
        res_x = test_group_x.create_dataset('result', shape=(2, 10), dtype=np.float64)
        res_x[:] = np.random.default_rng(2).random((2, 10))
        x.get_data_gain_phase(0)[:] = 0
        x.get_data_gain_phase(0)[:] = 0
        del x['channels/channel_000/time_ordered_data/data_IQ']

        test_group_y = y.create_group('tests')
        res_y = test_group_y.create_dataset('result', shape=(2, 10), dtype=np.float64)
        res_y[:] = res_x[:] / 2
        y.get_data_IQ(0)[:] = 0
        y.get_data_IQ(0)[:] = 0
        del y['channels/channel_000/time_ordered_data/data_gain_phase']

        return RoutineResult(
            created={
                'x': ('tests', 'tests/result'),
                'y': ('tests', 'tests/result'),
            },
            modified={
                'x': ('channels/channel_000/time_ordered_data/data_gain_phase',),
                'y': ('channels/channel_000/time_ordered_data/data_IQ',),
            },
            deleted={
                'x': ('channels/channel_000/time_ordered_data/data_IQ',),
                'y': ('channels/channel_000/time_ordered_data/data_gain_phase',),
            },
            value={
                'x': res_x[:],
                'y': res_y[:],
            },
        )


class CreateValueRoutine(DataRoutine):
    def __init__(self, val: int):
        super().__init__(val=val)

    def _run(self, pdata, inputs):
        if 'test' not in pdata:
            test_group = pdata.create_group('test')
        else:
            test_group = pdata['test']
        val = self.params['val']
        test_group.create_dataset(f'val_{val}', data=val)
        return RoutineResult(created={'input': [f'test/val_{val}']})


class MultiInputDefaultInputsRoutine(DataRoutine):
    max_inputs = 2
    map_over_inputs = False

    def _run(self, *pdata, inputs):
        return RoutineResult()


class NoRunRoutine(DataRoutine):
    pass


class SingleInputDefaultInputsRoutine(DataRoutine):
    def _run(self, pdata, inputs):
        return RoutineResult()


class ReturnNoneRoutine(DataRoutine):
    def _run(self, pdata, inputs):
        return None


class ReturnCollectionRoutine(DataRoutine):
    def _run(self, pdata, inputs):
        return []


class ListInputsRoutine(DataRoutine):
    def _inputs(self, pdata):
        self.expected_inputs = {
            'input': (
                pdata,
                (
                    'channels/channel_000/time_ordered_data/data_IQ',
                    'channels/channel_000/time_ordered_data/data_gain_phase',
                ),
            )
        }
        return [
            'channels/channel_000/time_ordered_data/data_IQ',
            'channels/channel_000/time_ordered_data/data_gain_phase',
        ]

    def _run(self, pdata, inputs):
        return RoutineResult()


class PositionalInputsRoutine(DataRoutine):
    min_inputs = 2
    max_inputs = 2
    map_over_inputs = False

    def _inputs(self, *pdata):
        self.expected_inputs = {
            'input_0': (
                pdata[0],
                (
                    'channels/channel_000/time_ordered_data/data_IQ',
                    'channels/channel_000/time_ordered_data/data_gain_phase',
                ),
            ),
            'input_1': (
                pdata[1],
                (
                    'channels/channel_000/time_ordered_data/data_IQ',
                    'channels/channel_000/time_ordered_data/data_gain_phase',
                ),
            ),
        }
        return (
            [
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            ],
            [
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            ],
        )

    def _run(self, *pdata, inputs):
        return RoutineResult()


class NamedInputsRoutine(DataRoutine):
    min_inputs = 2
    max_inputs = 2
    map_over_inputs = False

    def _inputs(self, pdata_x, pdata_y):
        self.expected_inputs = {
            'pdata_x': (
                pdata_x,
                (
                    'channels/channel_000/time_ordered_data/data_IQ',
                    'channels/channel_000/time_ordered_data/data_gain_phase',
                ),
            ),
            'pdata_y': (
                pdata_y,
                (
                    'channels/channel_000/time_ordered_data/data_IQ',
                    'channels/channel_000/time_ordered_data/data_gain_phase',
                ),
            ),
        }
        return {
            'pdata_x': [
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            ],
            'pdata_y': [
                'channels/channel_000/time_ordered_data/data_IQ',
                'channels/channel_000/time_ordered_data/data_gain_phase',
            ],
        }

    def _run(self, pdata_x, pdata_y, inputs):
        return RoutineResult()


class ArbitraryArgumentRoutine(DataRoutine):
    max_inputs = None

    def _run(self, *pdata, inputs):
        return RoutineResult()


# ruff: enable[ARG002]
