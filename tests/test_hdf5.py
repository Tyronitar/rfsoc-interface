"""Tests for HDF5-related code."""

import pytest
from tests.conftest import TOD_FILE
from unittest.mock import MagicMock
import h5py

from rfsocinterface.core.utils import (
    search,
)


@TOD_FILE
def test_search(datafiles):
    file = h5py.File(list(datafiles.iterdir())[0], 'r')

    # Standard search
    res = search(file, 'adc_i')
    assert res is not None
    name, obj = res
    assert name == '/time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']

    # Searching with full name
    name, obj = search(file, '/time_ordered_data/adc_i')
    assert name == '/time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']

    # Full name disabled
    res = search(file, 'adc_i', full_name=False)
    assert res is not None
    name, obj = res
    assert name == 'time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']

    # No match
    res = search(file, 'adc_iq')
    assert res is None

    # Exact match
    res = search(file, 'adc_i', exact_match=True)
    assert res is None

    res = search(file, '/time_ordered_data/adc_i', exact_match=True)
    assert res is not None
    name, obj = res
    assert name == '/time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']
