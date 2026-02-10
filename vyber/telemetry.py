"""Anonymous usage telemetry for Vyber."""

import hashlib
import logging
import platform
import sys
import threading
import uuid

import requests

from vyber import __version__

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

TELEMETRY_URL = "https://vyber-proxy.mortonapps.com/telemetry"
TELEMETRY_TIMEOUT = 10  # seconds


# =============================================================================
# Machine / Platform Identification
# =============================================================================

def get_machine_id() -> str:
    """Return a stable anonymous machine identifier (SHA-256 of MAC address)."""
    mac = uuid.getnode()
    return hashlib.sha256(str(mac).encode()).hexdigest()


def get_platform_info() -> dict:
    """Gather anonymous platform details."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "frozen": getattr(sys, "frozen", False),
    }


# =============================================================================
# Telemetry Sending
# =============================================================================

def send_telemetry(event_type: str, extra: dict | None = None):
    """
    Send a telemetry event in a background thread.

    Args:
        event_type: Event name (e.g. "app_start", "sound_played", "heartbeat").
        extra: Optional dict of additional data to include.
    """
    threading.Thread(
        target=_send_telemetry_sync,
        args=(event_type, extra),
        daemon=True,
    ).start()


def _send_telemetry_sync(event_type: str, extra: dict | None = None):
    """Synchronous telemetry POST — called from a background thread."""
    try:
        payload = {
            "event": event_type,
            "version": __version__,
            "machine_id": get_machine_id(),
            "platform": get_platform_info(),
        }
        if extra:
            payload["data"] = extra

        response = requests.post(
            TELEMETRY_URL,
            json=payload,
            timeout=TELEMETRY_TIMEOUT,
            headers={"User-Agent": f"Vyber/{__version__}"},
        )

        if response.status_code != 200:
            logger.debug("Telemetry response: %d", response.status_code)

    except Exception as e:
        # Telemetry failures are silent — never interrupt the user
        logger.debug("Telemetry send failed: %s", e)


def send_heartbeat():
    """Convenience wrapper for a heartbeat event."""
    send_telemetry("heartbeat")
