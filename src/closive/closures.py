"""Closures

Abstractions for callback-heavy control flows.
"""

from collections.abc import Callable
from functools import wraps
from typing import Optional


class _Closure:
    """A callable decorator factory that supports chaining transformations in a pipeline."""

    def __init__(self, fn: Callable, debug: bool = False):
        """
        Instantiates a new closure.

        Args:
          fn: 
            The function whose return value will be passed as the first argument to the next callback.
          debug:
            If True, prints each step of the transformation pipeline.
        """
        if not callable(fn):
            raise TypeError("Expected a callable to initialize closure.")
        self._callbacks = [fn]
        self._debug = debug

    def __call__(self, target):
        """
        Makes the _Closure class callable as a decorator.
        """
        @wraps(target)
        def wrapped(*args, **kwargs):
            result = target(*args, **kwargs)
            if self._debug:
                print(f"[closure] Initial result from {target.__name__}: {result!r}")
            for idx, fn in enumerate(self._callbacks):
                result = fn(result, *args, **kwargs)
                if self._debug:
                    print(f"[closure] After step {idx+1} ({fn.__name__}): {result!r}")
            return result
        return wrapped

    def __rshift__(self, other):
        """
        Enables chaining using the >> operator.
        """
        if not callable(other):
            raise TypeError("Can only chain callables with >>")
        new = _Closure(self._callbacks[0], debug=self._debug)
        new._callbacks = self._callbacks + [other]
        return new

    def pipe(self, fn: Callable) -> "_Closure":
        """
        Add a callback to the pipeline.
        """
        if not callable(fn):
            raise TypeError("pipe expects a callable")
        self._callbacks.append(fn)
        return self

    def repeat(self, x: int) -> "_Closure":
        """
        Repeats the last callback x additional times.
        """
        if not self._callbacks:
            raise ValueError("No callback to repeat.")
        if x < 1:
            raise ValueError("Repeat count must be at least 1.")
        
        callback = self._callbacks[-1]
        for _ in range(x):
            self.pipe(callback)
        return self

    # Aliases for a more expressive API
    do = next = then = pipe
    re = redo = rept = repeat


# Public API
def closure(fn: Callable, debug: bool = False) -> _Closure:
    """
    Factory function to create a new closure pipeline.

    Args:
      fn: 
        The first transformation function in the pipeline.
      debug:
        Optional flag to enable debug prints.

    Returns:
      A _Closure instance wrapping the initial function.
    """
    return _Closure(fn, debug=debug)