"""Main application controller — wires together all components."""

import os
import sys
import threading
from tkinter import filedialog, simpledialog, messagebox

import customtkinter as ctk

from vyber.config import Config
from vyber.audio_engine import AudioEngine
from vyber.virtual_cable import VirtualCableManager
from vyber.sound_manager import SoundManager, SUPPORTED_EXTENSIONS
from vyber.hotkey_manager import HotkeyManager
from vyber.ui.main_window import MainWindow
from vyber.ui.settings_dialog import SettingsDialog


class VyberApp:
    """Top-level application controller."""

    def __init__(self):
        self.config = Config()
        self.audio_engine = AudioEngine()
        self.cable_manager = VirtualCableManager()
        self.sound_manager = SoundManager(self.config)
        self.hotkey_manager = HotkeyManager()

        # Detect VB-CABLE
        self.cable_info = self.cable_manager.detect()

        # Configure audio engine from config/detected devices
        self._configure_audio()

        # Build the GUI
        self.root = ctk.CTk()
        self.root.title("Vyber")
        self.root.geometry(
            f"{self.config.get('window', 'width', default=900)}x"
            f"{self.config.get('window', 'height', default=600)}"
        )
        self.root.minsize(700, 400)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Create main window with callbacks
        self.main_window = MainWindow(self.root, callbacks={
            "on_play": self._on_play,
            "on_stop_all": self._on_stop_all,
            "on_add_sound": self._on_add_sound,
            "on_remove_sound": self._on_remove_sound,
            "on_rename_sound": self._on_rename_sound,
            "on_set_hotkey": self._on_set_hotkey,
            "on_move_sound": self._on_move_sound,
            "on_volume_sound": self._on_volume_sound,
            "on_volume_change": self._on_volume_change,
            "on_output_mode_change": self._on_output_mode_change,
            "on_add_category": self._on_add_category,
            "on_remove_category": self._on_remove_category,
            "on_open_settings": self._on_open_settings,
            "get_categories": self.sound_manager.get_categories,
        })

        # Populate tabs
        self._refresh_all_tabs()

        # Update status bar
        self.main_window.set_cable_status(
            self.cable_info.installed,
            self.cable_info.input_device_name
        )

        # Set initial volume from config
        vol = self.config.get("audio", "master_volume", default=0.8)
        self.main_window.set_volume(vol)
        self.audio_engine.set_master_volume(vol)

        # Set initial output mode
        mode = self.config.get("audio", "output_mode", default="both")
        self.main_window.set_output_mode(mode)

        # Register hotkeys
        self._register_hotkeys()
        self.hotkey_manager.start()

        # Start periodic status update
        self._update_status()

    def run(self):
        """Start the application main loop."""
        try:
            self.audio_engine.start()
        except Exception as e:
            print(f"Audio engine start warning: {e}")

        self.root.mainloop()

    def _on_close(self):
        """Clean shutdown."""
        self.hotkey_manager.stop()
        self.audio_engine.stop()
        self.config.save()
        self.root.destroy()

    def _configure_audio(self):
        """Configure audio engine devices from config and detected cables."""
        speaker = self.config.get("audio", "output_device")
        mic = self.config.get("audio", "mic_device")
        mode = self.config.get("audio", "output_mode", default="both")
        passthrough = self.config.get("audio", "mic_passthrough", default=True)

        self.audio_engine.speaker_device = speaker
        self.audio_engine.mic_device = mic
        self.audio_engine.output_mode = mode
        self.audio_engine.mic_passthrough = passthrough

        if self.cable_info.installed:
            self.audio_engine.virtual_cable_device = self.cable_info.input_device_index
            self.config.set("audio", "virtual_cable_device",
                           self.cable_info.input_device_index)

    def _register_hotkeys(self):
        """Register all sound hotkeys and the stop-all hotkey."""
        mappings = {}
        for hotkey, (cat, sound) in self.sound_manager.get_all_hotkey_mappings().items():
            filepath = sound.path
            volume = sound.volume
            mappings[hotkey] = lambda fp=filepath, v=volume: self.audio_engine.play_sound(fp, v)

        stop_key = self.config.get("hotkeys", "stop_all", default="escape")
        self.hotkey_manager.rebind_all(
            mappings,
            stop_all_hotkey=stop_key,
            stop_all_callback=self._on_stop_all
        )

    def _refresh_all_tabs(self):
        """Rebuild all category tabs with current sounds."""
        categories = {}
        for cat in self.sound_manager.get_categories():
            categories[cat] = self.sound_manager.get_sounds(cat)
        self.main_window.refresh_all(categories)

    def _refresh_tab(self, category: str):
        """Refresh a single category tab."""
        sounds = self.sound_manager.get_sounds(category)
        self.main_window.refresh_category(category, sounds)

    def _update_status(self):
        """Periodically update playing count in the status bar."""
        count = self.audio_engine.get_playing_count()
        self.main_window.set_playing_count(count)
        self.root.after(200, self._update_status)

    # --- Callbacks ---

    def _on_play(self, category: str, sound_name: str):
        """Play a sound by name from a category."""
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                self.audio_engine.play_sound(sound.path, sound.volume)
                break

    def _on_stop_all(self):
        self.audio_engine.stop_all()

    def _on_add_sound(self, category: str):
        """Open file dialog to add a sound."""
        filetypes = [
            ("Audio Files", " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)),
            ("All Files", "*.*")
        ]
        paths = filedialog.askopenfilenames(
            title="Add Sounds",
            filetypes=filetypes,
            parent=self.root
        )
        for path in paths:
            self.sound_manager.add_sound(category, path)
        if paths:
            self._refresh_tab(category)
            self._register_hotkeys()

    def _on_remove_sound(self, category: str, sound_name: str):
        """Remove a sound after confirmation."""
        if messagebox.askyesno("Remove Sound",
                               f"Remove '{sound_name}' from {category}?",
                               parent=self.root):
            self.sound_manager.remove_sound(category, sound_name)
            self._refresh_tab(category)
            self._register_hotkeys()

    def _on_rename_sound(self, category: str, sound_name: str):
        """Rename a sound via input dialog."""
        new_name = simpledialog.askstring(
            "Rename Sound", f"New name for '{sound_name}':",
            parent=self.root
        )
        if new_name and new_name.strip():
            self.sound_manager.rename_sound(category, sound_name,
                                            new_name.strip())
            self._refresh_tab(category)

    def _on_set_hotkey(self, category: str, sound_name: str):
        """Set a hotkey for a sound via input dialog."""
        current = None
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                current = sound.hotkey
                break

        prompt = f"Hotkey for '{sound_name}'"
        if current:
            prompt += f" (current: {current})"
        prompt += ":\n\nExamples: ctrl+1, f5, shift+a\nLeave empty to clear."

        hotkey = simpledialog.askstring("Set Hotkey", prompt, parent=self.root)
        if hotkey is not None:  # None means cancelled
            hotkey = hotkey.strip() or None
            self.sound_manager.set_hotkey(category, sound_name, hotkey)
            self._refresh_tab(category)
            self._register_hotkeys()

    def _on_move_sound(self, category: str, sound_name: str):
        """Move a sound to another category."""
        categories = [c for c in self.sound_manager.get_categories()
                      if c != category]
        if not categories:
            return

        # Simple dialog to pick target category
        target = simpledialog.askstring(
            "Move Sound",
            f"Move '{sound_name}' to which category?\n\n"
            f"Available: {', '.join(categories)}",
            parent=self.root
        )
        if target and target in self.sound_manager.categories:
            self.sound_manager.move_sound(category, target, sound_name)
            self._refresh_tab(category)
            self._refresh_tab(target)

    def _on_volume_sound(self, category: str, sound_name: str):
        """Adjust per-sound volume."""
        current = 1.0
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                current = sound.volume
                break

        value = simpledialog.askfloat(
            "Sound Volume",
            f"Volume for '{sound_name}' (0.0 to 1.0):",
            initialvalue=current,
            minvalue=0.0,
            maxvalue=1.0,
            parent=self.root
        )
        if value is not None:
            self.sound_manager.set_sound_volume(category, sound_name, value)

    def _on_volume_change(self, value: float):
        """Master volume changed."""
        self.audio_engine.set_master_volume(value)
        self.config.set("audio", "master_volume", value)

    def _on_output_mode_change(self, mode: str):
        """Output mode changed."""
        self.audio_engine.set_output_mode(mode)
        self.config.set("audio", "output_mode", mode)

    def _on_add_category(self):
        """Add a new category."""
        name = simpledialog.askstring("New Category", "Category name:",
                                      parent=self.root)
        if name and name.strip():
            if self.sound_manager.add_category(name.strip()):
                self._refresh_all_tabs()

    def _on_remove_category(self, name: str):
        """Remove a category."""
        if messagebox.askyesno("Remove Category",
                               f"Remove category '{name}' and all its sounds?",
                               parent=self.root):
            if self.sound_manager.remove_category(name):
                self._refresh_all_tabs()

    def _on_open_settings(self):
        """Open the settings dialog."""
        output_devices = self.cable_manager.get_all_output_devices()
        input_devices = self.cable_manager.get_all_input_devices()

        SettingsDialog(
            self.root,
            output_devices=output_devices,
            input_devices=input_devices,
            cable_installed=self.cable_info.installed,
            current_speaker=self.audio_engine.speaker_device,
            current_mic=self.audio_engine.mic_device,
            current_stop_hotkey=self.config.get("hotkeys", "stop_all",
                                                 default="escape"),
            mic_passthrough=self.audio_engine.mic_passthrough,
            on_save=self._apply_settings
        )

    def _apply_settings(self, settings: dict):
        """Apply settings from the settings dialog."""
        self.config.set("audio", "output_device", settings["speaker_device"])
        self.config.set("audio", "mic_device", settings["mic_device"])
        self.config.set("audio", "mic_passthrough", settings["mic_passthrough"])
        self.config.set("hotkeys", "stop_all", settings["stop_all_hotkey"])
        self.config.save()

        # Reconfigure audio
        self.audio_engine.speaker_device = settings["speaker_device"]
        self.audio_engine.mic_device = settings["mic_device"]
        self.audio_engine.mic_passthrough = settings["mic_passthrough"]

        # Restart audio with new devices
        self.audio_engine.start()

        # Re-register hotkeys with new stop-all key
        self._register_hotkeys()
