"""
Main entry point for ADBSound.
Dispatches to GUI (PySide6) or CLI based on arguments.
"""

from __future__ import annotations
import argparse
import os
import sys

# Suppress noisy Qt Wayland client warnings on Hyprland/Wayland compositors
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland*=false")

from sonopipe.stream.protocol import DEFAULT_PORT, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sonopipe",
        description="Stream system audio from PC (Linux/Windows) to Android smartphone via ADB USB.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--cli",
        action="store_true",
        help="Run in command-line interface (CLI) mode without GUI.",
    )
    mode_group.add_argument(
        "--gui",
        action="store_true",
        help="Run in graphical user interface (GUI) mode (default).",
    )

    parser.add_argument(
        "-m", "--mode",
        type=str,
        default="speaker",
        choices=["speaker", "mic", "duplex"],
        help="Streaming mode: speaker (PC -> Phone), mic (Phone -> PC virtual mic), duplex (both, default: speaker)",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port for ADB speaker streaming (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--mic-port",
        type=int,
        default=12851,
        help="TCP port for ADB microphone streaming (default: 12851)",
    )
    parser.add_argument(
        "--mic-gain",
        type=float,
        default=1.0,
        help="Microphone software gain multiplier (0.0 to 2.0, default: 1.0)",
    )
    parser.add_argument(
        "-d", "--device",
        type=str,
        default=None,
        help="Specific ADB device serial to use",
    )
    parser.add_argument(
        "-r", "--rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        choices=[44100, 48000],
        help=f"Audio sample rate in Hz (default: {DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "-c", "--channels",
        type=int,
        default=DEFAULT_CHANNELS,
        choices=[1, 2],
        help=f"Number of audio channels (1=Mono, 2=Stereo, default: {DEFAULT_CHANNELS})",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=960,
        help="Chunk frame size for low-latency streaming (default: 960 frames = 20ms at 48kHz)",
    )
    parser.add_argument(
        "-v", "--volume",
        type=float,
        default=1.0,
        help="Software volume multiplier (0.0 to 2.0, default: 1.0)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        choices=["auto", "pulse", "wasapi", "soundcard"],
        help="Audio capture backend to use (default: auto)",
    )
    parser.add_argument(
        "--audio-device",
        type=str,
        default=None,
        help="ID or name of audio capture device/monitor sink",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="Skip automatic ADB port forwarding",
    )
    parser.add_argument(
        "--list-adb-devices",
        action="store_true",
        help="List connected ADB devices and exit",
    )
    parser.add_argument(
        "--list-audio-devices",
        action="store_true",
        help="List available audio capture sources and exit",
    )
    parser.add_argument(
        "--install-apk",
        action="store_true",
        help="Build (if needed) and install APK onto connected phone via ADB, then launch it",
    )
    parser.add_argument(
        "--connect-wireless",
        type=str,
        default=None,
        metavar="IP[:PORT]",
        help="Connect to phone wirelessly over Wi-Fi via ADB (default port 5555)",
    )
    parser.add_argument(
        "--enable-tcpip",
        nargs="?",
        const=5555,
        type=int,
        metavar="PORT",
        help="Switch USB-connected phone to TCP/IP mode (default port: 5555)",
    )
    parser.add_argument(
        "--wireless-guide",
        action="store_true",
        help="Print step-by-step Wireless ADB setup instructions and exit",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    # If any CLI-specific action flags are present or --cli explicitly requested
    has_cli_flag = (
        args.cli
        or args.list_adb_devices
        or args.list_audio_devices
        or args.install_apk
        or (args.connect_wireless is not None)
        or (args.enable_tcpip is not None)
        or args.wireless_guide
    )

    if has_cli_flag:
        from sonopipe.cli import run_cli
        sys.exit(run_cli(args))
    else:
        try:
            from sonopipe.gui.main_window import run_gui
            sys.exit(run_gui())
        except ImportError as e:
            print(f"[Warning] PySide6 GUI could not be loaded ({e}). Falling back to CLI mode.\n")
            from sonopipe.cli import run_cli
            sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
