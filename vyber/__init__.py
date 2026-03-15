"""Vyber — Play audio through speakers and virtual microphone."""

import os as _os
from pathlib import Path as _Path

__version__ = "0.1.5"

# Project root (parent of the vyber package directory)
ROOT_DIR = _Path(_os.path.dirname(_os.path.abspath(__file__))).parent
IMAGES_DIR = ROOT_DIR / "images"
