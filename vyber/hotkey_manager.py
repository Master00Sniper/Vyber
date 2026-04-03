"""Global hotkey management - works even when the app is not focused."""

import logging
import threading
from typing import Callable

import keyboard

logger = logging.getLogger(__name__)


MODIFIER_KEY_NAMES = {"ctrl", "shift", "alt"}


def format_hotkey_key_name(event) -> str:
    """Return a readable storage label for a non-modifier key event."""
    key_name = (event.name or str(event.scan_code)).lower()
    if getattr(event, "is_keypad", False):
        return f"numpad {key_name}"
    return key_name


class HotkeySpec:
    """Parsed representation of the app's supported hotkey format."""

    def __init__(self, source: str, modifiers: set[str], key_name: str,
                 require_keypad: bool | None):
        self.source = source
        self.modifiers = modifiers
        self.key_name = key_name
        self.require_keypad = require_keypad

    @classmethod
    def parse(cls, hotkey: str) -> "HotkeySpec":
        parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
        modifiers: set[str] = set()
        key_name: str | None = None
        require_keypad: bool | None = None

        for part in parts:
            if part in MODIFIER_KEY_NAMES:
                modifiers.add(part)
                continue
            if part.startswith("numpad "):
                key_name = part[len("numpad "):].strip()
                require_keypad = True
                continue
            key_name = part
            require_keypad = None

        if key_name is None:
            raise ValueError(f"Hotkey '{hotkey}' does not include a trigger key")

        return cls(hotkey, modifiers, key_name, require_keypad)

    def matches(self, event) -> bool:
        if event.event_type != keyboard.KEY_DOWN:
            return False
        if (event.name or "").lower() != self.key_name:
            return False
        if self.require_keypad is True and not getattr(event, "is_keypad", False):
            return False
        if self.require_keypad is False and getattr(event, "is_keypad", False):
            return False
        return self._modifiers_match()

    def release_matches(self, event) -> bool:
        if event.event_type != keyboard.KEY_UP:
            return False
        if (event.name or "").lower() != self.key_name:
            return False
        if self.require_keypad is True and not getattr(event, "is_keypad", False):
            return False
        if self.require_keypad is False and getattr(event, "is_keypad", False):
            return False
        return True

    def _modifiers_match(self) -> bool:
        for modifier in MODIFIER_KEY_NAMES:
            pressed = _is_modifier_pressed(modifier)
            if modifier in self.modifiers:
                if not pressed:
                    return False
            elif pressed:
                return False
        return True


def _is_modifier_pressed(modifier: str) -> bool:
    try:
        return keyboard.is_pressed(modifier)
    except Exception:
        return False


class HotkeyManager:
    """Registers and manages global hotkeys for sound triggers and controls."""

    def __init__(self):
        self._bindings: dict[str, Callable] = {}
        self._binding_specs: dict[str, HotkeySpec] = {}
        self._stop_all_hotkey: str | None = None
        self._stop_all_callback: Callable | None = None
        self._stop_all_spec: HotkeySpec | None = None
        self._active = False
        self._hook = None
        self._fired_hotkeys: set[str] = set()

    def start(self):
        """Activate hotkey listening."""
        if self._active:
            return
        self._active = True
        self._register_hook()

    def stop(self):
        """Deactivate all hotkeys."""
        if not self._active:
            return
        self._active = False
        self._unregister_hook()

    def bind_sound(self, hotkey: str, callback: Callable):
        """Bind a hotkey to trigger a sound callback."""
        self._bindings[hotkey] = callback
        try:
            self._binding_specs[hotkey] = HotkeySpec.parse(hotkey)
        except ValueError as e:
            logger.warning("Failed to parse hotkey '%s': %s", hotkey, e)
            self._binding_specs.pop(hotkey, None)

    def unbind_sound(self, hotkey: str):
        """Remove a hotkey binding."""
        if hotkey in self._bindings:
            del self._bindings[hotkey]
            self._binding_specs.pop(hotkey, None)
            self._fired_hotkeys.discard(hotkey)

    def set_stop_all_hotkey(self, hotkey: str, callback: Callable):
        """Set the stop-all hotkey."""
        self._stop_all_hotkey = hotkey
        self._stop_all_callback = callback
        try:
            self._stop_all_spec = HotkeySpec.parse(hotkey)
        except ValueError as e:
            logger.warning("Failed to parse stop-all hotkey '%s': %s", hotkey, e)
            self._stop_all_spec = None

    def rebind_all(self, mappings: dict[str, Callable],
                   stop_all_hotkey: str | None = None,
                   stop_all_callback: Callable | None = None):
        """Replace all bindings at once. Used when config changes."""
        self._bindings = dict(mappings)
        self._binding_specs = {}
        for hotkey in self._bindings:
            try:
                self._binding_specs[hotkey] = HotkeySpec.parse(hotkey)
            except ValueError as e:
                logger.warning("Failed to parse hotkey '%s': %s", hotkey, e)
        if stop_all_hotkey and stop_all_callback:
            self._stop_all_hotkey = stop_all_hotkey
            self._stop_all_callback = stop_all_callback
            try:
                self._stop_all_spec = HotkeySpec.parse(stop_all_hotkey)
            except ValueError as e:
                logger.warning("Failed to parse stop-all hotkey '%s': %s",
                               stop_all_hotkey, e)
                self._stop_all_spec = None
        else:
            self._stop_all_hotkey = None
            self._stop_all_callback = None
            self._stop_all_spec = None
        self._fired_hotkeys.clear()
        logger.info("Registered %d hotkey(s), stop-all='%s'",
                    len(self._bindings), self._stop_all_hotkey or "none")

    def _register_hook(self):
        """Install the global keyboard hook."""
        try:
            self._hook = keyboard.hook(self._handle_event, suppress=False)
        except Exception as e:
            logger.warning("Failed to install keyboard hook: %s", e)
            self._hook = None

    def _unregister_hook(self):
        """Remove the global keyboard hook."""
        try:
            if self._hook is not None:
                keyboard.unhook(self._hook)
        except Exception:
            pass
        self._hook = None
        self._fired_hotkeys.clear()

    def _handle_event(self, event):
        """Dispatch matching hotkeys from raw keyboard events."""
        if event.event_type == keyboard.KEY_UP:
            self._clear_released_hotkeys(event)
            return
        if event.event_type != keyboard.KEY_DOWN:
            return

        if self._stop_all_hotkey and self._stop_all_callback and self._stop_all_spec:
            if self._match_and_mark(self._stop_all_hotkey, self._stop_all_spec, event):
                self._safe_call(self._stop_all_callback)
                return

        for hotkey, callback in self._bindings.items():
            spec = self._binding_specs.get(hotkey)
            if spec and self._match_and_mark(hotkey, spec, event):
                self._safe_call(callback)

    def _match_and_mark(self, hotkey: str, spec: HotkeySpec, event) -> bool:
        """Return True only once per matching key press."""
        if hotkey in self._fired_hotkeys:
            return False
        if not spec.matches(event):
            return False
        self._fired_hotkeys.add(hotkey)
        return True

    def _clear_released_hotkeys(self, event):
        """Allow a hotkey to fire again after its trigger key is released."""
        for hotkey, spec in self._binding_specs.items():
            if spec.release_matches(event):
                self._fired_hotkeys.discard(hotkey)
        if self._stop_all_hotkey and self._stop_all_spec:
            if self._stop_all_spec.release_matches(event):
                self._fired_hotkeys.discard(self._stop_all_hotkey)

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
