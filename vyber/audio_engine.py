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


# Default sample rate — may be overridden at runtime to match VB-CABLE
SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK_SIZE = 1024


class SoundClip:
    """A loaded sound ready for playback."""

    def __init__(self, filepath: str, target_rate: int = SAMPLE_RATE):
        self.filepath = filepath
        self.data: np.ndarray | None = None
        self.sample_rate: int = target_rate
        self._load(filepath, target_rate)

    def _load(self, filepath: str, target_rate: int):
        """Load an audio file into a numpy array, resampled to target_rate stereo."""
        ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

        if ext == "mp3" and HAS_PYDUB:
            self._load_mp3(filepath, target_rate)
        else:
            self._load_soundfile(filepath, target_rate)

    def _load_soundfile(self, filepath: str, target_rate: int):
        """Load via soundfile (WAV, FLAC, OGG)."""
        data, sr = sf.read(filepath, dtype="float32", always_2d=True)
        self.data = self._ensure_stereo(data)
        if sr != target_rate:
            self.data = self._resample(self.data, sr, target_rate)

    def _load_mp3(self, filepath: str, target_rate: int):
        """Load MP3 via pydub, convert to numpy array."""
        audio = AudioSegment.from_mp3(filepath)
        audio = audio.set_frame_rate(target_rate).set_channels(CHANNELS)
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

        # Effective sample rate — adapts to VB-CABLE's native rate
        self._effective_rate: int = SAMPLE_RATE

        # Mic passthrough — lock-free SPSC ring buffer
        self.mic_passthrough: bool = True
        self._mic_ring_size = BLOCK_SIZE * 8
        self._mic_ring = np.zeros((self._mic_ring_size, CHANNELS), dtype="float32")
        self._mic_write_pos = 0  # only written by mic callback
        self._mic_read_pos = 0   # only written by cable callback

        # Cached mix for "both" mode — speaker callback writes, cable reads
        self._cached_mix = np.zeros((BLOCK_SIZE, CHANNELS), dtype="float32")
        self._cached_mix_lock = threading.Lock()

        # Sound cache: filepath -> SoundClip
        self._cache: dict[str, SoundClip] = {}

    def start(self):
        """Start audio output streams."""
        self._stop_streams()

        # Adapt sample rate to VB-CABLE's native rate if available
        old_rate = self._effective_rate
        self._detect_effective_rate()
        if self._effective_rate != old_rate:
            logger.info("Sample rate changed from %d to %d Hz — clearing sound cache",
                        old_rate, self._effective_rate)
            self._cache.clear()

        rate = self._effective_rate

        try:
            if self.output_mode in ("speakers", "both"):
                self._log_device_samplerate(self.speaker_device, "Speaker")
                self._speaker_stream = sd.OutputStream(
                    samplerate=rate,
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
                self._log_device_samplerate(self.virtual_cable_device, "Virtual cable")
                self._cable_stream = sd.OutputStream(
                    samplerate=rate,
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
                self._log_device_samplerate(mic_dev, "Mic input")
                mic_channels = min(mic_info["max_input_channels"], CHANNELS)
                self._mic_stream = sd.InputStream(
                    samplerate=rate,
                    channels=mic_channels,
                    blocksize=BLOCK_SIZE,
                    device=mic_dev,
                    callback=self._mic_callback,
                    dtype="float32"
                )
                self._mic_stream.start()
        except Exception as e:
            logger.error("Failed to open mic stream: %s", e)

    def _detect_effective_rate(self):
        """Detect the VB-CABLE device's native sample rate and adapt to it."""
        if self.virtual_cable_device is None:
            self._effective_rate = SAMPLE_RATE
            return
        try:
            info = sd.query_devices(self.virtual_cable_device)
            native_sr = int(info.get("default_samplerate", 0))
            if native_sr > 0:
                if native_sr != SAMPLE_RATE:
                    logger.info(
                        "VB-CABLE native rate is %d Hz — adapting all streams to match",
                        native_sr
                    )
                self._effective_rate = native_sr
            else:
                self._effective_rate = SAMPLE_RATE
        except Exception:
            self._effective_rate = SAMPLE_RATE

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
            clip = SoundClip(filepath, target_rate=self._effective_rate)
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

    def stop_sound(self, filepath: str):
        """Stop all instances of a specific sound by filepath."""
        with self.lock:
            self.playing = [p for p in self.playing
                            if p.finished or p.clip.filepath != filepath]

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
        mixed = self._mix_playing_sounds(frames)
        outdata[:] = mixed
        # Cache for cable callback in "both" mode
        if self.output_mode == "both":
            with self._cached_mix_lock:
                self._cached_mix = mixed.copy()

    def _cable_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status):
        """Callback for virtual cable output — mixes Vyber audio + mic."""
        if self.output_mode == "both":
            # Reuse the mix from speaker callback to avoid double-advancing
            with self._cached_mix_lock:
                mixed = self._cached_mix[:frames].copy()
        else:
            mixed = self._mix_playing_sounds(frames)

        # Mix in microphone passthrough from ring buffer
        if self.mic_passthrough:
            rp = self._mic_read_pos
            wp = self._mic_write_pos
            ring = self._mic_ring_size
            available = (wp - rp) % ring

            # If writer lapped reader, skip ahead to stay close behind writer
            if available > ring // 2:
                rp = (wp - frames) % ring
                available = frames

            n = min(frames, available)
            mic_data = np.zeros((frames, CHANNELS), dtype="float32")
            if n > 0:
                end = rp + n
                if end <= ring:
                    mic_data[:n] = self._mic_ring[rp:end]
                else:
                    first = ring - rp
                    mic_data[:first] = self._mic_ring[rp:]
                    mic_data[first:n] = self._mic_ring[:n - first]
                self._mic_read_pos = (rp + n) % ring

            mixed += mic_data

        np.clip(mixed, -1.0, 1.0, out=mixed)
        outdata[:] = mixed

    def _mic_callback(self, indata: np.ndarray, frames: int,
                      time_info, status):
        """Callback for microphone input — writes to ring buffer for passthrough."""
        if indata.shape[1] < CHANNELS:
            processed = np.column_stack([indata[:frames, 0]] * CHANNELS)
        else:
            processed = indata[:frames, :CHANNELS]

        n = processed.shape[0]
        wp = self._mic_write_pos
        ring = self._mic_ring_size
        end = wp + n
        if end <= ring:
            self._mic_ring[wp:end] = processed
        else:
            first = ring - wp
            self._mic_ring[wp:] = processed[:first]
            self._mic_ring[:n - first] = processed[first:]
        self._mic_write_pos = (wp + n) % ring

    def _log_device_samplerate(self, device, label: str):
        """Log the device's default sample rate."""
        try:
            info = sd.query_devices(device)
            native_sr = info.get("default_samplerate", 0)
            logger.info("%s device '%s' native sample rate: %d Hz (using: %d Hz)",
                        label, info.get("name", "?"), native_sr, self._effective_rate)
        except Exception:
            pass

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
