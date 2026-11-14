"""
Audio capture backend using the soundcard library.
Supports Linux (PulseAudio/PipeWire) and Windows (WASAPI Loopback).
"""

from __future__ import annotations
import sys
from typing import List, Optional

# Safeguard for soundcard's _infer_program_name when sys.argv is empty or -c
if not sys.argv or sys.argv[0] == "-c":
    sys.argv = ["adbsound"]

import numpy as np
import soundcard as sc
from sonopipe.capture.base import AudioCaptureBase, AudioDeviceInfo


class SoundcardCapture(AudioCaptureBase):
    """Captures system audio loopback using soundcard."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_frames: int = 960,
    ):
        super().__init__(device_id, sample_rate, channels, chunk_frames)
        self._recorder_cm = None
        self._recorder = None
        self._mic = None

    @classmethod
    def get_available_devices(cls) -> List[AudioDeviceInfo]:
        devices: List[AudioDeviceInfo] = []
        try:
            default_spk = sc.default_speaker()
            default_id = str(default_spk.id) if default_spk else None
        except Exception:
            default_id = None

        try:
            mics = sc.all_microphones(include_loopback=True)
            for m in mics:
                if getattr(m, "isloopback", False):
                    if "sonopipe" in str(m.name).lower() or "sonopipe" in str(m.id).lower():
                        continue
                    is_def = (default_id is not None and default_id in str(m.id))
                    devices.append(
                        AudioDeviceInfo(
                            id=str(m.id),
                            name=m.name,
                            is_default=is_def,
                            is_loopback=True,
                        )
                    )
        except Exception as e:
            print(f"[Soundcard] Error listing devices: {e}", file=sys.stderr)

        return devices

    def _resolve_microphone(self):
        mics = sc.all_microphones(include_loopback=True)
        loopback_mics = [m for m in mics if getattr(m, "isloopback", False)]

        if not loopback_mics:
            # Fallback to any mic if no loopback found
            loopback_mics = mics

        if self.device_id:
            for m in loopback_mics:
                if str(m.id) == self.device_id or m.name == self.device_id:
                    return m

        # Try to find default speaker's loopback
        try:
            def_spk = sc.default_speaker()
            if def_spk:
                for m in loopback_mics:
                    if str(def_spk.id) in str(m.id):
                        return m
        except Exception:
            pass

        return loopback_mics[0] if loopback_mics else None

    def start(self) -> None:
        if self._is_running:
            return

        self._mic = self._resolve_microphone()
        if not self._mic:
            raise RuntimeError("No loopback audio device found to capture system sound.")

        # Create recorder context
        self._recorder_cm = self._mic.recorder(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.chunk_frames,
        )
        self._recorder = self._recorder_cm.__enter__()
        self._is_running = True

    def read_chunk(self) -> bytes:
        if not self._is_running or self._recorder is None:
            raise RuntimeError("Audio capture is not active")

        # Returns numpy float32 array in range [-1.0, 1.0] of shape (chunk_frames, channels)
        data = self._recorder.record(numframes=self.chunk_frames)

        # Convert float32 to int16 PCM
        int16_data = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
        return int16_data.tobytes()

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False

        if self._recorder_cm is not None:
            try:
                self._recorder_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._recorder_cm = None
            self._recorder = None
        self._mic = None
