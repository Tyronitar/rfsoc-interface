"""Code for manipulating the optical camera."""

from __future__ import annotations

import contextlib
import copy
import logging
import queue
import subprocess
import threading
import time
import typing
from multiprocessing import Array, Lock
from multiprocessing.connection import Connection
from queue import Queue
from typing import Any

import h5py
import matplotlib.pyplot as plt
import numpy as np
from vmbpy import (
    Camera,
    CameraEvent,
    Frame,
    FrameStatus,
    PixelFormat,
    Stream,
    VmbCameraError,
    VmbFeatureError,
    VmbSystem,
)

from rfsocinterface.core.utils import quit_function

_logger = logging.getLogger(__name__)
_camera_logger = logging.getLogger('rfsocinterface.cameraControl')


FRAME_QUEUE_SIZE = 10
MAX_FRAME_HEIGHT = 1944
MAX_FRAME_WIDTH = 2592


DEFAULT_CAMERA_FEATURE_VALUES = {
    'Width': MAX_FRAME_WIDTH,
    'Height': MAX_FRAME_HEIGHT,
    'PixelFormat': PixelFormat.Rgb8,
    'Gamma': 1,
    'ExposureAuto': 'Continuous',
    'AcquisitionMode': 'Continuous',
}
#
# Adapted from vmbpy example code
#


def try_put_frame(q: queue.Queue, cam: Camera, frame: Frame | None):
    """Try to put a frame into the queue."""
    with contextlib.suppress(queue.Full):
        q.put_nowait((cam.get_id(), frame))


class VideoFileWriter(threading.Thread):
    """Worker thread that writes the video to file."""

    def __init__(self, video_file: str, timestamp_file: str, frame_queue: Queue):
        """Initialize a VideoFileWriter."""
        threading.Thread.__init__(self)
        self.video_file = video_file
        self.timestamp_file = timestamp_file
        self.queue = frame_queue

        cmd = [
            'ffmpeg',
            '-y',
            '-f',
            'rawvideo',
            '-vcodec',
            'rawvideo',
            '-pix_fmt',
            'rgb24',
            '-s',
            f'{MAX_FRAME_WIDTH}x{MAX_FRAME_HEIGHT}',
            '-loglevel',
            'fatal',
            '-i',
            '-',  # Read from stdin
            '-an',
            str(video_file),
        ]

        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        _camera_logger.debug('VideoFileWriter: Succesfully opened ffmpeg subprocess.')

    @typing.override
    def run(self):
        _camera_logger.debug('VideoFileWriter: Started writing to file.')
        timestamp_file = h5py.File(self.timestamp_file, 'a')
        timestamp_dataset = timestamp_file.create_dataset(
            'timestamp', shape=(0,), maxshape=(None,), dtype=np.float64
        )
        timestamp_file.attrs['video_file'] = str(self.video_file)
        while True:
            obj = self.queue.get()
            if obj is None:
                _camera_logger.debug('VideoFileWriter: Received stop signal.')
                break  # None indicates the queue is finished
            frame, timestamp = obj
            self.proc.stdin.write(frame.tobytes())
            n_frames = timestamp_dataset.size
            if n_frames % 10 == 0:
                _camera_logger.debug(f'VideoFileWriter: {n_frames} frames written...')
            timestamp_dataset.resize(n_frames + 1, axis=0)
            timestamp_dataset[-1] = timestamp

        timestamp_file.close()
        self.proc.stdin.close()
        self.proc.wait()
        _camera_logger.debug('VideoFileWriter: Finished cleanup.')


class FrameProducer(threading.Thread):
    """Worker thread for getting frames from the camera."""

    def __init__(self, cam: Camera, frame_queue: Queue):
        """Initialize a FrameProducer."""
        threading.Thread.__init__(self)

        self.cam = cam
        self.frame_queue = frame_queue
        self.killswitch = threading.Event()

    def __call__(self, cam: Camera, stream: Stream, frame: Frame):  # noqa: ARG002
        """Get a frame and add it to the queue."""
        # This method is executed within VmbC context. All incoming frames
        # are reused for later frame acquisition. If a frame shall be queued, the
        # frame must be copied and the copy must be sent, otherwise the acquired
        # frame will be overridden as soon as the frame is reused.
        if frame.get_status() == FrameStatus.Complete and not self.frame_queue.full():
            frame_cpy = copy.deepcopy(frame)
            try_put_frame(self.frame_queue, cam, frame_cpy)

        cam.queue_frame(frame)

    def stop(self):
        """Triegger the killswitch to stop the thread."""
        self.killswitch.set()

    # def setup_camera(self):
    #     set_nearest_value(self.cam, 'Height', FRAME_HEIGHT)
    #     set_nearest_value(self.cam, 'Width', FRAME_WIDTH)

    #     # Try to enable automatic exposure time setting
    #     try:
    #         self.cam.ExposureAuto.set('Once')

    #     except (AttributeError, VmbFeatureError):
    #         self.log.info('Camera {}: Failed to set Feature \'ExposureAuto\'.'.format(
    #                       self.cam.get_id()))

    #     self.cam.set_pixel_format(PixelFormat.Mono8)
    #     self.cam.AcquisitionMode.set('Continuous')

    @typing.override
    def run(self):
        _camera_logger.debug(f"Thread 'FrameProducer({self.cam.get_id()})' started.")

        try:
            with self.cam:
                # self.setup_camera()

                try:
                    self.cam.start_streaming(self)
                    self.killswitch.wait()

                finally:
                    self.cam.stop_streaming()

        except VmbCameraError:
            pass

        finally:
            try_put_frame(self.frame_queue, self.cam, None)

        _camera_logger.debug(f"Thread 'FrameProducer({self.cam.get_id()})' terminated.")


def make_controller(
    connection: Connection,
    camera_array: Array,
    timestamp_array: Array,
    camera_lock: Lock,
    timestamp_lock: Lock,
    max_queue_size: int = FRAME_QUEUE_SIZE,
    **features,
) -> CameraController:
    """Create a CameraController."""
    return CameraController(
        connection,
        camera_array,
        timestamp_array,
        camera_lock,
        timestamp_lock,
        max_queue_size=max_queue_size,
        **features,
    )


class CameraController:
    """Orchestrator of camera operations and communications."""

    def __init__(
        self,
        conn: Connection,
        camera_array: Array,
        timestamp_array: Array,
        camera_lock: Lock,
        timestamp_lock: Lock,
        max_queue_size: int = FRAME_QUEUE_SIZE,
        **features,
    ):
        """Initialize a CameraController."""
        _camera_logger.debug(
            f'Initializing CameraController with max_queue_size={max_queue_size}, '
            f'features={features}'
        )
        self._initialized = False
        self.connection = conn
        self.frame_queue = Queue(maxsize=max_queue_size)
        self.producers = {}
        self.producers_lock = threading.Lock()
        self.camera_array = np.frombuffer(
            camera_array.get_obj(), dtype=np.uint8
        ).reshape(MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3)
        self.timestamp_array = np.frombuffer(
            timestamp_array.get_obj(), dtype=np.float64
        ).reshape(1)
        self.camera_lock = camera_lock
        self.timestamp_lock = timestamp_lock
        self._listener_thread = threading.Thread(target=self._consumer_loop)
        self._writer_thread = None
        self._recording = False
        self._joining_writer_thread = False
        self._write_queue = Queue()
        if self.connection is None:
            # Plot the images instead
            self.figure, self.axes = plt.subplots()
            self.im = plt.imshow(
                np.zeros((MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH)), animated=True
            )
            plt.show(block=False)
        self.vmb = VmbSystem.get_instance()
        with self.vmb:
            self._initialize_system(**features)
            self.run()

    def _initialize_system(self, **features):
        _camera_logger.debug('Initializing VMB Camera System...')
        try:
            if len(features) == 0:
                features = DEFAULT_CAMERA_FEATURE_VALUES
                _camera_logger.debug('Using default features for cameras')

            # Construct FrameProducer threads for all detected cameras
            all_cams = self.vmb.get_all_cameras()
            _camera_logger.debug(f'Identified {len(all_cams)} cameras')
            if len(all_cams) == 0:
                msg = 'Unable to identify any VMB cameras. Ensure camera is connected.'
                _camera_logger.error(msg, exc_info=True)
                self.send('err', 'NON-CRITICAL', msg)
                self.send('done')
                return
            for cam in all_cams:
                self.producers[cam.get_id()] = FrameProducer(cam, self.frame_queue)
                with cam:
                    for feature_name, val in features.items():
                        try:
                            self.set_feature(cam, feature_name, val)
                        except VmbFeatureError as e:
                            msg = (
                                f'Error setting feature "{feature_name}" to "{val}" '
                                f'for camera {cam.get_id()}: {e}'
                            )
                            _camera_logger.critical(msg, exc_info=True)
                            self.send('err', 'CRITICAL', msg)
                            self.send('done')

                            return
            self._initialized = True
            _camera_logger.debug('Succesfully initialized VMB Camera System')
        except Exception as e:
            msg = f'Error encoutered initializing camera controller: {e}'
            _camera_logger.critical(msg, exc_info=True)
            self.send('err', 'CRITICAL', msg)
            self.send('done')
            return

    def __call__(self, cam: Camera, event: CameraEvent):
        """Add a new camera to this controller."""
        # New camera was detected. Create FrameProducer, add it to active FrameProducers
        if event == CameraEvent.Detected:
            with self.producers_lock:
                self.producers[cam.get_id()] = FrameProducer(cam, self.frame_queue)
                self.producers[cam.get_id()].start()
            _camera_logger.debug(f'Added FrameProducer for camera {cam.get_id()}')

        # An existing camera was disconnected, stop associated FrameProducer.
        elif event == CameraEvent.Missing:
            with self.producers_lock:
                producer = self.producers.pop(cam.get_id())
                producer.stop()
                producer.join()
            _camera_logger.debug(f'Removed FrameProducer for camera {cam.get_id()}')

    def run(self):
        """Run the CameraController."""
        if not self._initialized:
            _logger.debug(
                'VMB Camera System could not be initialized, terminating process'
            )
            return

        _logger.debug('Starting VMB Camera System...')
        # Start FrameProducer threads
        with self.producers_lock:
            for producer in self.producers.values():
                producer.start()

        # Run the frame consumer to display the recorded images
        self.vmb.register_camera_change_handler(self)

        self._consumer_loop()

        # Stop recording if still doing that
        if self._recording:
            self._recording = False
            self._write_queue.put(None)
            self._writer_thread.join()
            self.send('recording_stopped')

        self.vmb.unregister_camera_change_handler(self)

        # Stop all FrameProducer threads
        with self.producers_lock:
            # Initiate concurrent shutdown
            for producer in self.producers.values():
                producer.stop()

            # Wait for shutdown to complete
            for producer in self.producers.values():
                producer.join()

        _logger.debug('All camera FrameProducer threads joined.')
        self.send('done')

    def send(self, command: str, *args, timeout: float | None = None):
        """Send a command to the main process."""
        if timeout:
            timer = threading.Timer(
                timeout,
                quit_function,
            )
            timer.start()
            try:
                self.connection.send([command, *args])
                _camera_logger.debug(
                    f'CAMERA sent command "{command}" with data {args}'
                )
            except KeyboardInterrupt:
                _camera_logger.error(f'CAMERA timed out sending command "{command}"')  # noqa: TRY400
            finally:
                timer.cancel()
        else:
            self.connection.send([command, *args])
            _camera_logger.debug(f'CAMERA sent command "{command}" with data {args}')

    def set_feature(self, cam: Camera | str, feature_name: str, val: Any):
        """Set the feature for the camera."""
        if isinstance(cam, str):
            cam = self.vmb.get_camera_by_id(cam)

        try:
            cam.get_feature_by_name(feature_name).set(val)
        except VmbFeatureError as e:
            self.send(
                'err', 'CRITICAL', f'Unable to set "{feature_name}" to "val": {e}'
            )
            raise VmbFeatureError from e

    def get_feature(self, cam: Camera | str, feature_name: str):
        """Set the feature for the camera."""
        if isinstance(cam, str):
            cam = self.vmb.get_camera_by_id(cam)

        try:
            return cam.get_feature_by_name(feature_name).get()
        except VmbFeatureError as e:
            self.send(
                'err', 'CRITICAL', f'Unable to set "{feature_name}" to "val": {e}'
            )
            raise VmbFeatureError from e

    def _consumer_loop(self):  # noqa: PLR0912
        frames: dict[str, Frame] = {}
        self.alive = True

        _camera_logger.debug('Camera consumer loop started.')

        interval = 0.2

        try:
            while self.alive:
                # Check for commands from the main process
                if self.connection is not None and self.connection.poll():
                    command, *args = self.connection.recv()
                    _camera_logger.debug(
                        f'CAMERA received command: "{command}", args: {args}'
                    )
                    match command:
                        case 'start_recording':
                            video_file, timestamp_file = args
                            self._writer_thread = VideoFileWriter(
                                video_file, timestamp_file, self._write_queue
                            )
                            self._recording = True
                            interval = 0.05  # faster frame rate when recording
                            self._writer_thread.start()
                            self.send('recording_started')
                        case 'stop_recording':
                            if self._recording:
                                self._write_queue.put(None)
                                self._recording = False
                                interval = 0.2
                                self._joining_writer_thread = True
                        case 'set_feature':
                            if len(args) == 2:  # noqa: PLR2004
                                feature_name, val = args
                                cams = self.vmb.get_all_cameras()
                            else:
                                cam_id, feature_name, val = args
                                cams = [self.vmb.get_camera_by_id(cam_id)]

                            for cam in cams:
                                with cam:
                                    try:
                                        self.set_feature(cam, feature_name, val)
                                    except VmbFeatureError:
                                        self.alive = False
                                        break
                        case 'get_feature':
                            if len(args) == 2:  # noqa: PLR2004
                                feature_name, val = args
                                cams = self.vmb.get_all_cameras()
                            else:
                                cam_id, feature_name, val = args
                                cams = [self.vmb.get_camera_by_id(cam_id)]
                            for cam in cams:
                                with cam:
                                    try:
                                        val = self.get_feature(cam, feature_name)
                                        self.send(
                                            'get_feature',
                                            cam.get_id(),
                                            feature_name,
                                            val,
                                        )
                                    except VmbFeatureError:
                                        self.alive = False
                                        break
                        case 'terminate':
                            self.alive = False
                            break
                        case _:
                            self.send(
                                'err',
                                'NON-CRITICAL',
                                f'Unknown command "{command}" received.',
                            )
                            continue

                if self._joining_writer_thread:
                    # join(0) returns immediately without waiting
                    self._writer_thread.join(0)
                    if not self._writer_thread.is_alive():
                        self._joining_writer_thread = False
                        self.send('recording_stopped')

                # Update current state by dequeuing all currently available frames.
                while True:
                    if not self.alive:
                        _camera_logger.debug('alive=False; Ending consumer loop...')
                        break
                    try:
                        cam_id, frame = self.frame_queue.get_nowait()
                    except queue.Empty:
                        break

                    # Add/Remove frame from current state.
                    if frame:
                        frames[cam_id] = frame

                    else:
                        frames.pop(cam_id, None)

                # Construct image by stitching frames together.
                if frames:
                    cv_images = [
                        frames[cam_id].as_numpy_ndarray()
                        for cam_id in sorted(frames.keys())
                    ]

                    # Rotate image so it's aligned properly
                    cv_images = np.flip(np.flip(cv_images, 1), 2)

                    timestamp = time.time()

                    # Write the frame to file if recording
                    if self._recording:
                        self._write_queue.put_nowait((cv_images[0], timestamp))
                    else:
                        # Send timestamp and image to the main process
                        with self.camera_lock, self.timestamp_lock:
                            self.camera_array[:] = cv_images[0]
                            self.timestamp_array[:] = timestamp

                    if self.connection is None:
                        self.im.set_array(cv_images[0])
                        self.figure.canvas.draw()
                        self.figure.canvas.flush_events()
                        # plt.pause(0.25)

                time.sleep(interval)

        except KeyboardInterrupt:
            self.alive = False
        finally:
            _logger.debug('Frame consumer loop terminated')


if __name__ == '__main__':
    arr = Array('B', MAX_FRAME_WIDTH * MAX_FRAME_HEIGHT * 3)
    lock = Lock()
    cam = CameraController(None, arr, lock)
