# Vyber - Project Guide for Claude

## What is Vyber?
A Windows soundboard app that plays audio through speakers and virtual microphone simultaneously, built for Discord/voice chat. Uses VB-CABLE for audio routing. Written in Python with CustomTkinter UI.

## Project Structure
- `run.py` — Entry point, creates `VyberApp` and calls `app.run()`
- `vyber/app.py` — Main controller, wires all components, contains most UI dialogs (volume, settings, help, discord guide, VB-CABLE install)
- `vyber/audio_engine.py` — Plays sounds via sounddevice/numpy. Per-sound volume uses exponential curve (`volume ** 2.5`). Final mix is clipped to [-1.0, 1.0]
- `vyber/sound_manager.py` — Manages sound library (categories, sounds, volumes, hotkeys). Persists to config. **Volume clamp is here** (max 2.0)
- `vyber/config.py` — Config with `DEFAULTS` dict. **This is the true source of defaults**, not the `default=` param on `config.get()` calls in app.py
- `vyber/vb_cable_installer.py` — Downloads and installs VB-CABLE driver. Uses `ShellExecuteExW` with `WaitForSingleObject` to wait for installer to finish
- `vyber/virtual_cable.py` — Detects VB-CABLE audio devices
- `vyber/hotkey_manager.py` — Global hotkeys via `keyboard` library
- `vyber/telemetry.py` — Anonymous usage stats (app_start, sound_played, hotkey_used, heartbeat). Uses SHA-256 of MAC address as install ID
- `vyber/ui/` — UI components:
  - `main_window.py` — Main window layout, tab management
  - `sound_grid.py` — Sound button grid with drag-and-drop reordering, context menu (right-click)
  - `widgets.py` — `VolumeSlider` (master volume), `OutputModeSelector`, `StatusBar`
  - `settings_dialog.py` — Settings window (has its own VB-CABLE install button)
- `vyber/tray_manager.py` — System tray icon via pystray
- `updater.py` — Auto-updater, checks GitHub releases via proxy every hour
- `cloudflare-worker/vyber-proxy.js` — Cloudflare Worker proxy for telemetry, GitHub API, downloads, stats
- `web/` — Website (index.html, policies.html, stats.html, style.css, script.js)

## Key Gotchas
- **Config defaults live in `vyber/config.py` DEFAULTS dict**, not in `config.get(default=...)` calls. When changing a default, update BOTH places, but config.py is what matters for fresh installs.
- **Per-sound volume range is 0.0–2.0** (0–200%). The clamp is in `sound_manager.py:set_sound_volume()`. The slider UI is in `app.py:_on_volume_sound()`.
- **VB-CABLE installer is async** — runs in a background thread. Uses `ShellExecuteExW` + `WaitForSingleObject` to block the thread until the installer window is closed. Don't use `ShellExecuteW` (returns immediately, no process handle).
- **Sound overlap setting** defaults to `"stop"` (clicking a playing sound stops it). Alternative is `"overlap"` (layers another instance).
- **Context menu callbacks in sound_grid.py** — watch for lambda capture issues. The `on_move` callback takes 3 args: `(source_category, sound_name, target_category)`.
- **File dialogs** default to `~/Music` (falls back to `~/Documents` then `~`). See `_default_sound_dir()` in app.py.
- **Popup dialogs must use the themed pattern** — never use `simpledialog.askstring` or other default tkinter dialogs (they appear white/unstyled with the wrong icon). Instead:
  1. Create with `tk.Toplevel(self.root)` + `dialog.withdraw()` (start hidden)
  2. `dialog.configure(bg=_DARK_BG)`, set title/geometry/`resizable(False, False)`/`transient(self.root)`/`grab_set()`
  3. Build content with CTk widgets inside `ctk.CTkFrame(dialog, fg_color=_DARK_BG)`
  4. Call `self._setup_dialog(dialog)` last — sets icon, force-renders, centers, then shows without flash
- **Telemetry events**: Only `app_start` and `heartbeat` are sent to the server. `sound_played` and `hotkey_used` were removed to conserve Cloudflare KV free tier usage.

## Build & Run
- `python run.py` to run from source
- `build_nuitka.ps1` for Windows executable build
- `.github/workflows/build.yml` for CI
- Dependencies in `requirements.txt`

## Website
- Lives in `web/` directory
- `style.css` is shared between index.html and policies.html
- Ko-fi widget is embedded in hero section (ID: `U7U51THXWE`)
- Privacy policy in `policies.html` documents actual telemetry behavior
- Stats dashboard at `stats.html` reads from proxy `/stats` endpoint

## License & Author
- GPLv3
- Greg Morton (@Master00Sniper)
- Ko-fi: https://ko-fi.com/master00sniper
