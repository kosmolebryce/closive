"""Closures

Abstractions for callback-heavy control flows.
"""
from collections.abc import Callable
from functools import wraps


class _Closure:
    """A callable decorator factory that supports chaining callbacks.

    Usage:
        ```
        @closure(
            lambda result, *_: do_something_else_with(result)
        )
        def foo(bar):
            result = do_something_with(bar)
            return result
        ```

    Chaining:
        ```
        def cb1(result, *_):
            return some_transforming_callable(result)

        def cb2(result, *_):
            return another_transforming_callable(result)

        def cb3(result *_):
            return yet_another_transforming_callable(result)

        @(closure(cb1)
            .pipe(cb2)
            .pipe(cb3)
        )
        def foo(bar):
            result = do_something_with(bar)
            return result
        ```
    """
    def __init__(self, fn: Callable):
        """Instantiates a new closure.

        Args:
          fn:
            The function whose return value will be passed as the first
            argument to the next callback in the closure pipeline.
        """
        self._callbacks = [fn]

    def __call__(self, target):
        """Makes the `_Closure` class callable.

        Instantiate the `_Closure` class by calling `closure`, which is
        the class's preferred alias and comprises the only publicly
        exposed object in Pristine's closure API. See class
        documentation for detailed discussion regarding usage.
        """
        @wraps(target)
        def wrapped(*args, **kwargs):
            result = target(*args, **kwargs)
            for fn in self._callbacks:
                result = fn(result, *args, **kwargs)
            return result
        return wrapped

    def __rshift__(self, other):
        if not callable(other):
            raise TypeError("Can only chain callables with >>")
        new = _Closure(self._callbacks[0])
        new._callbacks = self._callbacks + [other]
        return new

    def pipe(self, fn) -> "_Closure":
        """Add a callback to the pipeline.

        Each callback receives (result, *args, **kwargs) and may return
        a transformed result. The final return value is passed to the
        caller.
        """
        self._callbacks.append(fn)
        return self


    def repeat(self, x: int):
        """Add the previous callback to the chain another `x` times."""
        callback = self._callbacks[-1]

        for i in range(x):
            self.pipe(callback)

        return self


    # Aliases
    do = next = then = pipe
    re = redo = rept = repeat


# Public API
closure = _Closure
