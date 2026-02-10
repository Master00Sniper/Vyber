# updater.py
# Handles automatic updates for Vyber via GitHub releases.

import logging
import os
import subprocess
import tempfile
import time
import sys

import requests

from vyber import __version__ as CURRENT_VERSION

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

GITHUB_OWNER = "Master00Sniper"
GITHUB_REPO = "Vyber"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Vyber-Updater/1.0",
}

# Tracks downloaded update waiting to be applied
pending_update_path = None


# =============================================================================
# Utility Functions
# =============================================================================

def is_development_mode():
    """Check if running from source (not compiled .exe)."""
    return not getattr(sys, "frozen", False)


def compare_versions(version1, version2):
    """
    Compare semantic versions (e.g., '1.2.3' vs '1.2.2').
    Returns: 1 if v1 > v2, -1 if v1 < v2, 0 if equal.
    """
    v1 = list(map(int, version1.lstrip("v").split(".")))
    v2 = list(map(int, version2.lstrip("v").split(".")))

    for a, b in zip(v1, v2):
        if a > b:
            return 1
        if a < b:
            return -1

    return 0 if len(v1) == len(v2) else (1 if len(v1) > len(v2) else -1)


# =============================================================================
# Update Check & Download
# =============================================================================

def check_for_updates(show_notification_func=None):
    """
    Check GitHub for new releases and download if available.

    Args:
        show_notification_func: Callback to display user notifications.
    """
    global pending_update_path

    if is_development_mode():
        logger.info("Development mode — skipping update check")
        return

    try:
        logger.info("Checking for updates (current: v%s)...", CURRENT_VERSION)

        response = requests.get(GITHUB_API_URL, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            logger.error("GitHub API returned status %d", response.status_code)
            return

        release_data = response.json()
        latest_version = release_data.get("tag_name")

        if not latest_version:
            logger.error("No version tag found in release")
            return

        if compare_versions(latest_version, CURRENT_VERSION) <= 0:
            logger.info("Already up to date (v%s)", CURRENT_VERSION)
            return

        logger.info("Update available: %s", latest_version)

        # Find the Vyber.exe asset in the release
        assets = release_data.get("assets", [])
        asset = next(
            (a for a in assets if a["name"].lower() == "vyber.exe"), None
        )
        if not asset:
            logger.error("No Vyber.exe found in release assets")
            return

        download_url = asset["browser_download_url"]

        # Download the update
        logger.info("Starting download...")
        if show_notification_func:
            show_notification_func(
                f"Downloading Vyber {latest_version}..."
            )

        download_response = requests.get(
            download_url, headers=HEADERS, stream=True, timeout=60
        )
        download_response.raise_for_status()

        temp_dir = tempfile.gettempdir()
        temp_exe_path = os.path.join(temp_dir, "vyber_new.exe")

        total_size = 0
        with open(temp_exe_path, "wb") as f:
            for chunk in download_response.iter_content(chunk_size=8192):
                f.write(chunk)
                total_size += len(chunk)

        if not os.path.exists(temp_exe_path) or os.path.getsize(temp_exe_path) == 0:
            logger.error("Download failed — empty file")
            return

        logger.info("Download complete: %.2f MB", total_size / 1024 / 1024)
        pending_update_path = temp_exe_path

        logger.info("Applying update...")
        apply_pending_update(show_notification_func)

    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error: %s", e)
    except requests.exceptions.Timeout as e:
        logger.error("Timeout error: %s", e)
    except requests.RequestException as e:
        logger.error("Network error: %s", e)
    except Exception as e:
        logger.error("Unexpected error: %s: %s", type(e).__name__, e)


# =============================================================================
# Update Application
# =============================================================================

def apply_pending_update(show_notification_func=None):
    """Apply a previously downloaded update — restart Vyber with the new exe."""
    global pending_update_path

    if not pending_update_path or not os.path.exists(pending_update_path):
        pending_update_path = None
        return

    logger.info("Applying pending update from: %s", pending_update_path)

    if show_notification_func:
        show_notification_func("Vyber will restart in a few seconds...")

    time.sleep(3)
    perform_update(pending_update_path)
    pending_update_path = None


def perform_update(new_exe_path):
    """
    Replace the current executable with the new version.
    Uses a hidden batch script to swap the file and relaunch.
    """
    if getattr(sys, "frozen", False):
        current_exe = sys.argv[0]
    else:
        current_exe = sys.executable
    current_exe_dir = os.path.dirname(current_exe)
    temp_dir = tempfile.gettempdir()
    batch_path = os.path.join(temp_dir, "vyber_update.bat")
    vbs_path = os.path.join(temp_dir, "vyber_update.vbs")
    log_path = os.path.join(temp_dir, "vyber_update_log.txt")

    logger.info("Creating update scripts...")
    logger.info("Current exe: %s", current_exe)
    logger.info("New exe: %s", new_exe_path)

    batch_content = f'''@echo off
set attempts=0
set max_attempts=30
echo %date% %time% - Starting update process... > "{log_path}"
echo Waiting for Vyber to close... >> "{log_path}"
ping 127.0.0.1 -n 3 > nul

echo Force-killing any lingering Vyber processes... >> "{log_path}"
taskkill /f /im Vyber.exe >> "{log_path}" 2>&1
ping 127.0.0.1 -n 3 > nul

:delete_loop
set /a attempts+=1
echo Attempt %attempts%: Deleting old version... >> "{log_path}"
del /F /Q "{current_exe}" 2>> "{log_path}"
if exist "{current_exe}" (
    if %attempts% geq %max_attempts% (
        echo ERROR: Failed to delete after %max_attempts% attempts. >> "{log_path}"
        goto cleanup
    )
    echo Old exe still exists - retrying... >> "{log_path}"
    ping 127.0.0.1 -n 2 > nul
    goto delete_loop
)
echo Old version deleted after %attempts% attempt(s). >> "{log_path}"

echo Moving new version into place... >> "{log_path}"
move /Y "{new_exe_path}" "{current_exe}" >> "{log_path}" 2>&1
if not exist "{current_exe}" (
    echo ERROR: Move failed! >> "{log_path}"
    goto cleanup
)
echo Move successful. >> "{log_path}"
ping 127.0.0.1 -n 3 > nul

echo Starting updated Vyber... >> "{log_path}"
cd /d "{current_exe_dir}"
echo Working directory: %CD% >> "{log_path}"
explorer.exe "{current_exe}"
echo Launch complete. >> "{log_path}"

:cleanup
echo Cleaning up... >> "{log_path}"
del /F /Q "{vbs_path}" 2>nul
del /F /Q "%~f0"
'''

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{batch_path}" & chr(34), 0, False
Set WshShell = Nothing
'''

    try:
        with open(batch_path, "w", encoding="ascii", errors="replace") as f:
            f.write(batch_content)
        with open(vbs_path, "w", encoding="ascii", errors="replace") as f:
            f.write(vbs_content)

        logger.info("Executing update via VBScript (hidden)...")

        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["wscript.exe", "//nologo", vbs_path],
            creationflags=subprocess.DETACHED_PROCESS | CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

        logger.info("Update process launched — exiting Vyber...")
        time.sleep(0.5)
        os._exit(0)

    except Exception as e:
        logger.error("Update execution failed: %s", e)


# =============================================================================
# Background Update Checker
# =============================================================================

def periodic_update_check(stop_event, show_notification_func=None, check_interval=3600):
    """
    Background thread that periodically checks for updates.

    Args:
        stop_event: Threading event to signal shutdown.
        show_notification_func: Callback to display user notifications.
        check_interval: Seconds between checks (default: 1 hour).
    """
    logger.info(
        "Update checker starting (first check in %d minutes)...",
        check_interval // 60,
    )

    check_count = 0
    while not stop_event.is_set():
        if stop_event.wait(check_interval):
            break

        try:
            check_count += 1
            logger.info("Periodic update check #%d", check_count)
            check_for_updates(show_notification_func)
        except Exception as e:
            logger.error("Error in periodic check: %s", e)

    logger.info("Update checker stopped")
