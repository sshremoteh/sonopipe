"""
Native Linux audio capture backend using PipeWire / PulseAudio via parec or soundcard.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import List, Optional

from sonopipe.capture.base import AudioCaptureBase, AudioDeviceInfo
from sonopipe.capture.soundcard_backend import SoundcardCapture


class LinuxPulseCapture(AudioCaptureBase):
    """Captures Linux system audio monitor stream using parec or soundcard."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_frames: int = 960,
    ):
        super().__init__(device_id, sample_rate, channels, chunk_frames)
        self._parec_path = shutil.which("parec")
        self._proc: Optional[subprocess.Popen] = None
        self._fallback_sc: Optional[SoundcardCapture] = None

    @classmethod
    def get_available_devices(cls) -> List[AudioDeviceInfo]:
        devices: List[AudioDeviceInfo] = []
        pactl = shutil.which("pactl")

        default_sink = ""
        if pactl:
            try:
                info_out = subprocess.check_output([pactl, "info"], text=True, timeout=2)
                for line in info_out.splitlines():
                    if line.startswith("Default Sink:"):
                        default_sink = line.split(":", 1)[1].strip()
            except Exception:
                pass

            try:
                sources_out = subprocess.check_output([pactl, "list", "sources", "short"], text=True, timeout=2)
                for line in sources_out.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        src_name = parts[1]
                        if ".monitor" in src_name:
                            is_def = (default_sink and src_name.startswith(default_sink))
                            display_name = src_name.replace(".monitor", " (Monitor)")
                            devices.append(
                                AudioDeviceInfo(
                                    id=src_name,
                                    name=display_name,
                                    is_default=is_def,
                                    is_loopback=True,
                                )
                            )
            except Exception:
                pass

        if not devices:
            # Fallback to soundcard device enumeration
            return SoundcardCapture.get_available_devices()

        return devices

    def _resolve_monitor_device(self) -> Optional[str]:
        if self.device_id:
            return self.device_id

        devices = self.get_available_devices()
        for d in devices:
            if d.is_default:
                return d.id
        if devices:
            return devices[0].id
        return None

    def start(self) -> None:
        if self._is_running:
            return

        if not self._parec_path:
            # Fallback to soundcard
            self._fallback_sc = SoundcardCapture(
                device_id=self.device_id,
                sample_rate=self.sample_rate,
                channels=self.channels,
                chunk_frames=self.chunk_frames,
            )
            self._fallback_sc.start()
            self._is_running = True
            return

        target_source = self._resolve_monitor_device()
        cmd = [
            self._parec_path,
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            "--format=s16le",
            "--latency-msec=20",
        ]
        if target_source:
            cmd.extend(["-d", target_source])

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self.chunk_bytes * 4,
            )
            self._is_running = True
        except Exception as e:
            # Fallback to soundcard if parec fails
            print(f"[LinuxPulseCapture] parec failed ({e}), falling back to soundcard", file=sys.stderr)
            self._fallback_sc = SoundcardCapture(
                device_id=self.device_id,
                sample_rate=self.sample_rate,
                channels=self.channels,
                chunk_frames=self.chunk_frames,
            )
            self._fallback_sc.start()
            self._is_running = True

    def read_chunk(self) -> bytes:
        if not self._is_running:
            raise RuntimeError("Capture is not active")

        if self._fallback_sc is not None:
            return self._fallback_sc.read_chunk()

        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("Capture process is not running")

        data = self._proc.stdout.read(self.chunk_bytes)
        if not data:
            raise RuntimeError("Capture process closed stream")
        return data

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False

        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        if self._fallback_sc is not None:
            self._fallback_sc.stop()
            self._fallback_sc = None
