import vmbpy
from vimba_camera_control import SKPR_Camera_Control

if __name__ == '__main__':
    ctrl = SKPR_Camera_Control()
    cams = ctrl.init_cam()
    ctrl.take_pic(show=True)
