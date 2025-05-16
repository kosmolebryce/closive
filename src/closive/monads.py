"""Monads

This module re-exports from the `returns.result` subpackage the
`Results` monad and its concrete implementations, `Success` and
`Failure`. 
"""
# Dependency glue
from returns.result import (
    Result as _ReturnsResult,
    Success as _Success,
    Failure as _Failure,
)

# Public aliases
from typing import TypeAlias

Result:  TypeAlias = _ReturnsResult   # mypy / pyright get proper types
Success = _Success
Failure = _Failure