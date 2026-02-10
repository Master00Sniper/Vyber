"""Audio engine — handles playback, multi-device output, and mic mixing."""

import logging
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False


# Standard sample rate for all audio processing
SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK_SIZE = 1024


class SoundClip:
    """A loaded sound ready for playback."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.data: np.ndarray | None = None
        self.sample_rate: int = SAMPLE_RATE
        self._load(filepath)

    def _load(self, filepath: str):
        """Load an audio file into a numpy array, resampled to SAMPLE_RATE stereo."""
        ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

        if ext == "mp3" and HAS_PYDUB:
            self._load_mp3(filepath)
        else:
            self._load_soundfile(filepath)

    def _load_soundfile(self, filepath: str):
        """Load via soundfile (WAV, FLAC, OGG)."""
        data, sr = sf.read(filepath, dtype="float32", always_2d=True)
        self.data = self._ensure_stereo(data)
        if sr != SAMPLE_RATE:
            self.data = self._resample(self.data, sr, SAMPLE_RATE)

    def _load_mp3(self, filepath: str):
        """Load MP3 via pydub, convert to numpy array."""
        audio = AudioSegment.from_mp3(filepath)
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS)
        samples = np.array(audio.get_array_of_samples(), dtype="float32")
        samples = samples / (2 ** 15)  # Normalize int16 to float32
        samples = samples.reshape(-1, CHANNELS)
        self.data = samples

    @staticmethod
    def _ensure_stereo(data: np.ndarray) -> np.ndarray:
        """Convert mono to stereo if needed."""
        if data.ndim == 1:
            return np.column_stack([data, data])
        if data.shape[1] == 1:
            return np.column_stack([data[:, 0], data[:, 0]])
        if data.shape[1] > 2:
            return data[:, :2]
        return data

    @staticmethod
    def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple linear interpolation resampling."""
        if orig_sr == target_sr:
            return data
        ratio = target_sr / orig_sr
        new_length = int(len(data) * ratio)
        indices = np.linspace(0, len(data) - 1, new_length)
        left_idx = np.floor(indices).astype(int)
        right_idx = np.minimum(left_idx + 1, len(data) - 1)
        frac = (indices - left_idx).reshape(-1, 1)
        return (data[left_idx] * (1 - frac) + data[right_idx] * frac).astype("float32")


class PlayingSound:
    """Tracks a currently-playing sound instance."""

    def __init__(self, clip: SoundClip, volume: float = 1.0):
        self.clip = clip
        self.volume = volume
        self.position = 0
        self.finished = False

    def get_samples(self, num_frames: int) -> np.ndarray:
        """Get the next chunk of samples from this sound."""
        if self.finished or self.clip.data is None:
            return np.zeros((num_frames, CHANNELS), dtype="float32")

        remaining = len(self.clip.data) - self.position
        if remaining <= 0:
            self.finished = True
            return np.zeros((num_frames, CHANNELS), dtype="float32")

        count = min(num_frames, remaining)
        samples = self.clip.data[self.position:self.position + count].copy()
        samples *= self.volume
        self.position += count

        if count < num_frames:
            self.finished = True
            pad = np.zeros((num_frames - count, CHANNELS), dtype="float32")
            samples = np.vstack([samples, pad])

        return samples


class AudioEngine:
    """Manages audio playback to speakers and virtual cable with mic mixing."""

    def __init__(self):
        self.playing: list[PlayingSound] = []
        self.lock = threading.Lock()
        self.master_volume: float = 0.8

        # Output mode: "speakers", "mic", "both"
        self.output_mode: str = "both"

        # Device indices
        self.speaker_device: int | None = None
        self.virtual_cable_device: int | None = None
        self.mic_device: int | None = None

        # Audio streams
        self._speaker_stream: sd.OutputStream | None = None
        self._cable_stream: sd.OutputStream | None = None
        self._mic_stream: sd.InputStream | None = None

        # Mic passthrough
        self.mic_passthrough: bool = True
        self._mic_buffer = np.zeros((BLOCK_SIZE, CHANNELS), dtype="float32")
        self._mic_lock = threading.Lock()

        # Sound cache: filepath -> SoundClip
        self._cache: dict[str, SoundClip] = {}

    def start(self):
        """Start audio output streams."""
        self._stop_streams()

        try:
            if self.output_mode in ("speakers", "both"):
                self._speaker_stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    blocksize=BLOCK_SIZE,
                    device=self.speaker_device,
                    callback=self._speaker_callback,
                    dtype="float32"
                )
                self._speaker_stream.start()
        except Exception as e:
            logger.error("Failed to open speaker stream: %s", e)

        try:
            if self.output_mode in ("mic", "both") and self.virtual_cable_device is not None:
                self._cable_stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    blocksize=BLOCK_SIZE,
                    device=self.virtual_cable_device,
                    callback=self._cable_callback,
                    dtype="float32"
                )
                self._cable_stream.start()
        except Exception as e:
            logger.error("Failed to open virtual cable stream: %s", e)

        try:
            if self.mic_passthrough and self.virtual_cable_device is not None:
                mic_dev = self.mic_device  # None = system default mic
                mic_info = sd.query_devices(mic_dev, kind="input")
                mic_channels = min(mic_info["max_input_channels"], CHANNELS)
                self._mic_stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=mic_channels,
                    blocksize=BLOCK_SIZE,
                    device=mic_dev,
                    callback=self._mic_callback,
                    dtype="float32"
                )
                self._mic_stream.start()
        except Exception as e:
            logger.error("Failed to open mic stream: %s", e)

    def stop(self):
        """Stop all streams."""
        self._stop_streams()
        with self.lock:
            self.playing.clear()

    def _stop_streams(self):
        """Close all audio streams."""
        for stream in (self._speaker_stream, self._cable_stream, self._mic_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._speaker_stream = None
        self._cable_stream = None
        self._mic_stream = None

    def load_sound(self, filepath: str) -> SoundClip | None:
        """Load a sound file, using cache if available."""
        if filepath in self._cache:
            return self._cache[filepath]
        try:
            clip = SoundClip(filepath)
            self._cache[filepath] = clip
            return clip
        except Exception as e:
            logger.error("Failed to load sound '%s': %s", filepath, e)
            return None

    def play_sound(self, filepath: str, volume: float = 1.0):
        """Play a sound file. Starts output streams if not running."""
        clip = self.load_sound(filepath)
        if clip is None:
            return

        playing = PlayingSound(clip, volume)
        with self.lock:
            self.playing.append(playing)

        # Auto-start streams if not active
        if self._needs_speaker() and (self._speaker_stream is None or not self._speaker_stream.active):
            self.start()
        if self._needs_cable() and (self._cable_stream is None or not self._cable_stream.active):
            self.start()

    def stop_all(self):
        """Stop all currently playing sounds."""
        with self.lock:
            self.playing.clear()

    def set_output_mode(self, mode: str):
        """Change output mode and restart streams."""
        if mode not in ("speakers", "mic", "both"):
            return
        self.output_mode = mode
        self.start()

    def set_master_volume(self, volume: float):
        """Set master volume (0.0 to 1.0)."""
        self.master_volume = max(0.0, min(1.0, volume))

    def get_playing_count(self) -> int:
        """Get number of currently playing sounds."""
        with self.lock:
            return len([p for p in self.playing if not p.finished])

    def get_playing_filepaths(self) -> set[str]:
        """Get the set of filepaths currently playing."""
        with self.lock:
            return {p.clip.filepath for p in self.playing if not p.finished}

    def _mix_playing_sounds(self, num_frames: int) -> np.ndarray:
        """Mix all currently playing sounds into a single buffer."""
        mixed = np.zeros((num_frames, CHANNELS), dtype="float32")
        with self.lock:
            for playing in self.playing:
                if not playing.finished:
                    mixed += playing.get_samples(num_frames)
            # Clean up finished sounds
            self.playing = [p for p in self.playing if not p.finished]

        # Apply master volume and clamp
        mixed *= self.master_volume
        np.clip(mixed, -1.0, 1.0, out=mixed)
        return mixed

    def _speaker_callback(self, outdata: np.ndarray, frames: int,
                          time_info, status):
        """Callback for speaker output stream."""
        outdata[:] = self._mix_playing_sounds(frames)

    def _cable_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status):
        """Callback for virtual cable output — mixes Vyber audio + mic."""
        mixed = self._mix_playing_sounds(frames)

        # Mix in microphone passthrough
        if self.mic_passthrough:
            with self._mic_lock:
                mic_data = self._mic_buffer[:frames].copy()
            mixed += mic_data

        np.clip(mixed, -1.0, 1.0, out=mixed)
        outdata[:] = mixed

    def _mic_callback(self, indata: np.ndarray, frames: int,
                      time_info, status):
        """Callback for microphone input — stores data for passthrough mixing."""
        with self._mic_lock:
            if indata.shape[1] < CHANNELS:
                # Mono mic -> stereo
                self._mic_buffer[:frames] = np.column_stack(
                    [indata[:frames, 0]] * CHANNELS
                )
            else:
                self._mic_buffer[:frames] = indata[:frames, :CHANNELS]

    def _needs_speaker(self) -> bool:
        return self.output_mode in ("speakers", "both")

    def _needs_cable(self) -> bool:
        return self.output_mode in ("mic", "both")

    def invalidate_cache(self, filepath: str | None = None):
        """Clear sound cache. If filepath given, remove just that entry."""
        if filepath:
            self._cache.pop(filepath, None)
        else:
            self._cache.clear()
