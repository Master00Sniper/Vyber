# Soundboard

A Python soundboard that plays audio through your speakers **and** your virtual microphone simultaneously — so people in Discord, TeamSpeak, or any voice chat can hear your sounds without any manual audio routing setup.

## Features

- Play sounds through speakers and virtual mic at the same time
- Automatic VB-CABLE detection and configuration (no manual audio routing)
- Mic passthrough — your voice + soundboard audio are mixed together
- Dark-themed modern UI with tabbed categories
- Global hotkeys that work even while in games
- Stop-all button and hotkey to cut audio instantly
- Supports WAV, FLAC, OGG (and MP3 with ffmpeg)

## Requirements

- Python 3.9+
- [VB-CABLE Virtual Audio Device](https://vb-audio.com/Cable/) (free, one-time install)
- Windows 10/11

## Setup

1. Install [VB-CABLE](https://vb-audio.com/Cable/) and reboot
2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the soundboard:
   ```
   python run.py
   ```
4. In your voice chat app (Discord, etc.), set your input device to **CABLE Output (VB-Audio Virtual Cable)**

## Usage

- Click **Add Sound** or drag audio files into the app to add sounds
- Organize sounds into categories using tabs
- Right-click a sound to assign a hotkey, rename, or move it
- Use the output mode toggle to choose: **Speakers**, **Mic**, or **Both**
- Press the stop-all hotkey (default: `Escape`) to cut all audio instantly
