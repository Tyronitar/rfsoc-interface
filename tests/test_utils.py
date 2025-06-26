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

def test_sosfilt_in_chunks_out():
    """Test the sosfilt_in_chunks function with an output array."""
    sos = cheby1(4, 0.5, 0.2, output='sos')
    x = np.random.randn(10, 100, 1000)
    zi_shape = (sos.shape[0], 10, 100, 2)
    zi = np.zeros(zi_shape)
    y = (np.zeros((10, 100, 1000)), np.zeros(zi_shape))
    sosfilt_in_chunks(sos, x, zi=zi, n_chunks=10, out=y)
    assert y[0].shape == x.shape
    assert y[1].shape == zi_shape
    assert np.allclose(y[0], sosfilt(sos, x))

    y = np.zeros((10, 100, 1000))
    sosfilt_in_chunks(sos, x, n_chunks=10, out=y)
    assert y.shape == x.shape
    assert np.allclose(y, sosfilt(sos, x))

    # Wrong zi dimension
    with pytest.raises(ValueError, match='Invalid zi shape'):
        sosfilt_in_chunks(sos, x, n_chunks=10, zi=y)

    # Providing zi but with no output array for it
    with pytest.raises(ValueError, match='must be a tuple of two arrays'):
        sosfilt_in_chunks(sos, x, n_chunks=10, zi=zi, out=y)

    # Wrong zi output dimension
    with pytest.raises(ValueError, match='Invalid zi output array shape'):
        sosfilt_in_chunks(sos, x, n_chunks=10, zi=zi, out=(y, y))

    # Wrong output array shape
    with pytest.raises(ValueError, match='Output array must have shape'):
        sosfilt_in_chunks(sos, x, n_chunks=10, out=np.zeros((10, 100, 99)))

    # Providing zi but with an output array of wrong shape
    with pytest.raises(ValueError, match='Output array must have shape'):
        sosfilt_in_chunks(sos, x, n_chunks=10, zi=zi, out=(np.zeros((10, 100, 99)), zi))



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


def test_decimate_in_chunks_out():
    """Test the decimate_in_chunks function."""
    x = np.random.randn(10, 100, 1000)
    q = 10
    y = np.zeros((10, 100, 100))
    decimate_in_chunks(x, q, out=y)
    assert np.allclose(y, decimate(x, q))

    # Wrong output array shape
    with pytest.raises(ValueError, match='Output array must have shape'):
        decimate_in_chunks(x, 1, out=np.zeros((10, 100, 99)))
