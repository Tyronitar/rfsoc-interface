from typing import ParamSpec, TypeVar, Callable
from pathlib import Path
import functools
import os

PathLike = TypeVar('PathLike', str, Path, bytes, os.PathLike)

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
            new_args = [convert_path(arg) if i in targets else arg for i, arg in enumerate(args)]
            new_kwargs = {k: (convert_path(v) if k in targets else v) for k, v in kwargs.items()}
            return func(*new_args, **new_kwargs)
        return wrapper
    return decorator
