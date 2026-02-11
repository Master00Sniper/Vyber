# Vyber

A soundboard for Windows that plays audio through your speakers **and** your virtual microphone simultaneously — so people in Discord, TeamSpeak, or any voice chat hear your sounds without any manual audio routing.

## Features

**Audio & Playback**
- Play sounds through speakers, virtual mic, or both at the same time
- Automatic VB-CABLE detection and one-click in-app installation
- Mic passthrough — your voice and soundboard audio are mixed together
- Per-sound volume control (0–200%) for boosting quiet sounds
- Master volume slider
- Supports WAV, FLAC, OGG, and MP3
- Configurable replay behavior — click a playing sound to stop it, or layer multiple instances

**Sound Management**
- Organize sounds into tabbed categories
- Drag-and-drop to reorder sounds within a category
- Add individual files or entire folders at once
- Right-click context menu: set hotkey, rename, adjust volume, move to another category, remove, or delete from disk
- Rename a sound's display name or rename the underlying file

**Hotkeys**
- Assign a global hotkey to any sound — works even in fullscreen games
- Customizable stop-all hotkey (default: `Escape`)

**Interface**
- Dark-themed modern UI
- Gold pulse animation and countdown timer on playing sounds
- Responsive grid layout that adapts to window size
- System tray support — minimize to tray instead of closing
- Dark title bar on Windows 10/11

**Discord Integration**
- Built-in Discord setup guide with step-by-step instructions
- Covers input device, voice processing, gain control, and attenuation settings

**Other**
- Built-in bug reporter (submits to GitHub Issues with optional system info and logs, usernames auto-redacted)
- Automatic background update checker
- All settings persist between sessions (window size, volumes, hotkeys, device selections, sound library)

## Requirements

- Windows 10/11
- [VB-CABLE Virtual Audio Device](https://vb-audio.com/Cable/) (free — Vyber can install this for you on first launch)

### Running from source

- Python 3.9+
- Install dependencies: `pip install -r requirements.txt`

## Getting Started

1. **Download** the latest `.exe` from [Releases](https://github.com/Master00Sniper/Vyber/releases) — or run from source with `python run.py`
2. **Install VB-CABLE** when prompted (or install it manually from [vb-audio.com](https://vb-audio.com/Cable/) and reboot)
3. **Set your voice chat input device** to `CABLE Output (VB-Audio Virtual Cable)` (see the in-app Discord guide for detailed steps)
4. **Add sounds** — click the `+ Add Sound` button or right-click to add a folder
5. **Set output mode to "Both"** and enable mic passthrough in Settings so friends hear your sounds and your voice

## Usage

- **Click** a sound to play it. Click it again to stop it.
- **Right-click** a sound for options: hotkey, rename, volume, move, delete
- **Drag** sounds to reorder them within a category
- **Escape** (default) stops all playing sounds instantly
- **Adjust volume** per sound from 0–200% via right-click > Adjust Volume
- **Minimize** to the system tray by closing the window — right-click the tray icon to show or quit

## Discord Setup

Vyber includes a built-in Discord setup guide (Menu > Discord Setup), but the key steps are:

1. Set Discord input device to **CABLE Output (VB-Audio Virtual Cable)**
2. Disable Krisp Noise Suppression and Echo Cancellation
3. Disable Automatic Gain Control, Advanced Voice Activity, and related settings
4. Set Global Attenuation to **0%**

## Building

To build a standalone `.exe` with Nuitka:

```powershell
.\build_nuitka.ps1
```

## License

[GPL v3](LICENSE)

## Support

- [Report a Bug](https://github.com/Master00Sniper/Vyber/issues)
- [Support on Ko-fi](https://ko-fi.com/master00sniper)
- Follow on [X/Twitter](https://x.com/master00sniper)
