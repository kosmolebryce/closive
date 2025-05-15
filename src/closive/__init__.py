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

# Import and initialize the custom importer functionality
try:
    from . import _importer
    
    # Show welcome message
    _importer.display_welcome_message()
    
    # Create default config if needed
    _importer.create_default_config()
    
    # Load pipelines from external configuration
    pipelines = _importer.load_external_pipelines()
    for name, pipeline in pipelines.items():
        globals()[name] = pipeline
    
    # Add utility functions to the module namespace
    reload_pipelines = _importer.reload_pipelines
    save_pipeline = _importer.save_pipeline
except ImportError:
    pass  # If the custom importer is not available, proceed without it

# Update __all__ to include all exported symbols
__all__ = [
    "a",
    "add",
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
    "linfunc",
    "linplot",
    "linvis",
    "m",
    "multiply",
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
    "to_dataframe",
    "to_plot"
]
