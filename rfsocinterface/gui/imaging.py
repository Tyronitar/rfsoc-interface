"""GUI tab for creating maps."""

import copy
import logging
import time
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Concatenate

import h5py
import numpy as np
from kidpy3 import capture
from PySide6.QtWidgets import (
    QProgressDialog,
    QStackedLayout,
    QWidget,
)

from rfsocinterface.core.camera import MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH
from rfsocinterface.core.data import (
    Pipeline,
)
from rfsocinterface.core.rfsoc import RFSoCWrapper
from rfsocinterface.core.utils import (
    PERMISSIONS_USR_RW,
    P,
    PathLike,
    TabName,
    get_filename,
)
from rfsocinterface.gui.main_widget import DataCollectionMainWidget, TelescopeMainWidget
from rfsocinterface.gui.pipeline import PipelineDialog
from rfsocinterface.gui.uic.imaging_ui import Ui_ImagingWidget
from rfsocinterface.gui.utils import DATA_ROUTINE_FUNCTION_WIDGET_ARGS
from rfsocinterface.gui.widgets import ArgumentType, FunctionWidget

if TYPE_CHECKING:
    from rfsocinterface.gui.main_window import MainWindow


_logger = logging.getLogger(__name__)
_camera_logger = logging.getLogger('rfsocinterface.cameraControl')

enum_choices = ['hello', 'world']


class DitherPatternWidget(FunctionWidget):
    """FunctionWidget representing a telescope dither pattern."""

    def __init__(
        self,
        fn: Callable[Concatenate[str, PathLike, P], Any],
        command: str,
        file_func: Callable[[], PathLike],
        args: list[tuple] | None = None,
        parent=None,
    ):
        """Initialize a DitherPatternWidget."""
        if args is None:
            args = []
        super().__init__(fn, args, parent)
        self.command = command
        self.file_func = file_func

    def call_function(self):
        """Call the function tied to this widget."""
        values = self.get_inputs()
        file = self.file_func()
        self.fn(self.command, file, *values)


class ImagingWidget(TelescopeMainWidget, DataCollectionMainWidget, Ui_ImagingWidget):
    """GUI tab for dithering the telescope and creating maps."""

    tab_name = TabName.IMAGING

    def __init__(
        self,
        main_window: 'MainWindow',
        rfsocs: list[RFSoCWrapper],
        settings: dict,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize an ImagingWidget."""
        super().__init__(main_window, rfsocs, settings, parent=parent)
        self.setupUi(self)
        self.pipeline_dialog = PipelineDialog(self)
        self.pipeline = Pipeline()
        # self._add_default_routines()
        self.video_file: h5py.File = None
        self.video_file_lock = Lock()
        self.video_thread = None
        self._recording = False
        self._video_frames = []
        self._timestamps = []
        self.optical_frame_rate = 5  # Frames / second

        self._file = '.'
        self.channel_comboBox.set_default_title('Select Channels...')
        self.update_channel_choices(self.channel_comboBox)
        main_window.channelNamesUpdated.connect(
            lambda: self.update_channel_choices(self.channel_comboBox)
        )
        self.patterns: list[FunctionWidget] = []

        self.stacked_layout = QStackedLayout()
        self.dither_groupBox.layout().addLayout(self.stacked_layout, 2, 0, 1, 2)
        self.add_dither_pattern(
            'Dither Pattern',
            'dither_pattern',
            [
                (('Primary start: ', ArgumentType.FLOAT), {'default': -5}),
                (('Primary stop: ', ArgumentType.FLOAT), {'default': 5}),
                (('N Repeats: ', ArgumentType.INT), {'default': 2}),
                (('Secondary Dither: ', ArgumentType.FLOAT), {'default': 0.04}),
                (('Return to starting position', ArgumentType.BOOL), {'default': True}),
                (('Large Map Mode', ArgumentType.BOOL), {'default': False}),
                (
                    ('Primary Direction', ArgumentType.ENUM),
                    {'options': ['AZ', 'ZA'], 'default': 'AZ'},
                ),
            ],
        )
        self.add_dither_pattern(
            'Stared Image',
            'stared_image',
            [
                (('Duration (s): ', ArgumentType.FLOAT), {'default': 60}),
            ],
        )
        # self.dither_comboBox.setPlaceholderText('Choose dither pattern...')
        self.dither_comboBox.activated.connect(self.choose_pattern)
        self.start_pushButton.clicked.connect(self.run)
        self.mapping_pushButton.clicked.connect(self.choose_mapping_routines)
        self.choose_pattern(1)

    def _add_default_routines(self):
        default_routines = self.settings['defaults']['imaging']['mappingRoutines']
        for routine_dict in default_routines:
            routine_type = routine_dict['type']
            base_args = copy.copy(DATA_ROUTINE_FUNCTION_WIDGET_ARGS[routine_type])
            if 'defaults' in routine_dict:
                default_args_dict = routine_dict['defaults']
                for base_arg in base_args[2]:
                    base_arg_name = base_arg[0][0].strip(': ')
                    if base_arg_name in default_args_dict:
                        base_arg[1]['default'] = default_args_dict[base_arg_name]
            self.pipeline_dialog.add_routine(routine_type, *base_args)
            # self.pipeline_dialog.drag_function_widget.add_item(*base_args)
        self.pipeline_dialog.accept()
        self.pipeline = self.pipeline_dialog.make_pipeline()

    def run_telescope_scan(self, command: str, *args) -> int:
        """Send a command to the telescope controller and wait for the scan to end."""
        pd = QProgressDialog(
            'Running...', 'Cancel and Stop Telescope', 0, 100, parent=self
        )
        pd.canceled.connect(lambda: self.send_telescope_command('stop_telescope'))
        pd.setAutoClose(False)
        pd.setAutoReset(False)
        pd.setValue(0)
        pd.setWindowTitle('rfsocinterface')
        pd.setModal(True)

        self.active_command = command
        self.connect_to_telescope_command(f'{command}_maximum', pd.setMaximum)
        self.connect_to_telescope_command(f'{command}_progress', pd.setValue)
        self.connect_to_telescope_command(f'{command}_label', pd.setLabelText)
        _logger.debug('Connected to telescope commands')

        # Tell the controller to start moving the telescope according to the scan type
        self.send_telescope_command(command, *args)
        _logger.debug('Started telescope command')
        pd.show()

        # Wait until the motor controller indicates the scan is complete
        self.wait_for_telescope_command(
            f'{command}_complete',
            err_msg=f'Error occured while running command "{command}"',
        )
        _logger.info(f'{command} completed with data {self._telescope_command_data}.')
        self.disconnect_telescope_command(f'{command}_maximum', pd.setMaximum)
        self.disconnect_telescope_command(f'{command}_progress', pd.setValue)
        self.disconnect_telescope_command(f'{command}_label', pd.setLabelText)
        pd.close()

    def make_map(self):
        """Process the data from the observation."""
        # current_file = self.get_current_file().stem
        # date = current_file[:8]
        # setnum = int(current_file[-4:])
        # p = ProcessedData.from_tod(date, setnum)

    def update_current_file(self) -> Path:
        """Update the current save location."""
        f = self.save_location_widget.get_chosen_save_location()
        self._file = f
        return f

    def get_current_file(self) -> Path:
        """Get the current save location."""
        return self._file

    def get_azel_file(self) -> Path:
        """Get the name for the azel file."""
        return Path(str(self._file).replace('TOD', 'AZEL'))

    def add_dither_pattern(
        self, label: str, command: str, args: list[tuple[str, ArgumentType]]
    ):
        """Add a dither pattern option."""
        pattern = DitherPatternWidget(
            self.run_telescope_scan,
            command,
            # lambda: get_filename(file_type='azel').with_suffix('.h5'),
            self.get_azel_file,
            args=args,
            parent=self,
        )
        self.patterns.append(pattern)
        self.dither_comboBox.addItem(label)
        self.stacked_layout.addWidget(pattern)

    def choose_pattern(self, index: int):
        """Select the current dither pattern."""
        self.dither_comboBox.setCurrentIndex(index)
        self.stacked_layout.setCurrentIndex(index)
        self.active_pattern = self.patterns[index]

    def choose_mapping_routines(self):
        """Select the data processing routines."""
        if self.pipeline_dialog.exec():
            self.pipeline = self.pipeline_dialog.make_pipeline()
            # Get the selected routines, instantiate them, and store in the class
            # TODO: validate the inputs somehow...

    def capture_image(self):
        """Capture an optical image and save to file."""
        savefile = get_filename(file_type='optcam').with_suffix('.h5')
        savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
        optcam_file = h5py.File(savefile, 'a')
        optical_image_array = optcam_file.create_dataset(
            'optical_image',
            shape=(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3),
            dtype=np.uint8,
            compression='lzf',
            # chunks=(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3),
            # TODO: Is this a valid chunk shape?
        )
        image, _ = self.get_current_image()
        optical_image_array[:] = image
        optcam_file.close()

    def start_recording_video(self):
        """Start recording the optical camera to file."""
        optcam_savefile = get_filename(file_type='optcam').with_suffix('.h5')
        video_savefile = get_filename(file_type='optcam_video').with_suffix('.mp4')
        optcam_savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
        video_savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
        self.send_camera_command(
            'start_recording', str(video_savefile), str(optcam_savefile)
        )
        self.wait_for_camera_command('recording_started')
        _logger.info('Optical video recording started')

    def video_loop(self):
        """Append video frames to the optcam file until stopped."""
        self._recording = True
        while self._recording:
            t0 = time.time()
            self.append_video_frame()
            while time.time() < t0 + (1 / self.optical_frame_rate):
                time.sleep(1e-3)
        _logger.debug('Video loop thread done')

    def stop_recording_video(self):
        """Stop the optical video recording."""
        self.send_camera_command('stop_recording')
        self.wait_for_camera_command('recording_stopped')
        _logger.info('Optical video recording ended')

    def append_video_frame(self):
        """Add a frame to the optam video dataset."""
        with self.video_file_lock:
            if self.video_file is not None:
                t0 = time.time()
                n_frames = self.video_file['optical_video'].shape[-1]
                image, timestamp = self.get_current_image()
                # self._video_frames.append(image)
                # self._timestamps.append(timestamp[:])
                self.video_file['optical_video'].resize(n_frames + 1, axis=3)
                self.video_file['timestamp'].resize(n_frames + 1, axis=0)
                self.video_file['timestamp'][-1] = timestamp
                self.video_file['optical_video'][:, :, :, -1] = image
                t1 = time.time()
                _camera_logger.debug(
                    f'Wrote frame to optcam file in {t1 - t0:.3f} seconds'
                )

    def run(self):
        """Run the telescope scan."""
        # Update the current save file
        self.update_current_file()
        self.save_location_widget.update_timer.stop()
        rfsocs, channels, rfchans, _, _ = self.setup_data_collection()
        if not self.check_for_lo_sweep(rfsocs, channels):
            _logger.info('Missing 1 or more LO sweeps, cancelling data collection.')
            self.remove_TOD_files(rfchans)
            self.save_location_widget.update_timer.start()
            return

        # Take optical image
        if self.buttonGroup.checkedButton() == self.video_radioButton:
            self.start_recording_video()
        else:
            self.capture_image()

        # Dither telescope and collect data in separate thread
        _logger.info('Beginning data capture')
        capture(rfchans, self.active_pattern.call_function)
        _logger.info('Data capture complete')
        self.save_location_widget.update_default_save_location()
        self.save_location_widget.update_timer.start()
        self.append_global_data(rfsocs, channels, rfchans)
        if self.buttonGroup.checkedButton() == self.video_radioButton:
            self.stop_recording_video()

        if (
            self._telescope_command_data == 0
        ):  # Value other than 1 idicates the scan stopped early
            self.make_map()
