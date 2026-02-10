"""VB-CABLE virtual audio device detection and configuration."""

import sounddevice as sd


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
        except Exception:
            return self.info

        for i, device in enumerate(devices):
            name_lower = device["name"].lower()
            if not any(kw in name_lower for kw in VB_CABLE_KEYWORDS):
                continue

            # "CABLE Input" is an output device (we send audio TO it)
            if device["max_output_channels"] > 0 and "input" in name_lower:
                self.info.input_device_index = i
                self.info.input_device_name = device["name"]

            # "CABLE Output" is an input device (apps read FROM it as a mic)
            if device["max_input_channels"] > 0 and "output" in name_lower:
                self.info.output_device_index = i
                self.info.output_device_name = device["name"]

        self.info.installed = (
            self.info.input_device_index is not None
            and self.info.output_device_index is not None
        )
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
