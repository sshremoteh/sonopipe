"""
Material Design 3 Wireless ADB Connection, Saved Devices, and Guide Dialogs.
"""

from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from sonopipe.adb.manager import AdbManager
from sonopipe.adb.wifi_store import WifiDeviceStore
from sonopipe.adb.qr_dialog import WirelessQrDialog, WirelessPairDialog
from sonopipe.gui.theme import MD3, md3_base_stylesheet


class WifiScanWorker(QThread):
    """Non-blocking mDNS discovery for Wireless ADB services."""

    finished = Signal(list)

    def __init__(self, adb: AdbManager):
        super().__init__()
        self.adb = adb

    def run(self):
        services = self.adb.discover_mdns_services()
        self.finished.emit(services)


class WifiConnectWorker(QThread):
    """Non-blocking adb connect worker."""

    finished = Signal(bool, str, str, int)

    def __init__(self, adb: AdbManager, host: str, port: int):
        super().__init__()
        self.adb = adb
        self.host = host
        self.port = port

    def run(self):
        ok, msg = self.adb.connect_wireless(self.host, self.port)
        self.finished.emit(ok, msg, self.host, self.port)


class WirelessGuideDialog(QDialog):
    """Step-by-step Material Design 3 guide for Wireless ADB setup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = MD3
        self.setWindowTitle("Wireless ADB Guide")
        self.resize(480, 440)
        self.setStyleSheet(md3_base_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Wireless ADB Setup")
        title.setFont(QFont("sans-serif", 16, QFont.Bold))
        layout.addWidget(title)

        sub = QLabel("Two quick ways to connect your phone without a USB cable:")
        sub.setStyleSheet(f"color: {c['on_surface_variant']}; font-size: 12px;")
        layout.addWidget(sub)

        steps = [
            (
                "Method 1 — Android 11+ (No USB needed)",
                "1. Open Settings → Developer options → Wireless debugging.\n"
                "2. Tap 'Pair device with QR code' or 'Pair device with pairing code'.\n"
                "3. Use QR Pair or 6-Digit Code in Sonopipe, then click Auto-Find.",
            ),
            (
                "Method 2 — Classic Wi-Fi (Any Android)",
                "1. Plug in your phone via USB once.\n"
                "2. Click 'USB → Wi-Fi' in the Wi-Fi Devices menu.\n"
                "3. Unplug USB — Sonopipe remembers your phone and auto-reconnects next time.",
            ),
        ]

        for heading, body in steps:
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {c['surface_container']}; "
                f"border: 1px solid {c['outline_variant']}; border-radius: 16px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(6)
            h_lbl = QLabel(heading)
            h_lbl.setStyleSheet(f"color: {c['primary']}; font-weight: 700; font-size: 13px; border: none;")
            b_lbl = QLabel(body)
            b_lbl.setWordWrap(True)
            b_lbl.setStyleSheet(f"color: {c['on_surface_variant']}; font-size: 12px; border: none;")
            cl.addWidget(h_lbl)
            cl.addWidget(b_lbl)
            layout.addWidget(card)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("Got it")
        btn_ok.setFixedHeight(38)
        btn_ok.setStyleSheet(
            f"background-color: {c['primary']}; color: {c['on_primary']}; "
            "border-radius: 19px; padding: 0 24px; font-weight: 700; border: none;"
        )
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)


class WifiConnectDialog(QDialog):
    """
    MD3 dialog for easy Wi-Fi connection, mDNS discovery, and managing
    remembered Wi-Fi devices with 1-click reconnect and auto-connect toggles.
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.mw = main_window
        self.adb: AdbManager = main_window.adb
        self.store: WifiDeviceStore = main_window.wifi_store
        self._scan_worker: Optional[WifiScanWorker] = None
        self._conn_worker: Optional[WifiConnectWorker] = None

        self.setWindowTitle("Wi-Fi Devices & Quick Connect")
        self.resize(500, 560)
        self.setModal(True)
        self.setStyleSheet(md3_base_stylesheet())

        self._init_ui()
        self._reload_saved_list()

    def _init_ui(self):
        c = MD3
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Wi-Fi Devices")
        title.setFont(QFont("sans-serif", 17, QFont.Bold))
        title_col.addWidget(title)

        self.lbl_status = QLabel("Connect once — Sonopipe remembers your device automatically")
        self.lbl_status.setStyleSheet(f"color: {c['on_surface_variant']}; font-size: 12px;")
        title_col.addWidget(self.lbl_status)
        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

        # Quick Actions Bar (MD3 Tonal Chips)
        quick_card = QFrame()
        quick_card.setStyleSheet(
            f"background-color: {c['surface_container']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 16px;"
        )
        ql = QVBoxLayout(quick_card)
        ql.setContentsMargins(14, 12, 14, 12)
        ql.setSpacing(10)

        lbl_quick = QLabel("QUICK CONNECT")
        lbl_quick.setStyleSheet(
            f"color: {c['muted']}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; border: none;"
        )
        ql.addWidget(lbl_quick)

        btn_grid = QHBoxLayout()
        btn_grid.setSpacing(8)

        self.btn_mdns = QPushButton("⚡ Auto-Find")
        self.btn_mdns.setFixedHeight(36)
        self.btn_mdns.setStyleSheet(
            f"background-color: {c['primary_container']}; color: {c['on_primary_container']}; "
            "border-radius: 18px; padding: 0 14px; font-weight: 700; font-size: 12px; border: none;"
        )
        self.btn_mdns.clicked.connect(self._start_mdns_scan)
        btn_grid.addWidget(self.btn_mdns)

        btn_usb = QPushButton("🔌 USB → Wi-Fi")
        btn_usb.setFixedHeight(36)
        btn_usb.setToolTip("Switch plugged-in USB phone to Wi-Fi (port 5555)")
        btn_usb.setStyleSheet(self._tonal_chip_style())
        btn_usb.clicked.connect(self._switch_usb)
        btn_grid.addWidget(btn_usb)

        btn_qr = QPushButton("📷 QR Pair")
        btn_qr.setFixedHeight(36)
        btn_qr.setStyleSheet(self._tonal_chip_style())
        btn_qr.clicked.connect(self._open_qr)
        btn_grid.addWidget(btn_qr)

        btn_code = QPushButton("🔑 Code")
        btn_code.setFixedHeight(36)
        btn_code.setStyleSheet(self._tonal_chip_style())
        btn_code.clicked.connect(self._open_pair_code)
        btn_grid.addWidget(btn_code)

        ql.addLayout(btn_grid)

        # Manual IP + Port row
        manual_row = QHBoxLayout()
        manual_row.setSpacing(8)

        self.ip_input = QLineEdit(self.mw.wifi_ip_input.text())
        self.ip_input.setPlaceholderText("Phone IP (e.g. 192.168.1.50)")
        manual_row.addWidget(self.ip_input, 1)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.mw.wifi_port_spin.value())
        self.port_spin.setFixedWidth(92)
        manual_row.addWidget(self.port_spin)

        self.btn_manual_conn = QPushButton("Connect")
        self.btn_manual_conn.setFixedHeight(36)
        self.btn_manual_conn.setStyleSheet(
            f"background-color: {c['primary']}; color: {c['on_primary']}; "
            "border-radius: 18px; padding: 0 18px; font-weight: 700; font-size: 12px; border: none;"
        )
        self.btn_manual_conn.clicked.connect(self._connect_manual)
        manual_row.addWidget(self.btn_manual_conn)
        ql.addLayout(manual_row)

        root.addWidget(quick_card)

        # Remembered Devices Section
        saved_hdr = QHBoxLayout()
        lbl_saved = QLabel("REMEMBERED DEVICES")
        lbl_saved.setStyleSheet(
            f"color: {c['muted']}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )
        saved_hdr.addWidget(lbl_saved)
        saved_hdr.addStretch()
        root.addLayout(saved_hdr)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.saved_container = QWidget()
        self.saved_layout = QVBoxLayout(self.saved_container)
        self.saved_layout.setContentsMargins(0, 0, 4, 0)
        self.saved_layout.setSpacing(8)
        self.scroll_area.setWidget(self.saved_container)
        root.addWidget(self.scroll_area, 1)

        # Bottom Row
        bottom = QHBoxLayout()
        btn_guide = QPushButton("Setup Guide")
        btn_guide.setFixedHeight(36)
        btn_guide.setStyleSheet(
            f"background-color: transparent; color: {c['primary']}; "
            "border: none; font-weight: 600; font-size: 12px; padding: 0 10px;"
        )
        btn_guide.clicked.connect(lambda: WirelessGuideDialog(self).exec())
        bottom.addWidget(btn_guide)
        bottom.addStretch()

        btn_close = QPushButton("Done")
        btn_close.setFixedHeight(38)
        btn_close.setStyleSheet(
            f"background-color: {c['secondary_container']}; color: {c['on_secondary_container']}; "
            "border-radius: 19px; padding: 0 22px; font-weight: 700; border: none;"
        )
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    @staticmethod
    def _tonal_chip_style() -> str:
        c = MD3
        return (
            f"QPushButton {{ background-color: {c['surface_container_high']}; color: {c['on_surface']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 18px; padding: 0 12px; "
            "font-weight: 600; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {c['surface_container_highest']}; }}"
        )

    def _clear_saved_layout(self):
        while self.saved_layout.count():
            item = self.saved_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _reload_saved_list(self):
        c = MD3
        self._clear_saved_layout()
        saved = self.store.list_devices()
        active_serials = {
            d.serial for d in self.adb.list_devices() if d.state == "device"
        }

        if not saved:
            empty_card = QFrame()
            empty_card.setStyleSheet(
                f"background-color: {c['surface_container_low']}; "
                f"border: 1px dashed {c['outline_variant']}; border-radius: 16px;"
            )
            el = QVBoxLayout(empty_card)
            el.setContentsMargins(20, 24, 20, 24)
            el.setAlignment(Qt.AlignCenter)
            lbl = QLabel("No remembered Wi-Fi devices yet.\nUse Auto-Find, USB → Wi-Fi, or enter an IP above.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: {c['muted']}; font-size: 12px; border: none;")
            el.addWidget(lbl)
            self.saved_layout.addWidget(empty_card)
            self.saved_layout.addStretch()
            return

        for dev in saved:
            host = dev["host"]
            port = int(dev.get("port", 5555))
            serial = f"{host}:{port}"
            model = dev.get("model") or "Android Wi-Fi"
            auto_conn = bool(dev.get("auto_connect", True))
            is_connected = serial in active_serials

            card = QFrame()
            card.setStyleSheet(
                f"background-color: {c['surface_container']}; "
                f"border: 1px solid {c['primary'] if is_connected else c['outline_variant']}; "
                "border-radius: 16px;"
            )
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 10, 12, 10)
            row.setSpacing(10)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)

            top_line = QHBoxLayout()
            top_line.setSpacing(8)
            name_lbl = QLabel(model)
            name_lbl.setStyleSheet(f"color: {c['on_surface']}; font-weight: 700; font-size: 13px; border: none;")
            top_line.addWidget(name_lbl)

            badge = QLabel("Connected" if is_connected else "Saved")
            badge_bg = c["success_container"] if is_connected else c["surface_container_high"]
            badge_fg = c["on_success_container"] if is_connected else c["muted"]
            badge.setStyleSheet(
                f"background-color: {badge_bg}; color: {badge_fg}; "
                "border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; border: none;"
            )
            top_line.addWidget(badge)
            top_line.addStretch()
            info_col.addLayout(top_line)

            addr_lbl = QLabel(serial)
            addr_lbl.setStyleSheet(
                f"color: {c['on_surface_variant']}; font-family: {c['font_mono']}; font-size: 11px; border: none;"
            )
            info_col.addWidget(addr_lbl)
            row.addLayout(info_col, 1)

            # Auto-connect chip
            btn_auto = QPushButton("Auto" if auto_conn else "Manual")
            btn_auto.setCheckable(True)
            btn_auto.setChecked(auto_conn)
            btn_auto.setFixedHeight(30)
            btn_auto.setToolTip("Auto-reconnect to this device when Sonopipe starts")
            btn_auto.setStyleSheet(
                f"QPushButton {{ background-color: {c['surface_container_high']}; color: {c['muted']}; "
                f"border: 1px solid {c['outline_variant']}; border-radius: 15px; padding: 0 10px; "
                "font-size: 11px; font-weight: 600; }}"
                f"QPushButton:checked {{ background-color: {c['secondary_container']}; "
                f"color: {c['on_secondary_container']}; border-color: {c['primary']}; }}"
            )
            btn_auto.clicked.connect(
                lambda checked, s=serial: self._toggle_auto(s, checked)
            )
            row.addWidget(btn_auto)

            # Connect / Disconnect button
            btn_act = QPushButton("Disconnect" if is_connected else "Connect")
            btn_act.setFixedHeight(32)
            if is_connected:
                btn_act.setStyleSheet(
                    f"background-color: {c['surface_container_high']}; color: {c['on_surface']}; "
                    f"border: 1px solid {c['outline_variant']}; border-radius: 16px; "
                    "padding: 0 14px; font-size: 12px; font-weight: 600;"
                )
                btn_act.clicked.connect(lambda _, s=serial: self._disconnect_target(s))
            else:
                btn_act.setStyleSheet(
                    f"background-color: {c['primary']}; color: {c['on_primary']}; "
                    "border: none; border-radius: 16px; padding: 0 14px; font-size: 12px; font-weight: 700;"
                )
                btn_act.clicked.connect(lambda _, h=host, p=port: self._connect_async(h, p))
            row.addWidget(btn_act)

            # Forget button
            btn_del = QPushButton("✕")
            btn_del.setFixedSize(30, 30)
            btn_del.setToolTip("Forget this device")
            btn_del.setStyleSheet(
                f"QPushButton {{ background-color: transparent; color: {c['muted']}; border: none; border-radius: 15px; font-size: 13px; }}"
                f"QPushButton:hover {{ background-color: {c['error_container']}; color: {c['on_error_container']}; }}"
            )
            btn_del.clicked.connect(lambda _, s=serial: self._forget_device(s))
            row.addWidget(btn_del)

            self.saved_layout.addWidget(card)

        self.saved_layout.addStretch()

    def _toggle_auto(self, serial: str, enabled: bool):
        self.store.set_auto_connect(serial, enabled)
        self._reload_saved_list()

    def _forget_device(self, serial: str):
        self.store.remove_device(serial)
        self._reload_saved_list()
        self.mw._refresh_quick_wifi_bar()

    def _connect_manual(self):
        text = self.ip_input.text().strip()
        port = self.port_spin.value()
        if not text:
            return
        if ":" in text:
            host, p_str = text.split(":", 1)
            try:
                port = int(p_str)
                self.ip_input.setText(host)
                self.port_spin.setValue(port)
            except ValueError:
                pass
        else:
            host = text
        self._connect_async(host, port)

    def _connect_async(self, host: str, port: int):
        c = MD3
        self.lbl_status.setText(f"Connecting to {host}:{port}...")
        self.lbl_status.setStyleSheet(f"color: {c['primary']}; font-size: 12px;")
        self.btn_manual_conn.setEnabled(False)

        self._conn_worker = WifiConnectWorker(self.adb, host, port)
        self._conn_worker.finished.connect(self._on_connect_finished)
        self._conn_worker.start()

    def _on_connect_finished(self, ok: bool, msg: str, host: str, port: int):
        c = MD3
        self.btn_manual_conn.setEnabled(True)
        if ok:
            self.mw.wifi_ip_input.setText(host)
            self.mw.wifi_port_spin.setValue(port)
            self.store.save_device(host, port)
            self.mw.refresh_devices(select_serial=f"{host}:{port}")
            self.lbl_status.setText(f"Connected to {host}:{port}")
            self.lbl_status.setStyleSheet(f"color: {c['success']}; font-size: 12px;")
            self._reload_saved_list()
        else:
            self.lbl_status.setText(f"Could not connect to {host}:{port}")
            self.lbl_status.setStyleSheet(f"color: {c['error']}; font-size: 12px;")
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {host}:{port}:\n\n{msg}")

    def _disconnect_target(self, serial: str):
        self.adb.disconnect_wireless(serial)
        self.mw.refresh_devices()
        self._reload_saved_list()

    def _start_mdns_scan(self):
        c = MD3
        self.btn_mdns.setEnabled(False)
        self.btn_mdns.setText("Scanning...")
        self.lbl_status.setText("Scanning local Wi-Fi via mDNS...")
        self.lbl_status.setStyleSheet(f"color: {c['primary']}; font-size: 12px;")

        self._scan_worker = WifiScanWorker(self.adb)
        self._scan_worker.finished.connect(self._on_mdns_finished)
        self._scan_worker.start()

    def _on_mdns_finished(self, services: List[tuple]):
        c = MD3
        self.btn_mdns.setEnabled(True)
        self.btn_mdns.setText("⚡ Auto-Find")

        if not services:
            # Check if a USB device is connected to offer instant switch
            usb_devs = [d for d in self.adb.list_devices() if ":" not in d.serial and d.state == "device"]
            if usb_devs:
                self._switch_usb()
                return
            self.lbl_status.setText("No mDNS Wireless ADB devices found on Wi-Fi.")
            self.lbl_status.setStyleSheet(f"color: {c['warning']}; font-size: 12px;")
            return

        _, _, ip_port = services[0]
        if ":" in ip_port:
            host, port_str = ip_port.split(":", 1)
            port = int(port_str)
        else:
            host, port = ip_port, 5555

        self.ip_input.setText(host)
        self.port_spin.setValue(port)
        self._connect_async(host, port)

    def _switch_usb(self):
        self.mw._auto_switch_usb_to_wifi()
        self._reload_saved_list()

    def _open_qr(self):
        WirelessQrDialog(self.adb, parent=self).exec()

    def _open_pair_code(self):
        WirelessPairDialog(self.adb, default_ip=self.ip_input.text().strip(), parent=self).exec()
