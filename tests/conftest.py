"""Shared testing utilities."""

from collections.abc import Callable
from pathlib import Path

import h5py
import numpy as np
import pytest

FIXTURE_DIRECTORY = Path(__file__).parent.resolve() / 'test_data'

TOD_FILE = pytest.mark.datafiles(
    FIXTURE_DIRECTORY / '20260709/20260709_Test_Tile_TOD_set1001.h5'
)
CONSOLIDATED_FILE = pytest.mark.datafiles(
    FIXTURE_DIRECTORY / '20260709/20260709_set1001_consolidated_data.h5'
)
PROCESSED_FILE = pytest.mark.datafiles(
    FIXTURE_DIRECTORY / '20260709/20260709_set1001_processed_data.h5'
)


@pytest.fixture
def make_fake_data(tmp_path) -> Callable[[None], h5py.File]:
    """Factory for creating fake ProcessedData files."""

    def _make_fake_data(file_name) -> h5py.File:
        temp_hdf5_file = h5py.File(
            tmp_path / file_name, driver='core', backing_store=False, mode='w'
        )
        vdsets = temp_hdf5_file.create_group('vdsets')
        data_IQ = vdsets.create_dataset('data_IQ', shape=(2, 10, 100), dtype=np.float64)
        data_gain_phase = vdsets.create_dataset(
            'data_gain_phase', shape=(2, 10, 100), dtype=np.float64
        )
        data_IQ[:] = np.random.default_rng(0).random((2, 10, 100))
        data_gain_phase[:] = np.random.default_rng(1).random((2, 10, 100))
        temp_hdf5_file.attrs['date'] = '20260709'
        temp_hdf5_file.attrs['setnum'] = 1001
        return temp_hdf5_file

    return _make_fake_data
