"""
Settings and Advanced Tools Dialog for Sonopipe.
Keeps the main interface ultra-clean while offering full power-user controls.
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QFrame,
    QMessageBox,
    QTabWidget,
    QApplication,
)

from sonopipe.adb.manager import AdbManager
from sonopipe.adb.installer import install_and_launch
from sonopipe.adb.qr_dialog import WirelessQrDialog, WirelessPairDialog
from sonopipe.capture.factory import list_audio_devices


class SettingsDialog(QDialog):
    """Clean tabs for Wireless ADB, Audio Capture backend, and Utilities."""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.mw = parent_window
        self.adb: AdbManager = parent_window.adb

        self.setWindowTitle("Sonopipe Settings & Tools")
        self.resize(520, 460)
        self.setModal(True)

        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        tabs = QTabWidget()

        # TAB 1: WIRELESS ADB
        wifi_tab = QWidget()
        w_layout = QVBoxLayout(wifi_tab)
        w_layout.setContentsMargins(14, 14, 14, 14)
        w_layout.setSpacing(12)

        desc = QLabel("Connect to your smartphone wirelessly over Wi-Fi without cables:")
        desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        desc.setWordWrap(True)
        w_layout.addWidget(desc)

        ip_grid = QGridLayout()
        ip_grid.setSpacing(8)
        ip_grid.addWidget(QLabel("Phone IP:"), 0, 0)
        self.ip_input = QLineEdit(self.mw.wifi_ip_input.text())
        self.ip_input.setPlaceholderText("e.g. 192.168.1.50 or 192.168.1.50:41001")
        ip_grid.addWidget(self.ip_input, 0, 1)

        ip_grid.addWidget(QLabel("Port:"), 0, 2)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.mw.wifi_port_spin.value())
        self.port_spin.setFixedWidth(75)
        ip_grid.addWidget(self.port_spin, 0, 3)
        w_layout.addLayout(ip_grid)

        # Quick Actions
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        btn_find = QPushButton("🔍 Auto-Find (mDNS)")
        btn_find.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: bold; padding: 6px;")
        btn_find.clicked.connect(self._on_autofind)
        act_row.addWidget(btn_find)

        btn_conn = QPushButton("📶 Connect")
        btn_conn.setStyleSheet("background-color: #065F46; color: #6EE7B7; font-weight: bold; padding: 6px;")
        btn_conn.clicked.connect(self._on_connect)
        act_row.addWidget(btn_conn)

        btn_disc = QPushButton("Disconnect")
        btn_disc.clicked.connect(self._on_disconnect)
        act_row.addWidget(btn_disc)
        w_layout.addLayout(act_row)

        w_layout.addWidget(self._make_divider())

        # Pairing Actions
        pair_row = QHBoxLayout()
        pair_row.setSpacing(8)

        btn_qr = QPushButton("📷 Pair with QR Code")
        btn_qr.setToolTip("Show QR code for Android 11+ Developer Options")
        btn_qr.setStyleSheet("background-color: #1E293B; color: #38BDF8; padding: 6px;")
        btn_qr.clicked.connect(self._open_qr)
        pair_row.addWidget(btn_qr)

        btn_code = QPushButton("🔑 Pair with 6-Digit Code")
        btn_code.setStyleSheet("background-color: #1E293B; color: #CBD5E1; padding: 6px;")
        btn_code.clicked.connect(self._open_code)
        pair_row.addWidget(btn_code)
        w_layout.addLayout(pair_row)

        btn_usb_switch = QPushButton("⚡ Switch to Wi-Fi via USB (Auto-Setup)")
        btn_usb_switch.setToolTip("One-click: enables TCP/IP port 5555 while plugged into USB")
        btn_usb_switch.setStyleSheet("background-color: #1E293B; color: #94A3B8; padding: 6px; font-size: 11px;")
        btn_usb_switch.clicked.connect(self.mw._auto_switch_usb_to_wifi)
        w_layout.addWidget(btn_usb_switch)
        w_layout.addStretch()

        tabs.addTab(wifi_tab, "📶 Wireless ADB")

        # TAB 2: AUDIO & LATENCY
        audio_tab = QWidget()
        a_layout = QVBoxLayout(audio_tab)
        a_layout.setContentsMargins(14, 14, 14, 14)
        a_layout.setSpacing(12)

        a_layout.addWidget(QLabel("PC Audio Capture Source:"))
        self.source_combo = QComboBox()
        self._populate_audio_sources()
        a_layout.addWidget(self.source_combo)

        a_layout.addWidget(QLabel("Latency Preset (Buffer Size):"))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self.btn_p10 = QPushButton("⚡ 10 ms (Low)")
        self.btn_p20 = QPushButton("✓ 20 ms (Default)")
        self.btn_p40 = QPushButton("🛡 40 ms (Safe)")
        for b in (self.btn_p10, self.btn_p20, self.btn_p40):
            b.setCheckable(True)
            preset_row.addWidget(b)

        if self.mw.chunk_frames == 480:
            self.btn_p10.setChecked(True)
        elif self.mw.chunk_frames == 1920:
            self.btn_p40.setChecked(True)
        else:
            self.btn_p20.setChecked(True)

        self.btn_p10.clicked.connect(lambda: self._set_preset(480))
        self.btn_p20.clicked.connect(lambda: self._set_preset(960))
        self.btn_p40.clicked.connect(lambda: self._set_preset(1920))
        a_layout.addLayout(preset_row)

        a_layout.addWidget(self._make_divider())

        # Network Ports
        port_grid = QGridLayout()
        port_grid.setSpacing(8)
        port_grid.addWidget(QLabel("Speaker TCP Port:"), 0, 0)
        self.spk_port_spin = QSpinBox()
        self.spk_port_spin.setRange(1024, 65535)
        self.spk_port_spin.setValue(self.mw.port_spin.value())
        port_grid.addWidget(self.spk_port_spin, 0, 1)

        port_grid.addWidget(QLabel("Microphone TCP Port:"), 1, 0)
        self.mic_port_spin = QSpinBox()
        self.mic_port_spin.setRange(1024, 65535)
        self.mic_port_spin.setValue(self.mw.mic_port_spin.value())
        port_grid.addWidget(self.mic_port_spin, 1, 1)
        a_layout.addLayout(port_grid)

        btn_copy_cmd = QPushButton("📋 Copy ADB Forward Command")
        btn_copy_cmd.setStyleSheet("background-color: #1E293B; color: #94A3B8; font-size: 11px;")
        btn_copy_cmd.clicked.connect(self.mw._copy_forward_command)
        a_layout.addWidget(btn_copy_cmd)
        a_layout.addStretch()

        tabs.addTab(audio_tab, "🎛 Audio & Performance")

        # TAB 3: TOOLS & APK
        tools_tab = QWidget()
        t_layout = QVBoxLayout(tools_tab)
        t_layout.setContentsMargins(14, 14, 14, 14)
        t_layout.setSpacing(12)

        t_layout.addWidget(QLabel("Android Mobile Companion:"))
        btn_install = QPushButton("📲 Install & Launch APK on Connected Phone")
        btn_install.setStyleSheet(
            "background-color: #004A77; color: #C2E7FF; font-weight: bold; padding: 10px; border-radius: 6px;"
        )
        btn_install.clicked.connect(self.mw._on_install_apk_clicked)
        t_layout.addWidget(btn_install)

        t_layout.addWidget(self._make_divider())

        t_layout.addWidget(QLabel("Interactive Guides:"))
        btn_guide = QPushButton("📖 Open Step-by-Step Wireless Guide")
        btn_guide.setStyleSheet("background-color: #1E293B; color: #CBD5E1; padding: 8px;")
        btn_guide.clicked.connect(self.mw._open_wireless_guide)
        t_layout.addWidget(btn_guide)
        t_layout.addStretch()

        tabs.addTab(tools_tab, "🛠 Tools")

        layout.addWidget(tabs)

        # Bottom Close Row
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_done = QPushButton("Close")
        btn_done.setFixedWidth(90)
        btn_done.setStyleSheet("background-color: #27272A; color: #FFFFFF; font-weight: bold; padding: 6px 12px;")
        btn_done.clicked.connect(self.accept)
        bottom_row.addWidget(btn_done)
        layout.addLayout(bottom_row)

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #27272A; margin: 4px 0;")
        return line

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0D0F14;
                color: #F8FAFC;
            }
            QTabWidget::pane {
                border: 1px solid #1E293B;
                background-color: #13171F;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #0D0F14;
                color: #94A3B8;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #13171F;
                color: #38BDF8;
                border-bottom: 2px solid #38BDF8;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #090B0E;
                color: #F8FAFC;
                border: 1px solid #27272A;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                border-color: #64748B;
            }
            QLabel {
                color: #F8FAFC;
                font-size: 12px;
            }
        """)

    def _populate_audio_sources(self):
        self.source_combo.clear()
        devs = list_audio_devices("auto")
        if not devs:
            self.source_combo.addItem("Default Audio Loopback", "")
            return
        for d in devs:
            if "sonopipe" in d.id.lower():
                continue
            self.source_combo.addItem(d.name, d.id)

    def _set_preset(self, frames: int):
        self.mw._on_preset_changed(frames)
        self.btn_p10.setChecked(frames == 480)
        self.btn_p20.setChecked(frames == 960)
        self.btn_p40.setChecked(frames == 1920)

    def _on_autofind(self):
        self.mw._auto_find_and_connect()
        self.ip_input.setText(self.mw.wifi_ip_input.text())
        self.port_spin.setValue(self.mw.wifi_port_spin.value())

    def _on_connect(self):
        self.mw.wifi_ip_input.setText(self.ip_input.text())
        self.mw.wifi_port_spin.setValue(self.port_spin.value())
        self.mw._connect_wireless_adb()

    def _on_disconnect(self):
        self.mw._disconnect_wireless_adb()

    def _open_qr(self):
        dlg = WirelessQrDialog(self.adb, parent=self)
        dlg.exec()

    def _open_code(self):
        default_ip = self.ip_input.text().strip()
        dlg = WirelessPairDialog(self.adb, default_ip=default_ip, parent=self)
        dlg.exec()
