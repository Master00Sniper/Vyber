"""Main application controller — wires together all components."""

import logging
import os
import sys
import threading
from tkinter import filedialog, simpledialog, messagebox

import customtkinter as ctk

logger = logging.getLogger(__name__)

from vyber import IMAGES_DIR
from vyber.config import Config
from vyber.audio_engine import AudioEngine
from vyber.virtual_cable import VirtualCableManager
from vyber.sound_manager import SoundManager, SUPPORTED_EXTENSIONS
from vyber.hotkey_manager import HotkeyManager
from vyber.ui.main_window import MainWindow
from vyber.ui.settings_dialog import SettingsDialog
from vyber import vb_cable_installer
from vyber.tray_manager import TrayManager
from vyber.telemetry import send_telemetry
import updater


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

        self._install_pending = False

        # Build the GUI
        self.root = ctk.CTk()
        self.root.title("Vyber")
        w = max(1280, self.config.get("window", "width", default=1280))
        h = max(650, self.config.get("window", "height", default=650))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(1280, 650)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Set window icon
        ico_path = IMAGES_DIR / "vyber.ico"
        if ico_path.exists():
            self.root.iconbitmap(str(ico_path))

        # Create main window with callbacks
        self.main_window = MainWindow(self.root, callbacks={
            "on_play": self._on_play,
            "on_stop_all": self._on_stop_all,
            "on_add_sound": self._on_add_sound,
            "on_add_folder": self._on_add_folder,
            "on_remove_sound": self._on_remove_sound,
            "on_rename_sound": self._on_rename_sound,
            "on_set_hotkey": self._on_set_hotkey,
            "on_move_sound": self._on_move_sound,
            "on_volume_sound": self._on_volume_sound,
            "on_reorder_sound": self._on_reorder_sound,
            "on_volume_change": self._on_volume_change,
            "on_output_mode_change": self._on_output_mode_change,
            "on_add_category": self._on_add_category,
            "on_remove_category": self._on_remove_category,
            "on_open_settings": self._on_open_settings,
            "get_categories": self.sound_manager.get_categories,
        })

        # Populate tabs
        self._refresh_all_tabs()

        # Update status bar and output mode availability
        self.main_window.set_cable_status(
            self.cable_info.installed,
            self.cable_info.input_device_name
        )
        self.main_window.set_cable_available(self.cable_info.installed)

        # Set initial volume from config
        vol = self.config.get("audio", "master_volume", default=0.8)
        self.main_window.set_volume(vol)
        self.audio_engine.set_master_volume(vol)

        # Set initial output mode
        mode = self.config.get("audio", "output_mode", default="both")
        self.main_window.set_output_mode(mode)

        # Prompt VB-CABLE install if not detected
        if not self.cable_info.installed:
            self.root.after(500, self._prompt_vb_cable_install)

        # System tray icon
        tray_icon_path = IMAGES_DIR / "tray_icon.png"
        self.tray = TrayManager(
            icon_path=str(tray_icon_path),
            on_show=lambda: self.root.after(0, self._show_from_tray),
            on_quit=lambda: self.root.after(0, self._quit_from_tray),
        )
        if self.tray.available:
            self.tray.start()

        # Register hotkeys
        self._register_hotkeys()
        self.hotkey_manager.start()

        # Start periodic status update
        self._update_status()

        # Background auto-updater
        self._update_stop = threading.Event()
        self._update_thread = threading.Thread(
            target=updater.periodic_update_check,
            args=(self._update_stop, None),
            daemon=True,
        )
        self._update_thread.start()

        # Telemetry — record app launch
        send_telemetry("app_start")

    def run(self):
        """Start the application main loop."""
        try:
            self.audio_engine.start()
        except Exception as e:
            logger.warning("Audio engine start warning: %s", e)

        # Check for sample rate mismatches after streams are open
        if self.cable_info.installed:
            self.root.after(800, self._check_sample_rates)

        self.root.mainloop()

    def _on_close(self):
        """Minimize to tray on window close, or quit if tray unavailable."""
        if self.tray.available:
            self.root.withdraw()
        else:
            self._full_shutdown()

    def _show_from_tray(self):
        """Restore the window from the system tray."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_from_tray(self):
        """Quit from the tray menu."""
        self._full_shutdown()

    def _full_shutdown(self):
        """Clean shutdown — stop everything and exit."""
        self._update_stop.set()
        self.tray.stop()
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
            def _hotkey_play(fp=filepath, v=volume):
                self.audio_engine.play_sound(fp, v)
                send_telemetry("hotkey_used")
            mappings[hotkey] = _hotkey_play

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
        """Periodically update playing count and button states."""
        count = self.audio_engine.get_playing_count()
        self.main_window.set_playing_count(count)
        playing_fps = self.audio_engine.get_playing_filepaths()
        self.main_window.update_playing_states(playing_fps)
        self.root.after(200, self._update_status)

    # --- Callbacks ---

    def _on_play(self, category: str, sound_name: str):
        """Play a sound by name from a category."""
        overlap = self.config.get("preferences", "sound_overlap",
                                   default="overlap")
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                if overlap == "stop" and sound.path in self.audio_engine.get_playing_filepaths():
                    self.audio_engine.stop_sound(sound.path)
                else:
                    self.audio_engine.play_sound(sound.path, sound.volume)
                send_telemetry("sound_played")
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

    def _on_add_folder(self, category: str):
        """Open folder dialog to add all sounds in a directory."""
        folder = filedialog.askdirectory(
            title="Add Folder of Sounds",
            parent=self.root
        )
        if folder:
            added = self.sound_manager.add_sounds_from_directory(folder, category)
            if added:
                self._refresh_tab(category)
                self._register_hotkeys()

    def _on_reorder_sound(self, category: str, sound_name: str, new_index: int):
        """Reorder a sound within its category via drag-and-drop."""
        self.sound_manager.reorder_sound(category, sound_name, new_index)
        self._refresh_tab(category)

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
            sound_overlap=self.config.get("preferences", "sound_overlap",
                                           default="overlap"),
            on_save=self._apply_settings,
            on_install_vb_cable=self._start_vb_cable_install,
        )

    def _apply_settings(self, settings: dict):
        """Apply settings from the settings dialog."""
        self.config.set("audio", "output_device", settings["speaker_device"])
        self.config.set("audio", "mic_device", settings["mic_device"])
        self.config.set("audio", "mic_passthrough", settings["mic_passthrough"])
        self.config.set("hotkeys", "stop_all", settings["stop_all_hotkey"])
        self.config.set("preferences", "sound_overlap", settings["sound_overlap"])
        self.config.save()

        # Reconfigure audio
        self.audio_engine.speaker_device = settings["speaker_device"]
        self.audio_engine.mic_device = settings["mic_device"]
        self.audio_engine.mic_passthrough = settings["mic_passthrough"]

        # Restart audio with new devices
        self.audio_engine.start()

        # Re-register hotkeys with new stop-all key
        self._register_hotkeys()

    # --- VB-CABLE guided install ---

    def _prompt_vb_cable_install(self):
        """Show a dialog offering to install VB-CABLE if not detected."""
        answer = messagebox.askyesno(
            "VB-CABLE Not Detected",
            "VB-CABLE virtual audio driver is required for microphone "
            "output.\n\n"
            "Would you like to download and install it now?\n"
            "(You will need to approve an admin prompt.)",
            parent=self.root,
        )
        if answer:
            self._start_vb_cable_install()

    def _start_vb_cable_install(self):
        """Kick off the background download-and-install process."""
        if self._install_pending:
            return
        self._install_pending = True
        self.main_window.set_cable_status(False, "Installing...")

        vb_cable_installer.download_and_install(
            on_progress=lambda msg: self.root.after(
                0, self.main_window.set_cable_status, False, msg
            ),
            on_success=lambda: self.root.after(0, self._on_install_finished),
            on_error=lambda err: self.root.after(
                0, self._on_install_error, err
            ),
        )

    def _on_install_finished(self):
        """Called when the VB-CABLE installer has been launched."""
        self._install_pending = False
        messagebox.showinfo(
            "VB-CABLE Installer",
            "The VB-CABLE installer has been launched.\n\n"
            "After it finishes, please restart Vyber so the new "
            "audio device can be detected.",
            parent=self.root,
        )
        # Re-scan immediately in case the driver is already active
        self.cable_info = self.cable_manager.detect()
        if self.cable_info.installed:
            self._configure_audio()
            self.audio_engine.start()
        self.main_window.set_cable_status(
            self.cable_info.installed, self.cable_info.input_device_name
        )
        self.main_window.set_cable_available(self.cable_info.installed)

    def _on_install_error(self, error_msg: str):
        """Called when the install process fails."""
        self._install_pending = False
        self.main_window.set_cable_status(False, "")
        messagebox.showerror(
            "Installation Failed",
            f"{error_msg}\n\n"
            "You can install VB-CABLE manually from:\n"
            "https://vb-audio.com/Cable/",
            parent=self.root,
        )

    # --- Sample rate mismatch detection ---

    def _check_sample_rates(self):
        """Check for sample rate mismatches and alert the user."""
        from vyber.audio_engine import SAMPLE_RATE
        mismatches = self.audio_engine.check_sample_rate_mismatches()
        if not mismatches:
            return

        device_lines = "\n".join(
            f"  \u2022 {name} ({label}) \u2014 currently {rate} Hz"
            for label, name, rate in mismatches
        )
        answer = messagebox.askyesno(
            "Audio Sample Rate Mismatch",
            f"The following audio devices are not set to {SAMPLE_RATE} Hz, "
            f"which may cause robotic or distorted audio:\n\n"
            f"{device_lines}\n\n"
            f"To fix this:\n"
            f"1. Open Windows Sound settings\n"
            f"2. Find each device above \u2192 Properties \u2192 Advanced\n"
            f"3. Set the sample rate to {SAMPLE_RATE} Hz\n\n"
            f"Would you like to open Windows Sound settings now?",
            parent=self.root,
        )
        if answer:
            self._open_sound_settings()

    @staticmethod
    def _open_sound_settings():
        """Open the Windows Sound control panel."""
        try:
            os.startfile("mmsys.cpl")
        except Exception:
            try:
                import subprocess
                subprocess.Popen(["control", "mmsys.cpl"])
            except Exception as e:
                logger.error("Failed to open Sound settings: %s", e)
