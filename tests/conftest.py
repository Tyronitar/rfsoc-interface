"""Shared testing utilities."""

from pathlib import Path
import pytest

FIXTURE_DIRECTORY = Path(__file__).parent.resolve() / 'test_data'

TOD_FILE = pytest.mark.datafiles(FIXTURE_DIRECTORY / '20260709_Test_Tile_TOD_set1001.h5')
