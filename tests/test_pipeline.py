"""Tests for the data processing pipeline."""

import pytest

from rfsocinterface.core.data import Pipeline, ProcessedData, RoutineResult
from tests.utils import (
    ArbitraryArgumentRoutine,
    CreateValueRoutine,
    ListInputsRoutine,
    MultiInputDefaultInputsRoutine,
    MultiInputRoutine,
    NamedInputsRoutine,
    NoRunRoutine,
    PositionalInputsRoutine,
    ReturnCollectionRoutine,
    ReturnNoneRoutine,
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
    assert 'data_gain_phase' in pdata
    assert_equal(pdata.get_data_gain_phase(0)[:], 0)
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
        assert 'data_gain_phase' in pd
        assert_equal(pd.get_data_gain_phase(0)[:], 0)
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
    assert 'data_gain_phase' in pdata_x
    assert_equal(pdata_x.get_data_gain_phase(0)[:], 0)
    assert_equal(pdata_x['tests/result'][:], res_x)

    assert pdata_y.has('/tests/result', exact_match=True)
    assert 'data_IQ' in pdata_y
    assert 'data_gain_phase' not in pdata_y
    assert_equal(pdata_y.get_data_IQ(0)[:], 0)
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


# ruff: disable[SLF001]


def test_routine_input_normalization(make_fake_data, make_function_mock):
    """Ensure that routine inputs are normalized properly."""
    fake_data_x = make_fake_data('test_x.h5')
    pdata_x = ProcessedData.from_h5py(fake_data_x)
    fake_data_y = make_fake_data('test_y.h5')
    pdata_y = ProcessedData.from_h5py(fake_data_y)

    routine = ListInputsRoutine()
    with make_function_mock(routine._normalize_resolved_inputs) as mock_norm:
        result = routine.apply(pdata_x)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == routine.expected_inputs
        assert result is None

    routine = PositionalInputsRoutine()
    with make_function_mock(routine._normalize_resolved_inputs) as mock_norm:
        result = routine.apply(pdata_x, pdata_y)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == routine.expected_inputs
        assert result is None

    routine = NamedInputsRoutine()
    with make_function_mock(routine._normalize_resolved_inputs) as mock_norm:
        result = routine.apply(pdata_x, pdata_y)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == routine.expected_inputs
        assert result is None


def test_routine_output_normalization(make_fake_data, make_function_mock):
    """Ensure that routine outputs are normalized properly."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)

    routine = SingleInputDefaultInputsRoutine()
    with make_function_mock(routine._normalize_routine_outputs) as mock_norm:
        result = routine.apply(pdata)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == RoutineResult()
        assert result is None

    routine = ReturnNoneRoutine()
    with make_function_mock(routine._normalize_routine_outputs) as mock_norm:
        result = routine.apply(pdata)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == RoutineResult()
        assert result is None

    routine = ReturnCollectionRoutine()
    with make_function_mock(routine._normalize_routine_outputs) as mock_norm:
        result = routine.apply(pdata)
        args, kwargs = mock_norm.call_args
        normed_output = mock_norm._mock_wraps(*args, **kwargs)
        assert normed_output == RoutineResult(modified={'input': []})
        assert result is None


# ruff: enable[SLF001]


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


def test_wrong_number_of_inputs(make_fake_data):
    """Test that applying the routine with the wrong number of inputs fails."""
    routine = PositionalInputsRoutine()
    fake_data_x = make_fake_data('test_x.h5')
    pdata_x = ProcessedData.from_h5py(fake_data_x)
    fake_data_y = make_fake_data('test_y.h5')
    pdata_y = ProcessedData.from_h5py(fake_data_y)
    fake_data_z = make_fake_data('test_z.h5')
    pdata_z = ProcessedData.from_h5py(fake_data_z)

    with pytest.raises(
        ValueError, match='base requires at least one ProcessedData object'
    ):
        routine.apply()

    with pytest.raises(ValueError, match=r'requires at least 2 input dataset\(s\)'):
        routine.apply(pdata_x)

    routine.apply(pdata_x, pdata_y)

    with pytest.raises(ValueError, match=r'accepts at most 2 input dataset\(s\)'):
        routine.apply(pdata_x, pdata_y, pdata_z)


def test_run_not_implemented():
    """Test that using a routine that doesn't override _run fails."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        NoRunRoutine()


@pytest.mark.parametrize(
    'n_routines',
    [0, 1, 2, 3],
)
def test_pipeline(make_fake_data, n_routines):
    """Test that a pipeline works properly."""
    fake_data = make_fake_data('test.h5')
    pdata = ProcessedData.from_h5py(fake_data)

    pipeline = Pipeline([CreateValueRoutine(i) for i in range(n_routines)])
    pipeline.run(pdata)

    if n_routines > 0:
        assert pdata.has('/test', exact_match=True)
        for i in range(n_routines):
            assert pdata.has(f'/test/val_{i}', exact_match=True)
            assert_equal(pdata[f'/test/val_{i}'][()], i)
    else:
        assert 'test' not in pdata
