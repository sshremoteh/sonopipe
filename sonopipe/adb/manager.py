"""
ADB command wrapper and device manager.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from typing import List, Dict, Optional


class AdbDevice:
    def __init__(self, serial: str, state: str, model: str = ""):
        self.serial = serial
        self.state = state
        self.model = model

    def __repr__(self) -> str:
        name = f" ({self.model})" if self.model else ""
        return f"{self.serial}{name} [{self.state}]"


class AdbManager:
    """Handles ADB interaction: discovery, port-forwarding, and status."""

    def __init__(self, adb_path: Optional[str] = None):
        self.adb_path = adb_path or self._find_adb()

    @staticmethod
    def _find_adb() -> str:
        """Find ADB binary in PATH or standard installation locations."""
        # 1. Standard PATH
        which_adb = shutil.which("adb")
        if which_adb:
            return which_adb

        # 2. Check ANDROID_HOME or ANDROID_SDK_ROOT
        sdk_env = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if sdk_env:
            candidate = os.path.join(sdk_env, "platform-tools", "adb" + (".exe" if sys.platform == "win32" else ""))
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        # 3. Check Windows default appdata
        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                candidate = os.path.join(local_appdata, "Android", "Sdk", "platform-tools", "adb.exe")
                if os.path.isfile(candidate):
                    return candidate

        # 4. Fallback to just "adb"
        return "adb"

    def is_available(self) -> bool:
        """Check if ADB executable exists and can be executed."""
        try:
            res = subprocess.run(
                [self.adb_path, "version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def list_devices(self) -> List[AdbDevice]:
        """Return list of connected ADB devices."""
        try:
            res = subprocess.run(
                [self.adb_path, "devices", "-l"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return []

            devices: List[AdbDevice] = []
            lines = res.stdout.strip().splitlines()
            for line in lines[1:]:  # skip 'List of devices attached'
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    model = ""
                    for p in parts[2:]:
                        if p.startswith("model:"):
                            model = p.split(":", 1)[1]
                            break
                    devices.append(AdbDevice(serial=serial, state=state, model=model))
            return devices
        except Exception:
            return []

    def forward_port(self, local_port: int, remote_port: int, serial: Optional[str] = None) -> bool:
        """Forward a local TCP port to the remote device TCP port."""
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception as e:
            print(f"[ADB] Failed to forward port: {e}", file=sys.stderr)
            return False

    def remove_forward(self, local_port: int, serial: Optional[str] = None) -> bool:
        """Remove a port forward rule."""
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["forward", "--remove", f"tcp:{local_port}"])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def install_apk(self, apk_path: str, serial: Optional[str] = None) -> tuple[bool, str]:
        """Install an APK file onto the target device."""
        if not os.path.isfile(apk_path):
            return False, f"APK file not found at: {apk_path}"

        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["install", "-r", "-d", apk_path])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            if res.returncode == 0 and "Success" in output:
                return True, output
            return False, output or f"Failed with exit code {res.returncode}"
        except Exception as e:
            return False, str(e)

    def launch_app(
        self,
        package_name: str = "com.adbsound.app",
        activity_name: str = "com.adbsound.app.MainActivity",
        serial: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Launch an activity on the target device via 'am start'."""
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["shell", "am", "start", "-n", f"{package_name}/{activity_name}"])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            return res.returncode == 0, output
        except Exception as e:
            return False, str(e)

    def enable_tcpip(self, port: int = 5555, serial: Optional[str] = None) -> tuple[bool, str]:
        """Switch target device to TCP/IP mode on given port."""
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["tcpip", str(port)])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            out = (res.stdout + "\n" + res.stderr).strip()
            return res.returncode == 0, out
        except Exception as e:
            return False, str(e)

    def connect_wireless(self, host: str, port: int = 5555) -> tuple[bool, str]:
        """Connect to an Android device over Wi-Fi via adb connect <host>:<port>."""
        target = host.strip()
        if ":" in target:
            # host already contains port (e.g. 192.168.1.101:41001)
            pass
        else:
            target = f"{target}:{port}"
        cmd = [self.adb_path, "connect", target]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=12,
            )
            out = (res.stdout + "\n" + res.stderr).strip()
            if "connected to" in out.lower() or "already connected" in out.lower():
                return True, out
            return False, out
        except Exception as e:
            return False, str(e)

    def pair_wireless(self, host: str, port: int, pairing_code: str) -> tuple[bool, str]:
        """Pair with device using Android 11+ wireless debugging pairing code."""
        target = f"{host.strip()}:{port}"
        cmd = [self.adb_path, "pair", target, pairing_code.strip()]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
            out = (res.stdout + "\n" + res.stderr).strip()
            if "successfully paired" in out.lower():
                return True, out
            return False, out
        except Exception as e:
            return False, str(e)

    def disconnect_wireless(self, target: Optional[str] = None) -> tuple[bool, str]:
        """Disconnect wireless device (or all wireless devices if target is None)."""
        cmd = [self.adb_path, "disconnect"]
        if target:
            cmd.append(target.strip())

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
            )
            out = (res.stdout + "\n" + res.stderr).strip()
            return res.returncode == 0, out
        except Exception as e:
            return False, str(e)

    def get_device_wlan_ip(self, serial: Optional[str] = None) -> Optional[str]:
        """Attempt to discover the device's Wi-Fi IPv4 address while connected."""
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["shell", "ip -f inet addr show wlan0"])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and "inet " in res.stdout:
                for part in res.stdout.split():
                    if "/" in part and not part.startswith("/"):
                        ip = part.split("/")[0]
                        if ip.count(".") == 3:
                            return ip
        except Exception:
            pass

        # Fallback to getprop
        cmd_prop = [self.adb_path]
        if serial:
            cmd_prop.extend(["-s", serial])
        cmd_prop.extend(["shell", "getprop dhcp.wlan0.ipaddress"])
        try:
            res = subprocess.run(
                cmd_prop,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            ip = res.stdout.strip()
            if ip.count(".") == 3:
                return ip
        except Exception:
            pass

        return None
