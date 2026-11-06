"""Tests for fitting beams to maps, in particular maps with empty pixels."""

from types import SimpleNamespace
from unittest.mock import patch

import h5py
import numpy as np
import pytest
from packaging.version import Version

from rfsocinterface.analysis.beammap import AnalyzeBeamMap, gauss_2d

FWHM_AZ = 0.10
FWHM_ZA = 0.08
AMPLITUDE = 5e-6
ROW_SPACING = 0.03  # Spacing between the scans in ZA


class FakeProcessedData:
    """The parts of ProcessedData that AnalyzeBeamMap uses, held in memory."""

    def __init__(self, map_val, map_az, map_za):
        """Store the maps of shape (n_tones, n_za, n_az) in an in-memory file."""
        self.file = h5py.File(f'{id(self)}.h5', 'w', driver='core', backing_store=False)
        map_group = self.file.create_group('map')
        map_group.create_dataset('map_val', data=map_val)
        map_group.create_dataset('channel_map_val', data=map_val[np.newaxis])
        map_group.create_dataset('map_az', data=map_az)
        map_group.create_dataset('map_za', data=map_za)
        self.total_tones = map_val.shape[0]
        self.onres_ind = np.arange(self.total_tones)

    def __getitem__(self, key):
        """Return the group or dataset called key."""
        return self.file[key]

    def __contains__(self, key):
        """Return whether key is in the file."""
        return key in self.file

    def has(self, key, exact_match=False):  # noqa: ARG002
        """Return whether key is in the file."""
        return key in self.file

    def create_group(self, name):
        """Create a group in the file."""
        return self.file.create_group(name)

    def find_most_recent_history_step(self, _pattern):
        """Return a history step for a map that doesn't need its axes swapped."""
        return 'BinTODIntoMap', SimpleNamespace(attrs={'version': '"4.2.0"'})

    def get_version(self):
        """Return a version for a map that doesn't need its axes swapped."""
        return Version('2.0.0')


def _make_map(dpix, row_spacing, az_center=7.0, za_center=90.0, noise=0.02, seed=0):
    """Bin a Gaussian beam, scanned in rows along AZ, into a map.

    Pixels that no scan passes through are NaN, as in BinTODIntoMap. When the pixels
    are smaller than the row spacing, this leaves rows of the map empty.

    Returns:
        (tuple): The map, its AZ axis and its ZA axis.
    """
    rng = np.random.default_rng(seed)
    map_az = np.arange(6.5, 7.5, dpix)
    map_za = np.arange(89.5, 90.5, dpix)
    sum_map = np.zeros((map_za.size, map_az.size))
    hits = np.zeros_like(sum_map)
    for row_za in np.arange(89.5, 90.5, row_spacing):
        y_ind = int(np.round((row_za - map_za[0]) / dpix))
        if y_ind >= map_za.size:
            continue
        values = gauss_2d(
            (map_az, row_za), AMPLITUDE, az_center, za_center, FWHM_AZ, FWHM_ZA, 0.0
        )
        sum_map[y_ind] += values + rng.normal(0, noise * AMPLITUDE, map_az.size)
        hits[y_ind] += 1
    with np.errstate(invalid='ignore'):
        return sum_map / hits, map_az, map_za


def _analyze(maps, map_az, map_za, **kwargs):
    """Run AnalyzeBeamMap on the maps and return its results."""
    pdata = FakeProcessedData(np.stack(maps), map_az, map_za)
    routine = AnalyzeBeamMap(**kwargs)
    routine._run(pdata, [])  # noqa: SLF001
    return {name: pdata[f'beammap/{name}'][:] for name in pdata['beammap']}


@pytest.mark.parametrize('dpix', [0.01, 0.02, 0.03, 0.04])
def test_beam_recovered_at_any_pixel_size(dpix):
    """The fit doesn't depend on whether the pixels leave rows of the map empty."""
    # Move the beam relative to the rows, since the bad fits depend on where it falls
    za_centers = 90.0 + np.linspace(0, ROW_SPACING, 7)
    maps = []
    for i, za_center in enumerate(za_centers):
        maps.append(_make_map(dpix, ROW_SPACING, za_center=za_center, seed=i)[0])
    map_az, map_za = _make_map(dpix, ROW_SPACING)[1:]

    result = _analyze(maps, map_az, map_za)

    np.testing.assert_allclose(result['fwhm_za'], FWHM_ZA, rtol=0.25)
    np.testing.assert_allclose(result['fwhm_az'], FWHM_AZ, rtol=0.25)
    np.testing.assert_allclose(result['amplitude'], AMPLITUDE, rtol=0.25)
    np.testing.assert_allclose(result['az_center'], 7.0, atol=0.02)
    np.testing.assert_allclose(result['za_center'], za_centers, atol=0.02)


def test_empty_pixels_are_excluded_from_chi_squared():
    """Empty pixels are not part of the goodness of fit."""
    sparse = _analyze(
        [_make_map(0.02, ROW_SPACING)[0]], *_make_map(0.02, ROW_SPACING)[1:]
    )
    assert sparse['chisq'][0] < 1


def test_map_without_any_data_is_skipped():
    """A completely empty map doesn't stop the other tones from being fitted."""
    good, map_az, map_za = _make_map(0.03, ROW_SPACING)
    empty = np.full_like(good, np.nan)

    result = _analyze([empty, good], map_az, map_za)

    assert result['fwhm_za'][0] == 0
    assert np.isfinite(result['az_center'][0])
    assert result['fwhm_za'][1] == pytest.approx(FWHM_ZA, rel=0.25)


def test_too_few_pixels_to_fit_is_skipped():
    """A window with fewer pixels than fit parameters isn't fitted."""
    good, map_az, map_za = _make_map(0.03, ROW_SPACING)
    sparse = np.full_like(good, np.nan)
    sparse[10, 10:13] = good[10, 10:13]

    result = _analyze([sparse, good], map_az, map_za)

    assert result['fwhm_za'][0] == 0
    assert result['fwhm_za'][1] == pytest.approx(FWHM_ZA, rel=0.25)


def test_failed_fit_keeps_the_peak_pixel_as_amplitude():
    """If the fit fails, the amplitude is the brightest pixel in the fit window."""
    good, map_az, map_za = _make_map(0.03, ROW_SPACING)
    with patch(
        'rfsocinterface.analysis.beammap.curve_fit', side_effect=RuntimeError('no fit')
    ):
        result = _analyze([good], map_az, map_za)
    assert result['amplitude'][0] == pytest.approx(np.nanmax(good))
