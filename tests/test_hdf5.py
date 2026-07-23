"""Tests for HDF5-related code."""
# ruff: noqa: PLR2004

import h5py

from rfsocinterface.core.utils import (
    search,
    search_regex,
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


@TOD_FILE
def test_search_fullname(datafiles):
    """Test search with the fullname."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    name, obj = search(file, '/time_ordered_data/adc_i')
    assert name == '/time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']


@TOD_FILE
def test_search_fullname_disabled(datafiles):
    """Test search with `fullname=False`."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search(file, 'adc_i', full_name=False)
    assert res is not None
    name, obj = res
    assert name == 'time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']


@TOD_FILE
def test_search_no_match(datafiles):
    """Test search where no match is found."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    # No match
    res = search(file, 'adc_iq')
    assert res is None


@TOD_FILE
def test_search_exact_match_miss(datafiles):
    """Test search with `exact_match=True` and no match found."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    # Exact match
    res = search(file, 'adc_i', exact_match=True)
    assert res is None


@TOD_FILE
def test_search_exact_match_hit(datafiles):
    """Test search with `exact_match=True` and a match found."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search(file, '/time_ordered_data/adc_i', exact_match=True)
    assert res is not None
    name, obj = res
    assert name == '/time_ordered_data/adc_i'
    assert obj == file['/time_ordered_data/adc_i']


@TOD_FILE
def test_search_regex_no_pattern(datafiles):
    """Test search_regex when not using regex patterns."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')

    # Normal string pattern
    res = search_regex(file, 'adc_i')
    assert len(res) == 1
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']

    # Full name disabled
    res = search_regex(file, 'adc_i', full_name=False)
    assert len(res) == 1
    assert res[0][0] == 'time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']


@TOD_FILE
def test_search_regex_wildcard(datafiles):
    """Test search_regex with a wildcard expression."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, 'adc_.')
    assert len(res) == 2
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']
    assert res[1][0] == '/time_ordered_data/adc_q'
    assert res[1][1] == file['/time_ordered_data/adc_q']


@TOD_FILE
def test_search_regex_character_set(datafiles):
    """Test search_regex with a set of valid characters."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, 'adc_[iq]')
    assert len(res) == 2
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']
    assert res[1][0] == '/time_ordered_data/adc_q'
    assert res[1][1] == file['/time_ordered_data/adc_q']


@TOD_FILE
def test_search_regex_pipe(datafiles):
    """Test search_regex using a pipe "|" in the pattern."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, '(adc_i)|(adc_q)')
    assert len(res) == 2
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']
    assert res[1][0] == '/time_ordered_data/adc_q'
    assert res[1][1] == file['/time_ordered_data/adc_q']


@TOD_FILE
def test_search_regex_no_match(datafiles):
    """Test search_regex and getting no matches."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, 'adc_iq')
    assert len(res) == 0
    res = search_regex(file, 'adc_i{2}')
    assert len(res) == 0


@TOD_FILE
def test_search_regex_exact_match_miss(datafiles):
    """Test search_regex with `exact_match=True` and getting no matches."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    # Exact match
    res = search_regex(file, 'adc_i', exact_match=True)
    assert len(res) == 0


@TOD_FILE
def test_search_regex_exact_match_hit(datafiles):
    """Test search_regex with `exact_match=True` and getting a match."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, '.*/adc_i', exact_match=True)
    assert len(res) == 1
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']


@TOD_FILE
def test_search_regex_complicated_pattern(datafiles):
    """Test search_regex with a more complicated pattern."""
    file = h5py.File(next(iter(datafiles.iterdir())), 'r')
    res = search_regex(file, r'\w{3}_([iq]|idx)')
    assert len(res) == 3
    assert res[0][0] == '/time_ordered_data/adc_i'
    assert res[0][1] == file['/time_ordered_data/adc_i']
    assert res[1][0] == '/time_ordered_data/adc_q'
    assert res[1][1] == file['/time_ordered_data/adc_q']
    assert res[2][0] == '/time_ordered_data/pkt_idx'
    assert res[2][1] == file['/time_ordered_data/pkt_idx']
