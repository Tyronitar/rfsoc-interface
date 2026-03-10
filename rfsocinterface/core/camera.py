import logging
from pathlib import Path
import threading
from multiprocessing.connection import Connection
import queue
from queue import Queue
import copy
import time
from typing import Any, Optional

from vmbpy import (
    VmbSystem,
    PixelFormat,
    Camera,
    Frame,
    FrameStatus,
    Stream,
    AccessMode,
    VmbFeatureError,
    VmbCameraError,
    CameraEvent,
)
from vmbpy.util import LOG_CONFIG_INFO_CONSOLE_ONLY
import numpy as np
import numpy.typing as npt
import h5py
import cv2
import matplotlib.pyplot as plt

from rfsocinterface.core.utils import get_filename, PathLike, PERMISSIONS_USR_RW
from rfsocinterface.core.utils import ensure_path

_logger = logging.getLogger(__name__)


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

class SKPR_Camera_Control:
    def __init__(self):
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
                cam.AcquisitionMode.set('SingleFrame')
                cam.ExposureAuto.set('Continuous')
                cam.Height.set(MAX_FRAME_HEIGHT)
                cam.Width.set(MAX_FRAME_WIDTH)
                cam.Gamma.set = 1
                cam.set_pixel_format(PixelFormat.Rgb8)
    
    def take_pic(self, savefile: PathLike=None, save: bool=False, show: bool=False) -> cv2.typing.MatLike:
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
                frame = cam.get_frame()
            pic_data = np.flip(np.flip(frame.as_numpy_ndarray(),0),1)

            if save:
                if not savefile:
                    savefile = get_filename(file_type='optcam').with_suffix('.h5')
                savefile.touch(PERMISSIONS_USR_RW, exist_ok=True)
                f = h5py.File(savefile, 'a')
                f.create_dataset('optical_image', data=pic_data)
                f.close()

            if show:
                im_hsv = cv2.cvtColor(pic_data,cv2.COLOR_RGB2HSV)
                im_hsv[..., 1] = im_hsv[..., 1] * 1.
                pic_data = cv2.cvtColor(im_hsv,cv2.COLOR_HSV2RGB)

                plt.imshow(pic_data)
                plt.show()
            
            return pic_data

#
# Adapted from vmbpy example code
#

def try_put_frame(q: queue.Queue, cam: Camera, frame: Optional[Frame]):
    try:
        q.put_nowait((cam.get_id(), frame))

    except queue.Full:
        pass


class FrameProducer(threading.Thread):
    def __init__(self, cam: Camera, frame_queue: Queue):
        threading.Thread.__init__(self)

        self.cam = cam
        self.frame_queue = frame_queue
        self.killswitch = threading.Event()

    def __call__(self, cam: Camera, stream: Stream, frame: Frame):
        # This method is executed within VmbC context. All incoming frames
        # are reused for later frame acquisition. If a frame shall be queued, the
        # frame must be copied and the copy must be sent, otherwise the acquired
        # frame will be overridden as soon as the frame is reused.
        if frame.get_status() == FrameStatus.Complete:

            if not self.frame_queue.full():
                frame_cpy = copy.deepcopy(frame)
                try_put_frame(self.frame_queue, cam, frame_cpy)

        cam.queue_frame(frame)

    def stop(self):
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

    def run(self):
        _logger.info('Thread \'FrameProducer({})\' started.'.format(self.cam.get_id()))

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

        _logger.info('Thread \'FrameProducer({})\' terminated.'.format(self.cam.get_id()))


class CameraController:
    def __init__(self, conn: Connection, max_queue_size: int=FRAME_QUEUE_SIZE, **features):
        self._initialized = False
        self.connection = conn
        self.frame_queue = Queue(maxsize=max_queue_size)
        self.producers = {}
        self.producers_lock = threading.Lock()
        self._listener_thread = threading.Thread(tagret=self._consumer_loop)
        self._initialize_system(**features)
        self.run()
    
    def _initialize_system(self, **features):
        self.vmb = VmbSystem.get_instance()
        self.vmb.enable_log(LOG_CONFIG_INFO_CONSOLE_ONLY)

        if len(features) == 0:
            features = DEFAULT_CAMERA_FEATURE_VALUES

        _logger.debug('Initializing VMB Camera System...')
        with self.vmb:
            # Construct FrameProducer threads for all detected cameras
            for cam in self.vmb.get_all_cameras():
                for feature_name, val in features.items():
                    try:
                        self.set_feature(cam, feature_name, val)
                    except VmbFeatureError:
                        return
                self.producers[cam.get_id()] = FrameProducer(cam, self.frame_queue)
        self._initialized = True
        _logger.debug('Initialized VMB Camera System')

    def __call__(self, cam: Camera, event: CameraEvent):
        # New camera was detected. Create FrameProducer, add it to active FrameProducers
        if event == CameraEvent.Detected:
            with self.producers_lock:
                self.producers[cam.get_id()] = FrameProducer(cam, self.frame_queue)
                self.producers[cam.get_id()].start()
            _logger.debug(f'Added FrameProducer for camera {cam.get_id()}')

        # An existing camera was disconnected, stop associated FrameProducer.
        elif event == CameraEvent.Missing:
            with self.producers_lock:
                producer = self.producers.pop(cam.get_id())
                producer.stop()
                producer.join()
            _logger.debug(f'Removed FrameProducer for camera {cam.get_id()}')

    def run(self):
        if not self._initialized:
            _logger.debug('VMB Camera System could not be initialized, terminating process')
            return

        _logger.debug('Starting VMB Camera System...')
        with self.vmb:
            # Start FrameProducer threads
            with self.producers_lock:
                for producer in self.producers.values():
                    producer.start()

            # Run the frame consumer to display the recorded images
            self.vmb.register_camera_change_handler(self)

            self._consumer_loop()

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

    def send(self, command: str, *args):
        """Send a command to the telescope client"""
        self.connection.send([command, *args])
        _logger.debug(f'CAMERA sent command "{command}" with data {args}')
    
    def set_feature(self, cam: Camera | str, feature_name: str, val: Any):
        if isinstance(cam, str):
            cam = self.vmb.get_camera_by_id(cam)

        try:
            cam.get_feature_by_name(feature_name).set(val)
        except VmbFeatureError as e:
            self.send('err', 'CRITICAL', f'Unable to set "{feature_name}" to "val": {e}')
            raise VmbFeatureError from e

    def get_feature(self, cam: Camera | str, feature_name: str):
        if isinstance(cam, str):
            cam = self.vmb.get_camera_by_id(cam)

        try:
            return cam.get_feature_by_name(feature_name).get()
        except VmbFeatureError as e:
            self.send('err', 'CRITICAL', f'Unable to set "{feature_name}" to "val": {e}')
            raise VmbFeatureError from e
    
    def _consumer_loop(self):
        frames: dict[str, Frame] = {}
        alive = True

        _logger.info('Camera consumer loop started.')

        while alive:
            # Check for commands from the main process
            if self.connection.poll():
                command, *args = self.connection.recv()
                match command:
                    case 'set_feature':
                        if len(args) == 2:
                            feature_name, val = args
                            cams = self.vmb.get_all_cameras()
                        else:
                            id, feature_name, val = args
                            cams = [self.vmb.get_camera_by_id(id)]

                        for cam in cams:
                            try:
                                self.set_feature(cam, feature_name, val)
                            except VmbFeatureError:
                                self.alive = False
                                break
                    case 'get_feature':
                        if len(args) == 2:
                            feature_name, val = args
                            cams = self.vmb.get_all_cameras()
                        else:
                            id, feature_name, val = args
                            cams = [self.vmb.get_camera_by_id(id)]
                        for cam in cams:
                            try:
                                val = self.get_feature(cam, feature_name)
                                self.send('get_feature', cam.get_id(), feature_name, val)
                            except VmbFeatureError:
                                self.alive = False
                                break
                    case 'terminate':
                        self.alive = False
                        break
                    case _:
                        self.send('err', 'NON-CRITICAL', f'Unknown command "{command}" received.')
                        continue

            # Update current state by dequeuing all currently available frames.
            frames_left = self.frame_queue.qsize()
            while frames_left:
                try:
                    cam_id, frame = self.frame_queue.get_nowait()

                except queue.Empty:
                    break

                # Add/Remove frame from current state.
                if frame:
                    frames[cam_id] = frame

                else:
                    frames.pop(cam_id, None)

                frames_left -= 1

            # Construct image by stitching frames together.
            if frames:
                cv_images = [frames[cam_id].as_numpy_ndarray() for cam_id in sorted(frames.keys())]

                # Rotate image so it's aligned properly
                cv_images = np.flip(np.flip(cv_images, 0), 1)

                # Send timestamp and image to the main process
                self.send('image', time.time(), cv_images)

        self.send(None)
        _logger.debug('Frame consumer loop terminated')


if __name__ == '__main__':
    cam = SKPR_Camera_Control()
    cam.take_pic(show=True)
