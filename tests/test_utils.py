import pytest
import numpy as np
from scipy.signal import sosfilt, sosfiltfilt, sosfilt_zi, decimate, cheby1

from rfsocinterface.core.utils import decimate_in_chunks, sosfilt_in_chunks


@pytest.mark.parametrize(
    'shape, n_chunks, axis',
    [
        ((1000,), 1, -1),  # Sanity check
        ((1000,), 10, -1),
        ((100, 1000), 10, -1),
        # Changing axis
        ((100, 1000), 10, 0),
        ((10, 100, 1000), 10, 1),
        # Co-prime numbers
        ((10, 10, 999), 10, -1),
        ((10, 10, 1001), 10, -1),
        ((10, 10, 999), 8, -1),
        ((10, 10, 786), 17, -1),
    ],
)
def test_sosfilt_in_chunks(shape: tuple[int, ...], n_chunks: int, axis: int):
    """Test the sosfilt_in_chunks function."""
    sos = cheby1(4, 0.5, 0.2, output='sos')
    x = np.random.randn(*shape)
    y = sosfilt_in_chunks(sos, x, n_chunks=10, axis=axis)
    assert y.shape == x.shape
    assert np.allclose(y, sosfilt(sos, x, axis=axis))


@pytest.mark.parametrize(
    'shape, q, axis',
    [
        ((1000,), 1, -1),  # Sanity check
        ((1000,), 10, -1),
        ((100, 1000), 10, -1),
        # Changing axis
        ((100, 1000), 10, 0),
        ((10, 100, 1000), 10, 1),
        # Co-prime numbers
        ((10, 10, 999), 10, -1),
        ((10, 10, 1001), 10, -1),
        ((10, 10, 999), 8, -1),
        ((10, 10, 786), 17, -1),
    ],
)
def test_decimate_in_chunks(shape: tuple[int, ...], q: int, axis: int):
    """Test the decimate_in_chunks function."""
    x = np.random.randn(*shape)
    y = decimate_in_chunks(x, q, axis=axis)
    assert np.allclose(y, decimate(x, q, axis=axis))