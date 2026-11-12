"""Tests for logging and saving the statistics of the telescope alignment."""

# ruff: noqa: PLR2004

import json
import logging

import h5py
import numpy as np
import pytest

from rfsocinterface.core.data.storage import DataStorage, store_telescope_alignment
from rfsocinterface.core.data.utils import (
    align_telescope_positions,
    summarize_alignment,
)
from rfsocinterface.core.utils import DEFAULT_DATA_DIRECTORY

from .test_telescope_alignment import OFFSET, simulation  # noqa: F401


class Storage(DataStorage):
    """A DataStorage that can be opened from a file name."""

    @staticmethod
    def get_template(date, setnum, data_dir=DEFAULT_DATA_DIRECTORY):  # noqa: D102
        return f'{date}-{setnum}-{data_dir}'


def _align(simulation):  # noqa: F811
    data_t, pps, tel = simulation
    return align_telescope_positions(
        data_t, pps, tel['t'], tel['az'], tel['za'], tel['az_pps'], tel['za_pps']
    )


def _storage_with_channel(path):
    """Create a file with one channel group, as written by ConsolidatedData."""
    with h5py.File(path, 'w') as f:
        f.create_group('channels/channel_000')
    return Storage(str(path), mode='a')


@pytest.mark.slow
def test_log_line_includes_per_axis_offsets(simulation, caplog):  # noqa: F811
    """The log shows each axis' mean offset, range, residual and pulse counts."""
    with caplog.at_level(logging.INFO, logger='rfsocinterface.core.data.utils'):
        result = _align(simulation)
    message = next(r.message for r in caplog.records if 'Clock offset' in r.message)

    for axis in ('az', 'za'):
        stats = result.info['axis_stats'][axis]
        assert f'{axis.upper()}: mean {stats["mean_offset"] * 1e3:+.2f} ms' in message
        assert f'{stats["n_used"]}/{stats["n_pulses"]} pulses used' in message


@pytest.mark.slow
def test_summary_statistics(simulation):  # noqa: F811
    """The summary matches the pulses and can be saved as JSON."""
    result = _align(simulation)
    summary = summarize_alignment(result)
    assert json.loads(json.dumps(summary)) == summary

    info = result.info
    for axis in ('az', 'za'):
        used = info['pulse_inliers'] & (info['pulse_axes'] == axis)
        stats = summary['axes'][axis]
        assert stats['n_used'] == used.sum()
        assert stats['mean_offset'] == pytest.approx(info['pulse_offsets'][used].mean())
        assert stats['min_offset'] <= stats['mean_offset'] <= stats['max_offset']
    # The simulated clocks differ by about OFFSET, plus a drift and a slow wander
    assert summary['axes']['az']['mean_offset'] == pytest.approx(OFFSET, abs=0.03)
    assert summary['data_pps']['period'] == pytest.approx(1.0, abs=1e-4)


def test_summary_without_pps():
    """Without a PPS, the summary says so and has no fitted statistics."""
    data_t = np.arange(1000) / 488.0
    tel_t = np.arange(0, 2, 0.013)
    result = align_telescope_positions(
        data_t,
        np.zeros(data_t.size, dtype=np.uint8),
        tel_t,
        np.ones(tel_t.size),
        np.ones(tel_t.size),
        np.zeros(tel_t.size),
        np.zeros(tel_t.size),
    )
    summary = summarize_alignment(result)
    assert summary['aligned'] is False
    assert summary['axes'] is None
    assert summary['data_pps'] is None
    json.dumps(summary)


@pytest.mark.slow
def test_alignment_round_trip(simulation, tmp_path):  # noqa: F811
    """Statistics saved in a file are read back unchanged."""
    result = _align(simulation)
    storage = _storage_with_channel(tmp_path / 'data.h5')
    store_telescope_alignment(storage.get_channel_group(0), result, note='test')

    saved = storage.get_telescope_alignment(0)
    summary = summarize_alignment(result)
    for key, value in summary.items():
        assert saved[key] == value
    assert saved['note'] == 'test'
    assert saved['code_version']
    np.testing.assert_array_equal(saved['pulses']['time'], result.info['pulse_times'])
    np.testing.assert_array_equal(saved['pulses']['axis'], result.info['pulse_axes'])
    np.testing.assert_array_equal(saved['pulses']['used'], result.info['pulse_inliers'])
    np.testing.assert_array_equal(
        saved['clock_model']['values'], result.info['clock_model'].values
    )

    # Storing again replaces the old statistics
    store_telescope_alignment(storage.get_channel_group(0), None)
    assert storage.get_telescope_alignment(0)['aligned'] is False
    assert 'pulses' not in storage.get_telescope_alignment(0)
    storage.close()


def test_older_files_return_none(tmp_path):
    """Files written before these statistics were saved return None."""
    storage = _storage_with_channel(tmp_path / 'old.h5')
    assert storage.get_telescope_alignment(0) is None
    assert storage.get_n_missed_packets(0) is None

    storage.get_channel_group(0).attrs['n_missed_packets'] = np.int64(7)
    assert storage.get_n_missed_packets(0) == 7
    storage.close()
