"""
Microphone stream receiver: connects to Android phone, receives microphone PCM stream,
and feeds it into the host system's Virtual Microphone device.
"""

from __future__ import annotations
import socket
import sys
import threading
import time
from typing import Callable, Optional

import numpy as np

from sonopipe.mic.base import VirtualMicBase
from sonopipe.mic.factory import create_virtual_mic
from sonopipe.stream.protocol import HEADER_SIZE

DEFAULT_MIC_PORT = 12851


class MicReceiver:
    """Connects to Android microphone stream and routes it into PC virtual microphone."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_MIC_PORT,
        gain: float = 1.0,
        on_stats_update: Optional[Callable[[dict], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self.gain = max(0.0, min(2.0, gain))
        self.noise_gate_threshold = 0.0
        self.loopback_enabled = False
        self._loopback_cb: Optional[Callable[[bytes], None]] = None
        self.on_stats_update = on_stats_update
        self.on_error = on_error

        self._sock: Optional[socket.socket] = None
        self._virtual_mic: Optional[VirtualMicBase] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.is_running = False
        self.total_bytes_received = 0
        self.sample_rate = 48000
        self.channels = 1

    def set_gain(self, gain: float) -> None:
        self.gain = max(0.0, min(2.0, gain))

    def set_noise_gate(self, threshold: float) -> None:
        """Set noise gate threshold (0.0 to 0.1, 0.0 = disabled)."""
        self.noise_gate_threshold = max(0.0, min(0.1, threshold))

    def set_loopback(self, enabled: bool, callback: Optional[Callable[[bytes], None]] = None) -> None:
        """Enable or disable local audio loopback monitor."""
        self.loopback_enabled = enabled
        if callback is not None:
            self._loopback_cb = callback

    def start(self) -> None:
        if self.is_running:
            return

        self._stop_event.clear()
        self.is_running = True
        self.total_bytes_received = 0

        self._thread = threading.Thread(target=self._run, daemon=True, name="SonopipeMicReceiver")
        self._thread.start()

    def stop(self) -> None:
        if not self.is_running:
            return

        self._stop_event.set()
        self.is_running = False

        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        if self._virtual_mic is not None:
            try:
                self._virtual_mic.destroy()
            except Exception:
                pass
            self._virtual_mic = None

        if self._thread and self._thread is not threading.current_thread() and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            # 1. Connect to Android phone TCP socket
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(6.0)

            try:
                self._sock.connect((self.host, self.port))
            except ConnectionRefusedError:
                raise ConnectionError(
                    f"Microphone connection refused at {self.host}:{self.port}. "
                    f"Ensure Sonopipe is running on your phone in Mic or Duplex mode."
                )

            # 2. Read 16-byte protocol header
            header = b""
            while len(header) < HEADER_SIZE:
                chunk = self._sock.recv(HEADER_SIZE - len(header))
                if not chunk:
                    raise ConnectionError("Connection closed while reading microphone header.")
                header += chunk

            # Unpack header
            import struct
            magic = header[:6]
            if magic not in (b"ADBMIC", b"ADBSND"):
                raise ValueError(f"Invalid microphone magic header: {magic}")

            _, _, self.sample_rate, self.channels, _ = struct.unpack("<6sHIHH", header)

            # 3. Create virtual microphone device in host OS
            self._virtual_mic = create_virtual_mic(sample_rate=self.sample_rate, channels=self.channels)
            if not self._virtual_mic.create():
                raise RuntimeError("Failed to create Virtual Microphone device in host OS.")

            # 4. Stream loop
            chunk_size = 1920
            window_bytes = 0
            window_start = time.time()

            while not self._stop_event.is_set():
                chunk = self._sock.recv(chunk_size)
                if not chunk:
                    break

                # Apply microphone software gain
                samples = np.frombuffer(chunk, dtype=np.int16)
                if abs(self.gain - 1.0) > 0.02:
                    scaled = np.clip(samples.astype(np.float32) * self.gain, -32768, 32767).astype(np.int16)
                    out_bytes = scaled.tobytes()
                    level_samples = scaled
                else:
                    out_bytes = chunk
                    level_samples = samples

                # Calculate RMS / peak for live meter
                float_s = level_samples.astype(np.float32)
                rms = float(np.sqrt(np.mean(float_s ** 2))) / 32768.0
                peak = float(np.max(np.abs(float_s))) / 32768.0

                # Noise Gate: silence chunk if level is below noise floor threshold
                is_gated = False
                if self.noise_gate_threshold > 0.001 and rms < self.noise_gate_threshold:
                    out_bytes = b"\x00" * len(out_bytes)
                    is_gated = True

                # Write into virtual mic
                self._virtual_mic.write_chunk(out_bytes)
                if self.loopback_enabled and self._loopback_cb and not is_gated:
                    try:
                        self._loopback_cb(out_bytes)
                    except Exception:
                        pass
                self.total_bytes_received += len(out_bytes)
                window_bytes += len(out_bytes)

                now = time.time()
                elapsed = now - window_start
                if elapsed >= 0.15:
                    rate_kb = (window_bytes / 1024.0) / elapsed
                    if self.on_stats_update:
                        self.on_stats_update({
                            "mic_bytes": self.total_bytes_received,
                            "mic_kb_per_sec": rate_kb,
                            "mic_rms": min(1.0, rms * 4.0),
                            "mic_peak": min(1.0, peak),
                        })
                    window_bytes = 0
                    window_start = now

        except Exception as e:
            if not self._stop_event.is_set():
                err_msg = str(e)
                print(f"[MicReceiver] Error: {err_msg}", file=sys.stderr)
                if self.on_error:
                    self.on_error(err_msg)
        finally:
            self.stop()
