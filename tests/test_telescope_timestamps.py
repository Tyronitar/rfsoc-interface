"""Tests of how telescope data is recorded: timestamps, failed reads and saving.

Each row of data should be timestamped when its position was read. The motors are
simulated with a fake clock. Commands take time, and the telescope moves throughout, so
a row's position only matches the true position at the row's timestamp if that timestamp
really is the time of the position read.
"""

# ruff: noqa: PLR2004

from unittest.mock import Mock, patch

import h5py
import numpy as np
import pytest

from rfsocinterface.core.telescope import TelescopeMotorController

ROW_LENGTH = 7
SPEED = 0.5  # deg / s
START_AZ = 5.0
START_ZA = 90.0
AZ_COMMAND_TIME = 6.5e-3  # Measured row times: 2 commands in about 13 ms
ZA_COMMAND_TIME = 8.5e-3  # Measured row times: 2 commands in about 17 ms
PPS_PERIOD = 0.2  # Faster than 1 Hz so that the short moves here read the latch


class FakeMotors:
    """Motors moving at a constant speed, with commands that take time to complete."""

    def __init__(self):
        """Start the clock and the telescope."""
        self.now = 1000.0
        self.start = self.now
        self.bad_replies = set()
        self.bad_reply = 'garbage'
        self.za_armed_at = self.now
        self.n_latch_reads = 0

    def az(self, t):
        """Return the true azimuth at time t."""
        return START_AZ + SPEED * (t - self.start)

    def za(self, t):
        """Return the true zenith angle at time t."""
        return START_ZA + SPEED * (t - self.start)

    def time(self):
        """Return the current time."""
        return self.now

    def sleep(self, duration):
        """Let time pass."""
        self.now += duration

    def _reply(self, command, value):
        return self.bad_reply if command in self.bad_replies else value

    def write_ser_az(self, command, timeout=None):  # noqa: ARG002
        """Answer an azimuth command, sampling the position halfway through it."""
        sample_time = self.now + AZ_COMMAND_TIME / 2
        self.now += AZ_COMMAND_TIME
        return self._reply(command, f'{self.az(sample_time) * 1e4:.6f}\r\n')

    def _latch_pending(self):
        return np.floor((self.now - self.start) / PPS_PERIOD) > np.floor(
            (self.za_armed_at - self.start) / PPS_PERIOD
        )

    def write_ser_za(self, command, timeout=None):  # noqa: ARG002
        """Answer a zenith angle command, sampling halfway through the position read."""
        sample_time = self.now + ZA_COMMAND_TIME / 2
        self.now += ZA_COMMAND_TIME
        match command:
            case 'CAP0.STATE':
                return self._reply(command, f'{int(self._latch_pending())} \r\n')
            case 'CAP0.EN 1':
                self.za_armed_at = self.now
                self.n_latch_reads += 1
                return '\r\n'
            case _:
                return self._reply(command, f'{self.za(sample_time):.6f} [deg]\r\n')


@pytest.fixture
def motors():
    """Replace the time module that the telescope code sees with the fake clock."""
    fake = FakeMotors()
    with patch('rfsocinterface.core.telescope.time', fake):
        yield fake


def _controller(motors):
    controller = TelescopeMotorController.__new__(TelescopeMotorController)
    controller._run = True  # noqa: SLF001
    controller._initialized = False  # noqa: SLF001
    controller.send = Mock()
    controller.set_ao_value = Mock()
    controller.ser_az = Mock(is_open=True)
    controller.write_ser_az = motors.write_ser_az
    controller.write_ser_za = motors.write_ser_za
    controller.az_pos = controller.az_pps_pos = START_AZ
    controller.za_pos = controller.za_pps_pos = START_ZA
    controller.az_pos_time = controller.za_pos_time = motors.now
    return controller


def _rows(position_data):
    return np.asarray(position_data).reshape(-1, ROW_LENGTH)


def test_azimuth_rows_are_timestamped_at_the_position_read(motors):
    """Every row of an azimuth move, including the first, has the right time."""
    controller = _controller(motors)
    rows = _rows(
        controller._set_az_pos(  # noqa: SLF001
            START_AZ + 0.5, stop_run=False, store_position_data=True
        )
    )
    assert rows.shape[0] > 10
    np.testing.assert_allclose(rows[:, 0], motors.az(rows[:, 2]), atol=1e-6)


def test_zenith_angle_rows_are_timestamped_at_the_position_read(motors):
    """Each zenith angle row has the right time, even with latch reads."""
    controller = _controller(motors)
    rows = _rows(
        controller._set_za_pos(  # noqa: SLF001
            START_ZA + 0.5, stop_run=False, store_position_data=True
        )
    )
    assert rows.shape[0] > 10
    assert motors.n_latch_reads > 0  # Rows that read the latch take twice as long
    assert rows[:, 5].sum() > 0
    np.testing.assert_allclose(rows[:, 1], motors.za(rows[:, 2]), atol=1e-6)


def test_row_timestamps_increase_across_moves(motors):
    """Time goes forward within a move and from one move to the next."""
    controller = _controller(motors)
    moves = [
        controller._set_az_pos(  # noqa: SLF001
            START_AZ + 0.5, stop_run=False, store_position_data=True
        ),
        controller._set_za_pos(  # noqa: SLF001
            START_ZA + 1.5, stop_run=False, store_position_data=True
        ),
        controller._set_az_pos(  # noqa: SLF001
            START_AZ + 3.0, stop_run=False, store_position_data=True
        ),
    ]
    rows = _rows(np.concatenate(moves))
    assert np.all(np.diff(rows[:, 2]) > 0)


def test_failed_azimuth_read_keeps_the_time_of_the_last_good_read(motors):
    """An old position isn't given a new time, so it isn't placed in the wrong spot."""
    controller = _controller(motors)
    pos, _ = controller.get_ser_az_pos()
    pos_time = controller.az_pos_time
    motors.sleep(1.0)

    motors.bad_replies.add('PFB')
    assert controller.get_ser_az_pos()[0] == pos
    assert controller.az_pos_time == pos_time

    motors.bad_replies.clear()
    assert controller.get_ser_az_pos()[0] > pos
    assert controller.az_pos_time > pos_time


def test_failed_zenith_angle_read_keeps_the_time_of_the_last_good_read(motors):
    """An old position isn't given a new time, so it isn't placed in the wrong spot."""
    controller = _controller(motors)
    pos, *_ = controller.get_ser_za_pos()
    pos_time = controller.za_pos_time
    motors.sleep(1.0)

    motors.bad_replies.add('PL.FB')
    assert controller.get_ser_za_pos()[0] == pos
    assert controller.za_pos_time == pos_time

    motors.bad_replies.clear()
    assert controller.get_ser_za_pos()[0] > pos
    assert controller.za_pos_time > pos_time


def _error_messages(controller):
    return [
        call.args[2] for call in controller.send.call_args_list if call.args[0] == 'err'
    ]


@pytest.mark.parametrize('bad_reply', ['garbage', '', '>'])
def test_za_move_survives_bad_latch_state_replies(motors, bad_reply):
    """A bad reply to the latch state query doesn't end the move or raise."""
    motors.bad_replies.add('CAP0.STATE')
    motors.bad_reply = bad_reply
    controller = _controller(motors)
    target = START_ZA + 0.5

    rows = _rows(
        controller._set_za_pos(  # noqa: SLF001
            target, stop_run=False, store_position_data=True
        )
    )

    assert rows[-1, 1] == pytest.approx(target, abs=0.05)
    assert rows[:, 5].sum() == 0  # Can't know that the latch was set
    assert motors.n_latch_reads == 0  # An unread latch isn't re-armed
    assert _error_messages(controller)


@pytest.mark.parametrize('bad_reply', ['garbage', '', '>'])
def test_za_move_survives_bad_latch_position_replies(motors, bad_reply):
    """A bad latched position keeps the old value and carries on with the move."""
    motors.bad_replies.add('CAP0.PLFB')
    motors.bad_reply = bad_reply
    controller = _controller(motors)
    target = START_ZA + 0.5

    rows = _rows(
        controller._set_za_pos(  # noqa: SLF001
            target, stop_run=False, store_position_data=True
        )
    )

    assert rows[-1, 1] == pytest.approx(target, abs=0.05)
    assert motors.n_latch_reads > 0
    np.testing.assert_array_equal(rows[:, 4], START_ZA)  # Latched value never updated
    assert _error_messages(controller)


def test_good_latched_position_is_recorded(motors):
    """The latched position is parsed from a normal reply."""
    controller = _controller(motors)
    rows = _rows(
        controller._set_za_pos(  # noqa: SLF001
            START_ZA + 0.5, stop_run=False, store_position_data=True
        )
    )
    assert np.unique(rows[:, 4]).size > 1
    assert not _error_messages(controller)


@pytest.mark.parametrize('command', ['PFB', 'LATCH1P32'])
def test_azimuth_error_messages_are_strings(motors, command):
    """The GUI is sent text, not a tuple."""
    motors.bad_replies.add(command)
    controller = _controller(motors)
    controller.get_ser_az_pos()
    messages = _error_messages(controller)
    assert messages
    assert all(isinstance(message, str) for message in messages)


@pytest.mark.parametrize('command', ['PL.FB', 'CAP0.STATE', 'CAP0.PLFB'])
def test_zenith_angle_error_messages_are_strings(motors, command):
    """The GUI is sent text, not a tuple."""
    motors.bad_replies.add(command)
    controller = _controller(motors)
    motors.now += 2 * PPS_PERIOD  # So that the latch is set
    controller.get_ser_za_pos()
    messages = _error_messages(controller)
    assert messages
    assert all(isinstance(message, str) for message in messages)


def test_stared_image_saves_all_datasets(motors, tmp_path):
    """A stared image is saved in full and reports that it succeeded."""
    file = tmp_path / 'azel.h5'
    controller = _controller(motors)

    controller._stared_image(str(file), 0.2)  # noqa: SLF001

    with h5py.File(file, 'r') as f:
        n_rows = f['az_tel'].size
        assert n_rows > 0
        for name in ('za_tel', 'timestamp_tel', 'az_pps', 'za_pps', 'za_pps_latch'):
            assert f[name].size == n_rows
        assert f['map_signal_mask'].dtype == bool
        assert f['map_signal_mask'][:].all()
        assert 'optical_visibility' in f
        assert 'params' in f.attrs
    controller.send.assert_any_call('stared_image_complete', 0)
