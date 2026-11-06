"""Tests for decimating data without shifting it relative to the telescope positions."""

# ruff: noqa: PLR2004

import h5py
import numpy as np
import pytest
from scipy.signal import sosfiltfilt

from rfsocinterface.core.utils import (
    _decimation_filter,
    chunked_downsample,
    decimate_in_chunks,
)

FS = 488.28125
Q = 10
CHUNK_SIZE = 1024


def _decimate(x, q=Q, chunk_size=CHUNK_SIZE):
    """Run decimate_in_chunks on an (n_tones, n_samples) array."""
    n_out = int(np.ceil(x.shape[-1] / q))
    with h5py.File('decimate.h5', 'w', driver='core', backing_store=False) as f:
        dset = f.create_dataset(
            'in', data=x, chunks=(x.shape[0], min(chunk_size, x.shape[-1]))
        )
        out = f.create_dataset('out', shape=(x.shape[0], n_out), dtype='f8')
        decimate_in_chunks(dset, out, q, chunk_shape=dset.chunks)
        return out[:]


def _downsampled_times(t, q=Q, chunk_size=CHUNK_SIZE):
    """Downsample timestamps in the way that ConsolidatedData does."""
    n_out = int(np.ceil(t.size / q))
    with h5py.File('times.h5', 'w', driver='core', backing_store=False) as f:
        dset = f.create_dataset('in', data=t, chunks=(chunk_size,))
        out = f.create_dataset('out', shape=(n_out,), dtype='f8')
        chunked_downsample(dset, out, q, chunk_size, use_filter=False)
        return out[:]


@pytest.mark.parametrize('fwhm', [0.07, 0.2, 0.5])
def test_no_time_shift_relative_to_downsampled_timestamps(fwhm):
    """A pulse stays at the same time, whichever scan speed produced its width."""
    t = np.arange(2**16) / FS
    centers = np.arange(5, t[-1] - 5, 3.1)
    sigma = fwhm / 2.355
    x = np.exp(-0.5 * ((t[:, None] - centers[None, :]) / sigma) ** 2).sum(axis=1)

    y = _decimate(x[None, :])[0]
    t_out = _downsampled_times(t)

    centroids = []
    for center in centers:
        near = np.abs(t_out - center) < 4 * sigma
        centroids.append(np.sum(t_out[near] * y[near]) / np.sum(y[near]) - center)
    assert np.abs(centroids).max() < 1e-4  # 0.1 ms


def test_chunks_join_seamlessly():
    """The result does not depend on how the data is divided into chunks."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=(3, 20000))
    expected = sosfiltfilt(_decimation_filter(Q)[0], x, axis=-1)[..., ::Q]

    for chunk_size in (300, 1024, 5000):
        y = _decimate(x, chunk_size=chunk_size)
        np.testing.assert_allclose(y, expected, atol=1e-3)


def test_unit_gain_in_the_passband_and_rejects_aliases():
    """Slow signals keep their amplitude and those above the new Nyquist are removed."""
    t = np.arange(2**15) / FS
    new_nyquist = FS / Q / 2
    middle = slice(100, -100)

    constant = _decimate(np.full((1, t.size), 3.0))[0]
    np.testing.assert_allclose(constant, 3.0, rtol=1e-6)

    slow = _decimate(np.sin(2 * np.pi * 1.0 * t)[None, :])[0]
    assert np.ptp(slow[middle]) == pytest.approx(2.0, rel=1e-2)

    fast = _decimate(np.sin(2 * np.pi * 1.5 * new_nyquist * t)[None, :])[0]
    assert np.abs(fast[middle]).max() < 1e-3


@pytest.mark.parametrize('n', [9, 10, 11, 1000, 1024, 1025, 2048])
def test_every_output_sample_is_written(n):
    """All output samples are filled, however the length divides into chunks."""
    y = _decimate(np.ones((1, n)))
    assert y.shape[-1] == int(np.ceil(n / Q))
    np.testing.assert_allclose(y, 1.0, rtol=1e-6)


def test_nan_does_not_spread_through_the_rest_of_the_data():
    """A bad sample only affects the chunks that can see it."""
    x = np.ones((1, 40000))
    x[0, 2000] = np.nan
    y = _decimate(x)[0]
    assert np.isnan(y).any()
    assert np.isfinite(y[1000:]).all()


def test_no_decimation_copies_the_data():
    """A factor of 1 leaves the data untouched."""
    x = np.random.default_rng(1).normal(size=(2, 3000))
    np.testing.assert_array_equal(_decimate(x, q=1), x)
