from pathlib import Path
import timeit

import av
import numpy as np
import numpy.typing as npt


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


if __name__ == '__main__':
    # fname = '/data/20260917/20260917_optcam_video_set1007.mp4'
    fname = '/data/20260828/20260828_optcam_video_set1003.mp4'

    n = 3
    iterative_time = timeit.timeit(lambda: read_mp4_to_ndarray_iterative(fname), number=n)
    threaded_time = timeit.timeit(lambda: read_mp4_to_ndarray_threaded(fname), number=n)

    print(f'Total time for iterative: {iterative_time:.4f} seconds')
    print(f'Average time for iterative: {iterative_time / n:.4f} seconds')
    print('\n')
    print(f'Total time for threaded:  {threaded_time:.4f} seconds')
    print(f'Average time for threaded:  {threaded_time / n:.4f} seconds')


