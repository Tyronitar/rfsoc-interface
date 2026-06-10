"""Tests for RFSoC parameter files."""
import pytest
import h5py
import numpy as np

from rfsocinterface.core.params import RFSoCParameters

from tests.utils import all_close, assert_close, assert_equal


def test_initialize_params(tmpdir):
    tile_name = 'test_name'
    n_tones = 100
    params = RFSoCParameters.new_file(tile_name, n_tones, params_dir=tmpdir)

    assert params.tile_name == tile_name

    # Test default values 
    assert params.n_tones == n_tones
    assert_close(params.f_center, 4e8)
    assert_close(params.rfin, 0)
    assert_close(params.rfout, 0)
    assert_close(params.tile_number, 0)
    assert_close(params.chan_number, 0)
    assert_close(params.ifslice_number, 0)
    assert params.version == RFSoCParameters.VERSION

    assert_close(params.chanmask, np.ones(n_tones, dtype=int))
    assert_close(params.baseband_freqs, np.zeros(n_tones))
    assert_close(params.tone_powers, np.ones(n_tones))
    assert_close(params.detector_delta_x, np.zeros(n_tones))
    assert_close(params.detector_delta_y, np.zeros(n_tones))
    assert_close(params.detector_beam_ampl, np.ones(n_tones))
    assert_close(params.detector_beam_ampl, np.ones(n_tones, dtype=np.int8))
    assert_close(params.dfoverf_per_mK, np.ones(n_tones))

@pytest.mark.parametrize('field, dtype, size, low, high', [
    ('f_center', np.float64, 1, 0, 800e6),
    ('rfin', np.float64, 1, 0, 31.75),
    ('rfout', np.float64, 1, 0, 31.75),
    ('tile_number', int, 1, 0, 20),
    ('chan_number', int, 1, 0, 20),
    ('ifslice_number', int, 1, 0, 20),
    ('chanmask', np.int8, -1, -1, 2),
    ('baseband_freqs', np.float64, -1, None, None),
    ('tone_powers', np.float64, -1, None, None),
    ('detector_delta_x', np.float64, -1, None, None),
    ('detector_delta_y', np.float64, -1, None, None),
    ('detector_beam_ampl', np.float64, -1, None, None),
    ('detector_pol', np.int8, -1, 0, 3),
    ('dfoverf_per_mK', np.float64, -1, None, None),
])
def test_copy_and_update(tmpdir, field: str, dtype: np.dtype, size, low, high):
    tile_name = 'test_name'
    n_tones = 100
    if size == -1:
        size = n_tones
    params = RFSoCParameters.new_file(tile_name, n_tones, params_dir=tmpdir)

    rng = np.random.default_rng()
    if dtype == np.int8 or dtype == int:
        new_val = rng.integers(low, high, size, dtype=dtype)
    else:
        new_val = rng.random(size, dtype=dtype)
    if size == 1:
        new_val = new_val.item()

    original_val = getattr(params, field)
    kwargs = {field: new_val}

    params_copy = params.copy_and_update('test_name_copy', **kwargs)

    # Make sure the original array was preserved
    assert_close(getattr(params, field), original_val)

    assert_close(getattr(params_copy, field), new_val)