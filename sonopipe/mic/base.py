"""
Base interface for Virtual Microphone device providers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class VirtualMicBase(ABC):
    """Abstract interface for system virtual microphone sinks."""

    def __init__(self, sample_rate: int = 48000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_active = False

    @abstractmethod
    def create(self) -> bool:
        """Create and register the virtual microphone in the host OS."""
        pass

    @abstractmethod
    def write_chunk(self, pcm_bytes: bytes) -> None:
        """Write raw PCM s16le bytes into the virtual microphone stream."""
        pass

    @abstractmethod
    def destroy(self) -> None:
        """Unload and remove the virtual microphone device."""
        pass
