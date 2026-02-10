"""Sound button grid — displays sounds within a category tab."""

import os
import textwrap
import customtkinter as ctk
from tkinter import Menu
from typing import Callable


class SoundButton(ctk.CTkButton):
    """Flat sound button with playing-state gold pulse."""

    _COLOR_NORMAL = "#2B4C7E"
    _COLOR_HOVER = "#3A6BA5"
    _COLOR_GOLD = "#FFD700"
    _COLOR_GOLD_DIM = "#8B7500"
    _COLOR_DRAG_TARGET = "#4A7A2B"
    _BUTTON_WIDTH = 130
    _BUTTON_HEIGHT = 70
    _WRAP_CHARS = 16  # max characters per line before wrapping

    def __init__(self, master, sound_name: str, filepath: str = "",
                 hotkey: str | None = None,
                 on_play: Callable | None = None,
                 on_context_menu: Callable | None = None, **kwargs):
        display = self._format_display(sound_name, hotkey)

        super().__init__(
            master, text=display,
            width=self._BUTTON_WIDTH, height=self._BUTTON_HEIGHT,
            corner_radius=8, fg_color=self._COLOR_NORMAL,
            hover_color=self._COLOR_HOVER,
            border_width=0,
            font=ctk.CTkFont(size=12),
            command=self._clicked,
            **kwargs,
        )
        self.sound_name = sound_name
        self.filepath = filepath
        self._hotkey = hotkey
        self._on_play = on_play
        self._on_context_menu = on_context_menu
        self._playing = False
        self._pulse_bright = True
        self._pulse_id = None
        self._drag_blocked = False  # set by grid when drag completes

        self.bind("<Button-3>", self._show_context_menu)

    @classmethod
    def _format_display(cls, sound_name: str, hotkey: str | None = None) -> str:
        """Word-wrap the display name, truncating to 2 lines max."""
        max_lines = 2
        wrapped = textwrap.fill(sound_name, width=cls._WRAP_CHARS)
        lines = wrapped.split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            # Truncate last visible line with ellipsis
            lines[-1] = lines[-1][:cls._WRAP_CHARS - 1].rstrip() + "\u2026"
        result = "\n".join(lines)
        if hotkey:
            result += f"\n[{hotkey}]"
        return result

    def _clicked(self, *_args):
        if self._drag_blocked:
            self._drag_blocked = False
            return
        if self._on_play:
            self._on_play(self.sound_name)

    def _show_context_menu(self, event):
        if self._on_context_menu:
            self._on_context_menu(self.sound_name, event)

    def set_playing(self, playing: bool, remaining: float = 0.0):
        """Start or stop the gold border pulse animation with countdown."""
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
            # Restore original display text
            self.configure(text=self._format_display(self.sound_name, self._hotkey))

        if playing and remaining > 0:
            secs = int(remaining)
            mins, secs = divmod(secs, 60)
            countdown = f"{mins}:{secs:02d}" if mins else f"0:{secs:02d}"
            self.configure(text=f"{self._format_display(self.sound_name)}\n{countdown}")

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
        self._hotkey = hotkey
        self.configure(text=self._format_display(sound_name, hotkey))


class SoundGrid(ctk.CTkScrollableFrame):
    """Scrollable grid of sound buttons for a single category."""

    _BUTTON_WIDTH = 130
    _BUTTON_PAD = 10  # 5px on each side
    _CELL_WIDTH = _BUTTON_WIDTH + _BUTTON_PAD
    _MIN_COLUMNS = 3
    _DRAG_THRESHOLD = 8  # pixels before drag activates

    def __init__(self, master, category: str,
                 on_play: Callable[[str, str], None] | None = None,
                 on_add: Callable[[str], None] | None = None,
                 on_add_folder: Callable[[str], None] | None = None,
                 on_remove: Callable[[str, str], None] | None = None,
                 on_rename: Callable[[str, str], None] | None = None,
                 on_set_hotkey: Callable[[str, str], None] | None = None,
                 on_move: Callable[[str, str], None] | None = None,
                 on_volume: Callable[[str, str], None] | None = None,
                 on_reorder: Callable[[str, str, int], None] | None = None,
                 get_categories: Callable[[], list[str]] | None = None,
                 **kwargs):
        super().__init__(master, **kwargs)
        self.category = category
        self._on_play = on_play
        self._on_add = on_add
        self._on_add_folder = on_add_folder
        self._on_remove = on_remove
        self._on_rename = on_rename
        self._on_set_hotkey = on_set_hotkey
        self._on_move = on_move
        self._on_volume = on_volume
        self._on_reorder = on_reorder
        self._get_categories = get_categories
        self._buttons: dict[str, SoundButton] = {}
        self._button_order: list[str] = []  # ordered list of sound names
        self._columns = self._MIN_COLUMNS
        self._sounds_cache: list | None = None  # cached for re-layout

        # Drag state
        self._drag_source: str | None = None
        self._drag_active = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_target_btn: SoundButton | None = None

        # Add sound button (always at the end, same size as sound buttons)
        self._add_button = ctk.CTkButton(
            self, text="+ Add Sound",
            width=SoundButton._BUTTON_WIDTH, height=SoundButton._BUTTON_HEIGHT,
            corner_radius=8, fg_color="#2B5B2B", hover_color="#3A7A3A",
            font=ctk.CTkFont(size=12),
            command=self._add_sound_clicked
        )

        # Respond to width changes
        self.bind("<Configure>", self._on_configure)

    def populate(self, sounds: list):
        """Fill the grid with sound buttons. `sounds` is a list of SoundEntry."""
        # Clear existing buttons
        for btn in self._buttons.values():
            btn.destroy()
        self._buttons.clear()
        self._button_order.clear()
        self._sounds_cache = sounds

        for sound in sounds:
            btn = SoundButton(
                self,
                sound_name=sound.name,
                filepath=sound.path,
                hotkey=sound.hotkey,
                on_play=lambda name: self._play(name),
                on_context_menu=self._context_menu
            )
            self._buttons[sound.name] = btn
            self._button_order.append(sound.name)
            self._bind_drag(btn)

        self._layout_buttons()

    def _on_configure(self, event):
        """Recalculate columns when the grid is resized."""
        width = event.width
        new_cols = max(self._MIN_COLUMNS, width // self._CELL_WIDTH)
        if new_cols != self._columns:
            self._columns = new_cols
            self._layout_buttons()

    def _layout_buttons(self):
        """Place all buttons on the grid using current column count."""
        for i, name in enumerate(self._button_order):
            btn = self._buttons.get(name)
            if btn:
                row, col = divmod(i, self._columns)
                btn.grid(row=row, column=col, padx=5, pady=5)

        add_idx = len(self._button_order)
        row, col = divmod(add_idx, self._columns)
        self._add_button.grid(row=row, column=col, padx=5, pady=5)

    def _bind_drag(self, btn: SoundButton):
        """Bind drag events to a sound button and its children."""
        for widget in [btn] + list(btn.winfo_children()):
            widget.bind("<ButtonPress-1>", lambda e, b=btn: self._drag_press(e, b), add="+")
            widget.bind("<B1-Motion>", lambda e, b=btn: self._drag_motion(e, b), add="+")
            widget.bind("<ButtonRelease-1>", lambda e, b=btn: self._drag_release(e, b), add="+")

    def _drag_press(self, event, btn: SoundButton):
        """Record start position for potential drag."""
        self._drag_source = btn.sound_name
        self._drag_active = False
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

    def _drag_motion(self, event, btn: SoundButton):
        """Activate drag if mouse moved past threshold."""
        if self._drag_source is None:
            return

        dx = abs(event.x_root - self._drag_start_x)
        dy = abs(event.y_root - self._drag_start_y)
        if not self._drag_active and (dx > self._DRAG_THRESHOLD or dy > self._DRAG_THRESHOLD):
            self._drag_active = True
            # Dim the source button
            src_btn = self._buttons.get(self._drag_source)
            if src_btn:
                src_btn.configure(fg_color="#1A3050")

        if self._drag_active:
            # Highlight the button under the cursor
            target_widget = self.winfo_containing(event.x_root, event.y_root)
            target_btn = self._find_sound_button(target_widget)

            # Clear previous highlight
            if self._drag_target_btn and self._drag_target_btn.sound_name != self._drag_source:
                self._drag_target_btn.configure(
                    border_width=0 if not self._drag_target_btn._playing else 2
                )
            self._drag_target_btn = None

            if target_btn and target_btn.sound_name != self._drag_source:
                target_btn.configure(border_width=2, border_color=SoundButton._COLOR_DRAG_TARGET)
                self._drag_target_btn = target_btn

    def _drag_release(self, event, btn: SoundButton):
        """Complete drag or fall through to normal click."""
        if self._drag_active and self._drag_source:
            # Block the command callback from firing on the source button
            src_btn = self._buttons.get(self._drag_source)
            if src_btn:
                src_btn._drag_blocked = True
                src_btn.configure(fg_color=SoundButton._COLOR_NORMAL)

            # Clear target highlight
            if self._drag_target_btn:
                self._drag_target_btn.configure(
                    border_width=0 if not self._drag_target_btn._playing else 2
                )

            # Find drop target
            target_widget = self.winfo_containing(event.x_root, event.y_root)
            target_btn = self._find_sound_button(target_widget)

            if target_btn and target_btn.sound_name != self._drag_source:
                # Determine target index
                target_idx = self._button_order.index(target_btn.sound_name)
                if self._on_reorder:
                    self._on_reorder(self.category, self._drag_source, target_idx)

        self._drag_source = None
        self._drag_active = False
        self._drag_target_btn = None

    def _find_sound_button(self, widget) -> SoundButton | None:
        """Walk up the widget tree to find a SoundButton ancestor."""
        while widget is not None:
            if isinstance(widget, SoundButton) and widget.sound_name in self._buttons:
                return widget
            try:
                widget = widget.master
            except AttributeError:
                break
        return None

    def update_playing_states(self, playing_remaining: dict[str, float]):
        """Update gold pulse and countdown on buttons whose sounds are playing."""
        for btn in self._buttons.values():
            remaining = playing_remaining.get(btn.filepath, 0.0)
            btn.set_playing(btn.filepath in playing_remaining, remaining)

    def _play(self, sound_name: str):
        if self._on_play:
            self._on_play(self.category, sound_name)

    def _add_sound_clicked(self):
        """Show menu with Add Files / Add Folder options."""
        menu = Menu(self, tearoff=0)
        menu.configure(
            bg="#2b2b2b", fg="white", activebackground="#404040",
            activeforeground="white"
        )
        menu.add_command(
            label="Add Files...",
            command=lambda: self._on_add(self.category) if self._on_add else None
        )
        menu.add_command(
            label="Add Folder...",
            command=lambda: self._on_add_folder(self.category) if self._on_add_folder else None
        )
        # Position the menu at the Add button
        btn = self._add_button
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        menu.tk_popup(x, y)

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
