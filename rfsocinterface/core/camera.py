from pathlib import Path
import numpy as np
import h5py
import cv2
import matplotlib.pyplot as plt
from vmbpy import VmbSystem
from rfsocinterface.core.utils import get_filename
from rfsocinterface.core.utils import ensure_path

class SKPR_Camera_Control:
    def __init__(self):
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
                cam.AcquisitionMode.set('SingleFrame')
                cam.ExposureAuto.set('Continuous')
                cam.Gamma.set = 1
    
    def take_pic(self, save: bool=False, show: bool=False) -> cv2.typing.MatLike:
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
                frame = cam.get_frame()
            pic_data = np.flip(np.flip(frame.as_numpy_ndarray(),0),1)

            if save:
                savefile = get_filename(file_type='optcam').with_suffix('.h5')
                f = h5py.File(savefile, 'a')
                f.create_dataset('optical_image', data=pic_data)
                f.close()

            if show:
                im_hsv = cv2.cvtColor(pic_data,cv2.COLOR_RGB2HSV)
                im_hsv[..., 1] = im_hsv[..., 1] * 2.
                pic_data = cv2.cvtColor(im_hsv,cv2.COLOR_HSV2RGB)

                plt.imshow(pic_data)
                plt.show()
            
            return pic_data


if __name__ == '__main__':
    ctrl = SKPR_Camera_Control()
    ctrl.take_pic(show=True)
