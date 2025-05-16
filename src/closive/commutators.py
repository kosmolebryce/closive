"""Commutators
==============

A *commutator* is the ordinary Python function you decorate with a Closive
pipeline.  In many exploratory or glue-code scenarios you repeatedly need the
same handful of “do-nothing” or “peek-only” wrappers.  This module provides
those generic helpers so that users can start composing pipelines immediately
without writing boiler-plate every time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Tuple, TypeVar

T = TypeVar("T")          # value flowing through the pipeline
U = TypeVar("U")          # value returned by a tap function

# --------------------------------------------------------------------------- #
# Basic / passthrough commutators                                             #
# --------------------------------------------------------------------------- #
def identity(x: T, *args: Any, **kw: Any) -> T:
    """
    Return *x* unchanged.

    The most minimal commutator – handy when you only want to attach a pipeline
    for its side-effects or error-handling logic.
    """
    return x


def noop(*args: Any, **kw: Any) -> None:
    """
    Do absolutely nothing and return ``None``.

    Useful when you want to trigger a pipeline that produces side-effects but
    whose own entry-point has no meaningful return value.
    """
    return None


# --------------------------------------------------------------------------- #
# Introspection helpers                                                       #
# --------------------------------------------------------------------------- #
def tap(fn: Callable[[T], U]) -> Callable[[T], T]:
    """
    Create a commutator that *peeks* at the value with *fn* (for logging,
    metrics, debugging…) and then forwards the original value unchanged.

    Example
    -------
    >>> from closive import commutators as cm
    >>> @cm.tap(print)           # will print the raw input value
    ... def passthrough(x): ...
    """
    def _inner(x: T, *a: Any, **k: Any) -> T:
        fn(x)
        return x

    _inner.__name__ = f"tap_{getattr(fn, '__name__', 'fn')}"
    _inner.__doc__ = (
        f"Invoke {fn!r} for its side-effect and return the input value unchanged."
    )
    return _inner


def log(level: int = logging.INFO,
        logger: logging.Logger | None = None) -> Callable[[T], T]:
    """
    Produce a commutator that logs its input and then returns it unchanged.

    Parameters
    ----------
    level   : logging level (default: INFO)
    logger  : explicit logger; defaults to ``logging.getLogger('closive')``

    Example
    -------
    >>> @commutators.log()                # logs at INFO
    ... def passthrough(x): ...
    """
    _logger = logger or logging.getLogger("closive")

    def _inner(x: T, *a: Any, **k: Any) -> T:
        _logger.log(level, "Closive commutator value: %r", x)
        return x

    _inner.__name__ = f"log_{logging.getLevelName(level).lower()}"
    return _inner


# --------------------------------------------------------------------------- #
# Utility helpers                                                             #
# --------------------------------------------------------------------------- #
def as_tuple(x: T, *a: Any, **k: Any) -> Tuple[T, T]:
    """
    Return ``(x, x)``.

    Lets you keep a copy of the raw input alongside downstream pipeline
    results without writing custom wrappers.
    """
    return x, x


def ignore_return(x: T, *a: Any, **k: Any) -> T:           # alias for clarity
    """
    Equivalent to ``identity`` – provided only for semantic variety when the
    function’s *name* should express “I do not care about the value”.
    """
    return x
    