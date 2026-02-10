"""Sound library management — loading, organizing, and tracking sounds."""

import os
from pathlib import Path

from vyber.config import Config

SUPPORTED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}


class SoundEntry:
    """Represents a single sound in the library."""

    def __init__(self, name: str, path: str, hotkey: str | None = None,
                 volume: float = 1.0):
        self.name = name
        self.path = path
        self.hotkey = hotkey
        self.volume = volume

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "hotkey": self.hotkey,
            "volume": self.volume
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoundEntry":
        return cls(
            name=data.get("name", "Unknown"),
            path=data.get("path", ""),
            hotkey=data.get("hotkey"),
            volume=data.get("volume", 1.0)
        )

    def exists(self) -> bool:
        return os.path.isfile(self.path)


class SoundManager:
    """Manages the sound library — categories, adding/removing sounds."""

    def __init__(self, config: Config):
        self.config = config
        self.categories: dict[str, list[SoundEntry]] = {}
        self._load_from_config()

    def _load_from_config(self):
        """Load sound library from config."""
        self.categories.clear()
        for category in self.config.get_categories():
            sounds_data = self.config.get_sounds_in_category(category)
            self.categories[category] = [
                SoundEntry.from_dict(s) for s in sounds_data
            ]

    def save_to_config(self):
        """Persist current sound library to config."""
        categories_dict = {}
        for cat_name, sounds in self.categories.items():
            categories_dict[cat_name] = [s.to_dict() for s in sounds]
        self.config.data["categories"] = categories_dict
        self.config.save()

    def get_categories(self) -> list[str]:
        return list(self.categories.keys())

    def get_sounds(self, category: str) -> list[SoundEntry]:
        return self.categories.get(category, [])

    def add_category(self, name: str) -> bool:
        """Add a new category. Returns False if it already exists."""
        if name in self.categories:
            return False
        self.categories[name] = []
        self.save_to_config()
        return True

    def remove_category(self, name: str) -> bool:
        """Remove a category. Cannot remove the last one."""
        if name not in self.categories or len(self.categories) <= 1:
            return False
        del self.categories[name]
        self.save_to_config()
        return True

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Rename a category."""
        if old_name not in self.categories or new_name in self.categories:
            return False
        sounds = self.categories.pop(old_name)
        self.categories[new_name] = sounds
        self.save_to_config()
        return True

    def add_sound(self, category: str, filepath: str,
                  name: str | None = None) -> SoundEntry | None:
        """Add a sound file to a category."""
        if category not in self.categories:
            return None

        ext = Path(filepath).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return None

        if name is None:
            name = Path(filepath).stem

        # Ensure unique name within category
        existing_names = {s.name for s in self.categories[category]}
        base_name = name
        counter = 1
        while name in existing_names:
            name = f"{base_name} ({counter})"
            counter += 1

        entry = SoundEntry(name=name, path=os.path.abspath(filepath))
        self.categories[category].append(entry)
        self.save_to_config()
        return entry

    def remove_sound(self, category: str, sound_name: str) -> bool:
        """Remove a sound from a category."""
        if category not in self.categories:
            return False
        before = len(self.categories[category])
        self.categories[category] = [
            s for s in self.categories[category] if s.name != sound_name
        ]
        removed = len(self.categories[category]) < before
        if removed:
            self.save_to_config()
        return removed

    def rename_sound(self, category: str, old_name: str, new_name: str) -> bool:
        """Rename a sound within a category."""
        sounds = self.categories.get(category, [])
        existing = {s.name for s in sounds}
        if new_name in existing:
            return False
        for sound in sounds:
            if sound.name == old_name:
                sound.name = new_name
                self.save_to_config()
                return True
        return False

    def move_sound(self, from_category: str, to_category: str,
                   sound_name: str) -> bool:
        """Move a sound from one category to another."""
        if from_category not in self.categories or to_category not in self.categories:
            return False
        sound = None
        for s in self.categories[from_category]:
            if s.name == sound_name:
                sound = s
                break
        if sound is None:
            return False
        self.categories[from_category].remove(sound)
        self.categories[to_category].append(sound)
        self.save_to_config()
        return True

    def set_hotkey(self, category: str, sound_name: str,
                   hotkey: str | None) -> bool:
        """Set or clear the hotkey for a sound."""
        for sound in self.categories.get(category, []):
            if sound.name == sound_name:
                sound.hotkey = hotkey
                self.save_to_config()
                return True
        return False

    def set_sound_volume(self, category: str, sound_name: str,
                         volume: float) -> bool:
        """Set the volume for a sound (0.0 to 1.0)."""
        for sound in self.categories.get(category, []):
            if sound.name == sound_name:
                sound.volume = max(0.0, min(1.0, volume))
                self.save_to_config()
                return True
        return False

    def reorder_sound(self, category: str, sound_name: str,
                      new_index: int) -> bool:
        """Move a sound to a new position within its category."""
        sounds = self.categories.get(category, [])
        sound = next((s for s in sounds if s.name == sound_name), None)
        if sound is None:
            return False
        sounds.remove(sound)
        sounds.insert(min(new_index, len(sounds)), sound)
        self.save_to_config()
        return True

    def get_all_hotkey_mappings(self) -> dict[str, tuple[str, SoundEntry]]:
        """Get all hotkey -> (category, sound) mappings."""
        mappings = {}
        for cat, sounds in self.categories.items():
            for sound in sounds:
                if sound.hotkey:
                    mappings[sound.hotkey] = (cat, sound)
        return mappings

    def add_sounds_from_directory(self, directory: str,
                                  category: str) -> list[SoundEntry]:
        """Scan a directory and add all supported audio files."""
        added = []
        for filename in sorted(os.listdir(directory)):
            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue
            ext = Path(filename).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                entry = self.add_sound(category, filepath)
                if entry:
                    added.append(entry)
        return added
