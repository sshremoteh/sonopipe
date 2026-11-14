"""
Base interface and dataclasses for audio capture backends.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AudioDeviceInfo:
    id: str
    name: str
    is_default: bool = False
    is_loopback: bool = True

    def __repr__(self) -> str:
        default_tag = " (Default)" if self.is_default else ""
        return f"{self.name}{default_tag}"


class AudioCaptureBase(ABC):
    """Abstract base class for system audio capture backends."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_frames: int = 960,
    ):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_frames = chunk_frames
        self.bytes_per_sample = 2  # 16-bit PCM
        self.frame_size = self.channels * self.bytes_per_sample
        self.chunk_bytes = self.chunk_frames * self.frame_size
        self._is_running = False

    @abstractmethod
    def start(self) -> None:
        """Start capturing audio stream."""
        pass

    @abstractmethod
    def read_chunk(self) -> bytes:
        """Read a single chunk of raw PCM (s16le) audio data.

        Returns exactly or up to chunk_bytes bytes.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing audio and release resources."""
        pass

    @classmethod
    @abstractmethod
    def get_available_devices(cls) -> List[AudioDeviceInfo]:
        """List available output/loopback audio devices."""
        pass

    @property
    def is_running(self) -> bool:
        return self._is_running
