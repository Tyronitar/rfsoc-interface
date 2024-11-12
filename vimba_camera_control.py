"""
    vimba_camera_control.py
    Written by ZBH, 1/31/24
    
    Python script to use the Vimba X Python API to control an
    Allied Vision 1800 U-500c camera for basic image acquisition.
    
    API notes: https://docs.alliedvision.com/Vimba_X/Vimba_X_DeveloperGuide/pythonAPIManual.html
    Installation for Vimba X: https://www.alliedvision.com/en/products/software/vimba-x-sdk/

"""

from vmbpy import *
import numpy as np
import matplotlib.pyplot as plt
import cv2 # opencv - for saving files nicely, though now that I have conversion to numpy working we might be able to do other things
import pdb
import time
import onrkidpy
import h5py
import cv2

class SKPR_Camera_Control:
    def init_cam(self):
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
                # Setting pixel format to something opencv likes - might be able to ignore if using numpy
                print(cam.get_name() )
                # cam.set_pixel_format(PixelFormat.Bgr8)
                # print("Camera pixel format set")
                # print(cam.get_pixel_format())
                #pdb.set_trace()
                # Changing acquisition mode to SingleFrame
                #cam.TriggerSource.set('Software')
                # cam.TriggerSelector.set('FrameStart')
                # cam.TriggerMode.set('On')
                cam.AcquisitionMode.set('SingleFrame')
                # print(cam.AcquisitionMode)
                #pdb.set_trace()
                # Turning on Auto Exposure - options are Off, Once, Continuous
                cam.ExposureAuto.set('Continuous')
        return cams

    def take_pic(self, save_file=False,show = False):
        with VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            with cams[0] as cam:
    #            # Setting pixel format to something opencv likes - might be able to ignore if using numpy
    #            print(cam.get_name() )
    #            # cam.set_pixel_format(PixelFormat.Bgr8)
    #            # print("Camera pixel format set")
    #            # print(cam.get_pixel_format())
    #            #pdb.set_trace()
    #            # Changing acquisition mode to SingleFrame
    #            #cam.TriggerSource.set('Software')
    #            # cam.TriggerSelector.set('FrameStart')
    #            # cam.TriggerMode.set('On')
    #            # cam.AcquisitionMode.set('SingleFrame')
    #            # print(cam.AcquisitionMode)
    #            #pdb.set_trace()
    #            # Turning on Auto Exposure - options are Off, Once, Continuous
                cam.ExposureAuto.set('Continuous')
                cam.Gamma.set = 1
    #    #       print(cam.ExposureAuto)
    #            # Turning on Auto Gain - options are Off, Once, Continuous
                #cam.GainAuto.set('Continuous')
    #            # print(cam.GainAuto)
    #            # Trying to take a stream of synchronous frames to allow the auto exposure and gain to work
    #    #        print("Taking short stream to auto adjust exposure and gain")
    #            # for frame in cam.get_frame_generator(limit=20):
    #               # pass
    #            # print("Done with stream")
    #            # Aquire single frame synchronously
    #            # with cam.get_frame_with_context() as frame:
                frame = cam.get_frame()
                pic_data = np.flip(np.flip(frame.as_numpy_ndarray(),0),1)
                if save_file:
                    savefile = onrkidpy.get_filename(type="optcam") + ".h5"
                    f = h5py.File(savefile, "a")
                    f.create_dataset("optical_image", data=pic_data)
                    f.close()
                #make the image HDR
#                im_hsv = cv2.cvtColor(pic_data,cv2.COLOR_RGB2HSV)
#                im_hsv_bright = im_hsv
#                hb, sb, vb = cv2.split(im_hsv_bright)
#                bright_shift = 30
#                vb[vb < (255-bright_shift)] = vb[vb < (255-bright_shift)] + bright_shift
#                im_hsv_bright = cv2.merge((hb,sb,vb))
#                im_bright = cv2.cvtColor(im_hsv_bright,cv2.COLOR_HSV2RGB)
#                im_hsv_dim = im_hsv
#                hb, sb, vb = cv2.split(im_hsv_dim)
#                vb[vb > bright_shift] = vb[vb > bright_shift] - bright_shift
#                im_hsv_dim = cv2.merge((hb,sb,vb))
#                im_dim = cv2.cvtColor(im_hsv_dim,cv2.COLOR_HSV2RGB)
#                merge_debevec = cv2.createMergeDebevec()
#                hdr_debevec = merge_debevec.process([im_dim, pic_data, im_bright], times=np.array([0.5,1.,2.],dtype=np.float32))
#                tmap = cv2.createTonemap(gamma=2.2)
#                res_debevec = tmap.process(hdr_debevec.copy())
#                hdr_pic = np.clip(res_debevec*255,0,255).astype('uint8')
#                pdb.set_trace()              

                #increase saturation to a more natural level
                im_hsv = cv2.cvtColor(pic_data,cv2.COLOR_RGB2HSV)
                im_hsv[:,:,1] = im_hsv[:,:,1] * 2.
                pic_data = cv2.cvtColor(im_hsv,cv2.COLOR_HSV2RGB)

                if show:
                    plt.imshow(pic_data)
                    plt.show()
                #np.logspace(2,
                #pdb.set_trace()
    #            #time.sleep(2)
    #            #        pdb.set_trace()
    #            #frame = frame.copy.deepcopy
    #            # print("Frame acquired")
    #            #print(frame)
    #            
    #            # Show frame to file
    #            if ret_pic == True:
    #                return pic_data
    #cams = init_cam()  


    #take_pic(cams)
    #pdb.set_trace()
                #plt.imshow(frame.as_numpy_ndarray())
                #plt.show()
                #print("Frame displayed!")
                # Save frame to file using opencv
                #cv2.imwrite('test_frame.jpg', frame.as_opencv_image())
                #print("Frame written!")
