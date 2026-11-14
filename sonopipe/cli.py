"""
Command-line interface (CLI) for ADBSound.
"""

from __future__ import annotations
import argparse
import signal
import sys
import time

from sonopipe.adb.manager import AdbManager
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS


def format_vu_meter(level: float, width: int = 20) -> str:
    """Render a text-based ASCII VU meter bar."""
    filled = int(max(0.0, min(1.0, level)) * width)
    empty = width - filled
    return f"[{'#' * filled}{'-' * empty}]"


def run_cli(args: argparse.Namespace) -> int:
    adb = AdbManager()

    # 1. Action: list ADB devices
    if args.list_adb_devices:
        if not adb.is_available():
            print("[Error] ADB is not installed or not found in PATH.", file=sys.stderr)
            return 1
        devices = adb.list_devices()
        print(f"Connected ADB Devices ({len(devices)}):")
        for dev in devices:
            print(f"  - {dev.serial} [{dev.state}] {dev.model}")
        return 0

    # 2. Action: list audio capture devices
    if args.list_audio_devices:
        devices = list_audio_devices(backend=args.backend)
        print(f"Available Audio Capture Sources ({len(devices)}):")
        for dev in devices:
            def_str = " (Default)" if dev.is_default else ""
            print(f"  - [{dev.id}] {dev.name}{def_str}")
        return 0

    # 3. Action: install APK to phone
    if getattr(args, "install_apk", False):
        from sonopipe.adb.installer import install_and_launch
        print("[ADB] Starting APK installation onto device...")
        ok, msg = install_and_launch(
            serial=args.device,
            progress_cb=lambda s: print(f"  > {s}"),
        )
        if ok:
            print(f"[Success] {msg}")
            return 0
        else:
            print(f"[Error] {msg}", file=sys.stderr)
            return 1

    # 4. Action: Wireless Guide
    if getattr(args, "wireless_guide", False):
        print("\n=======================================================")
        print("          Sonopipe Wireless ADB Setup Guide")
        print("=======================================================")
        print("Method 1: One-Click via USB Cable (Recommended)")
        print("  1. Connect phone via USB cable with USB Debugging enabled.")
        print("  2. Ensure phone and PC are on the same Wi-Fi network.")
        print("  3. Run: sonopipe --enable-tcpip")
        print("  4. Look up your phone's Wi-Fi IP and connect:")
        print("     sonopipe --connect-wireless <PHONE_IP>")
        print("  5. Unplug the USB cable! Sound will now stream over Wi-Fi.\n")
        print("Method 2: Android 11+ Wireless Debugging (No Cable)")
        print("  1. On Phone: Settings -> Developer Options -> Wireless debugging.")
        print("  2. Tap 'Pair device with pairing code' -> note IP:Port & Code.")
        print("  3. Run: adb pair <IP>:<PORT> <code>")
        print("  4. Run: sonopipe --connect-wireless <MAIN_IP>:<MAIN_PORT>\n")
        return 0

    # 5. Action: Enable TCP/IP mode on USB device
    if getattr(args, "enable_tcpip", None) is not None:
        port = args.enable_tcpip
        print(f"[ADB] Enabling TCP/IP mode on port {port}...")
        ok, msg = adb.enable_tcpip(port, serial=args.device)
        if ok:
            print(f"[Success] Phone switched to TCP/IP port {port}. Output: {msg}")
            ip = adb.get_device_wlan_ip(serial=args.device)
            if ip:
                print(f"[Info] Detected phone Wi-Fi IP: {ip}")
                print(f"       Connect wirelessly using: sonopipe --connect-wireless {ip}:{port}")
            return 0
        else:
            print(f"[Error] Failed to switch to TCP/IP mode: {msg}", file=sys.stderr)
            return 1

    # 6. Action: Connect to wireless device
    if getattr(args, "connect_wireless", None) is not None:
        target = args.connect_wireless.strip()
        if ":" in target:
            host, port_str = target.split(":", 1)
            port = int(port_str)
        else:
            host = target
            port = 5555
        print(f"[ADB] Connecting to wireless device at {host}:{port}...")
        ok, msg = adb.connect_wireless(host, port)
        if ok:
            print(f"[Success] {msg}")
            return 0
        else:
            print(f"[Error] Failed to connect wirelessly: {msg}", file=sys.stderr)
            return 1

    # Check ADB installation
    if not args.no_forward:
        if not adb.is_available():
            print("[Warning] ADB not found in PATH. Continuing without automatic port forwarding.", file=sys.stderr)
        else:
            adb_devices = adb.list_devices()
            target_device = None
            if args.device:
                target_device = args.device
            elif adb_devices:
                # pick first active device
                active_devs = [d for d in adb_devices if d.state == "device"]
                if active_devs:
                    target_device = active_devs[0].serial

            print(f"[ADB] Setting up port forward tcp:{args.port} -> tcp:{args.port} (device: {target_device or 'default'})")
            success = adb.forward_port(local_port=args.port, remote_port=args.port, serial=target_device)
            if not success:
                print(f"[Warning] Failed to run adb forward. Make sure phone is connected via USB with USB debugging enabled.", file=sys.stderr)

    print(f"\n==========================================")
    print(f"    Sonopipe Audio Streaming (CLI)")
    print(f"==========================================")
    print(f"Target:       127.0.0.1:{args.port}")
    print(f"Sample Rate:  {args.rate} Hz")
    print(f"Channels:     {'Stereo' if args.channels == 2 else 'Mono'}")
    print(f"Backend:      {args.backend or get_default_backend_name()}")
    print(f"Volume:       {int(args.volume * 100)}%")
    print(f"Audio Source: {args.audio_device or 'Default Output'}")
    print(f"Press Ctrl+C to stop streaming.\n")

    latest_stats = {"bytes_sent": 0, "kb_per_sec": 0.0, "rms_level": 0.0, "peak_level": 0.0, "uptime": 0.0}

    def on_stats(stats: dict):
        nonlocal latest_stats
        latest_stats = stats

    error_occurred = False

    def on_error(err: str):
        nonlocal error_occurred
        error_occurred = True
        print(f"\n[Stream Error] {err}", file=sys.stderr)

    streamer = AudioStreamer(
        host="127.0.0.1",
        port=args.port,
        sample_rate=args.rate,
        channels=args.channels,
        chunk_frames=args.chunk_size,
        volume=args.volume,
        backend=args.backend,
        audio_device_id=args.audio_device,
        on_stats_update=on_stats,
        on_error=on_error,
    )

    def signal_handler(sig, frame):
        print("\nStopping audio stream...")
        streamer.stop()
        if not args.no_forward and adb.is_available():
            adb.remove_forward(local_port=args.port, serial=args.device)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        streamer.start()
    except Exception as e:
        print(f"[Fatal] Failed to start stream: {e}", file=sys.stderr)
        return 1

    # Status refresh loop
    while streamer.is_running and not error_occurred:
        time.sleep(0.3)
        mb = latest_stats["bytes_sent"] / (1024.0 * 1024.0)
        vu = format_vu_meter(latest_stats["rms_level"])
        rate = latest_stats["kb_per_sec"]
        uptime = int(latest_stats["uptime"])
        sys.stdout.write(f"\r  Streaming: {vu}  Rate: {rate:6.1f} KB/s  Total: {mb:5.1f} MB  Time: {uptime:02d}s ")
        sys.stdout.flush()

    if error_occurred:
        return 1

    return 0
