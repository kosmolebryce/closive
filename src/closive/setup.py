"""Setup script for the closive package."""

from setuptools import setup, find_packages
import os
from pathlib import Path

# Create the default configuration directory
config_dir = Path.home() / ".local" / "share" / "closive"
config_dir.mkdir(parents=True, exist_ok=True)

# Define package metadata
setup(
    name="closive",
    version="0.2.0",
    description="A first-class solution for callback-heavy control flows",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "pyyaml>=5.1",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
