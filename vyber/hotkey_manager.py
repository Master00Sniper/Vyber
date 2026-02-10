"""Global hotkey management — works even when the app is not focused."""

import logging
import threading
from typing import Callable

import keyboard

logger = logging.getLogger(__name__)


class HotkeyManager:
    """Registers and manages global hotkeys for sound triggers and controls."""

    def __init__(self):
        self._bindings: dict[str, Callable] = {}
        self._stop_all_hotkey: str | None = None
        self._stop_all_callback: Callable | None = None
        self._active = False

    def start(self):
        """Activate hotkey listening."""
        self._active = True
        self._register_all()

    def stop(self):
        """Deactivate all hotkeys."""
        self._active = False
        self._unregister_all()

    def bind_sound(self, hotkey: str, callback: Callable):
        """Bind a hotkey to trigger a sound callback."""
        # Remove old binding if this hotkey was already bound
        if hotkey in self._bindings:
            self._unbind(hotkey)
        self._bindings[hotkey] = callback
        if self._active:
            self._register(hotkey, callback)

    def unbind_sound(self, hotkey: str):
        """Remove a hotkey binding."""
        if hotkey in self._bindings:
            self._unbind(hotkey)
            del self._bindings[hotkey]

    def set_stop_all_hotkey(self, hotkey: str, callback: Callable):
        """Set the stop-all hotkey."""
        # Remove old stop-all binding
        if self._stop_all_hotkey:
            self._unbind(self._stop_all_hotkey)
        self._stop_all_hotkey = hotkey
        self._stop_all_callback = callback
        if self._active:
            self._register(hotkey, callback)

    def rebind_all(self, mappings: dict[str, Callable],
                   stop_all_hotkey: str | None = None,
                   stop_all_callback: Callable | None = None):
        """Replace all bindings at once. Used when config changes."""
        self._unregister_all()
        self._bindings = dict(mappings)
        if stop_all_hotkey and stop_all_callback:
            self._stop_all_hotkey = stop_all_hotkey
            self._stop_all_callback = stop_all_callback
        if self._active:
            self._register_all()
        logger.info("Registered %d hotkey(s), stop-all='%s'",
                     len(self._bindings), self._stop_all_hotkey or "none")

    def _register_all(self):
        """Register all current bindings with the keyboard library."""
        for hotkey, callback in self._bindings.items():
            self._register(hotkey, callback)
        if self._stop_all_hotkey and self._stop_all_callback:
            self._register(self._stop_all_hotkey, self._stop_all_callback)

    def _unregister_all(self):
        """Remove all keyboard hooks."""
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

    def _register(self, hotkey: str, callback: Callable):
        """Register a single hotkey."""
        try:
            # suppress=False so the key still works normally in other apps
            keyboard.add_hotkey(hotkey, lambda cb=callback: self._safe_call(cb),
                                suppress=False, trigger_on_release=False)
        except Exception as e:
            logger.warning("Failed to register hotkey '%s': %s", hotkey, e)

    def _unbind(self, hotkey: str):
        """Unregister a single hotkey."""
        try:
            keyboard.remove_hotkey(hotkey)
        except (KeyError, ValueError):
            pass

    @staticmethod
    def _safe_call(callback: Callable):
        """Call a callback in a separate thread to avoid blocking the hook."""
        threading.Thread(target=callback, daemon=True).start()

    def get_active_bindings(self) -> dict[str, str]:
        """Get a summary of active bindings for display.
        Returns {hotkey: description}.
        """
        result = {}
        for hotkey in self._bindings:
            result[hotkey] = "Sound trigger"
        if self._stop_all_hotkey:
            result[self._stop_all_hotkey] = "Stop all sounds"
        return result
