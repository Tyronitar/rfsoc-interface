"""
Headless (non-GUI) automated data collection.

This mirrors the setup -> check -> capture -> teardown flow used by
DataCollectionMainWidget in the GUI, but is driven directly by
(rfsoc, channel) pairs instead of a CheckableComboBox, and replaces the
QMessageBox LO-sweep confirmation with a `force` flag + logging, so it can
run unattended (cron job, CLI script, etc.) with no Qt event loop required.
"""
from __future__ import annotations

import logging
from pathlib import Path

from kidpy3.data_handler import Rfchan
from kidpy3 import capture

from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.settings import Settings
from rfsocinterface.core.sweeps import LoSweep, LoSweepData
from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW
import time
import numpy as np
import h5py
import pdb
_logger = logging.getLogger(__name__)


class AutomatedDataCollector:
    """Headless equivalent of DataCollectionMainWidget.

    Parameters
    ----------
    rfsocs_and_channels : list of (RFSOCWrapper, channel) pairs to collect
        from. This replaces the GUI's checkable combo-box channel selection.
    """

    def __init__(self, rfsocs_and_channels: list[tuple[RFSOCWrapper, int]]):
        self.rfsocs_and_channels = rfsocs_and_channels

    def setup_data_collection(self) -> tuple[list[RFSOCWrapper], list[int], list[Rfchan], str, int]:
        rfsocs: list[RFSOCWrapper] = []
        channels: list[int] = []
        rfchans: list[Rfchan] = []
        save_location: Path | None = None

        for rfsoc, chan in self.rfsocs_and_channels:
            rfsocs.append(rfsoc)
            channels.append(chan)
            rfchan = rfsoc.get_channel(chan)
            save_location = get_filename(
                file_type='tod', tile_name=rfchan.tile_name, mkdir=True
            ).with_suffix('.h5')
            rfchan.raw_filename = str(save_location)
            rfchan = rfsoc.get_channel(chan)
            rfchans.append(rfchan)
        if save_location is None:
            raise ValueError('No (rfsoc, channel) pairs were provided to collect from.')

        date = save_location.stem[:8]
        setnum = int(save_location.stem[-4:])
        return rfsocs, channels, rfchans, date, setnum, save_location

    def append_global_data(self, rfsocs: list[RFSOCWrapper], channels: list[int], rfchans: list[Rfchan]):
        """Append global data for each selected channel."""
        for rfsoc, channel, rfchan in zip(rfsocs, channels, rfchans):
            rfsoc.append_global_data(channel, rfchan.raw_filename)

    def remove_TOD_files(self, rfchans: list[Rfchan]):
        """Remove TOD files in case of collection cancellation after setup."""
        for rfchan in rfchans:
            Path(rfchan.raw_filename).unlink(missing_ok=True)

    def check_for_lo_sweep(
        self,
        rfsocs: list[RFSOCWrapper],
        channels: list[int],
        force: bool = False,
    ) -> bool:
        """
        Verify every channel has a recent LO sweep on file.

        The GUI pops a QMessageBox to ask whether to proceed without one;
        headless there's nothing to click, so this instead logs a warning
        and either aborts (force=False, the safe default) or proceeds
        anyway (force=True) -- decide up front rather than being prompted
        mid-run.
        """
        all_ok = True
        for rfsoc, channel in zip(rfsocs, channels):
            tile_name = rfsoc.get_tile_name(channel)
            sweep = LoSweepData.load_most_recent(tile_name)
            if sweep is None:
                msg = (
                    f'No high-res LO Sweeps have been performed today for '
                    f'"{tile_name}". A missing LO sweep may cause issues for '
                    f'data processing later.'
                )
                if force:
                    _logger.warning(f'{msg} Proceeding anyway (force=True).')
                else:
                    _logger.error(f'{msg} Aborting (pass force=True to proceed anyway).')
                    all_ok = False
        return all_ok

    def start_streaming(self, duration: int = 100, force: bool = False):
        """Set up capture, stream `duration` seconds of data, and tear down."""
        rfsocs, channels, rfchans, date, setnum, save_file = self.setup_data_collection()

        if not self.check_for_lo_sweep(rfsocs, channels, force=force):
            self.remove_TOD_files(rfchans)
            _logger.error('Aborting data collection: LO sweep check failed.')
            return

        _logger.debug(
            f'Streaming {duration} seconds of data for chans: '
            f'{[rfchan.tile_name for rfchan in rfchans]}'
        )
        capture(rfchans, time.sleep, duration)
        _logger.info('Completed data streaming')

        self.append_global_data(rfsocs, channels, rfchans)
        return save_file

    @staticmethod
    def _on_capture_progress(remaining: float):
        """
        Headless stand-in for the GUI's wait_for_TOD progress callback.

        NOTE: I inferred this callback's signature (seconds remaining) from
        context -- double check it against capture()'s actual expected
        callback signature and adjust if it differs.
        """
        _logger.debug(f'{remaining:.1f}s remaining...')


def run_lo_sweep(
    rfsoc: RFSOCWrapper,
    tile_name: str,
    chan: int = 1,
    step: float = 5e3,
    span: float = 200e3,
    tone_shift: float = 0,
    filename_suffix: str | None = None,
) -> Path:
    """Run and save a single LO sweep."""
    sweep_file = get_filename(
        file_type='lo', tile_name=tile_name, mkdir=True, filename_suffix=filename_suffix
    ).with_suffix('.h5')

    sweep = LoSweep(
        rfsoc=rfsoc,
        chan=chan,
        savefile=sweep_file,
        tone_shift=tone_shift,
        freq_step=step,
        full_span=span,
        filename_suffix=filename_suffix,
    )
    sweep_data = sweep.run_sweep()
    sweep_data.save()
    return sweep_file



def run_noise_data_collection(
    rfsoc: RFSOCWrapper,
    tile_name: str,
    chan: int = 1,
    duration: int = 10,
    force: bool = False,
):
    """Collect `duration` seconds of noise (TOD) data for one channel, headless."""
    collector = AutomatedDataCollector([(rfsoc, chan)])
    save_file = collector.start_streaming(duration=duration, force=force)
    return save_file

def remote_data_collection(chan = 1, tile_name: str = 'Be260114BL_100_tones_260721', duration: int = 10):
    settings = Settings()
    settings.load_settings()

    rfsoc = RFSOCWrapper(settings['rfsocs'][0])
    chan = chan
    tile_name = tile_name

    rfsoc.load_params_file(
        1,
        f'/data/params/params_tile_{tile_name}.h5',
        upload_tones=False,
        set_freq=False,
        set_atten=False,
    )

    save_file = run_noise_data_collection(rfsoc, tile_name=tile_name, chan=chan, duration=duration)
    return str(save_file)