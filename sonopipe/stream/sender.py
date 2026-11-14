"""
Audio stream sender: captures PCM audio and streams it to Android via TCP over ADB.
"""

from __future__ import annotations
import socket
import sys
import threading
import time
from typing import Callable, Optional

import numpy as np

from sonopipe.capture.base import AudioCaptureBase
from sonopipe.capture.factory import create_audio_capture
from sonopipe.stream.protocol import create_header, DEFAULT_PORT


class AudioStreamer:
    """Orchestrates audio capture and TCP transmission to the Android receiver."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_frames: int = 960,
        volume: float = 1.0,
        backend: Optional[str] = None,
        audio_device_id: Optional[str] = None,
        on_stats_update: Optional[Callable[[dict], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_frames = chunk_frames
        self.volume = max(0.0, min(2.0, volume))
        self.backend_name = backend
        self.audio_device_id = audio_device_id

        self.on_stats_update = on_stats_update
        self.on_error = on_error

        self._capture: Optional[AudioCaptureBase] = None
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.is_running = False
        self.total_bytes_sent = 0
        self.start_time: Optional[float] = None

    def set_volume(self, vol: float) -> None:
        """Update streaming volume level in real-time (0.0 to 2.0)."""
        self.volume = max(0.0, min(2.0, vol))

    def start(self) -> None:
        """Start streaming audio in a background worker thread."""
        if self.is_running:
            return

        self._stop_event.clear()
        self.is_running = True
        self.total_bytes_sent = 0
        self.start_time = time.time()

        self._thread = threading.Thread(target=self._run, daemon=True, name="ADBSoundStreamer")
        self._thread.start()

    def stop(self) -> None:
        """Stop streaming audio and close connections."""
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

        if self._capture is not None:
            try:
                self._capture.stop()
            except Exception:
                pass
            self._capture = None

        if self._thread and self._thread is not threading.current_thread() and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            # 1. Initialize audio capture backend
            self._capture = create_audio_capture(
                backend=self.backend_name,
                device_id=self.audio_device_id,
                sample_rate=self.sample_rate,
                channels=self.channels,
                chunk_frames=self.chunk_frames,
            )
            self._capture.start()

            # 2. Connect to Android TCP socket (port forwarded via ADB)
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self._sock.settimeout(5.0)

            try:
                self._sock.connect((self.host, self.port))
            except ConnectionRefusedError:
                raise ConnectionError(
                    f"Connection refused at {self.host}:{self.port}. "
                    f"Make sure ADBSound app is running on phone and port forwarding is active."
                )

            # 3. Send 16-byte protocol header
            header = create_header(
                sample_rate=self.sample_rate,
                channels=self.channels,
                bits_per_sample=16,
            )
            self._sock.sendall(header)

            # Set normal socket timeout for streaming
            self._sock.settimeout(3.0)

            # 4. Stream loop
            window_bytes = 0
            window_start = time.time()

            while not self._stop_event.is_set():
                chunk = self._capture.read_chunk()
                if not chunk:
                    continue

                # Process chunk & volume
                samples = np.frombuffer(chunk, dtype=np.int16)
                if abs(self.volume - 1.0) > 0.01:
                    scaled = np.clip(samples.astype(np.float32) * self.volume, -32768, 32767).astype(np.int16)
                    send_bytes = scaled.tobytes()
                else:
                    send_bytes = chunk

                # Calculate Stereo RMS / peak for audio visualizer
                float_samples = samples.astype(np.float32)
                if self.channels == 2 and len(float_samples) >= 2:
                    stereo = float_samples.reshape(-1, 2)
                    left_rms = float(np.sqrt(np.mean(stereo[:, 0] ** 2))) / 32768.0
                    right_rms = float(np.sqrt(np.mean(stereo[:, 1] ** 2))) / 32768.0
                    left_peak = float(np.max(np.abs(stereo[:, 0]))) / 32768.0
                    right_peak = float(np.max(np.abs(stereo[:, 1]))) / 32768.0
                    rms = (left_rms + right_rms) / 2.0
                    peak = max(left_peak, right_peak)
                else:
                    rms = float(np.sqrt(np.mean(float_samples ** 2))) / 32768.0
                    peak = float(np.max(np.abs(float_samples))) / 32768.0
                    left_rms = right_rms = rms
                    left_peak = right_peak = peak

                # Send over TCP
                self._sock.sendall(send_bytes)
                self.total_bytes_sent += len(send_bytes)
                window_bytes += len(send_bytes)

                now = time.time()
                elapsed = now - window_start
                if elapsed >= 0.25:
                    rate_kb = (window_bytes / 1024.0) / elapsed
                    uptime = now - (self.start_time or now)
                    if self.on_stats_update:
                        self.on_stats_update({
                            "bytes_sent": self.total_bytes_sent,
                            "kb_per_sec": rate_kb,
                            "rms_level": min(1.0, rms * 3.0),
                            "peak_level": min(1.0, peak),
                            "left_rms": min(1.0, left_rms * 3.0),
                            "right_rms": min(1.0, right_rms * 3.0),
                            "left_peak": min(1.0, left_peak),
                            "right_peak": min(1.0, right_peak),
                            "uptime": uptime,
                        })
                    window_bytes = 0
                    window_start = now

        except Exception as e:
            if not self._stop_event.is_set():
                err_msg = str(e)
                print(f"[AudioStreamer] Error: {err_msg}", file=sys.stderr)
                if self.on_error:
                    self.on_error(err_msg)
        finally:
            self.stop()
