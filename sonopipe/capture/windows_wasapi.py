"""
Windows WASAPI loopback audio capture backend.
Captures system audio using WASAPI loopback via soundcard or PyAudioWPatch.
"""

from __future__ import annotations
import sys
from typing import List, Optional

from sonopipe.capture.base import AudioCaptureBase, AudioDeviceInfo
from sonopipe.capture.soundcard_backend import SoundcardCapture


class WindowsWasapiCapture(AudioCaptureBase):
    """Captures Windows system audio using WASAPI loopback."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_frames: int = 960,
    ):
        super().__init__(device_id, sample_rate, channels, chunk_frames)
        # Use Soundcard's native WASAPI loopback implementation
        self._backend = SoundcardCapture(
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
            chunk_frames=chunk_frames,
        )

    @classmethod
    def get_available_devices(cls) -> List[AudioDeviceInfo]:
        return SoundcardCapture.get_available_devices()

    def start(self) -> None:
        self._backend.start()
        self._is_running = True

    def read_chunk(self) -> bytes:
        return self._backend.read_chunk()

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        self._backend.stop()
