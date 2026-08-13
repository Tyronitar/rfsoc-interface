"""Tests for the data processing pipeline."""

import pytest

from rfsocinterface.core.data import ProcessedData
from tests.utils import (
    ArbitraryArgumentRoutine,
    MultiInputDefaultInputsRoutine,
    MultiInputRoutine,
    NoReturnRoutine,
    NoRunRoutine,
    SingleInputDefaultInputsRoutine,
    SingleInputRoutine,
    assert_equal,
)


def test_single_input_routine(make_fake_data):
    """Test that a single-input routine works properly."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)
    routine = SingleInputRoutine()
    result = routine.apply(pdata)

    assert pdata.has('/tests/result', exact_match=True)
    assert 'data_IQ' not in pdata
    assert_equal(pdata.data_gain_phase[:], 0)
    assert_equal(pdata['tests/result'][:], result)


def test_mapped_inputs(make_fake_data):
    """Test a routine with mapped inputs."""
    pdata = []
    for i in range(3):
        fake_data = make_fake_data(f'test_{i}.h5')
        pdata.append(ProcessedData.from_h5py(fake_data))
    routine = SingleInputRoutine()
    result = routine.apply(*pdata)

    for i, pd in enumerate(pdata):
        assert pd.has('/tests/result', exact_match=True)
        assert 'data_IQ' not in pd
        assert_equal(pd.data_gain_phase[:], 0)
        assert_equal(pd['tests/result'][:], result[i])


def test_multi_input_routine(make_fake_data):
    """Test that a multi-input routine works properly."""
    fake_data_x = make_fake_data('test_x.h5')
    pdata_x = ProcessedData.from_h5py(fake_data_x)
    fake_data_y = make_fake_data('test_y.h5')
    pdata_y = ProcessedData.from_h5py(fake_data_y)

    routine = MultiInputRoutine()
    result = routine.apply(pdata_x, pdata_y)

    assert isinstance(result, dict)
    res_x = result['x']
    res_y = result['y']

    assert pdata_x.has('/tests/result', exact_match=True)
    assert 'data_IQ' not in pdata_x
    assert_equal(pdata_x.data_gain_phase[:], 0)
    assert_equal(pdata_x['tests/result'][:], res_x)

    assert pdata_y.has('/tests/result', exact_match=True)
    assert 'data_gain_phase' not in pdata_y
    assert_equal(pdata_y.data_IQ[:], 0)
    assert_equal(pdata_y['tests/result'][:], res_y)

    assert_equal(res_y, res_x / 2)


def test_single_input_routine_with_default_inputs(make_fake_data):
    """Test that single-input routines work without overriding _inputs."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)
    routine = SingleInputDefaultInputsRoutine()
    routine.apply(pdata)


def test_multi_input_routine_with_default_inputs(make_fake_data):
    """Test that multi-input routines work without overriding _inputs."""
    fake_data_x = make_fake_data('test_x.h5')
    pdata_x = ProcessedData.from_h5py(fake_data_x)
    fake_data_y = make_fake_data('test_y.h5')
    pdata_y = ProcessedData.from_h5py(fake_data_y)
    routine = MultiInputDefaultInputsRoutine()
    routine.apply(pdata_x, pdata_y)


def test_routine_no_return(make_fake_data):
    """Test that a routine works properly if _run returns nothing."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)
    routine = NoReturnRoutine()
    result = routine.apply(pdata)

    assert result is None


@pytest.mark.parametrize(
    'n_inputs',
    [1, 2, 3, 4],
)
def test_arbitrary_multi_input_routine(make_fake_data, n_inputs):
    """Test routines that take an arbitrary number of arguments."""
    routine = ArbitraryArgumentRoutine()

    pdata = []
    for i in range(n_inputs):
        fake_data = make_fake_data(f'test_{i}.h5')
        pdata.append(ProcessedData.from_h5py(fake_data))

    routine.apply(*pdata)


def test_no_inputs_fails():
    """Test that applying the routine with no inputs fails."""
    routine = ArbitraryArgumentRoutine()
    with pytest.raises(
        ValueError, match='base requires at least one ProcessedData object'
    ):
        routine.apply()


def test_run_not_implemented(make_fake_data):
    """Test that using a routine that doesn't override _run fails."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)
    routine = NoRunRoutine()
    with pytest.raises(NotImplementedError, match='missing a run method'):
        routine.apply(pdata)
