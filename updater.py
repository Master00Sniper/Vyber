# updater.py
# Handles manual updates for Vyber via GitHub releases.

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
PROXY_BASE_URL = "https://vyber-proxy.mortonapps.com"
GITHUB_API_URL = f"{PROXY_BASE_URL}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
AUTH_KEY = "ufxknajtcpqylxuvtumanhypesbtexsq"

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Vyber-Updater/1.0",
    "X-Vyber-Auth": AUTH_KEY,
}


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
# Update Check
# =============================================================================

def check_for_updates():
    """
    Check GitHub for a newer release.

    Returns:
        {"status": "update", "version": str, "url": str} if update available,
        {"status": "up_to_date"} if already current,
        {"status": "error", "message": str} on failure.
    """
    try:
        logger.info("Checking for updates (current: v%s)...", CURRENT_VERSION)

        response = requests.get(GITHUB_API_URL, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            msg = f"Server returned status {response.status_code}"
            logger.error("GitHub API returned status %d", response.status_code)
            return {"status": "error", "message": msg}

        release_data = response.json()
        latest_version = release_data.get("tag_name")

        if not latest_version:
            logger.error("No version tag found in release")
            return {"status": "error", "message": "No version found in release"}

        if compare_versions(latest_version, CURRENT_VERSION) <= 0:
            logger.info("Already up to date (v%s)", CURRENT_VERSION)
            return {"status": "up_to_date"}

        logger.info("Update available: %s", latest_version)

        # Find the Vyber.exe asset in the release
        assets = release_data.get("assets", [])
        asset = next(
            (a for a in assets if a["name"].lower() == "vyber.exe"), None
        )
        if not asset:
            logger.error("No Vyber.exe found in release assets")
            return {"status": "error", "message": "No Vyber.exe found in release"}

        return {"status": "update", "version": latest_version,
                "url": asset["browser_download_url"]}

    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error: %s", e)
        return {"status": "error", "message": "Connection failed — check your internet"}
    except requests.exceptions.Timeout as e:
        logger.error("Timeout error: %s", e)
        return {"status": "error", "message": "Request timed out"}
    except requests.RequestException as e:
        logger.error("Network error: %s", e)
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error("Unexpected error: %s: %s", type(e).__name__, e)
        return {"status": "error", "message": str(e)}


# =============================================================================
# Download & Apply Update
# =============================================================================

def download_and_apply(download_url, show_notification_func=None):
    """
    Download the new exe and apply the update (restarts Vyber).

    Args:
        download_url: Direct URL to the new Vyber.exe asset.
        show_notification_func: Optional callback for status messages.
    """
    try:
        logger.info("Starting download...")
        if show_notification_func:
            show_notification_func("Downloading update...")

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

        if show_notification_func:
            show_notification_func("Vyber will restart in a few seconds...")

        time.sleep(3)
        perform_update(temp_exe_path)

    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error during download: %s", e)
    except requests.exceptions.Timeout as e:
        logger.error("Timeout during download: %s", e)
    except requests.RequestException as e:
        logger.error("Network error during download: %s", e)
    except Exception as e:
        logger.error("Unexpected error during download: %s: %s", type(e).__name__, e)


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
