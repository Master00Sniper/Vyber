"""Sound button grid — displays sounds within a category tab."""

import os
import customtkinter as ctk
from tkinter import filedialog, simpledialog, Menu
from typing import Callable


class SoundButton(ctk.CTkFrame):
    """A 3D-styled sound button with press animation."""

    # Color palette for raised / pressed states
    _BG_RAISED = "#3B3B5C"
    _BG_HOVER = "#4A4A70"
    _BG_PRESSED = "#2A2A42"
    _BORDER_LIGHT = "#6565A0"   # top/left highlight
    _BORDER_DARK = "#222240"    # bottom/right shadow
    _BORDER_PRESSED = "#1A1A30"

    def __init__(self, master, sound_name: str, hotkey: str | None = None,
                 on_play: Callable | None = None,
                 on_context_menu: Callable | None = None, **kwargs):
        super().__init__(master, width=130, height=70, corner_radius=8,
                         **kwargs)
        self.sound_name = sound_name
        self._on_play = on_play
        self._on_context_menu = on_context_menu
        self._pressed = False

        # Build display text
        display = sound_name
        if hotkey:
            display += f"\n[{hotkey}]"

        # Outer highlight border (top-left light edge)
        self._highlight = ctk.CTkFrame(
            self, corner_radius=8, fg_color=self._BORDER_LIGHT,
        )
        self._highlight.pack(fill="both", expand=True, padx=0, pady=0)

        # Shadow border (bottom-right dark edge) — nested inside highlight
        self._shadow = ctk.CTkFrame(
            self._highlight, corner_radius=7, fg_color=self._BORDER_DARK,
        )
        self._shadow.pack(fill="both", expand=True, padx=(2, 0), pady=(2, 0))

        # Inner face of the button
        self._face = ctk.CTkFrame(
            self._shadow, corner_radius=6, fg_color=self._BG_RAISED,
        )
        self._face.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))

        # Label
        self._label = ctk.CTkLabel(
            self._face, text=display,
            font=ctk.CTkFont(size=12), text_color="white",
            anchor="center",
        )
        self._label.pack(fill="both", expand=True, padx=4, pady=4)

        # Bind mouse events on all child widgets
        for widget in (self, self._highlight, self._shadow, self._face,
                        self._label):
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-3>", self._show_context_menu)

    def _on_press(self, event):
        """Swap highlight/shadow to look pressed-in."""
        self._pressed = True
        self._highlight.configure(fg_color=self._BORDER_PRESSED)
        self._shadow.configure(fg_color=self._BORDER_LIGHT)
        self._face.configure(fg_color=self._BG_PRESSED)
        self._shadow.pack_configure(padx=(0, 2), pady=(0, 2))
        self._face.pack_configure(padx=(2, 0), pady=(2, 0))

    def _on_release(self, event):
        """Restore raised look and fire the play callback."""
        if self._pressed:
            self._pressed = False
            self._highlight.configure(fg_color=self._BORDER_LIGHT)
            self._shadow.configure(fg_color=self._BORDER_DARK)
            self._face.configure(fg_color=self._BG_RAISED)
            self._shadow.pack_configure(padx=(2, 0), pady=(2, 0))
            self._face.pack_configure(padx=(0, 2), pady=(0, 2))
            if self._on_play:
                self._on_play(self.sound_name)

    def _on_enter(self, event):
        if not self._pressed:
            self._face.configure(fg_color=self._BG_HOVER)

    def _on_leave(self, event):
        if not self._pressed:
            self._face.configure(fg_color=self._BG_RAISED)

    def _show_context_menu(self, event):
        if self._on_context_menu:
            self._on_context_menu(self.sound_name, event)

    def update_display(self, sound_name: str, hotkey: str | None = None):
        self.sound_name = sound_name
        display = sound_name
        if hotkey:
            display += f"\n[{hotkey}]"
        self._label.configure(text=display)


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
