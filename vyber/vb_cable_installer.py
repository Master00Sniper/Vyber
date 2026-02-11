"""Download and install VB-CABLE virtual audio driver."""

import os
import sys
import platform
import tempfile
import zipfile
import subprocess
import threading
import urllib.request
import urllib.error

# Known download URL for VB-CABLE driver pack
VB_CABLE_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"
VB_CABLE_PAGE = "https://vb-audio.com/Cable/"


def _get_installer_name() -> str:
    """Return the correct installer exe name based on system architecture."""
    if platform.machine().endswith("64") or sys.maxsize > 2**32:
        return "VBCABLE_Setup_x64.exe"
    return "VBCABLE_Setup.exe"


def download_and_install(
    on_progress: callable = None,
    on_success: callable = None,
    on_error: callable = None,
):
    """Download VB-CABLE and launch the installer.

    All callbacks are called from the background thread — the caller is
    responsible for scheduling UI updates on the main thread.

    Args:
        on_progress: Called with a status string as work proceeds.
        on_success: Called (no args) after the installer finishes.
        on_error: Called with an error message string on failure.
    """
    thread = threading.Thread(
        target=_install_worker,
        args=(on_progress, on_success, on_error),
        daemon=True,
    )
    thread.start()
    return thread


def _install_worker(on_progress, on_success, on_error):
    """Background worker that downloads and launches the VB-CABLE installer."""
    tmp_dir = None
    try:
        # --- Download ---
        if on_progress:
            on_progress("Downloading VB-CABLE driver...")

        tmp_dir = tempfile.mkdtemp(prefix="vyber_vbcable_")
        zip_path = os.path.join(tmp_dir, "vbcable.zip")

        urllib.request.urlretrieve(VB_CABLE_URL, zip_path)

        # --- Extract ---
        if on_progress:
            on_progress("Extracting installer...")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # --- Locate installer ---
        installer_name = _get_installer_name()
        installer_path = os.path.join(tmp_dir, installer_name)

        if not os.path.isfile(installer_path):
            # Search subdirectories in case the zip nests files
            for root, _dirs, files in os.walk(tmp_dir):
                if installer_name in files:
                    installer_path = os.path.join(root, installer_name)
                    break

        if not os.path.isfile(installer_path):
            if on_error:
                on_error(
                    f"Could not find {installer_name} in the downloaded archive."
                )
            return

        # --- Launch installer with elevation (triggers UAC) ---
        if on_progress:
            on_progress(
                "Launching installer — please approve the admin prompt..."
            )

        # ShellExecuteExW with "runas" requests admin elevation and returns
        # a process handle so we can wait for the installer to finish.
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes

            class SHELLEXECUTEINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.DWORD),
                    ("fMask", ctypes.c_ulong),
                    ("hwnd", ctypes.wintypes.HANDLE),
                    ("lpVerb", ctypes.c_wchar_p),
                    ("lpFile", ctypes.c_wchar_p),
                    ("lpParameters", ctypes.c_wchar_p),
                    ("lpDirectory", ctypes.c_wchar_p),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", ctypes.wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p),
                    ("lpClass", ctypes.c_wchar_p),
                    ("hkeyClass", ctypes.wintypes.HKEY),
                    ("dwHotKey", ctypes.wintypes.DWORD),
                    ("hIconOrMonitor", ctypes.wintypes.HANDLE),
                    ("hProcess", ctypes.wintypes.HANDLE),
                ]

            SEE_MASK_NOCLOSEPROCESS = 0x00000040
            INFINITE = 0xFFFFFFFF

            sei = SHELLEXECUTEINFO()
            sei.cbSize = ctypes.sizeof(sei)
            sei.fMask = SEE_MASK_NOCLOSEPROCESS
            sei.lpVerb = "runas"
            sei.lpFile = installer_path
            sei.lpDirectory = tmp_dir
            sei.nShow = 1  # SW_SHOWNORMAL

            if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
                if on_error:
                    on_error(
                        "Installer could not be launched. "
                        "You may need to run it manually from:\n"
                        f"{installer_path}"
                    )
                return

            if on_progress:
                on_progress(
                    "VB-CABLE installer is running. "
                    "Click 'Install Driver' in the installer window..."
                )

            # Wait for the user to finish the VB-CABLE installer
            if sei.hProcess:
                ctypes.windll.kernel32.WaitForSingleObject(
                    sei.hProcess, INFINITE
                )
                ctypes.windll.kernel32.CloseHandle(sei.hProcess)
        else:
            proc = subprocess.Popen([installer_path], cwd=tmp_dir)
            if on_progress:
                on_progress(
                    "VB-CABLE installer is running. "
                    "Click 'Install Driver' in the installer window..."
                )
            proc.wait()

        if on_success:
            on_success()

    except urllib.error.URLError as exc:
        if on_error:
            on_error(
                f"Download failed — check your internet connection.\n{exc}"
            )
    except zipfile.BadZipFile:
        if on_error:
            on_error("Downloaded file is corrupted. Please try again.")
    except Exception as exc:
        if on_error:
            on_error(f"Installation failed: {exc}")
