"""
Persistent storage for remembered Wi-Fi ADB devices using QSettings.
"""

from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSettings


class WifiDeviceStore:
    """Stores and manages remembered Wi-Fi ADB devices."""

    SETTINGS_KEY = "wifi_devices_v1"

    def __init__(self, settings: Optional[QSettings] = None):
        self.settings = settings or QSettings("Sonopipe", "Sonopipe")

    def list_devices(self) -> List[Dict[str, Any]]:
        """Return saved Wi-Fi devices ordered by most recently connected."""
        raw = self.settings.value(self.SETTINGS_KEY, "[]")
        try:
            items = json.loads(str(raw)) if raw else []
            if not isinstance(items, list):
                return []
        except Exception:
            return []

        valid = [d for d in items if isinstance(d, dict) and d.get("host")]
        valid.sort(key=lambda d: float(d.get("last_connected", 0)), reverse=True)
        return valid

    def _write(self, devices: List[Dict[str, Any]]) -> None:
        self.settings.setValue(self.SETTINGS_KEY, json.dumps(devices))
        self.settings.sync()

    def save_device(
        self,
        host: str,
        port: int = 5555,
        model: str = "",
        auto_connect: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Insert or update a remembered Wi-Fi device (deduplicated by host)."""
        host = host.strip()
        if ":" in host:
            h_part, p_part = host.split(":", 1)
            host = h_part.strip()
            try:
                port = int(p_part)
            except ValueError:
                pass

        serial = f"{host}:{port}"
        devices = self.list_devices()
        existing = next((d for d in devices if d.get("host") == host), None)

        if existing is not None:
            existing["port"] = int(port)
            existing["serial"] = serial
            if model:
                existing["model"] = model
            if auto_connect is not None:
                existing["auto_connect"] = bool(auto_connect)
            existing["last_connected"] = time.time()
            entry = existing
        else:
            entry = {
                "serial": serial,
                "host": host,
                "port": int(port),
                "model": model or "Android Wi-Fi",
                "last_connected": time.time(),
                "auto_connect": True if auto_connect is None else bool(auto_connect),
            }
            devices.append(entry)

        self._write(devices)
        return entry

    def remove_device(self, host_or_serial: str) -> None:
        """Forget a saved Wi-Fi device by serial (host:port) or host."""
        target_host = host_or_serial.split(":", 1)[0].strip()
        devices = [
            d for d in self.list_devices()
            if d.get("serial") != host_or_serial and d.get("host") != target_host
        ]
        self._write(devices)

    def set_auto_connect(self, host_or_serial: str, enabled: bool) -> None:
        """Toggle auto-reconnect on launch for a saved device."""
        target_host = host_or_serial.split(":", 1)[0].strip()
        devices = self.list_devices()
        for d in devices:
            if d.get("serial") == host_or_serial or d.get("host") == target_host:
                d["auto_connect"] = bool(enabled)
        self._write(devices)

    def get_auto_connect_devices(self) -> List[Dict[str, Any]]:
        """Return saved devices that have auto-connect enabled."""
        return [d for d in self.list_devices() if d.get("auto_connect", True)]
