"""Closive Initialization

This module exposes the public API for Closive, 
a first-class solution for callback-heavy control flows.
"""

# Expose the public API
from .closures import (
    add, closure, cube, cuberoot, dataframe, divide, exponentiate, linfunc,
    linvis, linplot, multiply, partial, plot, root, square, squareroot,
    subtract, to_dataframe, to_plot
)

from .commutators import as_tuple, identity, ignore_return, log, noop, tap
from .monads import Result, Success, Failure
from .types import AwareTransformer, NaiveTransformer, Pipeline

# Define aliases
c = closure

a = add
s = subtract
m = multiply
d = divide

e = exponentiate
cb = cube
cbrt = cuberoot
sq = square
sqrt = squareroot
r = root

# Import and initialize the custom importer functionality.
try:
    from . import _importer
    
    # Show the welcome message.
    _importer.display_welcome_message()
    
    # Create a default config file, if needed.
    _importer.create_default_config()
    
    # Load pipelines from external configuration.
    pipelines = _importer.load_external_pipelines()
    for name, pipeline in pipelines.items():
        globals()[name] = pipeline
    
    # Add utility functions to the module namespace.
    reload_pipelines = _importer.reload_pipelines
    save_pipeline = _importer.save_pipeline
except ImportError:
    pass  # If the custom importer is not available, proceed without it


__all__ = [
    # Monads, re-exported from `returns.result`
    "Result",
    "Success",
    "Failure",

    # Closive: custom typedefs
    "AwareTransformer",
    "NaiveTransformer",
    "Pipeline",

    # Closive: functions/methods
    "a",
    "add",
    "as_tuple",
    "c",
    "cb",
    "cbrt",
    "closure",
    "cube",
    "cuberoot",
    "d",
    "dataframe",
    "divide",
    "e",
    "exponentiate",
    "identity",
    "ignore_return",
    "linfunc",
    "linplot",
    "linvis",
    "log",
    "m",
    "multiply",
    "noop",
    "r",
    "reload_pipelines",
    "root",
    "partial",
    "plot",
    "s",
    "sq",
    "sqrt",
    "square",
    "subtract",
    "save_pipeline",
    "tap",
    "to_dataframe",
    "to_plot"
]
