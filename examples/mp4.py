from pathlib import Path
import timeit
import subprocess

import av
import ffmpeg
import numpy as np
import numpy.typing as npt

from rfsocinterface.core.camera import MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH


def read_mp4_to_ndarray_iterative(file: str | Path) -> npt.NDArray:
    """Read an mp4 video from file into a Numpy array."""
    container = av.open(file)
    video = container.streams.video[0]
    n_frames = video.frames
    shape = (video.height, video.width, 3, n_frames)
    full_optical_video = np.zeros(shape, dtype=np.uint8)
    for i_frame, frame in enumerate(container.decode(video=0)):
        full_optical_video[..., i_frame] = frame.to_ndarray(format='rgb24')

def read_mp4_to_ndarray_threaded(file: str | Path) -> npt.NDArray:
    """Read an mp4 video from file into a Numpy array."""
    container = av.open(file)
    video = container.streams.video[0]
    video.thread_type = 'AUTO'
    n_frames = video.frames
    shape = (video.height, video.width, 3, n_frames)
    full_optical_video = np.zeros(shape, dtype=np.uint8)
    for i_frame, frame in enumerate(container.decode(video=0)):
        full_optical_video[..., i_frame] = frame.to_ndarray(format='rgb24')

def load_mp4_ffmpeg_python(filename):
    # Stream raw video bytes directly into stdout pipe
    out, _ = (
        ffmpeg
        .input(filename)
        .output('pipe:', format='rawvideo', pix_fmt='rgb24')
        .run(capture_stdout=True, quiet=True)
    )

    # Read the buffer directly into NumPy without looping
    video = np.frombuffer(out, np.uint8).reshape([-1, MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3])
    return video

def load_mp4_ffmpeg(filename):
    cmd = [
        "ffmpeg",
        "-i",
        str(filename),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",  # Pixels format: 3 bytes per pixel (R, G, B)
        "-",
    ]

    # Run the process and capture stdout
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Read the entire raw video stream from memory
    raw_video, stderr_output = process.communicate()
    # video = np.frombuffer(raw_video, dtype=np.uint8)
    video = np.frombuffer(raw_video, np.uint8).reshape([-1, MAX_FRAME_HEIGHT, MAX_FRAME_WIDTH, 3])
    return video


if __name__ == '__main__':
    # fname = '/data/20260917/20260917_optcam_video_set1007.mp4'
    fname = '/data/20260828/20260828_optcam_video_set1003.mp4'

    n = 3
    # iterative_time = timeit.timeit(lambda: read_mp4_to_ndarray_iterative(fname), number=n)
    # threaded_time = timeit.timeit(lambda: read_mp4_to_ndarray_threaded(fname), number=n)
    ffmpeg_python_time = timeit.timeit(lambda: load_mp4_ffmpeg_python(fname), number=n)
    ffmpeg_time = timeit.timeit(lambda: load_mp4_ffmpeg(fname), number=n)

    # print(f'Total time for iterative: {iterative_time:.4f} seconds')
    # print(f'Average time for iterative: {iterative_time / n:.4f} seconds')
    # print('\n')
    # print(f'Total time for threaded:  {threaded_time:.4f} seconds')
    # print(f'Average time for threaded:  {threaded_time / n:.4f} seconds')
    # print('\n')
    print(f'Total time for ffmpeg-python:  {ffmpeg_python_time:.4f} seconds')
    print(f'Average time for ffmpeg-python:  {ffmpeg_python_time / n:.4f} seconds')
    print('\n')
    print(f'Total time for ffmpeg:  {ffmpeg_time:.4f} seconds')
    print(f'Average time for ffmpeg:  {ffmpeg_time / n:.4f} seconds')


