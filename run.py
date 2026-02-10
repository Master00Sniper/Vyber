#!/usr/bin/env python3
"""Entry point for the Vyber application."""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vyber.app import VyberApp


def main():
    app = VyberApp()
    app.run()


if __name__ == "__main__":
    main()
