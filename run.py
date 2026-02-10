#!/usr/bin/env python3
"""Entry point for the Vyber application."""

import sys
import os
import logging

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vyber.config import DATA_DIR, LOG_FILE


def _setup_logging():
    """Configure logging to file and console."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main():
    _setup_logging()
    logger = logging.getLogger("vyber")
    logger.info("Starting Vyber — data dir: %s", DATA_DIR)

    from vyber.app import VyberApp
    app = VyberApp()
    app.run()


if __name__ == "__main__":
    main()
