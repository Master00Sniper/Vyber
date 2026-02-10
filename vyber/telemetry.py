"""Anonymous usage telemetry for Vyber."""

import hashlib
import logging
import platform
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
AUTH_KEY = "ufxknajtcpqylxuvtumanhypesbtexsq"


# =============================================================================
# Machine / Platform Identification
# =============================================================================

def get_machine_id() -> str:
    """Return a stable anonymous machine identifier (SHA-256 of MAC address)."""
    mac = uuid.getnode()
    return hashlib.sha256(str(mac).encode()).hexdigest()


# =============================================================================
# Telemetry Sending
# =============================================================================

def send_telemetry(event_type: str):
    """
    Send a telemetry event in a background thread.

    Args:
        event_type: Event name (e.g. "app_start", "sound_played", "heartbeat").
    """
    threading.Thread(
        target=_send_telemetry_sync,
        args=(event_type,),
        daemon=True,
    ).start()


def _send_telemetry_sync(event_type: str):
    """Synchronous telemetry POST — called from a background thread."""
    try:
        payload = {
            "event": event_type,
            "version": __version__,
            "os": platform.system(),
            "install_id": get_machine_id(),
        }

        response = requests.post(
            TELEMETRY_URL,
            json=payload,
            timeout=TELEMETRY_TIMEOUT,
            headers={
                "User-Agent": f"Vyber/{__version__}",
                "X-Vyber-Auth": AUTH_KEY,
            },
        )

        if response.status_code != 200:
            logger.debug("Telemetry response: %d", response.status_code)

    except Exception as e:
        # Telemetry failures are silent — never interrupt the user
        logger.debug("Telemetry send failed: %s", e)


def send_heartbeat():
    """Convenience wrapper for a heartbeat event."""
    send_telemetry("heartbeat")
