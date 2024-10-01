import functools
import os
from pathlib import Path
import json
from typing import Callable, ParamSpec, TypeVar
import logging
import numpy as np
import numpy.typing as npt
from kidpy import wait_for_free, wait_for_reply, kidpy
import redis

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)
Number = TypeVar('Number', int, float, complex, bytes)

# Generic types for type hints
T = TypeVar('T')
R = TypeVar('R')

P = ParamSpec('P')
Q = ParamSpec('Q')


def convert_path(path: PathLike) -> Path:
    """Ensure that a Path is a Path object."""
    if isinstance(path, Path):
        return path
    if isinstance(path, bytes):
        return Path(path.decode())
    if isinstance(path, str | os.PathLike):
        return Path(path)

    # Input was not a PathLike
    raise ValueError(f'Argument must be PathLike, got {type(path)}')


def ensure_path(
    *targets: int | str,
) -> Callable[[Callable[P, R]], Callable[Q, R]]:
    """Function decorator factory for converting PathLike's to Path's.

    Arguments:
        *targets (int | str): The arguments to convert to Path's before evaluating the
            function. If a target is an integer, it indicates the index of the
            positional argument. If it is a string, it indicates the key in kwargs to
            convert.
    """

    def decorator(func: Callable[P, R]) -> Callable[Q, R]:
        """Decorator that converts PathLike's into Path's before calling the function.

        Arguments:
            func (Callable[P, R]): A function that may take Path objects as arguments.

        Returns:
            (Callable[Q, R]): A function that can take PathLike arguments and converts
                them to Path objects.
        """

        @functools.wraps(func)
        def wrapper(
            *args: Q.args,
            **kwargs: Q.kwargs,
        ) -> R:
            new_args = [
                convert_path(arg) if i in targets else arg for i, arg in enumerate(args)
            ]
            new_kwargs = {
                k: (convert_path(v) if k in targets else v) for k, v in kwargs.items()
            }
            return func(*new_args, **new_kwargs)

        return wrapper

    return decorator




def write_fList(kpy: kidpy, fList: npt.ArrayLike, ampList: npt.ArrayLike):
    """
    Function for writing tones to the rfsoc. Accepts both numpy arrays and lists.
    :param fList: List of desired tones
    :type fList: list
    :param ampList: List of desired amplitudes
    :type ampList: list
    .. note::
        fList and ampList must be the same size
    """
    # log = logger.getChild("write_fList")
    f = fList
    a = ampList

    # Convert to numpy arrays as needed
    if isinstance(fList, np.ndarray):
        f = fList.tolist()
    if isinstance(ampList, np.ndarray):
        a = ampList.tolist()

    # Format Command based on provided parameters
    cmd = {}
    if len(f) == 0:
        cmd = {"cmd": "ulWaveform", "args": []}
    elif len(f) > 0 and len(a) == 0:
        a = np.ones_like(f).tolist()
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    elif len(f) > 0 and len(a) > 0:
        assert len(a) == len(
            f
        ), "Frequency list and Amplitude list must be the same dimmension"
        cmd = {"cmd": "ulWaveform", "args": [f, a]}
    else:
        # log.error("Weird edge case, something went very wrong.....")
        return

    cmdstr = json.dumps(cmd)
    kpy.r.publish("picard", cmdstr)
    success, _ = wait_for_reply(kpy.p, "ulWaveform", max_timeout=10)
    # if success:
    #     log.info("Wrote waveform.")
    # else:
    #     log.error("FAILED TO WRITE WAVEFORM")

def test_connection(r):
    try:
        r.set("testkey", "123")
        return True
    except redis.exceptions.ConnectionError as e:
        print(e)
        return False