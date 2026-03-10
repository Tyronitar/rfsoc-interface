from pathlib import Path
import threading
from multiprocessing.connection import Connection

from vmbpy import VmbSystem, PixelFormat, Camera, Frame, FrameStatus, Stream, AccessMode
import numpy as np
import h5py
import cv2
import matplotlib.pyplot as plt
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

class CameraController:
    def __init__(self, conn: ):
        pass


if __name__ == '__main__':
    cam = SKPR_Camera_Control()
    cam.take_pic(show=True)
