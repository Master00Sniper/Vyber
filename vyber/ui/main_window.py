"""Main application window — ties together all UI components."""

import customtkinter as ctk
from tkinter import Menu
from typing import Callable
from PIL import Image

from vyber import IMAGES_DIR
from vyber.ui.widgets import VolumeSlider, OutputModeSelector, StatusBar
from vyber.ui.sound_grid import SoundGrid


class MainWindow:
    """The main Vyber window."""

    def __init__(self, root: ctk.CTk, callbacks: dict[str, Callable]):
        """
        Args:
            root: The CTk root window.
            callbacks: Dict of callback functions from the app controller:
                - on_play(category, sound_name)
                - on_stop_all()
                - on_add_sound(category)
                - on_remove_sound(category, sound_name)
                - on_rename_sound(category, sound_name)
                - on_set_hotkey(category, sound_name)
                - on_move_sound(category, sound_name)
                - on_volume_sound(category, sound_name)
                - on_volume_change(value)
                - on_output_mode_change(mode)
                - on_add_category()
                - on_remove_category(name)
                - on_open_settings()
                - get_categories() -> list[str]
        """
        self.root = root
        self.callbacks = callbacks
        self._tab_grids: dict[str, SoundGrid] = {}

        self._build_ui()

    def _build_ui(self):
        """Construct the main window layout."""
        # --- Top control bar ---
        self.top_frame = ctk.CTkFrame(self.root)
        self.top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Output mode selector
        self.output_mode = OutputModeSelector(
            self.top_frame,
            initial="both",
            on_change=self.callbacks.get("on_output_mode_change")
        )
        self.output_mode.pack(side="left", padx=5)

        # Master volume
        self.volume_slider = VolumeSlider(
            self.top_frame,
            label="Volume",
            initial=0.5,
            on_change=self.callbacks.get("on_volume_change")
        )
        self.volume_slider.pack(side="left", padx=15)

        # Stop all button
        self.stop_button = ctk.CTkButton(
            self.top_frame,
            text="Stop All",
            width=90,
            height=32,
            fg_color="#B71C1C",
            hover_color="#D32F2F",
            command=self.callbacks.get("on_stop_all")
        )
        self.stop_button.pack(side="left", padx=10)

        # Settings button
        self.settings_button = ctk.CTkButton(
            self.top_frame,
            text="Settings",
            width=80,
            height=32,
            fg_color="#37474F",
            hover_color="#546E7A",
            command=self.callbacks.get("on_open_settings")
        )
        self.settings_button.pack(side="right", padx=5)

        # Add category button
        self.add_cat_button = ctk.CTkButton(
            self.top_frame,
            text="+ Category",
            width=90,
            height=32,
            fg_color="#2B5B2B",
            hover_color="#3A7A3A",
            command=self.callbacks.get("on_add_category")
        )
        self.add_cat_button.pack(side="right", padx=5)

        # --- Tab view for categories ---
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        # Right-click on tab headers to delete categories
        self._bind_tab_context_menu()

        # --- Status bar ---
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x", padx=10, pady=(0, 5))

    def add_category_tab(self, name: str, sounds: list):
        """Add a category tab with its sound grid."""
        self.tabview.add(name)
        tab_frame = self.tabview.tab(name)

        grid = SoundGrid(
            tab_frame,
            category=name,
            on_play=self.callbacks.get("on_play"),
            on_add=self.callbacks.get("on_add_sound"),
            on_add_folder=self.callbacks.get("on_add_folder"),
            on_remove=self.callbacks.get("on_remove_sound"),
            on_delete_file=self.callbacks.get("on_delete_file"),
            on_rename=self.callbacks.get("on_rename_sound"),
            on_rename_file=self.callbacks.get("on_rename_file"),
            on_set_hotkey=self.callbacks.get("on_set_hotkey"),
            on_move=self.callbacks.get("on_move_sound"),
            on_volume=self.callbacks.get("on_volume_sound"),
            on_reorder=self.callbacks.get("on_reorder_sound"),
            get_categories=self.callbacks.get("get_categories")
        )
        grid.pack(fill="both", expand=True)
        grid.populate(sounds)
        self._tab_grids[name] = grid
        self._bind_tab_context_menu()

    def remove_category_tab(self, name: str):
        """Remove a category tab."""
        if name in self._tab_grids:
            del self._tab_grids[name]
        try:
            self.tabview.delete(name)
        except Exception:
            pass

    def refresh_category(self, name: str, sounds: list):
        """Refresh the sound grid for a category."""
        if name in self._tab_grids:
            self._tab_grids[name].populate(sounds)

    def refresh_all(self, categories: dict[str, list]):
        """Rebuild all tabs."""
        # Remove existing tabs
        for name in list(self._tab_grids.keys()):
            self.remove_category_tab(name)
        # Recreate
        for name, sounds in categories.items():
            self.add_category_tab(name, sounds)

    def _bind_tab_context_menu(self):
        """Bind right-click on tab headers for category management."""
        try:
            seg_button = self.tabview._segmented_button
            # CTkSegmentedButton doesn't support .bind() directly,
            # so bind on the underlying tk frame and its children
            tk_frame = seg_button._canvas if hasattr(seg_button, '_canvas') else None
            targets = list(seg_button.winfo_children())
            if tk_frame:
                targets.append(tk_frame)
            for widget in targets:
                try:
                    widget.bind("<Button-3>", self._tab_context_menu)
                except (NotImplementedError, AttributeError):
                    pass
                # Also bind on grandchildren (the actual button labels)
                for grandchild in widget.winfo_children():
                    try:
                        grandchild.bind("<Button-3>", self._tab_context_menu)
                    except (NotImplementedError, AttributeError):
                        pass
        except (AttributeError, NotImplementedError):
            pass

    def _tab_context_menu(self, event):
        """Show right-click menu on the current tab."""
        current = self.tabview.get()
        if not current:
            return
        menu = Menu(self.root, tearoff=0)
        menu.configure(
            bg="#2b2b2b", fg="white", activebackground="#404040",
            activeforeground="white"
        )
        if current == "General":
            menu.add_command(
                label="Delete All Sounds",
                command=lambda: self.callbacks["on_clear_category"](current)
            )
        else:
            menu.add_command(
                label=f"Delete \"{current}\"",
                command=lambda: self.callbacks["on_remove_category"](current)
            )
        menu.tk_popup(event.x_root, event.y_root)

    def set_cable_status(self, installed: bool, name: str = ""):
        self.status_bar.set_cable_status(installed, name)

    def set_playing_count(self, count: int):
        self.status_bar.set_playing_count(count)

    def set_device_info(self, text: str):
        self.status_bar.set_device_info(text)

    def set_output_mode(self, mode: str):
        self.output_mode.set(mode)

    def set_cable_available(self, available: bool):
        """Enable or disable mic-dependent output modes."""
        self.output_mode.set_cable_available(available)

    def update_playing_states(self, playing_remaining: dict[str, float]):
        """Update gold pulse and countdown on all sound buttons across all tabs."""
        for grid in self._tab_grids.values():
            grid.update_playing_states(playing_remaining)

    def set_volume(self, volume: float):
        self.volume_slider.set(volume)
