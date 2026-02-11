"""Settings dialog — audio device selection, VB-CABLE status, preferences."""

import ctypes
import sys
import tkinter as tk

import customtkinter as ctk
from typing import Callable
import webbrowser

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


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog."""

    def __init__(self, master,
                 output_devices: list[dict],
                 input_devices: list[dict],
                 cable_installed: bool,
                 current_speaker: int | None,
                 current_mic: int | None,
                 current_stop_hotkey: str,
                 mic_passthrough: bool,
                 sound_overlap: str = "overlap",
                 on_save: Callable[[dict], None] | None = None,
                 on_install_vb_cable: Callable[[], None] | None = None,
                 on_exit: Callable[[], None] | None = None,
                 icon_path: str | None = None):
        super().__init__(master)
        self.withdraw()
        self.configure(bg=_DARK_BG)

        self.title("Vyber Settings")
        self.geometry("500x620")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        # Set icon while hidden
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self._on_save = on_save
        self._on_install_vb_cable = on_install_vb_cable
        self._on_exit = on_exit
        self._output_devices = output_devices
        self._input_devices = input_devices

        # Outer frame covers tk.Toplevel background
        self._outer = ctk.CTkFrame(self, fg_color=_DARK_BG)
        self._outer.pack(fill="both", expand=True)

        self._build_ui(
            output_devices, input_devices, cable_installed,
            current_speaker, current_mic, current_stop_hotkey,
            mic_passthrough, sound_overlap
        )

        # Force full render while hidden, then center and show
        self.update()
        pw, ph = master.winfo_width(), master.winfo_height()
        px, py = master.winfo_x(), master.winfo_y()
        dw, dh = self.winfo_width(), self.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.geometry(f"+{x}+{y}")

        self.deiconify()
        _set_dark_title_bar(self)
        self.lift()
        self.focus_force()

    def _build_ui(self, output_devices, input_devices, cable_installed,
                  current_speaker, current_mic, current_stop_hotkey,
                  mic_passthrough, sound_overlap):

        # Scrollable content in case the window is tight
        content = ctk.CTkScrollableFrame(self._outer, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        pad = {"padx": 10, "pady": (8, 4)}

        # --- VB-CABLE Status ---
        status_frame = ctk.CTkFrame(content)
        status_frame.pack(fill="x", **pad)

        ctk.CTkLabel(status_frame, text="VB-CABLE Status",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 2))

        if cable_installed:
            ctk.CTkLabel(status_frame, text="Connected and ready",
                         text_color="#4CAF50").pack(anchor="w", padx=10,
                                                     pady=(0, 10))
        else:
            ctk.CTkLabel(
                status_frame,
                text="Not detected. Install VB-CABLE to enable mic output.",
                text_color="#FF5722"
            ).pack(anchor="w", padx=10, pady=(0, 5))

            btn_row = ctk.CTkFrame(status_frame, fg_color="transparent")
            btn_row.pack(anchor="w", padx=10, pady=(0, 10))

            if self._on_install_vb_cable:
                ctk.CTkButton(
                    btn_row,
                    text="Install VB-CABLE",
                    width=160,
                    command=self._handle_install_vb_cable,
                ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                btn_row,
                text="Manual Download",
                width=140,
                fg_color="#37474F",
                hover_color="#546E7A",
                command=lambda: webbrowser.open("https://vb-audio.com/Cable/"),
            ).pack(side="left")

        # --- Speaker Device ---
        ctk.CTkLabel(content, text="Speaker Output Device",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        speaker_names = [d["name"] for d in output_devices]
        speaker_names.insert(0, "System Default")
        current_speaker_name = "System Default"
        for d in output_devices:
            if d["index"] == current_speaker:
                current_speaker_name = d["name"]
                break

        self.speaker_var = ctk.StringVar(value=current_speaker_name)
        self.speaker_dropdown = ctk.CTkOptionMenu(
            content, values=speaker_names, variable=self.speaker_var,
            width=400
        )
        self.speaker_dropdown.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Microphone Device ---
        ctk.CTkLabel(content, text="Microphone Input Device",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        mic_names = [d["name"] for d in input_devices]
        mic_names.insert(0, "System Default")
        current_mic_name = "System Default"
        for d in input_devices:
            if d["index"] == current_mic:
                current_mic_name = d["name"]
                break

        self.mic_var = ctk.StringVar(value=current_mic_name)
        self.mic_dropdown = ctk.CTkOptionMenu(
            content, values=mic_names, variable=self.mic_var, width=400
        )
        self.mic_dropdown.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Mic Passthrough ---
        self.passthrough_var = ctk.BooleanVar(value=mic_passthrough)
        ctk.CTkCheckBox(
            content,
            text="Mix microphone audio into virtual cable (mic passthrough)",
            variable=self.passthrough_var
        ).pack(anchor="w", padx=10, pady=5)

        # --- Stop All Hotkey ---
        ctk.CTkLabel(content, text="Stop All Hotkey",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        self.hotkey_var = ctk.StringVar(value=current_stop_hotkey)
        self.hotkey_entry = ctk.CTkEntry(
            content, textvariable=self.hotkey_var, width=200
        )
        self.hotkey_entry.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Replay Behavior ---
        ctk.CTkLabel(content, text="Replay Behavior",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        ctk.CTkLabel(
            content,
            text="When clicking a sound that is already playing:",
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 4))

        self.overlap_var = ctk.StringVar(value=sound_overlap)

        ctk.CTkRadioButton(
            content,
            text="Play another instance (layer on top)",
            variable=self.overlap_var,
            value="overlap",
        ).pack(anchor="w", padx=20, pady=2)

        ctk.CTkRadioButton(
            content,
            text="Stop the sound",
            variable=self.overlap_var,
            value="stop",
        ).pack(anchor="w", padx=20, pady=2)

        # --- Save / Cancel / Exit buttons ---
        btn_frame = ctk.CTkFrame(self._outer, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 12))

        ctk.CTkButton(
            btn_frame, text="Exit Vyber", width=110,
            fg_color="#8B0000", hover_color="#B22222",
            command=self._handle_exit,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Save", width=100,
            command=self._save
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100,
            fg_color="#37474F", hover_color="#546E7A",
            command=self.destroy
        ).pack(side="right", padx=5)

    def _handle_exit(self):
        """Fully exit Vyber (not just minimize to tray)."""
        self.destroy()
        if self._on_exit:
            self._on_exit()

    def _handle_install_vb_cable(self):
        """Start the VB-CABLE install and close the dialog."""
        self.destroy()
        if self._on_install_vb_cable:
            self._on_install_vb_cable()

    def _save(self):
        """Collect settings and call on_save callback."""
        # Resolve speaker device index
        speaker_name = self.speaker_var.get()
        speaker_index = None
        if speaker_name != "System Default":
            for d in self._output_devices:
                if d["name"] == speaker_name:
                    speaker_index = d["index"]
                    break

        # Resolve mic device index
        mic_name = self.mic_var.get()
        mic_index = None
        if mic_name != "System Default":
            for d in self._input_devices:
                if d["name"] == mic_name:
                    mic_index = d["index"]
                    break

        settings = {
            "speaker_device": speaker_index,
            "mic_device": mic_index,
            "mic_passthrough": self.passthrough_var.get(),
            "stop_all_hotkey": self.hotkey_var.get().strip() or "escape",
            "sound_overlap": self.overlap_var.get(),
        }

        if self._on_save:
            self._on_save(settings)
        self.destroy()
