#!/usr/bin/env python3
"""Entry point for the Soundboard application."""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soundboard.app import SoundboardApp


def main():
    app = SoundboardApp()
    app.run()


if __name__ == "__main__":
    main()
