"""
Factory function to instantiate the proper audio capture backend.
"""

from __future__ import annotations
import sys
from typing import List, Optional, Type

from sonopipe.capture.base import AudioCaptureBase, AudioDeviceInfo
from sonopipe.capture.soundcard_backend import SoundcardCapture
from sonopipe.capture.linux_pulse import LinuxPulseCapture
from sonopipe.capture.windows_wasapi import WindowsWasapiCapture


def get_default_backend_name() -> str:
    if sys.platform == "win32":
        return "wasapi"
    elif sys.platform.startswith("linux"):
        return "pulse"
    return "soundcard"


def get_backend_class(backend_name: Optional[str] = None) -> Type[AudioCaptureBase]:
    name = (backend_name or "auto").lower()
    if name == "auto":
        name = get_default_backend_name()

    if name in ("pulse", "pipewire", "linux"):
        return LinuxPulseCapture
    elif name in ("wasapi", "windows"):
        return WindowsWasapiCapture
    elif name == "soundcard":
        return SoundcardCapture
    else:
        # Fallback to platform default
        return get_backend_class("auto")


def create_audio_capture(
    backend: Optional[str] = None,
    device_id: Optional[str] = None,
    sample_rate: int = 48000,
    channels: int = 2,
    chunk_frames: int = 960,
) -> AudioCaptureBase:
    """Create an AudioCapture instance with the given configuration."""
    backend_cls = get_backend_class(backend)
    return backend_cls(
        device_id=device_id,
        sample_rate=sample_rate,
        channels=channels,
        chunk_frames=chunk_frames,
    )


def list_audio_devices(backend: Optional[str] = None) -> List[AudioDeviceInfo]:
    """List available audio capture devices for the specified or default backend."""
    backend_cls = get_backend_class(backend)
    return backend_cls.get_available_devices()
