"""Type Definitions

This module surfaces the API for Closive's typing infrastructure.
"""

from typing import Callable, TypeVar, Generic
from returns.result import Result

InT  = TypeVar("InT")
OutT = TypeVar("OutT")
ErrT = TypeVar("ErrT", bound=Exception)

# (a) A plain “transformer”: value → value
NaiveTransformer = Callable[[InT], OutT]

# (b) A Result-aware transformer: Result → Result
AwareTransformer = Callable[[Result[InT, ErrT]], Result[OutT, ErrT]]

# (c) A full pipeline that you hand back to the user
try:
    from typing import TypeAlias
    Pipeline: TypeAlias = "_Pipeline[InT, OutT, ErrT]"
except ImportError:
    Pipeline = "_Pipeline"