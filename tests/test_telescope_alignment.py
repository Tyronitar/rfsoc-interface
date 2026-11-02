"""Tests for PPS-based alignment of telescope positions to the RFSoC data.

These tests build a synthetic observation in which the true telescope trajectory and
the true relationship between the telescope and data clocks are known, then check that
:func:`align_telescope_positions` recovers them.

The simulation mimics how ``TelescopeMotorController._dither_pattern`` records data:

* Only the axis currently being driven is read each loop; the other axis keeps the
  stale value it had at the start of the move.
* Each axis' position is read slightly before/after the row timestamp is taken
  (``LATENCY``), and the latency differs between the axes.
* The AZ latch continuously holds the position at the most recent pulse, while the ZA
  latch holds the first pulse after it was last re-armed and is re-armed when read.
* Positions are quantized to the resolution the motors report (1e-4 deg for AZ,
  1e-3 deg for ZA).
* The telescope clock differs from the data clock by an offset, a drift, and a slow
  wander, like the host clock does in real data.

All times in the helper functions are on the *data* clock unless stated otherwise.
"""

# ruff: noqa: PLR2004

import numpy as np
import pytest

from rfsocinterface.core.data.utils import (
    align_telescope_positions,
    fit_data_pps_grid,
)

FS = 488.28125  # RFSoC sample rate (Hz)
T_START = 1.7e9 + 0.123  # Data clock start time (s)
DURATION = 150.0  # Length of the simulated observation (s)

# Host clock vs. data clock: data_time - tel_time = offset + drift + slow wander,
# similar to what is seen in real data (tens of ms over a few minutes).
OFFSET = 0.037  # Constant offset (s)
DRIFT = 2e-5  # Linear drift (s / s)
WANDER = 0.04  # Amplitude of the slow sinusoidal wander (s)
WANDER_PERIOD = 120.0  # Period of the wander (s)

# Time at which each axis' position is actually read, relative to the row timestamp.
# AZ is timestamped before its read (positive), ZA after its read (negative).
LATENCY = {'az': 0.004, 'za': -0.006}


def _clock_offset(t):
    """Return ``data_time - tel_time`` at data-clock time ``t``."""
    return (
        OFFSET
        + DRIFT * (t - T_START)
        + WANDER * np.sin(2 * np.pi * (t - T_START) / WANDER_PERIOD)
    )


def _ramp(t, t0, t1, p0, p1):
    """Return a smooth (cosine) move from ``p0`` to ``p1`` between ``t0`` and ``t1``.

    The position is held at ``p0`` before ``t0`` and at ``p1`` after ``t1``, and the
    velocity goes smoothly to zero at both ends, like a real motor move.
    """
    s = np.clip((t - t0) / (t1 - t0), 0, 1)
    return p0 + (p1 - p0) * (1 - np.cos(np.pi * s)) / 2


def _segments():
    """Return the moves making up the simulated observation.

    The pattern is a dither in AZ with ZA steps in between (one axis moving at a
    time, as in a typical map), followed by one diagonal move where both axes move
    simultaneously.

    Returns:
        list[tuple]: ``(start, stop, active_axes, az_target, za_target)`` for each
            move, with ``start`` and ``stop`` in data-clock time. ``active_axes`` are
            the axes being driven (and therefore read) during the move.
    """
    segs = []
    t, az, za = T_START + 2.0, 0.0, 88.0
    for i in range(8):
        # Primary AZ sweep, alternating direction
        az_new = 4.0 if i % 2 == 0 else 0.0
        segs.append((t, t + 8.0, ('az',), az_new, za))
        t, az = t + 8.4, az_new
        # Secondary ZA step
        segs.append((t, t + 1.5, ('za',), az, za + 0.03))
        t, za = t + 1.9, za + 0.03
    # Simultaneous (diagonal) motion
    segs.append((t, t + 10.0, ('az', 'za'), az + 3.0, za + 1.0))
    return segs


def _true_position(t):
    """Return the true ``(az, za)`` of the telescope at data-clock times ``t``."""
    az = np.zeros_like(t)
    za = np.full_like(t, 88.0)
    # Apply each move in order; later moves override earlier ones from their start
    for t0, t1, _, az_new, za_new in _segments():
        az = np.where(t >= t0, _ramp(t, t0, t1, _az_at(t0), az_new), az)
        za = np.where(t >= t0, _ramp(t, t0, t1, _za_at(t0), za_new), za)
    return az, za


def _az_at(t0):
    """Return the AZ target of the last move starting before ``t0`` (start of move)."""
    az = 0.0
    for s0, _, _, az_new, _ in _segments():
        if s0 < t0:
            az = az_new
    return az


def _za_at(t0):
    """Return the ZA target of the last move starting before ``t0`` (start of move)."""
    za = 88.0
    for s0, _, _, _, za_new in _segments():
        if s0 < t0:
            za = za_new
    return za


def _simulate_telescope(rng):
    """Simulate the rows written by ``TelescopeMotorController._dither_pattern``.

    Arguments:
        rng (np.random.Generator): Random generator for the row timing jitter.

    Returns:
        tuple[dict, np.ndarray]: The telescope rows (``t`` on the telescope clock,
            ``az``, ``za``, ``az_pps``, ``za_pps``) and the true PPS pulse times on
            the data clock.
    """
    # True pulse times on the data clock (arbitrary phase within the second)
    pulses = T_START + 0.4321 + np.arange(DURATION + 2)
    rows = {k: [] for k in ('t', 'az', 'za', 'az_pps', 'za_pps')}
    # Last value read for each axis; reused while the axis is not being driven
    stale = {'az': 0.0, 'za': 88.0}
    # Last latch value read for each axis
    latch = {'az': 0.0, 'za': 0.0}
    za_armed_at = T_START  # ZA latch is re-armed after each successful read
    za_latched = None  # Value captured by the ZA latch but not yet read
    for t0, t1, active, _, _ in _segments():
        t = t0
        # Keep logging a little past the end of the move, like the motor loop does
        # while it settles into tolerance
        while t < t1 + 0.3:
            # ~77 Hz loop with jitter, similar to the real telescope loop
            t += 0.013 + rng.uniform(-0.003, 0.003)

            # Positions: fresh read for driven axes, stale value for the others
            pos = {}
            for ax in ('az', 'za'):
                if ax in active:
                    az_true, za_true = _true_position(np.array([t + LATENCY[ax]]))
                    pos[ax] = float({'az': az_true, 'za': za_true}[ax][0])
                    stale[ax] = pos[ax]
                else:
                    pos[ax] = stale[ax]

            # AZ latch: continuously latches the position at the last pulse, and is
            # only read while AZ is being driven
            if 'az' in active:
                last = pulses[pulses <= t][-1]
                latch['az'] = float(np.round(_true_position(np.array([last]))[0][0], 4))

            # ZA latch: captures the first pulse after re-arming and holds it until
            # read. It is only polled (and re-armed) while ZA is being driven, so the
            # first read of a new ZA move can return a value latched long ago.
            if 'za' in active:
                if za_latched is None:
                    after = pulses[pulses > za_armed_at]
                    if after.size and after[0] <= t:
                        za_latched = float(
                            np.round(_true_position(np.array([after[0]]))[1][0], 3)
                        )
                if za_latched is not None:
                    latch['za'] = za_latched
                    za_latched = None
                    za_armed_at = t

            # Record the row with a telescope-clock timestamp and the motors'
            # reported resolution
            tel_time = t - _clock_offset(t)
            rows['t'].append(tel_time)
            rows['az'].append(np.round(pos['az'], 4))
            rows['za'].append(np.round(pos['za'], 3))
            rows['az_pps'].append(latch['az'])
            rows['za_pps'].append(latch['za'])
    return {k: np.asarray(v) for k, v in rows.items()}, pulses


@pytest.fixture
def simulation():
    """Return a simulated observation: data timestamps, data PPS, telescope rows.

    The data PPS has a few pulses removed (as if their packets were dropped) and one
    spurious pulse added, to check that the PPS grid fit is robust to both.
    """
    rng = np.random.default_rng(1234)
    tel, pulses = _simulate_telescope(rng)
    # Equally spaced data timestamps, as produced by interpolate_timestamp_streaming
    data_t = T_START + np.arange(int(DURATION * FS)) / FS
    # Mark the sample in which each pulse arrives
    pps = np.zeros(data_t.size, dtype=np.uint8)
    idx = np.searchsorted(data_t, pulses)
    idx = idx[idx < data_t.size]
    pps[idx] = 1
    pps[idx[[5, 6, 40]]] = 0  # Dropped packets
    pps[idx[20] + 100] = 1  # Spurious pulse ~0.2 s after a real one
    return data_t, pps, tel


@pytest.mark.slow
def test_data_pps_grid_handles_missing_and_spurious_pulses(simulation):
    """The data PPS grid ignores dropped and spurious pulses.

    The fitted period should be 1 s and pulse 0 should land on the first true pulse
    to within the sample quantization.
    """
    data_t, pps, _ = simulation
    grid = fit_data_pps_grid(data_t, pps)
    assert grid is not None
    assert grid.b == pytest.approx(1.0, abs=1e-4)
    true_first = T_START + 0.4321
    assert grid.time(0) == pytest.approx(true_first, abs=1.5 / FS)


@pytest.mark.slow
def test_alignment_recovers_positions(simulation):
    """The aligned positions match the true trajectory on the data clock."""
    data_t, pps, tel = simulation
    res = align_telescope_positions(
        data_t, pps, tel['t'], tel['az'], tel['za'], tel['az_pps'], tel['za_pps']
    )
    assert res.aligned
    # Pulse times agree with the clock model to within ~ms
    assert res.info['rms_residual'] < 2e-3

    az_true, za_true = _true_position(data_t)
    valid = ~np.isnan(res.az)
    # Positions agree to within a few ms of motion at the max speed (~0.8 deg/s)
    assert np.nanmax(np.abs(res.az - az_true)[valid]) < 5e-3
    assert np.nanmax(np.abs(res.za - za_true)[valid]) < 5e-3

    # Sanity check that the test is meaningful: without alignment the error is
    # dominated by the clock offset and is much larger
    plain_az = np.interp(data_t, tel['t'], tel['az'])
    assert np.max(np.abs(plain_az - az_true)[valid]) > 2e-2


@pytest.mark.slow
def test_single_axis_motion_is_preserved(simulation):
    """Alignment does not introduce motion on an axis that is not moving.

    During each single-axis move, the other axis must be exactly constant in the
    output (the old algorithm shifted the axes independently and created spurious
    simultaneous motion). Genuine simultaneous motion must still be kept.
    """
    data_t, pps, tel = simulation
    res = align_telescope_positions(
        data_t, pps, tel['t'], tel['az'], tel['za'], tel['az_pps'], tel['za_pps']
    )
    segs = _segments()
    for t0, t1, active, _, _ in segs[:-1]:
        # Stay a little away from the move boundaries, where the axis constants
        # (a few ms) and the row spacing legitimately blur the transition
        inside = (data_t > t0 + 0.05) & (data_t < t1 - 0.05)
        still = 'za' if active == ('az',) else 'az'
        values = {'az': res.az, 'za': res.za}[still][inside]
        assert np.ptp(values) == 0, f'{still} moved during a {active} move'

    # The diagonal segment keeps moving on both axes
    t0, t1, *_ = segs[-1]
    inside = (data_t > t0 + 1) & (data_t < t1 - 1)
    assert np.all(np.diff(res.az[inside]) > 0)
    assert np.ptp(res.za[inside]) > 0.5


@pytest.mark.slow
def test_falls_back_without_pps(simulation):
    """Without any data PPS pulses, the raw telescope timestamps are used."""
    data_t, _, tel = simulation
    res = align_telescope_positions(
        data_t,
        np.zeros(data_t.size, dtype=np.uint8),  # No pulses in the data
        tel['t'],
        tel['az'],
        tel['za'],
        tel['az_pps'],
        tel['za_pps'],
        drop_latch_rows=False,  # Keep every row so the result is plain interpolation
    )
    assert not res.aligned
    expected = np.interp(data_t, tel['t'], tel['az'], left=np.nan, right=np.nan)
    np.testing.assert_array_equal(res.az, expected)


@pytest.mark.slow
def test_stationary_latches_are_ignored(simulation):
    """A telescope that never moves gives no usable pulses; nothing should break.

    The single AZ latch change equals the (constant) current position, like a stale
    latch read at the start of a move, so it must not be used as a pulse.
    """
    data_t, pps, tel = simulation
    n = tel['t'].size
    res = align_telescope_positions(
        data_t,
        pps,
        tel['t'],
        np.full(n, 5.0),  # AZ never moves
        np.full(n, 88.0),  # ZA never moves
        np.r_[np.zeros(n // 2), np.full(n - n // 2, 5.0)],  # One stale latch change
        np.full(n, 88.0),
    )
    assert not res.aligned
    assert np.all(res.az[~np.isnan(res.az)] == 5.0)
