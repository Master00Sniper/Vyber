"""Reusable custom widgets for the Vyber UI."""

import customtkinter as ctk
from typing import Callable


class VolumeSlider(ctk.CTkFrame):
    """A labeled volume slider with percentage display."""

    def __init__(self, master, label: str = "Volume", initial: float = 0.8,
                 on_change: Callable[[float], None] | None = None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_change = on_change

        self.label = ctk.CTkLabel(self, text=label, width=60, anchor="w")
        self.label.pack(side="left", padx=(5, 2))

        self.slider = ctk.CTkSlider(
            self, from_=0, to=1, number_of_steps=100,
            command=self._slider_changed, width=140
        )
        self.slider.set(initial)
        self.slider.pack(side="left", padx=2)

        self.value_label = ctk.CTkLabel(self, text=f"{int(initial * 100)}%",
                                         width=40)
        self.value_label.pack(side="left", padx=(2, 5))

    def _slider_changed(self, value: float):
        self.value_label.configure(text=f"{int(value * 100)}%")
        if self._on_change:
            self._on_change(value)

    def get(self) -> float:
        return self.slider.get()

    def set(self, value: float):
        self.slider.set(value)
        self.value_label.configure(text=f"{int(value * 100)}%")


class OutputModeSelector(ctk.CTkFrame):
    """Toggle between Speakers / Mic / Both output modes."""

    def __init__(self, master, initial: str = "both",
                 on_change: Callable[[str], None] | None = None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_change = on_change
        self._buttons: dict[str, ctk.CTkRadioButton] = {}

        self.label = ctk.CTkLabel(self, text="Output:", width=50, anchor="w")
        self.label.pack(side="left", padx=(5, 5))

        self._mode_var = ctk.StringVar(value=initial)

        modes = [("Speakers", "speakers"), ("Mic", "mic"), ("Both", "both")]
        for display_text, value in modes:
            btn = ctk.CTkRadioButton(
                self, text=display_text, variable=self._mode_var,
                value=value, command=self._mode_changed
            )
            btn.pack(side="left", padx=5)
            self._buttons[value] = btn

    def _mode_changed(self):
        if self._on_change:
            self._on_change(self._mode_var.get())

    def get(self) -> str:
        return self._mode_var.get()

    def set(self, mode: str):
        self._mode_var.set(mode)

    def set_cable_available(self, available: bool):
        """Enable or disable Mic and Both modes based on VB-CABLE status."""
        for mode in ("mic", "both"):
            btn = self._buttons.get(mode)
            if btn:
                btn.configure(state="normal" if available else "disabled")
        # If currently on a disabled mode, fall back to speakers
        if not available and self._mode_var.get() in ("mic", "both"):
            self._mode_var.set("speakers")
            if self._on_change:
                self._on_change("speakers")


class StatusBar(ctk.CTkFrame):
    """Status bar at the bottom of the main window."""

    def __init__(self, master, **kwargs):
        super().__init__(master, height=30, **kwargs)

        self.cable_status = ctk.CTkLabel(
            self, text="VB-CABLE: Not detected", anchor="w",
            text_color="gray"
        )
        self.cable_status.pack(side="left", padx=10)

        self.playing_status = ctk.CTkLabel(
            self, text="Playing: 0", anchor="e",
            text_color="gray"
        )
        self.playing_status.pack(side="right", padx=10)

        self.device_status = ctk.CTkLabel(
            self, text="", anchor="center",
            text_color="gray"
        )
        self.device_status.pack(side="right", padx=10)

    def set_cable_status(self, installed: bool, name: str = ""):
        if installed:
            self.cable_status.configure(
                text=f"VB-CABLE: Connected", text_color="#4CAF50"
            )
        else:
            msg = name if name else (
                "VB-CABLE not detected — install VB-CABLE to play "
                "sound clips through speakers and microphone"
            )
            self.cable_status.configure(text=msg, text_color="#FF5722")

    def set_playing_count(self, count: int):
        color = "#4CAF50" if count > 0 else "gray"
        self.playing_status.configure(text=f"Playing: {count}",
                                       text_color=color)

    def set_device_info(self, text: str):
        self.device_status.configure(text=text)
