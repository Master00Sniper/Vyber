"""System tray icon — allows Vyber to minimize to the tray."""

import logging
import threading
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False


class TrayManager:
    """Manages the system tray icon and its menu."""

    def __init__(self, icon_path: str, on_show: callable, on_quit: callable,
                 on_check_update: callable = None):
        """
        Args:
            icon_path: Path to the tray icon image (PNG).
            on_show: Callback to restore/show the main window.
            on_quit: Callback to fully quit the application.
            on_check_update: Callback to manually check for updates.
        """
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_check_update = on_check_update
        self._icon = None
        self._icon_image = None

        if not HAS_PYSTRAY:
            logger.warning("pystray not installed — tray icon disabled")
            return

        try:
            self._icon_image = Image.open(icon_path)
        except Exception as e:
            logger.error("Failed to load tray icon '%s': %s", icon_path, e)
            return

        menu = pystray.Menu(
            pystray.MenuItem("Show Vyber", self._show, default=True),
            pystray.MenuItem("Check for Updates", self._check_update),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self._icon = pystray.Icon("Vyber", self._icon_image, "Vyber", menu)

    @property
    def available(self) -> bool:
        """Whether the tray icon is ready to use."""
        return self._icon is not None

    def start(self):
        """Start the tray icon in a background thread."""
        if not self._icon:
            return
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def stop(self):
        """Remove the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _show(self, icon=None, item=None):
        if self._on_show:
            self._on_show()

    def _check_update(self, icon=None, item=None):
        if self._on_check_update:
            self._on_check_update()

    def _quit(self, icon=None, item=None):
        if self._on_quit:
            self._on_quit()
