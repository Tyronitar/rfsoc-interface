from pathlib import Path
import numpy as np
import h5py
import cv2
import matplotlib.pyplot as plt
import threading
from vmbpy import VmbSystem, PixelFormat, Camera, Frame, FrameStatus, Stream, AccessMode
from rfsocinterface.core.utils import get_filename, PathLike, PERMISSIONS_USR_RW
from rfsocinterface.core.utils import ensure_path

MAX_FRAME_HEIGHT = 1944
MAX_FRAME_WIDTH = 2592

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


class CameraStreamer:
    def __init__(self):
        self.vmb = VmbSystem.get_instance()
        self.cam = None
        self.latest_frame = None
        self.lock = threading.Lock()
    
    def __enter__(self):
        self.vmb.__enter__()

        self.cam = self.vmb.get_all_cameras()[0]
        self.cam.__enter__()

        self.cam.start_streaming(self._frame_handler)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cam.stop_streaming()
        self.cam.__exit__(exc_type, exc_val, exc_tb)
        self.vmb.__exit__(exc_type, exc_val, exc_tb)
    
    def _frame_handler(self, cam: Camera, stream: Stream, frame: Frame):
        """Handle an incoming frame from the camera.
        
        Runs about 30-100 Hz.
        """
        if frame.get_status() == FrameStatus.Complete:
            with self.lock:
                self.latest_frame = frame.as_numpy_ndarray()
        cam.queue_frame(frame)
    
    def get_current_image(self):
        with self.lock:
            return self.latest_frame


if __name__ == '__main__':
    cam = SKPR_Camera_Control()
    cam.take_pic(show=True)
