"""Main application controller — wires together all components."""

import ctypes
import logging
import os
from pathlib import Path
import platform
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

import customtkinter as ctk
import requests

logger = logging.getLogger(__name__)

# Dark background color matching CTk dark theme
_DARK_BG = "#2b2b2b"


def _set_dark_title_bar(window):
    """Set the Windows title bar to dark mode (Windows 10 20H1+)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass

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
        logger.info("VB-CABLE installed: %s", self.cable_info.installed)
        self._configure_audio()

        self._install_pending = False

        # Build the GUI
        self.root = ctk.CTk()
        self.root.title("Vyber")
        w = max(1070, self.config.get("window", "width", default=1070))
        h = max(650, self.config.get("window", "height", default=650))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(1070, 650)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Set window icon
        self._ico_path = IMAGES_DIR / "vyber.ico"
        if self._ico_path.exists():
            self.root.iconbitmap(str(self._ico_path))

        # Create main window with callbacks
        self.main_window = MainWindow(self.root, callbacks={
            "on_play": self._on_play,
            "on_stop_all": self._on_stop_all,
            "on_add_sound": self._on_add_sound,
            "on_add_folder": self._on_add_folder,
            "on_remove_sound": self._on_remove_sound,
            "on_delete_file": self._on_delete_file,
            "on_rename_sound": self._on_rename_sound,
            "on_rename_file": self._on_rename_file,
            "on_set_hotkey": self._on_set_hotkey,
            "on_move_sound": self._on_move_sound,
            "on_volume_sound": self._on_volume_sound,
            "on_reorder_sound": self._on_reorder_sound,
            "on_volume_change": self._on_volume_change,
            "on_output_mode_change": self._on_output_mode_change,
            "on_add_category": self._on_add_category,
            "on_remove_category": self._on_remove_category,
            "on_clear_category": self._on_clear_category,
            "on_open_settings": self._on_open_settings,
            "on_discord_guide": self._on_discord_guide,
            "on_refresh_audio": self._on_refresh_audio,
            "on_help": self._on_help,
            "on_about": self._on_about,
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
        vol = self.config.get("audio", "master_volume", default=0.5)
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

    def _setup_dialog(self, dialog):
        """Finish a dialog: set icon, center, render, then show without flash.

        Dialogs must be created with tk.Toplevel + withdraw() so this
        method can set the icon while hidden, force-render all CTk
        widgets, and only then deiconify for a flash-free appearance.
        """
        # Set icon while still hidden
        if self._ico_path.exists():
            try:
                dialog.iconbitmap(str(self._ico_path))
            except Exception:
                pass

        # Force full render of all CTk widgets while hidden
        dialog.update()

        # Center on main window using rendered size
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dialog.geometry(f"+{x}+{y}")

        # Show the fully-rendered window
        dialog.deiconify()
        _set_dark_title_bar(dialog)
        dialog.lift()
        dialog.focus_force()

    def _configure_audio(self):
        """Configure audio engine devices from config and detected cables."""
        speaker = self.config.get("audio", "output_device")
        mic = self.config.get("audio", "mic_device")
        mode = self.config.get("audio", "output_mode", default="both")
        passthrough = self.config.get("audio", "mic_passthrough", default=True)
        logger.info("Audio config: speaker=%s, mic=%s, mode=%s, passthrough=%s",
                     speaker, mic, mode, passthrough)

        self.audio_engine.speaker_device = speaker
        self.audio_engine.mic_device = mic
        self.audio_engine.output_mode = mode
        self.audio_engine.mic_passthrough = passthrough

        if self.cable_info.installed:
            self.audio_engine.virtual_cable_device = self.cable_info.input_device_index
            self.config.set("audio", "virtual_cable_device",
                           self.cable_info.input_device_index)

    def _on_refresh_audio(self):
        """Re-detect audio devices and restart streams."""
        logger.info("Refreshing audio devices...")
        self.cable_info = self.cable_manager.detect()
        self._configure_audio()
        self.audio_engine.start()
        self.main_window.set_cable_status(
            self.cable_info.installed, self.cable_info.input_device_name
        )
        self.main_window.set_cable_available(self.cable_info.installed)
        logger.info("Audio devices refreshed — VB-CABLE: %s, speaker: %s, mic: %s",
                     self.cable_info.installed,
                     self.audio_engine.speaker_device,
                     self.audio_engine.mic_device)

    def _register_hotkeys(self):
        """Register all sound hotkeys and the stop-all hotkey."""
        mappings = {}
        for hotkey, (cat, sound) in self.sound_manager.get_all_hotkey_mappings().items():
            filepath = sound.path
            volume = sound.volume
            def _hotkey_play(fp=filepath, v=volume):
                self.audio_engine.play_sound(fp, v)
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
        playing_remaining = self.audio_engine.get_playing_remaining()
        self.main_window.update_playing_states(playing_remaining)
        self.root.after(200, self._update_status)

    # --- Callbacks ---

    def _on_play(self, category: str, sound_name: str):
        """Play a sound by name from a category."""
        overlap = self.config.get("preferences", "sound_overlap",
                                   default="stop")
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                if overlap == "stop" and sound.path in self.audio_engine.get_playing_filepaths():
                    logger.info("Stopping sound: %s (overlap=stop)", sound_name)
                    self.audio_engine.stop_sound(sound.path)
                else:
                    logger.info("Playing sound: %s [%s] vol=%.0f%%",
                                sound_name, category, sound.volume * 100)
                    self.audio_engine.play_sound(sound.path, sound.volume)
                break

    def _on_stop_all(self):
        logger.info("Stop all sounds")
        self.audio_engine.stop_all()

    @staticmethod
    def _default_sound_dir() -> str:
        """Return the best default directory for file dialogs (Music > Documents > Home)."""
        home = Path.home()
        for folder in (home / "Music", home / "Documents", home):
            if folder.is_dir():
                return str(folder)
        return str(home)

    def _on_add_sound(self, category: str):
        """Open file dialog to add a sound."""
        filetypes = [
            ("Audio Files", " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)),
            ("All Files", "*.*")
        ]
        paths = filedialog.askopenfilenames(
            title="Add Sounds",
            filetypes=filetypes,
            initialdir=self._default_sound_dir(),
            parent=self.root
        )
        for path in paths:
            self.sound_manager.add_sound(category, path)
        if paths:
            logger.info("Added %d sound(s) to '%s'", len(paths), category)
            self._refresh_tab(category)
            self._register_hotkeys()

    def _on_add_folder(self, category: str):
        """Open folder dialog to add all sounds in a directory."""
        folder = filedialog.askdirectory(
            title="Add Folder of Sounds",
            initialdir=self._default_sound_dir(),
            parent=self.root
        )
        if folder:
            added = self.sound_manager.add_sounds_from_directory(folder, category)
            if added:
                logger.info("Added %d sound(s) from folder to '%s'",
                            len(added), category)
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

    def _on_delete_file(self, category: str, sound_name: str):
        """Remove a sound and delete its file from disk."""
        # Find the file path before removing
        filepath = None
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                filepath = sound.path
                break
        if not filepath:
            return

        if messagebox.askyesno(
            "Delete Sound File",
            f"Remove '{sound_name}' and permanently delete the file?\n\n"
            f"{filepath}\n\n"
            f"This cannot be undone.",
            parent=self.root
        ):
            self.sound_manager.remove_sound(category, sound_name)
            self.audio_engine.stop_sound(filepath)
            self.audio_engine.invalidate_cache(filepath)
            try:
                os.remove(filepath)
                logger.info("Deleted file: %s", filepath)
            except OSError as e:
                logger.error("Failed to delete file '%s': %s", filepath, e)
                messagebox.showerror("Delete Failed",
                                     f"Could not delete file:\n{e}",
                                     parent=self.root)
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

    def _on_rename_file(self, category: str, sound_name: str):
        """Rename a sound and its underlying file on disk."""
        # Find the current file path and extension
        filepath = None
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                filepath = sound.path
                break
        if not filepath:
            return

        new_name = simpledialog.askstring(
            "Rename Sound & File", f"New name for '{sound_name}':",
            parent=self.root
        )
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()

        # Build new file path: same directory and extension, new name
        directory = os.path.dirname(filepath)
        ext = os.path.splitext(filepath)[1]
        new_filepath = os.path.join(directory, new_name + ext)

        if os.path.exists(new_filepath) and new_filepath != filepath:
            messagebox.showerror("Rename Failed",
                                 f"A file named '{new_name}{ext}' already exists.",
                                 parent=self.root)
            return

        try:
            os.rename(filepath, new_filepath)
            logger.info("Renamed file: %s -> %s", filepath, new_filepath)
        except OSError as e:
            logger.error("Failed to rename file '%s': %s", filepath, e)
            messagebox.showerror("Rename Failed",
                                 f"Could not rename file:\n{e}",
                                 parent=self.root)
            return

        # Update the sound entry and caches
        self.audio_engine.stop_sound(filepath)
        self.audio_engine.invalidate_cache(filepath)
        self.sound_manager.rename_sound(category, sound_name, new_name)
        self.sound_manager.update_sound_path(category, new_name, new_filepath)
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

    def _on_move_sound(self, category: str, sound_name: str,
                       target: str | None = None):
        """Move a sound to another category."""
        if not target:
            return
        if target not in self.sound_manager.categories:
            return
        self.sound_manager.move_sound(category, target, sound_name)
        self._refresh_tab(category)
        self._refresh_tab(target)

    def _on_volume_sound(self, category: str, sound_name: str):
        """Adjust per-sound volume with a slider dialog (0–200%)."""
        current = 1.0
        for sound in self.sound_manager.get_sounds(category):
            if sound.name == sound_name:
                current = sound.volume
                break

        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.configure(bg=_DARK_BG)
        dialog.title(f"Volume — {sound_name}")
        dialog.geometry("420x160")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ctk.CTkFrame(dialog, fg_color=_DARK_BG)
        outer.pack(fill="both", expand=True)

        ctk.CTkLabel(outer, text=sound_name,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))

        label = ctk.CTkLabel(outer, text=f"{int(current * 100)}%",
                             font=ctk.CTkFont(size=14))
        label.pack(pady=(0, 0))

        slider = ctk.CTkSlider(outer, from_=0, to=2, number_of_steps=200,
                                width=375)
        slider.set(current)
        slider.pack(pady=8)

        def on_slide(val):
            label.configure(text=f"{int(float(val) * 100)}%")

        slider.configure(command=on_slide)

        def on_ok():
            self.sound_manager.set_sound_volume(
                category, sound_name, round(slider.get(), 2))
            dialog.destroy()

        ctk.CTkButton(outer, text="OK", width=80,
                       command=on_ok).pack(pady=(0, 10))

        self._setup_dialog(dialog)

    def _on_volume_change(self, value: float):
        """Master volume changed."""
        self.audio_engine.set_master_volume(value)
        self.config.set("audio", "master_volume", value)

    def _on_output_mode_change(self, mode: str):
        """Output mode changed."""
        logger.info("Output mode changed to '%s'", mode)
        self.audio_engine.set_output_mode(mode)
        self.config.set("audio", "output_mode", mode)

    def _on_add_category(self):
        """Add a new category via a themed dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.configure(bg=_DARK_BG)
        dialog.title("New Category")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ctk.CTkFrame(dialog, fg_color=_DARK_BG)
        outer.pack(fill="both", expand=True)

        ctk.CTkLabel(outer, text="Category name:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(15, 5))

        entry = ctk.CTkEntry(outer, width=250, placeholder_text="e.g. Memes")
        entry.pack(pady=(0, 10))

        def on_ok(_event=None):
            name = entry.get().strip()
            if name:
                if self.sound_manager.add_category(name):
                    logger.info("Added category: %s", name)
                    self._refresh_all_tabs()
            dialog.destroy()

        btn_frame = ctk.CTkFrame(outer, fg_color="transparent")
        btn_frame.pack(pady=(0, 10))

        ctk.CTkButton(btn_frame, text="OK", width=80,
                       command=on_ok).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=80,
                       fg_color="#444444", hover_color="#555555",
                       command=dialog.destroy).pack(side="left", padx=5)

        entry.bind("<Return>", on_ok)
        self._setup_dialog(dialog)
        entry.focus_set()

    def _on_remove_category(self, name: str):
        """Remove a category."""
        if messagebox.askyesno("Remove Category",
                               f"Remove category '{name}' and all its sounds?",
                               parent=self.root):
            if self.sound_manager.remove_category(name):
                logger.info("Removed category: %s", name)
                self._refresh_all_tabs()

    def _on_clear_category(self, name: str):
        """Remove all sounds from a category without deleting the category."""
        sounds = self.sound_manager.get_sounds(name)
        if not sounds:
            return
        if messagebox.askyesno("Clear Category",
                               f"Remove all {len(sounds)} sounds from '{name}'?",
                               parent=self.root):
            for sound in list(sounds):
                self.sound_manager.remove_sound(name, sound.name)
            self._refresh_tab(name)
            self._register_hotkeys()

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
                                           default="stop"),
            on_save=self._apply_settings,
            on_install_vb_cable=self._start_vb_cable_install,
            icon_path=str(self._ico_path) if self._ico_path.exists() else None,
        )

    def _on_discord_guide(self):
        """Show the Discord setup guide dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.configure(bg=_DARK_BG)
        dialog.title("Discord Setup Guide")
        dialog.geometry("520x560")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ctk.CTkFrame(dialog, fg_color=_DARK_BG)
        outer.pack(fill="both", expand=True)

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        bold = ctk.CTkFont(size=14, weight="bold")
        heading = ctk.CTkFont(size=16, weight="bold")
        body = ctk.CTkFont(size=13)
        dim = "gray70"

        # --- Title ---
        ctk.CTkLabel(scroll, text="Setting Up Vyber with Discord",
                     font=heading).pack(anchor="w", pady=(5, 10))

        # --- Step 1 ---
        ctk.CTkLabel(scroll, text="Step 1 — Set Your Input Device",
                     font=bold).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(
            scroll, font=body, wraplength=470, justify="left",
            text="In Discord, go to Settings > Voice & Video.\n\n"
                 "Under INPUT DEVICE, select:\n"
                 "    CABLE Output (VB-Audio Virtual Cable)\n\n"
                 "This tells Discord to listen to VB-CABLE, which is "
                 "where Vyber sends its audio."
        ).pack(anchor="w", padx=(10, 0), pady=(0, 4))

        # --- Step 2 ---
        ctk.CTkLabel(scroll, text="Step 2 — Use Push to Talk or Voice Activity",
                     font=bold).pack(anchor="w", pady=(12, 2))
        ctk.CTkLabel(
            scroll, font=body, wraplength=470, justify="left",
            text="If using Voice Activity, set the sensitivity slider manually "
                 "rather than relying on automatic detection, since VB-CABLE "
                 "audio levels differ from a real microphone."
        ).pack(anchor="w", padx=(10, 0), pady=(0, 4))

        # --- Step 3 ---
        ctk.CTkLabel(scroll, text="Step 3 — Disable Audio Processing",
                     font=bold).pack(anchor="w", pady=(12, 2))
        ctk.CTkLabel(
            scroll, font=body, wraplength=470, justify="left",
            text="Discord's audio processing is designed for real "
                 "microphones and will distort soundboard audio. "
                 "Scroll down to the Voice Processing section and "
                 "disable the following:"
        ).pack(anchor="w", padx=(10, 0), pady=(0, 6))

        toggles = [
            ("Krisp Noise Suppression", "Will filter out your sound effects"),
            ("Echo Cancellation", "Causes audio artifacts on played sounds"),
        ]
        for name, reason in toggles:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=(10, 0), pady=1)
            ctk.CTkLabel(row, text=f"OFF", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#FF5722", width=32).pack(side="left")
            ctk.CTkLabel(row, text=f"  {name}", font=body).pack(side="left")
            ctk.CTkLabel(row, text=f"  — {reason}", font=body,
                         text_color=dim).pack(side="left")

        # --- Step 4 ---
        ctk.CTkLabel(scroll, text="Step 4 — Advanced Voice Settings",
                     font=bold).pack(anchor="w", pady=(14, 2))
        ctk.CTkLabel(
            scroll, font=body, wraplength=470, justify="left",
            text="Expand \"Advanced Voice Settings\" at the bottom of "
                 "the Voice & Video page and also disable:"
        ).pack(anchor="w", padx=(10, 0), pady=(0, 6))

        advanced_toggles = [
            "Automatic Gain Control",
            "Advanced Voice Activity",
            "Bypass System Audio Input Processing",
            "No Audio Detected Warning",
        ]
        for name in advanced_toggles:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=(10, 0), pady=1)
            ctk.CTkLabel(row, text=f"OFF", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#FF5722", width=32).pack(side="left")
            ctk.CTkLabel(row, text=f"  {name}", font=body).pack(side="left")

        # --- Step 5 ---
        ctk.CTkLabel(scroll, text="Step 5 — Global Attenuation",
                     font=bold).pack(anchor="w", pady=(14, 2))
        ctk.CTkLabel(
            scroll, font=body, wraplength=470, justify="left",
            text="Set Global Attenuation to 0%. This prevents Discord "
                 "from lowering the volume of other applications when "
                 "someone is speaking, which can interfere with Vyber's "
                 "audio output."
        ).pack(anchor="w", padx=(10, 0), pady=(0, 4))

        # --- Tip ---
        tip_frame = ctk.CTkFrame(scroll, fg_color="#1a3a1a", corner_radius=8)
        tip_frame.pack(fill="x", padx=15, pady=(14, 8))
        ctk.CTkLabel(
            tip_frame, font=body, wraplength=420, justify="left",
            text="Tip: In Vyber, set the output mode to \"Both\" so your "
                 "friends hear the sounds and you do too. If your own voice "
                 "needs to go through as well, make sure \"Mic Passthrough\" "
                 "is enabled in Vyber Settings."
        ).pack(padx=14, pady=10)

        # --- Close button ---
        ctk.CTkButton(outer, text="Got It", width=100,
                       command=dialog.destroy).pack(pady=(8, 12))

        self._setup_dialog(dialog)

    def _on_help(self):
        """Show the Help / Report a Bug dialog."""
        from vyber import __version__
        from vyber.telemetry import AUTH_KEY

        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.configure(bg=_DARK_BG)
        dialog.title("Help — Report a Bug")
        dialog.geometry("580x620")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ctk.CTkFrame(dialog, fg_color=_DARK_BG)
        outer.pack(fill="both", expand=True)

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        heading = ctk.CTkFont(size=16, weight="bold")
        bold = ctk.CTkFont(size=14, weight="bold")
        body = ctk.CTkFont(size=13)

        # --- Title ---
        ctk.CTkLabel(scroll, text="Help & Bug Reports",
                     font=heading).pack(anchor="center", pady=(5, 2))
        ctk.CTkLabel(
            scroll, font=body, text_color="gray60",
            text="Get help with Vyber or submit a bug report to GitHub Issues.",
        ).pack(anchor="center", pady=(0, 10))

        # --- How Vyber Works ---
        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=8)
        ctk.CTkLabel(scroll, text="How Vyber Works",
                     font=bold).pack(anchor="center", pady=(8, 4))
        ctk.CTkLabel(
            scroll, font=body, wraplength=440, justify="left",
            text="Vyber is a soundboard that plays audio through your speakers "
                 "and into voice chat at the same time. It uses VB-CABLE to "
                 "route audio into a virtual microphone that Discord (or any "
                 "voice app) picks up as your input device.\n\n"
                 "  \u2022  Add sounds, organize them into categories\n"
                 "  \u2022  Set global hotkeys to trigger sounds from any app\n"
                 "  \u2022  Mic Passthrough mixes your real voice in so friends "
                 "hear both you and your sounds",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        # --- Troubleshooting ---
        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=8)
        ctk.CTkLabel(scroll, text="Troubleshooting",
                     font=bold).pack(anchor="center", pady=(8, 4))
        ctk.CTkLabel(
            scroll, font=body, wraplength=440, justify="left",
            text="If Vyber isn't working as expected:\n\n"
                 "  \u2022  Make sure VB-CABLE is installed (restart PC after install)\n"
                 "  \u2022  Set Discord's Input Device to \"CABLE Output\"\n"
                 "  \u2022  Disable Discord's voice processing (see Discord Setup)\n"
                 "  \u2022  Click \"Refresh Audio Devices\" in the menu if you changed\n"
                 "     audio devices after launching Vyber\n"
                 "  \u2022  Try setting the output mode to \"Both\"",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        # --- Bug Report ---
        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=8)
        ctk.CTkLabel(scroll, text="Report a Bug",
                     font=bold).pack(anchor="center", pady=(8, 2))
        ctk.CTkLabel(
            scroll, font=body, text_color="gray60",
            text="Your report will be submitted to GitHub Issues.",
        ).pack(anchor="center", pady=(0, 8))

        ctk.CTkLabel(scroll, text="Title (brief summary)",
                     font=body).pack(anchor="center", pady=(2, 2))
        title_entry = ctk.CTkEntry(scroll, width=400, height=32,
                                   placeholder_text="e.g., Sound doesn't play through Discord")
        title_entry.pack(anchor="center", pady=(0, 8))

        ctk.CTkLabel(scroll, text="Description (steps to reproduce)",
                     font=body).pack(anchor="center", pady=(2, 2))
        desc_textbox = ctk.CTkTextbox(scroll, width=400, height=100, wrap="word")
        desc_textbox.pack(anchor="center", pady=(0, 8))

        checkbox_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        checkbox_frame.pack(anchor="center", pady=(2, 2))

        include_system_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            checkbox_frame,
            text="Include system info (OS, Vyber version)",
            variable=include_system_var, font=body,
        ).pack(anchor="w", pady=(2, 4))

        include_logs_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            checkbox_frame,
            text="Include recent logs (last 250 lines)",
            variable=include_logs_var, font=body,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            scroll, font=ctk.CTkFont(size=11), text_color="gray50",
            text="Your Windows username is redacted from logs. Other\n"
                 "folder names in paths may be visible in the report.",
        ).pack(anchor="center", pady=(0, 6))

        status_label = ctk.CTkLabel(scroll, text="", font=body)
        status_label.pack(anchor="center", pady=(0, 4))

        submit_time = [0.0]

        def _get_system_info():
            import re as _re
            lines = [
                f"- **Vyber Version**: {__version__}",
                f"- **OS**: {platform.system()} {platform.release()} "
                f"({platform.version()})",
                f"- **Python**: {platform.python_version()}",
                f"- **Architecture**: {platform.machine()}",
            ]
            return "\n".join(lines)

        def _get_recent_logs(num_lines=250):
            """Read the last N lines from the log file, redacting usernames."""
            import re as _re
            from vyber.config import LOG_FILE
            if not LOG_FILE.exists():
                return None
            try:
                with open(LOG_FILE, "r", encoding="utf-8",
                          errors="replace") as f:
                    all_lines = f.readlines()
                recent = all_lines[-num_lines:] if len(all_lines) > num_lines else all_lines
                text = "".join(recent).strip()
                # Redact Windows usernames from paths
                text = _re.sub(
                    r'(C:[/\\][Uu]sers[/\\])([^/\\]+)([/\\])',
                    r'\1[REDACTED]\3', text)
                return text
            except Exception:
                return None

        def _submit():
            submit_btn.configure(state="disabled", fg_color="gray50")
            submit_time[0] = time.time()

            def _re_enable():
                elapsed = time.time() - submit_time[0]
                remaining = max(0, 5.0 - elapsed)

                def _do_enable():
                    try:
                        submit_btn.configure(state="normal",
                                             fg_color="#2563eb")
                    except Exception:
                        pass  # dialog already closed

                self.root.after(int(remaining * 1000), _do_enable)

            title = title_entry.get().strip()
            desc = desc_textbox.get("1.0", "end-1c").strip()
            if not title:
                status_label.configure(
                    text="Please enter a title.", text_color="#ff6b6b")
                _re_enable()
                return
            if not desc:
                status_label.configure(
                    text="Please describe the bug.", text_color="#ff6b6b")
                _re_enable()
                return

            body_parts = ["## Description", desc]
            if include_system_var.get():
                body_parts.append("\n## System Information")
                body_parts.append(_get_system_info())
            if include_logs_var.get():
                recent_logs = _get_recent_logs(250)
                if recent_logs:
                    body_parts.append("\n## Recent Logs")
                    body_parts.append("<details>")
                    body_parts.append(
                        "<summary>Click to expand logs "
                        "(last 250 lines)</summary>")
                    body_parts.append("")
                    body_parts.append("```")
                    body_parts.append(recent_logs)
                    body_parts.append("```")
                    body_parts.append("</details>")
            body_parts.append("\n---")
            body_parts.append("*Submitted via Vyber*")
            issue_body = "\n".join(body_parts)

            status_label.configure(text="Submitting...",
                                   text_color="gray60")
            self.root.update()

            def _safe_configure(widget, **kwargs):
                try:
                    widget.configure(**kwargs)
                except Exception:
                    pass  # dialog already closed

            def _do_submit():
                try:
                    resp = requests.post(
                        "https://vyber-proxy.mortonapps.com/repos/Master00Sniper/Vyber/issues",
                        headers={
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": f"Vyber/{__version__}",
                            "X-Vyber-Auth": AUTH_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "title": f"[Bug Report] {title}",
                            "body": issue_body,
                        },
                        timeout=15,
                    )
                    if resp.status_code == 201:
                        num = resp.json().get("number", "?")
                        self.root.after(0, lambda: _safe_configure(
                            status_label,
                            text=f"Submitted! (Issue #{num})",
                            text_color="#4ade80"))
                        self.root.after(0, lambda: (
                            title_entry.delete(0, "end"),
                            desc_textbox.delete("1.0", "end"),
                        ))
                    else:
                        detail = resp.text[:200]
                        logger.error("Bug report failed: HTTP %d — %s",
                                     resp.status_code, detail)
                        self.root.after(0, lambda: _safe_configure(
                            status_label,
                            text=f"Failed (HTTP {resp.status_code}): {detail}",
                            text_color="#ff6b6b"))
                except requests.exceptions.Timeout:
                    self.root.after(0, lambda: _safe_configure(
                        status_label,
                        text="Request timed out.", text_color="#ff6b6b"))
                except Exception:
                    self.root.after(0, lambda: _safe_configure(
                        status_label,
                        text="Network error.", text_color="#ff6b6b"))
                self.root.after(0, _re_enable)

            threading.Thread(target=_do_submit, daemon=True).start()

        submit_btn = ctk.CTkButton(
            scroll, text="Submit Bug Report", width=180,
            fg_color="#2563eb", hover_color="#1d4ed8", command=_submit)
        submit_btn.pack(anchor="center", pady=(4, 20))

        # --- Close ---
        ctk.CTkButton(outer, text="Close", width=100,
                       command=dialog.destroy).pack(pady=(8, 12))

        self._setup_dialog(dialog)

    def _on_about(self):
        """Show the About Vyber dialog."""
        from vyber import __version__

        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.configure(bg=_DARK_BG)
        dialog.title("About Vyber")
        dialog.geometry("480x540")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ctk.CTkFrame(dialog, fg_color=_DARK_BG)
        outer.pack(fill="both", expand=True)

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        heading = ctk.CTkFont(size=20, weight="bold")
        bold = ctk.CTkFont(size=14, weight="bold")
        body = ctk.CTkFont(size=13)

        # --- Title & version ---
        ctk.CTkLabel(scroll, text="Vyber",
                     font=heading).pack(anchor="center", pady=(10, 2))
        ctk.CTkLabel(scroll, text=f"Version {__version__}",
                     font=body).pack(anchor="center", pady=(0, 10))

        # --- Description ---
        ctk.CTkLabel(
            scroll, font=body, wraplength=420, justify="center",
            text="Vyber is a free, open-source soundboard for Windows that "
                 "plays audio through your speakers and into voice chat at the "
                 "same time. Built for Discord, gaming, and streaming — no "
                 "complicated audio routing required.",
        ).pack(anchor="center", pady=(0, 8))

        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=10)

        # --- Developer ---
        ctk.CTkLabel(scroll, text="Developed by",
                     font=body).pack(anchor="center", pady=(4, 0))
        ctk.CTkLabel(scroll, text="Greg Morton (@Master00Sniper)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(
                         anchor="center", pady=(0, 8))

        ctk.CTkLabel(
            scroll, font=body, wraplength=420, justify="center",
            text="I'm a passionate gamer, Sr. Systems Administrator, wine "
                 "enthusiast, and proud small winery owner. Vyber was born from "
                 "wanting a dead-simple soundboard that actually works in voice "
                 "chat. I hope it makes your sessions more fun!",
        ).pack(anchor="center", pady=(0, 8))

        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=10)

        # --- Support ---
        ctk.CTkLabel(scroll, text="Support Development",
                     font=bold).pack(anchor="center", pady=(4, 4))
        ctk.CTkLabel(
            scroll, font=body, justify="center",
            text="If Vyber has made your voice chats better,\nconsider "
                 "supporting development!",
        ).pack(anchor="center", pady=(0, 8))

        ctk.CTkButton(
            scroll, text="Support on Ko-fi", width=200,
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=lambda: os.startfile("https://ko-fi.com/master00sniper"),
        ).pack(anchor="center", pady=(0, 8))

        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=10)

        # --- Contact ---
        ctk.CTkLabel(scroll, text="Contact & Connect",
                     font=bold).pack(anchor="center", pady=(4, 4))
        ctk.CTkLabel(scroll, text="Email: greg@mortonapps.com",
                     font=body).pack(anchor="center", pady=2)

        x_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        x_frame.pack(anchor="center", pady=2)
        ctk.CTkLabel(x_frame, text="X: ", font=body).pack(side="left")
        x_link = ctk.CTkLabel(
            x_frame, text="x.com/master00sniper",
            font=ctk.CTkFont(size=13, underline=True),
            text_color="#1DA1F2", cursor="hand2")
        x_link.pack(side="left")
        x_link.bind("<Button-1>",
                     lambda e: os.startfile("https://x.com/master00sniper"))

        ctk.CTkFrame(scroll, height=2, fg_color="gray50").pack(
            fill="x", padx=30, pady=10)

        # --- Copyright ---
        ctk.CTkLabel(
            scroll, font=ctk.CTkFont(size=11),
            text="\u00a9 2025-2026 Greg Morton (@Master00Sniper)",
        ).pack(anchor="center", pady=(4, 2))
        ctk.CTkLabel(
            scroll, font=ctk.CTkFont(size=11), text_color="gray50",
            text="Licensed under the GNU General Public License v3.0",
        ).pack(anchor="center", pady=(0, 4))
        ctk.CTkLabel(
            scroll, font=ctk.CTkFont(size=10), text_color="gray50",
            wraplength=420, justify="center",
            text="This program is distributed in the hope that it will be "
                 "useful, but WITHOUT ANY WARRANTY; without even the implied "
                 "warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR "
                 "PURPOSE. See the GPL v3 license for details.",
        ).pack(anchor="center", pady=(0, 16))

        # --- Close ---
        ctk.CTkButton(outer, text="Close", width=100,
                       command=dialog.destroy).pack(pady=(8, 12))

        self._setup_dialog(dialog)

    def _apply_settings(self, settings: dict):
        """Apply settings from the settings dialog."""
        logger.info("Applying settings: speaker=%s, mic=%s, passthrough=%s, "
                     "stop_key=%s, overlap=%s",
                     settings["speaker_device"], settings["mic_device"],
                     settings["mic_passthrough"], settings["stop_all_hotkey"],
                     settings["sound_overlap"])
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
        messagebox.showinfo(
            "VB-CABLE Required",
            "Vyber requires the VB-CABLE virtual audio driver to send "
            "sounds through voice chat.\n\n"
            "Press OK to download and install VB-CABLE.\n"
            "You will need to approve an admin prompt.",
            parent=self.root,
        )
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
        """Called when the VB-CABLE installer has finished."""
        self._install_pending = False
        messagebox.showinfo(
            "Restart Required",
            "The VB-CABLE installer has finished.\n\n"
            "Please restart your computer to complete the setup.",
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

