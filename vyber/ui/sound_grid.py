"""Sound button grid — displays sounds within a category tab."""

import os
import customtkinter as ctk
from tkinter import filedialog, simpledialog, Menu
from typing import Callable


class SoundButton(ctk.CTkButton):
    """Flat sound button with playing-state gold pulse."""

    _COLOR_NORMAL = "#2B4C7E"
    _COLOR_HOVER = "#3A6BA5"
    _COLOR_GOLD = "#FFD700"
    _COLOR_GOLD_DIM = "#8B7500"

    def __init__(self, master, sound_name: str, filepath: str = "",
                 hotkey: str | None = None,
                 on_play: Callable | None = None,
                 on_context_menu: Callable | None = None, **kwargs):
        display = sound_name
        if hotkey:
            display += f"\n[{hotkey}]"

        super().__init__(
            master, text=display, width=130, height=70,
            corner_radius=8, fg_color=self._COLOR_NORMAL,
            hover_color=self._COLOR_HOVER,
            border_width=0,
            font=ctk.CTkFont(size=12),
            command=self._clicked,
            **kwargs,
        )
        self.sound_name = sound_name
        self.filepath = filepath
        self._on_play = on_play
        self._on_context_menu = on_context_menu
        self._playing = False
        self._pulse_bright = True
        self._pulse_id = None

        self.bind("<Button-3>", self._show_context_menu)

    def _clicked(self, *_args):
        if self._on_play:
            self._on_play(self.sound_name)

    def _show_context_menu(self, event):
        if self._on_context_menu:
            self._on_context_menu(self.sound_name, event)

    def set_playing(self, playing: bool):
        """Start or stop the gold border pulse animation."""
        if playing and not self._playing:
            self._playing = True
            self._pulse_bright = True
            self.configure(border_width=2)
            self._pulse()
        elif not playing and self._playing:
            self._playing = False
            if self._pulse_id is not None:
                self.after_cancel(self._pulse_id)
                self._pulse_id = None
            self.configure(border_width=0)

    def _pulse(self):
        """Alternate gold border brightness."""
        if not self._playing:
            return
        color = self._COLOR_GOLD if self._pulse_bright else self._COLOR_GOLD_DIM
        self.configure(border_color=color)
        self._pulse_bright = not self._pulse_bright
        self._pulse_id = self.after(400, self._pulse)

    def update_display(self, sound_name: str, hotkey: str | None = None):
        self.sound_name = sound_name
        display = sound_name
        if hotkey:
            display += f"\n[{hotkey}]"
        self.configure(text=display)


class SoundGrid(ctk.CTkScrollableFrame):
    """Scrollable grid of sound buttons for a single category."""

    COLUMNS = 5

    def __init__(self, master, category: str,
                 on_play: Callable[[str, str], None] | None = None,
                 on_add: Callable[[str], None] | None = None,
                 on_remove: Callable[[str, str], None] | None = None,
                 on_rename: Callable[[str, str], None] | None = None,
                 on_set_hotkey: Callable[[str, str], None] | None = None,
                 on_move: Callable[[str, str], None] | None = None,
                 on_volume: Callable[[str, str], None] | None = None,
                 get_categories: Callable[[], list[str]] | None = None,
                 **kwargs):
        super().__init__(master, **kwargs)
        self.category = category
        self._on_play = on_play
        self._on_add = on_add
        self._on_remove = on_remove
        self._on_rename = on_rename
        self._on_set_hotkey = on_set_hotkey
        self._on_move = on_move
        self._on_volume = on_volume
        self._get_categories = get_categories
        self._buttons: dict[str, SoundButton] = {}

        # Add sound button (always at the end)
        self._add_button = ctk.CTkButton(
            self, text="+ Add Sound", width=130, height=70,
            corner_radius=8, fg_color="#2B5B2B", hover_color="#3A7A3A",
            font=ctk.CTkFont(size=12),
            command=self._add_sound_clicked
        )

    def populate(self, sounds: list):
        """Fill the grid with sound buttons. `sounds` is a list of SoundEntry."""
        # Clear existing buttons
        for btn in self._buttons.values():
            btn.destroy()
        self._buttons.clear()

        for i, sound in enumerate(sounds):
            btn = SoundButton(
                self,
                sound_name=sound.name,
                filepath=sound.path,
                hotkey=sound.hotkey,
                on_play=lambda name: self._play(name),
                on_context_menu=self._context_menu
            )
            row, col = divmod(i, self.COLUMNS)
            btn.grid(row=row, column=col, padx=5, pady=5)
            self._buttons[sound.name] = btn

        # Place Add button at the end
        add_idx = len(sounds)
        row, col = divmod(add_idx, self.COLUMNS)
        self._add_button.grid(row=row, column=col, padx=5, pady=5)

    def update_playing_states(self, playing_filepaths: set[str]):
        """Update gold pulse on buttons whose sounds are currently playing."""
        for btn in self._buttons.values():
            btn.set_playing(btn.filepath in playing_filepaths)

    def _play(self, sound_name: str):
        if self._on_play:
            self._on_play(self.category, sound_name)

    def _add_sound_clicked(self):
        if self._on_add:
            self._on_add(self.category)

    def _context_menu(self, sound_name: str, event):
        """Show right-click context menu for a sound button."""
        menu = Menu(self, tearoff=0)
        menu.configure(
            bg="#2b2b2b", fg="white", activebackground="#404040",
            activeforeground="white"
        )
        menu.add_command(
            label="Set Hotkey",
            command=lambda: self._on_set_hotkey(self.category, sound_name)
            if self._on_set_hotkey else None
        )
        menu.add_command(
            label="Rename",
            command=lambda: self._on_rename(self.category, sound_name)
            if self._on_rename else None
        )
        menu.add_command(
            label="Adjust Volume",
            command=lambda: self._on_volume(self.category, sound_name)
            if self._on_volume else None
        )

        # Move to category submenu
        if self._get_categories:
            move_menu = Menu(menu, tearoff=0)
            move_menu.configure(
                bg="#2b2b2b", fg="white", activebackground="#404040",
                activeforeground="white"
            )
            for cat in self._get_categories():
                if cat != self.category:
                    move_menu.add_command(
                        label=cat,
                        command=lambda c=cat: self._on_move(self.category, sound_name)
                        if self._on_move else None
                    )
            if move_menu.index("end") is not None:
                menu.add_cascade(label="Move to", menu=move_menu)

        menu.add_separator()
        menu.add_command(
            label="Remove",
            command=lambda: self._on_remove(self.category, sound_name)
            if self._on_remove else None
        )

        menu.tk_popup(event.x_root, event.y_root)
