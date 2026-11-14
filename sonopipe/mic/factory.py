"""
Factory for creating the appropriate Virtual Microphone provider for current platform.
"""

from __future__ import annotations
import sys
from sonopipe.mic.base import VirtualMicBase
from sonopipe.mic.linux_pulse import LinuxVirtualMic
from sonopipe.mic.windows_cable import WindowsVirtualMic


def create_virtual_mic(sample_rate: int = 48000, channels: int = 1) -> VirtualMicBase:
    if sys.platform.startswith("linux"):
        return LinuxVirtualMic(sample_rate=sample_rate, channels=channels)
    return WindowsVirtualMic(sample_rate=sample_rate, channels=channels)
