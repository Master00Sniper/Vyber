"""Configuration management for the Vyber application."""

import json
import os
import sys
from pathlib import Path
from typing import Any


def _get_data_dir() -> Path:
    """Return the Vyber data directory, platform-appropriate.

    Windows: %APPDATA%\\Vyber   (e.g. C:\\Users\\<user>\\AppData\\Roaming\\Vyber)
    Other:   ~/.vyber
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Vyber"
    return Path.home() / ".vyber"


# Default config / data directory
DATA_DIR = _get_data_dir()
CONFIG_DIR = DATA_DIR
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = DATA_DIR / "vyber_log.txt"

DEFAULT_CONFIG = {
    "sounds_directory": "",
    "categories": {
        "General": []
    },
    "hotkeys": {
        "stop_all": "escape"
    },
    "audio": {
        "output_device": None,
        "mic_device": None,
        "virtual_cable_device": None,
        "output_mode": "both",  # "speakers", "mic", "both"
        "master_volume": 0.8,
        "mic_passthrough": True
    },
    "preferences": {
        "sound_overlap": "overlap"  # "overlap" or "stop"
    },
    "window": {
        "width": 1100,
        "height": 650
    }
}


class Config:
    """Manages application configuration with JSON persistence."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or CONFIG_FILE
        self.data: dict[str, Any] = {}
        self.load()

    def load(self):
        """Load config from disk, falling back to defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    saved = json.load(f)
                # Merge saved config over defaults so new keys get defaults
                self.data = self._deep_merge(DEFAULT_CONFIG, saved)
            except (json.JSONDecodeError, IOError):
                self.data = dict(DEFAULT_CONFIG)
        else:
            self.data = dict(DEFAULT_CONFIG)

    def save(self):
        """Persist current config to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get a nested config value. Example: config.get('audio', 'master_volume')"""
        value = self.data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, *keys_and_value: Any):
        """Set a nested config value. Last argument is the value.
        Example: config.set('audio', 'master_volume', 0.5)
        """
        if len(keys_and_value) < 2:
            raise ValueError("Need at least one key and a value")
        keys = keys_and_value[:-1]
        value = keys_and_value[-1]
        target = self.data
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def get_sounds_in_category(self, category: str) -> list[dict]:
        """Get all sounds in a category."""
        categories = self.data.get("categories", {})
        return categories.get(category, [])

    def get_categories(self) -> list[str]:
        """Get list of category names."""
        return list(self.data.get("categories", {}).keys())

    def add_category(self, name: str):
        """Add a new sound category."""
        if "categories" not in self.data:
            self.data["categories"] = {}
        if name not in self.data["categories"]:
            self.data["categories"][name] = []

    def remove_category(self, name: str):
        """Remove a category. Cannot remove the last one."""
        categories = self.data.get("categories", {})
        if len(categories) <= 1:
            return
        categories.pop(name, None)

    def add_sound(self, category: str, sound: dict):
        """Add a sound to a category.
        Sound dict: {"name": str, "path": str, "hotkey": str|None, "volume": float}
        """
        if category not in self.data.get("categories", {}):
            self.add_category(category)
        self.data["categories"][category].append(sound)

    def remove_sound(self, category: str, sound_name: str):
        """Remove a sound from a category by name."""
        sounds = self.data.get("categories", {}).get(category, [])
        self.data["categories"][category] = [
            s for s in sounds if s.get("name") != sound_name
        ]

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge override into base, returning a new dict."""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
