"""
Native Linux virtual microphone provider for PipeWire and PulseAudio.
Creates a virtual null-sink and streams microphone audio via pacat.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import Optional

from sonopipe.mic.base import VirtualMicBase


class LinuxVirtualMic(VirtualMicBase):
    """Virtual microphone for Linux PipeWire / PulseAudio."""

    def __init__(self, sample_rate: int = 48000, channels: int = 1):
        super().__init__(sample_rate, channels)
        self.sink_name = "sonopipe_mic_sink"
        self._module_id: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._pactl = shutil.which("pactl")
        self._pacat = shutil.which("pacat") or shutil.which("paplay")

    def create(self) -> bool:
        if self.is_active:
            return True

        if not self._pactl or not self._pacat:
            print("[VirtualMic] 'pactl' or 'pacat' not found in PATH", file=sys.stderr)
            return False

        # 1. Unload any lingering sonopipe_mic_sink module
        self._cleanup_old_module()

        # 2. Load module-null-sink
        cmd = [
            self._pactl,
            "load-module",
            "module-null-sink",
            f"sink_name={self.sink_name}",
            "sink_properties=device.description=\"Sonopipe_Virtual_Microphone\"",
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                self._module_id = res.stdout.strip()
            else:
                print(f"[VirtualMic] Failed to load null-sink module: {res.stderr}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[VirtualMic] Error running pactl: {e}", file=sys.stderr)
            return False

        # 3. Start pacat streaming process writing into the sink
        pacat_cmd = [
            self._pacat,
            "-p",
            "-d",
            self.sink_name,
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            "--format=s16le",
            "--latency-msec=15",
        ]
        try:
            self._proc = subprocess.Popen(
                pacat_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                bufsize=1920 * 4,
            )
            self.is_active = True
            print(f"[VirtualMic] Created virtual microphone '{self.sink_name}.monitor' (Module ID: {self._module_id})")
            return True
        except Exception as e:
            print(f"[VirtualMic] Failed to start pacat: {e}", file=sys.stderr)
            self.destroy()
            return False

    def write_chunk(self, pcm_bytes: bytes) -> None:
        if not self.is_active or self._proc is None or self._proc.stdin is None:
            return

        try:
            self._proc.stdin.write(pcm_bytes)
            self._proc.stdin.flush()
        except Exception:
            pass

    def destroy(self) -> None:
        if not self.is_active:
            return

        self.is_active = False

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

        if self._module_id and self._pactl:
            try:
                subprocess.run([self._pactl, "unload-module", self._module_id], timeout=3)
            except Exception:
                pass
            self._module_id = None

    def _cleanup_old_module(self):
        if not self._pactl:
            return
        try:
            out = subprocess.check_output([self._pactl, "list", "modules", "short"], text=True, timeout=3)
            for line in out.splitlines():
                if self.sink_name in line:
                    mod = line.split()[0]
                    subprocess.run([self._pactl, "unload-module", mod], timeout=2)
        except Exception:
            pass
