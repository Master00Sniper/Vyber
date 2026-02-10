"""VB-CABLE virtual audio device detection and configuration."""

import logging
import sounddevice as sd

logger = logging.getLogger(__name__)

VB_CABLE_KEYWORDS = ["cable", "vb-audio", "virtual cable"]


class VirtualCableInfo:
    """Holds info about detected virtual cable devices."""

    def __init__(self):
        self.installed = False
        # The virtual cable INPUT device (where we write audio TO)
        # This appears as an output device in the system
        self.input_device_index: int | None = None
        self.input_device_name: str = ""
        # The virtual cable OUTPUT device (what apps see as a microphone)
        # This appears as an input device in the system
        self.output_device_index: int | None = None
        self.output_device_name: str = ""


class VirtualCableManager:
    """Detects and manages VB-CABLE virtual audio devices."""

    def __init__(self):
        self.info = VirtualCableInfo()

    def detect(self) -> VirtualCableInfo:
        """Scan audio devices and detect VB-CABLE.

        VB-CABLE creates two devices:
        - "CABLE Input": A system output device — we write Vyber audio here.
        - "CABLE Output": A system input device — voice chat apps use this as a mic.
        """
        self.info = VirtualCableInfo()
        try:
            devices = sd.query_devices()
        except Exception as e:
            logger.error("Failed to query audio devices: %s", e)
            return self.info

        logger.info("Scanning %d audio devices for VB-CABLE...", len(devices))
        for i, device in enumerate(devices):
            name = device["name"]
            name_lower = name.lower()
            in_ch = device["max_input_channels"]
            out_ch = device["max_output_channels"]

            if not any(kw in name_lower for kw in VB_CABLE_KEYWORDS):
                continue

            logger.info("  VB-CABLE candidate [%d]: '%s' (in=%d, out=%d)",
                        i, name, in_ch, out_ch)

            # "CABLE Input" is a system output device — we write audio TO it.
            # Match by output channels, prefer names containing "input".
            if out_ch > 0 and self.info.input_device_index is None:
                if "input" in name_lower or "output" not in name_lower:
                    self.info.input_device_index = i
                    self.info.input_device_name = name

            # "CABLE Output" is a system input device — apps read FROM it.
            if in_ch > 0 and self.info.output_device_index is None:
                if "output" in name_lower or "input" not in name_lower:
                    self.info.output_device_index = i
                    self.info.output_device_name = name

        self.info.installed = self.info.input_device_index is not None
        logger.info("VB-CABLE detected: %s (input_dev=%s, output_dev=%s)",
                    self.info.installed,
                    self.info.input_device_name or "none",
                    self.info.output_device_name or "none")
        return self.info

    def get_cable_input_index(self) -> int | None:
        """Get the device index to write audio to (the virtual cable input)."""
        return self.info.input_device_index

    def get_cable_output_index(self) -> int | None:
        """Get the device index that apps see as a microphone."""
        return self.info.output_device_index

    @staticmethod
    def get_all_output_devices() -> list[dict]:
        """List all available output (speaker) devices."""
        devices = []
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0:
                    devices.append({"index": i, "name": dev["name"],
                                    "channels": dev["max_output_channels"]})
        except Exception:
            pass
        return devices

    @staticmethod
    def get_all_input_devices() -> list[dict]:
        """List all available input (microphone) devices."""
        devices = []
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    devices.append({"index": i, "name": dev["name"],
                                    "channels": dev["max_input_channels"]})
        except Exception:
            pass
        return devices
