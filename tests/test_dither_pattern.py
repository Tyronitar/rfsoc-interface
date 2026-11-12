"""Tests for the sequence of moves made by the telescope's dither pattern."""

from unittest.mock import Mock

import h5py
import numpy as np
import pytest

from rfsocinterface.core.telescope import TelescopeMotorController

INITIAL_AZ = 5.0
INITIAL_ZA = 90.0
START = -2.0  # Relative to the initial position of the primary axis
STOP = 2.0
OVERSCAN = 0.5  # Distance scanned past the requested primary range
DITHER = 0.03


def _run_dither(file, primary, n_repeats, large_map_mode):
    """Run a dither pattern with the motors mocked, returning the moves it made.

    Returns:
        list[tuple[str, float, bool]]: The axis, target and signal flag of each move
            made during the pattern, excluding the moves back to the initial position.
    """
    moves = []

    def move(axis):
        def _move(
            new_pos, *_args, store_position_data=False, is_signal=True, **_kwargs
        ):
            if not store_position_data:  # Returning to the initial position
                return None
            moves.append((axis, float(new_pos), is_signal))
            az, za = (new_pos, INITIAL_ZA) if axis == 'az' else (INITIAL_AZ, new_pos)
            return np.array([az, za, 0.0, 0.0, 0.0, 0.0, float(is_signal)])

        return _move

    controller = TelescopeMotorController.__new__(TelescopeMotorController)
    controller._run = True  # noqa: SLF001
    controller.send = Mock()
    controller.set_za_speed_relation = Mock()
    controller.get_ser_az_pos = Mock(return_value=(INITIAL_AZ, 0.0))
    controller.get_ser_za_pos = Mock(return_value=(INITIAL_ZA, 0.0, 0.0))
    controller._set_az_pos = move('az')  # noqa: SLF001
    controller._set_za_pos = move('za')  # noqa: SLF001

    controller._dither_pattern(  # noqa: SLF001
        str(file),
        START,
        STOP,
        n_repeats=n_repeats,
        secondary_dither=DITHER,
        large_map_mode=large_map_mode,
        primary_dither_direction=primary,
    )
    return moves


@pytest.mark.parametrize(
    'primary, secondary',
    [('az', 'za'), ('za', 'az'), ('AZ', 'za'), ('ZA', 'az')],
)
@pytest.mark.parametrize('large_map_mode', [True, False])
def test_secondary_moves_are_on_the_other_axis(
    tmp_path, primary, secondary, large_map_mode
):
    """Signal scans are on the primary axis and row steps on the secondary axis."""
    moves = _run_dither(tmp_path / 'azel.h5', primary, 4, large_map_mode)

    # The move to the start position, then a row step and a scan for each repeat
    assert len(moves) == 1 + 2 * 4
    assert moves[0][0] == primary.lower()
    assert all(axis == secondary and not signal for axis, _, signal in moves[1::2])
    assert all(axis == primary.lower() and signal for axis, _, signal in moves[2::2])


@pytest.mark.parametrize('primary', ['az', 'za'])
def test_large_map_rows_step_across_the_secondary_axis(tmp_path, primary):
    """Rows are evenly spaced and centered on the initial secondary position."""
    moves = _run_dither(tmp_path / 'azel.h5', primary, 5, large_map_mode=True)
    center = INITIAL_ZA if primary == 'az' else INITIAL_AZ
    rows = [target for _, target, _ in moves[1::2]]
    np.testing.assert_allclose(rows, center + np.arange(-2, 3) * DITHER)


@pytest.mark.parametrize('primary', ['az', 'za'])
def test_small_map_rows_alternate_on_the_secondary_axis(tmp_path, primary):
    """Without large map mode, the secondary axis oscillates between two positions."""
    moves = _run_dither(tmp_path / 'azel.h5', primary, 4, large_map_mode=False)
    center = INITIAL_ZA if primary == 'az' else INITIAL_AZ
    rows = [target for _, target, _ in moves[1::2]]
    np.testing.assert_allclose(rows, center + np.array([0, 1, 0, 1]) * DITHER)


@pytest.mark.parametrize('primary', ['az', 'za'])
@pytest.mark.parametrize('large_map_mode', [True, False])
def test_scans_cover_the_same_range_in_both_directions(
    tmp_path, primary, large_map_mode
):
    """Opposite scans go between the same two points, so that they overlap."""
    moves = _run_dither(tmp_path / 'azel.h5', primary, 4, large_map_mode)
    center = INITIAL_AZ if primary == 'az' else INITIAL_ZA
    low = center + START - OVERSCAN
    high = center + STOP + OVERSCAN
    scans = [target for _, target, _ in moves[2::2]]
    np.testing.assert_allclose(scans, [high, low, high, low])


def test_positions_are_saved(tmp_path):
    """The rows of the position data end up in the right datasets."""
    file = tmp_path / 'azel.h5'
    moves = _run_dither(file, 'za', 2, large_map_mode=True)
    with h5py.File(file, 'r') as f:
        assert f['az_tel'].size == len(moves)
        np.testing.assert_array_equal(
            f['map_signal_mask'][:], [signal for _, _, signal in moves]
        )
