"""Settings dialog — audio device selection, VB-CABLE status, preferences."""

import customtkinter as ctk
from typing import Callable
import webbrowser


class SettingsDialog(ctk.CTkToplevel):
    """Modal settings dialog."""

    def __init__(self, master,
                 output_devices: list[dict],
                 input_devices: list[dict],
                 cable_installed: bool,
                 current_speaker: int | None,
                 current_mic: int | None,
                 current_stop_hotkey: str,
                 mic_passthrough: bool,
                 on_save: Callable[[dict], None] | None = None):
        super().__init__(master)

        self.title("Soundboard Settings")
        self.geometry("500x520")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._on_save = on_save
        self._output_devices = output_devices
        self._input_devices = input_devices

        self._build_ui(
            output_devices, input_devices, cable_installed,
            current_speaker, current_mic, current_stop_hotkey,
            mic_passthrough
        )

    def _build_ui(self, output_devices, input_devices, cable_installed,
                  current_speaker, current_mic, current_stop_hotkey,
                  mic_passthrough):

        pad = {"padx": 20, "pady": (10, 5)}

        # --- VB-CABLE Status ---
        status_frame = ctk.CTkFrame(self)
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
            ctk.CTkButton(
                status_frame,
                text="Download VB-CABLE (Free)",
                width=200,
                command=lambda: webbrowser.open("https://vb-audio.com/Cable/")
            ).pack(anchor="w", padx=10, pady=(0, 10))

        # --- Speaker Device ---
        ctk.CTkLabel(self, text="Speaker Output Device",
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
            self, values=speaker_names, variable=self.speaker_var, width=400
        )
        self.speaker_dropdown.pack(anchor="w", padx=20, pady=(0, 10))

        # --- Microphone Device ---
        ctk.CTkLabel(self, text="Microphone Input Device",
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
            self, values=mic_names, variable=self.mic_var, width=400
        )
        self.mic_dropdown.pack(anchor="w", padx=20, pady=(0, 10))

        # --- Mic Passthrough ---
        self.passthrough_var = ctk.BooleanVar(value=mic_passthrough)
        ctk.CTkCheckBox(
            self, text="Mix microphone audio into virtual cable (mic passthrough)",
            variable=self.passthrough_var
        ).pack(anchor="w", padx=20, pady=5)

        # --- Stop All Hotkey ---
        ctk.CTkLabel(self, text="Stop All Hotkey",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        self.hotkey_var = ctk.StringVar(value=current_stop_hotkey)
        self.hotkey_entry = ctk.CTkEntry(
            self, textvariable=self.hotkey_var, width=200
        )
        self.hotkey_entry.pack(anchor="w", padx=20, pady=(0, 10))

        # --- Buttons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkButton(
            btn_frame, text="Save", width=100,
            command=self._save
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100,
            fg_color="#37474F", hover_color="#546E7A",
            command=self.destroy
        ).pack(side="right", padx=5)

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
            "stop_all_hotkey": self.hotkey_var.get().strip() or "escape"
        }

        if self._on_save:
            self._on_save(settings)
        self.destroy()
