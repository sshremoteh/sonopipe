"""
Local microphone loopback tester: routes microphone audio directly to PC speakers/headphones
for immediate audio self-check without needing web browser test sites.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
import threading
from typing import Optional


class LocalMicTester:
    """Streams microphone PCM directly to physical PC speakers/headphones for testing."""

    def __init__(self, sample_rate: int = 48000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_active = False

        self._proc: Optional[subprocess.Popen] = None
        self._pacat = shutil.which("pacat")
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self.is_active:
                return True

            if not self._pacat:
                return False

            cmd = [
                self._pacat,
                "-p",
                f"--rate={self.sample_rate}",
                f"--channels={self.channels}",
                "--format=s16le",
                "--latency-msec=10",
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    bufsize=1920 * 4,
                )
                self.is_active = True
                return True
            except Exception as e:
                print(f"[LocalMicTester] Error starting playback: {e}", file=sys.stderr)
                return False

    def write_chunk(self, pcm_bytes: bytes) -> None:
        with self._lock:
            if not self.is_active or not self._proc or not self._proc.stdin:
                return
            try:
                self._proc.stdin.write(pcm_bytes)
                self._proc.stdin.flush()
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            if not self.is_active:
                return
            self.is_active = False
            if self._proc is not None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=0.5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
