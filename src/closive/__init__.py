"""Closive Initialization

This module exposes the public API for Closive, 
a first-class solution for callback-heavy control flows.
"""

# Expose only the clean factory function
from .closures import closure

__all__ = ["closure"]