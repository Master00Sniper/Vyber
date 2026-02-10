"""Settings dialog — audio device selection, VB-CABLE status, preferences."""

import customtkinter as ctk
from typing import Callable
import webbrowser


class SettingsDialog(ctk.CTkToplevel):
    """Modal settings dialog with Audio and Preferences tabs."""

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
                 on_install_vb_cable: Callable[[], None] | None = None):
        super().__init__(master)

        self.title("Vyber Settings")
        self.geometry("520x560")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._on_save = on_save
        self._on_install_vb_cable = on_install_vb_cable
        self._output_devices = output_devices
        self._input_devices = input_devices

        self._build_ui(
            output_devices, input_devices, cable_installed,
            current_speaker, current_mic, current_stop_hotkey,
            mic_passthrough, sound_overlap
        )

    def _build_ui(self, output_devices, input_devices, cable_installed,
                  current_speaker, current_mic, current_stop_hotkey,
                  mic_passthrough, sound_overlap):

        # --- Tabview ---
        self.tabview = ctk.CTkTabview(self, height=440)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        self.tabview.add("Audio")
        self.tabview.add("Preferences")

        # =====================================================================
        # Audio tab
        # =====================================================================
        audio_tab = self.tabview.tab("Audio")
        pad = {"padx": 10, "pady": (8, 4)}

        # --- VB-CABLE Status ---
        status_frame = ctk.CTkFrame(audio_tab)
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
        ctk.CTkLabel(audio_tab, text="Speaker Output Device",
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
            audio_tab, values=speaker_names, variable=self.speaker_var,
            width=400
        )
        self.speaker_dropdown.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Microphone Device ---
        ctk.CTkLabel(audio_tab, text="Microphone Input Device",
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
            audio_tab, values=mic_names, variable=self.mic_var, width=400
        )
        self.mic_dropdown.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Mic Passthrough ---
        self.passthrough_var = ctk.BooleanVar(value=mic_passthrough)
        ctk.CTkCheckBox(
            audio_tab,
            text="Mix microphone audio into virtual cable (mic passthrough)",
            variable=self.passthrough_var
        ).pack(anchor="w", padx=10, pady=5)

        # --- Stop All Hotkey ---
        ctk.CTkLabel(audio_tab, text="Stop All Hotkey",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", **pad)

        self.hotkey_var = ctk.StringVar(value=current_stop_hotkey)
        self.hotkey_entry = ctk.CTkEntry(
            audio_tab, textvariable=self.hotkey_var, width=200
        )
        self.hotkey_entry.pack(anchor="w", padx=10, pady=(0, 8))

        # =====================================================================
        # Preferences tab
        # =====================================================================
        prefs_tab = self.tabview.tab("Preferences")

        # --- Replay Behavior ---
        ctk.CTkLabel(prefs_tab, text="Replay Behavior",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 2))

        ctk.CTkLabel(
            prefs_tab,
            text="When clicking a sound that is already playing:",
            text_color="gray",
        ).pack(anchor="w", padx=10, pady=(0, 6))

        self.overlap_var = ctk.StringVar(value=sound_overlap)

        ctk.CTkRadioButton(
            prefs_tab,
            text="Play another instance (layer on top)",
            variable=self.overlap_var,
            value="overlap",
        ).pack(anchor="w", padx=20, pady=3)

        ctk.CTkRadioButton(
            prefs_tab,
            text="Stop the sound",
            variable=self.overlap_var,
            value="stop",
        ).pack(anchor="w", padx=20, pady=3)

        # =====================================================================
        # Save / Cancel buttons (outside tabs)
        # =====================================================================
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 12))

        ctk.CTkButton(
            btn_frame, text="Save", width=100,
            command=self._save
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100,
            fg_color="#37474F", hover_color="#546E7A",
            command=self.destroy
        ).pack(side="right", padx=5)

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
