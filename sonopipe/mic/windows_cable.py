"""
Windows virtual microphone bridge targeting virtual audio cables (e.g. VB-Cable).
"""

from __future__ import annotations
import sys
from typing import Optional

import numpy as np
from sonopipe.mic.base import VirtualMicBase


class WindowsVirtualMic(VirtualMicBase):
    """Outputs received microphone PCM to a virtual cable playback device on Windows."""

    def __init__(self, sample_rate: int = 48000, channels: int = 1):
        super().__init__(sample_rate, channels)
        self._player = None
        self._player_cm = None

    def create(self) -> bool:
        try:
            import soundcard as sc

            speakers = sc.all_speakers()
            cable_spk = None
            for s in speakers:
                if "cable" in s.name.lower() or "virtual" in s.name.lower():
                    cable_spk = s
                    break

            if not cable_spk:
                cable_spk = sc.default_speaker()

            if cable_spk:
                self._player_cm = cable_spk.player(samplerate=self.sample_rate, channels=self.channels)
                self._player = self._player_cm.__enter__()
                self.is_active = True
                return True
        except Exception as e:
            print(f"[WindowsVirtualMic] Error initializing virtual cable output: {e}", file=sys.stderr)

        return False

    def write_chunk(self, pcm_bytes: bytes) -> None:
        if not self.is_active or not self._player:
            return

        try:
            int16_samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            float32_data = int16_samples.astype(np.float32) / 32768.0
            if self.channels == 1:
                float32_data = float32_data.reshape(-1, 1)
            self._player.play(float32_data)
        except Exception:
            pass

    def destroy(self) -> None:
        self.is_active = False
        if self._player_cm is not None:
            try:
                self._player_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._player_cm = None
            self._player = None
