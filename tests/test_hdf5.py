"""Tests for HDF5-related code."""

import h5py

from rfsocinterface.core.utils import (
    search,
)
from tests.conftest import TOD_FILE


@TOD_FILE
def test_search(datafiles):
    """Test searching for keywords in HDF5 files."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')

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
