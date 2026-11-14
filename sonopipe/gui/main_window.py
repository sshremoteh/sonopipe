"""
Sonopipe v1.2.0 — Material Design 3 (MD3) Desktop GUI.
Features:
- USB & Wireless ADB (Wi-Fi) modes with one-click setup & pairing
- Built-in interactive Wireless Connection Guide
- Scrollable responsive layout (no clipping on any display/window size)
- MD3 Dark elevation surfaces and tokens
- Animated breathing live status badge
- Hardware-grade dual-channel stereo VU meter with peak hold decay
- MD3 Segmented latency buttons
- Fluid master volume slider with quick mute
- Instant telemetry tiles
- Settings persistence (QSettings)
"""

from __future__ import annotations
import math
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QSettings, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QBrush,
    QPen,
    QLinearGradient,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QSlider,
    QGroupBox,
    QFrame,
    QMessageBox,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QDialog,
    QStackedWidget,
)

from sonopipe.adb.manager import AdbManager
from sonopipe.adb.installer import install_and_launch
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT


class StreamerSignals(QObject):
    stats_updated = Signal(dict)
    error_occurred = Signal(str)


class ApkInstallWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, serial: Optional[str] = None):
        super().__init__()
        self.serial = serial

    def run(self):
        success, msg = install_and_launch(
            serial=self.serial,
            progress_cb=lambda text: self.progress.emit(text),
        )
        self.finished.emit(success, msg)


class WirelessGuideDialog(QDialog):
    """Interactive Material Design 3 Wireless ADB Guide Dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wireless ADB Connection Guide")
        self.resize(540, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F1116;
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QGroupBox {
                background-color: #171A21;
                border: 1px solid #262934;
                border-radius: 12px;
                margin-top: 10px;
                padding: 14px;
                font-weight: bold;
                color: #38BDF8;
                font-size: 13px;
            }
            QLabel {
                color: #CBD5E1;
                font-size: 12px;
                line-height: 1.4;
            }
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        h_lbl = QLabel("📶 How to connect via Wireless ADB")
        h_lbl.setFont(QFont("sans-serif", 15, QFont.Bold))
        h_lbl.setStyleSheet("color: #F8FAFC;")
        layout.addWidget(h_lbl)

        sub = QLabel("Stream sound to your phone wirelessly over the local Wi-Fi network without a USB cable.")
        sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(sub)

        # Method 1
        g1 = QGroupBox("Method 1: One-Click via USB Cable (Easiest & Recommended)")
        l1 = QVBoxLayout(g1)
        l1.setSpacing(6)
        l1.addWidget(QLabel("1. Connect your phone via USB cable with USB Debugging enabled."))
        l1.addWidget(QLabel("2. Ensure phone and PC are connected to the same Wi-Fi network."))
        l1.addWidget(QLabel("3. Click '⚡ Switch to Wi-Fi via USB' in the Wireless ADB tab."))
        l1.addWidget(QLabel("4. Once connected, unplug the USB cable! Audio will stream over Wi-Fi."))
        layout.addWidget(g1)

        # Method 2
        g2 = QGroupBox("Method 2: Android 11+ Wireless Debugging (No USB Cable)")
        l2 = QVBoxLayout(g2)
        l2.setSpacing(6)
        l2.addWidget(QLabel("1. On Phone: Settings → Developer options → enable Wireless debugging."))
        l2.addWidget(QLabel("2. Tap 'Pair device with pairing code'. Note the IP, Port and 6-digit code."))
        l2.addWidget(QLabel("3. In Sonopipe: Click '🔑 Pair Code (Android 11+)' and enter pairing info."))
        l2.addWidget(QLabel("4. Then enter the main Wireless debugging IP:Port and click 'Connect Wi-Fi'."))
        layout.addWidget(g2)

        # Method 3
        g3 = QGroupBox("Method 3: Terminal Commands")
        l3 = QVBoxLayout(g3)
        l3.setSpacing(4)
        cmd1 = QLabel("adb tcpip 5555")
        cmd1.setStyleSheet("background-color: #111318; padding: 6px; font-family: monospace; color: #38BDF8; border-radius: 4px;")
        cmd2 = QLabel("adb connect <PHONE_IP>:5555")
        cmd2.setStyleSheet("background-color: #111318; padding: 6px; font-family: monospace; color: #38BDF8; border-radius: 4px;")
        l3.addWidget(cmd1)
        l3.addWidget(cmd2)
        layout.addWidget(g3)

        layout.addStretch()

        btn_close = QPushButton("Got It")
        btn_close.setFixedHeight(38)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class WirelessPairDialog(QDialog):
    """Dialog to pair devices using Android 11+ Wireless Pairing Code."""

    def __init__(self, adb: AdbManager, default_ip: str = "", parent=None):
        super().__init__(parent)
        self.adb = adb
        self.setWindowTitle("Android 11+ Wireless Pairing")
        self.resize(420, 280)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F1116;
                color: #F8FAFC;
            }
            QLineEdit, QSpinBox {
                background-color: #20242D;
                color: #F8FAFC;
                border: 1px solid #333846;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl = QLabel("Enter the Pairing information shown on your phone's\n'Pair device with pairing code' screen:")
        lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(lbl)

        grid = QGridLayout()
        grid.addWidget(QLabel("IP Address:"), 0, 0)
        self.ip_input = QLineEdit(default_ip or "192.168.1.")
        grid.addWidget(self.ip_input, 0, 1)

        grid.addWidget(QLabel("Pairing Port:"), 1, 0)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(37000)
        grid.addWidget(self.port_spin, 1, 1)

        grid.addWidget(QLabel("6-Digit Code:"), 2, 0)
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. 123456")
        grid.addWidget(self.code_input, 2, 1)
        layout.addLayout(grid)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #262932; color: #94A3B8;")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_pair = QPushButton("Pair Device")
        btn_pair.clicked.connect(self._do_pair)
        btn_row.addWidget(btn_pair)
        layout.addLayout(btn_row)

    def _do_pair(self):
        host = self.ip_input.text().strip()
        port = self.port_spin.value()
        code = self.code_input.text().strip()
        if not host or not code:
            QMessageBox.warning(self, "Missing Data", "Please fill in IP address and 6-digit pairing code.")
            return

        ok, msg = self.adb.pair_wireless(host, port, code)
        if ok:
            QMessageBox.information(self, "Pairing Successful", f"Successfully paired with {host}:{port}!\n\nNow enter the main connection port and click Connect Wi-Fi.")
            self.accept()
        else:
            QMessageBox.warning(self, "Pairing Failed", f"Could not pair with device:\n\n{msg}")


class AnimatedStatusBadge(QWidget):
    """MD3 Animated Status Pill with breathing LED glow when streaming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setMinimumWidth(140)

        self._is_streaming = False
        self._glow_phase = 0.0
        self._text = "○ DISCONNECTED"

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(40)  # ~25 FPS
        self._anim_timer.timeout.connect(self._step_animation)

    def set_streaming(self, streaming: bool):
        self._is_streaming = streaming
        if streaming:
            self._text = "● LIVE STREAMING"
            self._glow_phase = 0.0
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._text = "○ DISCONNECTED"
            self._anim_timer.stop()
            self._glow_phase = 0.0
        self.update()

    def set_error(self, err_text: str = "✕ ERROR"):
        self._is_streaming = False
        self._anim_timer.stop()
        self._text = err_text
        self.update()

    def _step_animation(self):
        self._glow_phase = (self._glow_phase + 0.08) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0

        if self._is_streaming:
            pulse = 0.5 + 0.5 * math.sin(self._glow_phase)
            bg_color = QColor(6, 78, 59, 220)
            border_color = QColor(16, 185, 129, int(160 + pulse * 95))
            text_color = QColor("#34D399")
            dot_color = QColor(52, 211, 153, int(200 + pulse * 55))
        elif "ERROR" in self._text:
            bg_color = QColor(69, 10, 10, 220)
            border_color = QColor(239, 68, 68, 180)
            text_color = QColor("#FCA5A5")
            dot_color = QColor("#EF4444")
        else:
            bg_color = QColor(24, 26, 32, 220)
            border_color = QColor(43, 47, 58, 200)
            text_color = QColor("#94A3B8")
            dot_color = QColor("#64748B")

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)

        dot_x = 14
        dot_y = h / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(QRectF(dot_x - 3.5, dot_y - 3.5, 7, 7))

        clean_text = self._text.replace("● ", "").replace("○ ", "")
        painter.setFont(QFont("sans-serif", 10, QFont.Bold))
        painter.setPen(text_color)
        painter.drawText(QRectF(dot_x + 10, 0, w - dot_x - 14, h), Qt.AlignVCenter | Qt.AlignLeft, clean_text)


class StereoVuMeterWidget(QWidget):
    """
    MD3 Stereo Peak & RMS level meter with smooth physics,
    rounded segment styling, and dB-scale markings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(52)
        self.setMaximumHeight(58)

        self._l_rms = 0.0
        self._r_rms = 0.0
        self._l_peak = 0.0
        self._r_peak = 0.0

        self._l_peak_hold = 0.0
        self._r_peak_hold = 0.0

        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(30)
        self._decay_timer.timeout.connect(self._decay_peaks)
        self._decay_timer.start()

    def set_levels(self, l_rms: float, r_rms: float, l_peak: float, r_peak: float):
        self._l_rms = max(0.0, min(1.0, l_rms))
        self._r_rms = max(0.0, min(1.0, r_rms))
        self._l_peak = max(0.0, min(1.0, l_peak))
        self._r_peak = max(0.0, min(1.0, r_peak))

        if self._l_peak > self._l_peak_hold:
            self._l_peak_hold = self._l_peak
        if self._r_peak > self._r_peak_hold:
            self._r_peak_hold = self._r_peak

        self.update()

    def _decay_peaks(self):
        decay_step = 0.025
        changed = False

        if self._l_peak_hold > 0.0:
            self._l_peak_hold = max(0.0, self._l_peak_hold - decay_step)
            changed = True
        if self._r_peak_hold > 0.0:
            self._r_peak_hold = max(0.0, self._r_peak_hold - decay_step)
            changed = True

        if changed or self._l_rms > 0 or self._r_rms > 0:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        label_w = 20
        bar_x = label_w + 6
        bar_w = max(50, w - bar_x - 10)
        bar_h = 11
        gap = 7

        db_y = 11
        painter.setFont(QFont("monospace", 8))
        painter.setPen(QColor("#64748B"))
        scale_points = [
            (-36, 0.20),
            (-24, 0.40),
            (-12, 0.65),
            (-6, 0.82),
            (0, 1.0),
        ]
        for db_val, frac in scale_points:
            x_pos = int(bar_x + frac * bar_w)
            txt = f"{db_val}dB" if db_val != 0 else "0dB"
            painter.drawText(x_pos - 12, db_y, txt)

        l_y = 17
        self._draw_bar(painter, "L", bar_x, l_y, bar_w, bar_h, self._l_rms, self._l_peak_hold)

        r_y = l_y + bar_h + gap
        self._draw_bar(painter, "R", bar_x, r_y, bar_w, bar_h, self._r_rms, self._r_peak_hold)

    def _draw_bar(self, painter: QPainter, label: str, x: int, y: int, w: int, h: int, rms: float, peak_hold: float):
        painter.setFont(QFont("sans-serif", 9, QFont.Bold))
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(2, y + h - 1, label)

        painter.setBrush(QBrush(QColor("#161820")))
        painter.setPen(QPen(QColor("#272A34"), 1))
        painter.drawRoundedRect(QRectF(x, y, w, h), 4, 4)

        fill_w = int(w * rms)
        if fill_w > 0:
            grad = QLinearGradient(x, y, x + w, y)
            grad.setColorAt(0.0, QColor("#10B981"))
            grad.setColorAt(0.60, QColor("#38BDF8"))
            grad.setColorAt(0.82, QColor("#F59E0B"))
            grad.setColorAt(0.96, QColor("#EF4444"))

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x + 1, y + 1, max(2, fill_w - 2), h - 2), 3, 3)

        if peak_hold > 0.02:
            pk_x = min(x + w - 2, int(x + peak_hold * w))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawLine(pk_x, y, pk_x, y + h - 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonopipe v1.2.0 — PC Audio to Android Speaker")
        self.resize(540, 750)
        self.setMinimumSize(440, 480)

        self.adb = AdbManager()
        self.streamer: Optional[AudioStreamer] = None
        self.signals = StreamerSignals()
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.error_occurred.connect(self._on_error_occurred)

        self.settings = QSettings("Sonopipe", "Sonopipe")

        self.chunk_frames = 960
        self.is_muted = False
        self.saved_volume = 100

        self._init_ui()
        self._apply_theme()
        self._load_saved_settings()
        self.refresh_devices()

    def _init_ui(self):
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll_area)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)

        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        # 1. HEADER (MD3 Top App Bar)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title_lbl = QLabel("Sonopipe")
        title_lbl.setFont(QFont("sans-serif", 19, QFont.Bold))
        title_lbl.setStyleSheet("color: #F8FAFC; letter-spacing: -0.5px;")
        title_row.addWidget(title_lbl)

        ver_badge = QLabel("v1.2.0")
        ver_badge.setStyleSheet(
            "background-color: #172554; color: #60A5FA; font-size: 11px; "
            "font-weight: bold; padding: 2px 8px; border-radius: 9px; border: 1px solid #1D4ED8;"
        )
        title_row.addWidget(ver_badge)
        title_row.addStretch()
        brand_col.addLayout(title_row)

        sub_lbl = QLabel("Lossless low-latency sound over USB & Wireless ADB")
        sub_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        brand_col.addWidget(sub_lbl)
        header_row.addLayout(brand_col)

        header_row.addStretch()

        self.status_badge = AnimatedStatusBadge()
        header_row.addWidget(self.status_badge)
        main_layout.addLayout(header_row)

        # 2. CARD: ANDROID CONNECTION (USB & WIRELESS ADB)
        conn_card = self._create_card("📱  Android Connection (USB / Wireless Wi-Fi)")
        conn_layout = QVBoxLayout(conn_card)
        conn_layout.setContentsMargins(14, 14, 14, 14)
        conn_layout.setSpacing(12)

        # Transport Segmented Mode Selector
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self.btn_mode_usb = QPushButton("🔌  USB Cable")
        self.btn_mode_usb.setCheckable(True)
        self.btn_mode_usb.setChecked(True)
        mode_row.addWidget(self.btn_mode_usb)

        self.btn_mode_wifi = QPushButton("📶  Wireless ADB (Wi-Fi)")
        self.btn_mode_wifi.setCheckable(True)
        mode_row.addWidget(self.btn_mode_wifi)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self.btn_mode_usb)
        mode_group.addButton(self.btn_mode_wifi)
        self.btn_mode_usb.clicked.connect(lambda: self.conn_stack.setCurrentIndex(0))
        self.btn_mode_wifi.clicked.connect(lambda: self.conn_stack.setCurrentIndex(1))

        conn_layout.addLayout(mode_row)

        # Stacked Panel for USB vs Wireless controls
        self.conn_stack = QStackedWidget()

        # --- SUB-PANEL 0: USB MODE ---
        usb_widget = QWidget()
        usb_grid = QGridLayout(usb_widget)
        usb_grid.setContentsMargins(0, 4, 0, 0)
        usb_grid.setSpacing(8)

        usb_grid.addWidget(self._make_field_label("Connected Device:"), 0, 0)
        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        usb_grid.addWidget(self.device_combo, 0, 1)

        self.btn_refresh_devices = QPushButton("↻ Refresh")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        usb_grid.addWidget(self.btn_refresh_devices, 0, 2)

        # Helper to convert USB connection to Wireless in 1 click
        self.btn_usb_to_wifi = QPushButton("⚡ Switch to Wi-Fi via USB (Auto-Setup)")
        self.btn_usb_to_wifi.setToolTip("Auto-detect phone's Wi-Fi IP, enable TCP/IP port 5555, and connect wirelessly")
        self.btn_usb_to_wifi.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; border: 1px solid #0284C7; font-weight: bold; padding: 6px;"
        )
        self.btn_usb_to_wifi.clicked.connect(self._auto_switch_usb_to_wifi)
        usb_grid.addWidget(self.btn_usb_to_wifi, 1, 0, 1, 3)

        self.conn_stack.addWidget(usb_widget)

        # --- SUB-PANEL 1: WIRELESS ADB MODE ---
        wifi_widget = QWidget()
        wifi_grid = QGridLayout(wifi_widget)
        wifi_grid.setContentsMargins(0, 4, 0, 0)
        wifi_grid.setSpacing(8)

        wifi_grid.addWidget(self._make_field_label("Phone Wi-Fi IP:"), 0, 0)
        self.wifi_ip_input = QLineEdit()
        self.wifi_ip_input.setPlaceholderText("e.g. 192.168.1.50")
        wifi_grid.addWidget(self.wifi_ip_input, 0, 1)

        wifi_grid.addWidget(self._make_field_label("Port:"), 0, 2)
        self.wifi_port_spin = QSpinBox()
        self.wifi_port_spin.setRange(1024, 65535)
        self.wifi_port_spin.setValue(5555)
        self.wifi_port_spin.setFixedWidth(75)
        wifi_grid.addWidget(self.wifi_port_spin, 0, 3)

        btn_wifi_row = QHBoxLayout()
        btn_wifi_row.setSpacing(6)

        self.btn_wifi_connect = QPushButton("📶 Connect Wi-Fi")
        self.btn_wifi_connect.setStyleSheet("background-color: #065F46; color: #6EE7B7; font-weight: bold;")
        self.btn_wifi_connect.clicked.connect(self._connect_wireless_adb)
        btn_wifi_row.addWidget(self.btn_wifi_connect)

        self.btn_wifi_disconnect = QPushButton("Disconnect")
        self.btn_wifi_disconnect.clicked.connect(self._disconnect_wireless_adb)
        btn_wifi_row.addWidget(self.btn_wifi_disconnect)

        self.btn_wifi_pair = QPushButton("🔑 Pair (Android 11+)")
        self.btn_wifi_pair.setToolTip("Pair with phone using 6-digit wireless pairing code")
        self.btn_wifi_pair.clicked.connect(self._open_pair_dialog)
        btn_wifi_row.addWidget(self.btn_wifi_pair)

        self.btn_wifi_guide = QPushButton("📖 Guide")
        self.btn_wifi_guide.setToolTip("Step-by-step wireless connection instructions")
        self.btn_wifi_guide.clicked.connect(self._open_wireless_guide)
        btn_wifi_row.addWidget(self.btn_wifi_guide)

        wifi_grid.addLayout(btn_wifi_row, 1, 0, 1, 4)

        self.conn_stack.addWidget(wifi_widget)
        conn_layout.addWidget(self.conn_stack)

        # Port & Quick Commands (Common to both modes)
        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_row.addWidget(self._make_field_label("Audio Stream Port:"))

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        self.port_spin.setFixedWidth(85)
        port_row.addWidget(self.port_spin)

        self.btn_copy_cmd = QPushButton("📋 Copy Forward Command")
        self.btn_copy_cmd.setToolTip("Copy 'adb forward tcp:PORT tcp:PORT' to clipboard")
        self.btn_copy_cmd.clicked.connect(self._copy_forward_command)
        port_row.addWidget(self.btn_copy_cmd)
        port_row.addStretch()

        conn_layout.addLayout(port_row)

        # APK Install Button
        self.btn_install_apk = QPushButton("📲  Install & Launch APK on Phone")
        self.btn_install_apk.setToolTip("Install the mobile receiver app directly via ADB")
        self.btn_install_apk.setStyleSheet(
            "background-color: #004A77; color: #C2E7FF; border: 1px solid #0284C7; "
            "font-weight: bold; padding: 8px; border-radius: 8px; font-size: 13px;"
        )
        self.btn_install_apk.clicked.connect(self._on_install_apk_clicked)
        conn_layout.addWidget(self.btn_install_apk)

        main_layout.addWidget(conn_card)

        # 3. CARD: AUDIO CAPTURE ENGINE
        audio_card = self._create_card("🔊  System Audio Engine")
        audio_layout = QGridLayout(audio_card)
        audio_layout.setContentsMargins(14, 14, 14, 14)
        audio_layout.setSpacing(10)

        audio_layout.addWidget(self._make_field_label("Audio Source:"), 0, 0)
        self.source_combo = QComboBox()
        self.source_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        audio_layout.addWidget(self.source_combo, 0, 1)

        self.btn_refresh_sources = QPushButton("↻ Refresh")
        self.btn_refresh_sources.clicked.connect(self.refresh_audio_sources)
        audio_layout.addWidget(self.btn_refresh_sources, 0, 2)

        audio_layout.addWidget(self._make_field_label("Capture Backend:"), 1, 0)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Auto (Recommended)", "PipeWire / PulseAudio", "WASAPI (Windows)", "Soundcard"])
        def_idx = 1 if get_default_backend_name() == "pulse" else (2 if get_default_backend_name() == "wasapi" else 0)
        self.backend_combo.setCurrentIndex(def_idx)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        audio_layout.addWidget(self.backend_combo, 1, 1, 1, 2)

        # MD3 Segmented Latency Presets
        audio_layout.addWidget(self._make_field_label("Latency Mode:"), 2, 0)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)

        self.preset_group = QButtonGroup(self)

        self.btn_p10 = QPushButton("⚡ Low (10ms)")
        self.btn_p10.setCheckable(True)
        self.preset_group.addButton(self.btn_p10, 480)
        preset_row.addWidget(self.btn_p10)

        self.btn_p20 = QPushButton("⚖ Balanced (20ms)")
        self.btn_p20.setCheckable(True)
        self.btn_p20.setChecked(True)
        self.preset_group.addButton(self.btn_p20, 960)
        preset_row.addWidget(self.btn_p20)

        self.btn_p40 = QPushButton("🛡 Reliable (40ms)")
        self.btn_p40.setCheckable(True)
        self.preset_group.addButton(self.btn_p40, 1920)
        preset_row.addWidget(self.btn_p40)

        self.preset_group.idClicked.connect(self._on_preset_changed)
        audio_layout.addLayout(preset_row, 2, 1, 1, 2)

        main_layout.addWidget(audio_card)

        # 4. CARD: OUTPUT VOLUME & STEREO VU METER
        vol_card = self._create_card("🎚  Master Output & Stereo Levels")
        vol_layout = QVBoxLayout(vol_card)
        vol_layout.setContentsMargins(14, 14, 14, 14)
        vol_layout.setSpacing(10)

        vol_row = QHBoxLayout()
        vol_row.setSpacing(10)

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedSize(36, 32)
        self.btn_mute.setToolTip("Toggle Mute")
        self.btn_mute.clicked.connect(self._toggle_mute)
        vol_row.addWidget(self.btn_mute)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self.vol_slider)

        self.lbl_volume = QLabel("100%")
        self.lbl_volume.setFixedWidth(48)
        self.lbl_volume.setFont(QFont("monospace", 10, QFont.Bold))
        self.lbl_volume.setStyleSheet("color: #F8FAFC;")
        vol_row.addWidget(self.lbl_volume)

        vol_layout.addLayout(vol_row)

        self.meter_widget = StereoVuMeterWidget()
        vol_layout.addWidget(self.meter_widget)

        main_layout.addWidget(vol_card)

        # 5. CARD: LIVE TELEMETRY TILES
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet(
            "background-color: #14171E; border: 1px solid #232732; border-radius: 10px;"
        )
        t_layout = QGridLayout(telemetry_frame)
        t_layout.setContentsMargins(12, 10, 12, 10)
        t_layout.setSpacing(10)

        def make_tile(title_text: str, val_text: str, color: str = "#F8FAFC"):
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            lbl = QLabel(title_text)
            lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold;")
            val = QLabel(val_text)
            val.setFont(QFont("monospace", 12, QFont.Bold))
            val.setStyleSheet(f"color: {color};")
            vl.addWidget(lbl)
            vl.addWidget(val)
            return w, val

        t1, self.lbl_rate = make_tile("THROUGHPUT", "0.0 KB/s", "#38BDF8")
        t2, self.lbl_total = make_tile("TRANSFERRED", "0.0 MB", "#F8FAFC")
        t3, self.lbl_uptime = make_tile("SESSION TIME", "00:00", "#F8FAFC")
        t4, self.lbl_delay = make_tile("EST. DELAY", "~20 ms", "#10B981")

        t_layout.addWidget(t1, 0, 0)
        t_layout.addWidget(t2, 0, 1)
        t_layout.addWidget(t3, 0, 2)
        t_layout.addWidget(t4, 0, 3)

        main_layout.addWidget(telemetry_frame)

        # 6. ACTION BUTTON (START / STOP STREAMING) - Stadium Capsule
        self.btn_toggle = QPushButton("▶   START STREAMING")
        self.btn_toggle.setFixedHeight(54)
        self.btn_toggle.setFont(QFont("sans-serif", 14, QFont.Bold))
        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 27px; "
            "font-weight: bold; border: none; letter-spacing: 0.5px;"
        )
        self.btn_toggle.clicked.connect(self.toggle_streaming)
        main_layout.addWidget(self.btn_toggle)

    def _create_card(self, title: str) -> QGroupBox:
        card = QGroupBox(title)
        card.setStyleSheet(
            "QGroupBox {"
            "  background-color: #171A21;"
            "  border: 1px solid #262934;"
            "  border-radius: 12px;"
            "  margin-top: 10px;"
            "  padding-top: 14px;"
            "  font-weight: 600;"
            "  color: #94A3B8;"
            "  font-size: 12px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  left: 14px;"
            "  padding: 0 4px;"
            "}"
        )
        return card

    def _make_field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        return lbl

    def _apply_theme(self):
        style = """
        QMainWindow, QWidget {
            background-color: #0F1116;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }
        QScrollArea {
            background-color: transparent;
            border: none;
        }
        QScrollBar:vertical {
            background: #12141A;
            width: 8px;
            margin: 0;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #2D323E;
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #3B82F6;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QComboBox, QSpinBox, QLineEdit {
            background-color: #20242D;
            color: #F8FAFC;
            border: 1px solid #333846;
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 22px;
        }
        QComboBox:hover, QSpinBox:hover, QLineEdit:hover {
            border-color: #4B5563;
        }
        QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
            border-color: #3B82F6;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton {
            background-color: #232732;
            color: #F8FAFC;
            border: 1px solid #353A47;
            border-radius: 8px;
            padding: 7px 12px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #2D3240;
            border-color: #475062;
        }
        QPushButton:pressed {
            background-color: #1A1D25;
        }
        QPushButton:checked {
            background-color: #1E3A8A;
            color: #93C5FD;
            border: 1px solid #3B82F6;
            font-weight: bold;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #222631;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #3B82F6;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #FFFFFF;
            width: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }
        QSlider::handle:horizontal:hover {
            background: #60A5FA;
        }
        """
        self.setStyleSheet(style)

    def _load_saved_settings(self):
        saved_port = self.settings.value("port", DEFAULT_PORT, type=int)
        self.port_spin.setValue(saved_port)

        saved_vol = self.settings.value("volume", 100, type=int)
        self.vol_slider.setValue(saved_vol)
        self._on_volume_changed(saved_vol)

        saved_ip = self.settings.value("wifi_ip", "", type=str)
        if saved_ip:
            self.wifi_ip_input.setText(saved_ip)

        saved_preset = self.settings.value("preset", 960, type=int)
        if saved_preset == 480:
            self.btn_p10.setChecked(True)
            self._on_preset_changed(480)
        elif saved_preset == 1920:
            self.btn_p40.setChecked(True)
            self._on_preset_changed(1920)
        else:
            self.btn_p20.setChecked(True)
            self._on_preset_changed(960)

    def _save_settings(self):
        self.settings.setValue("port", self.port_spin.value())
        self.settings.setValue("volume", self.vol_slider.value())
        self.settings.setValue("preset", self.chunk_frames)
        self.settings.setValue("wifi_ip", self.wifi_ip_input.text().strip())

    def refresh_devices(self):
        self.device_combo.clear()
        if not self.adb.is_available():
            self.device_combo.addItem("⚠ ADB not found in PATH", "")
            return

        devices = self.adb.list_devices()
        if not devices:
            self.device_combo.addItem("○ No devices connected (USB or Wi-Fi)", "")
            return

        for dev in devices:
            is_wifi = ":" in dev.serial
            tag = " [Wi-Fi]" if is_wifi else " [USB]"
            name = dev.model or ("Wireless Device" if is_wifi else "Android Device")
            label = f"{name}{tag} ({dev.serial})"
            self.device_combo.addItem(label, dev.serial)

        self.refresh_audio_sources()

    def refresh_audio_sources(self):
        self.source_combo.clear()
        backend_idx = self.backend_combo.currentIndex()
        backend_name = "auto"
        if backend_idx == 1:
            backend_name = "pulse"
        elif backend_idx == 2:
            backend_name = "wasapi"
        elif backend_idx == 3:
            backend_name = "soundcard"

        devices = list_audio_devices(backend_name)
        if not devices:
            self.source_combo.addItem("Default Audio Loopback", "")
            return

        for dev in devices:
            self.source_combo.addItem(str(dev), dev.id)

    def _on_backend_changed(self):
        self.refresh_audio_sources()

    def _on_preset_changed(self, preset_id: int):
        self.chunk_frames = preset_id
        if preset_id == 480:
            self.lbl_delay.setText("~10 ms")
            self.lbl_delay.setStyleSheet("color: #38BDF8;")
        elif preset_id == 1920:
            self.lbl_delay.setText("~40 ms")
            self.lbl_delay.setStyleSheet("color: #F59E0B;")
        else:
            self.lbl_delay.setText("~20 ms")
            self.lbl_delay.setStyleSheet("color: #10B981;")

    def _toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            self.btn_mute.setText("🔊")
            self.vol_slider.setValue(self.saved_volume)
        else:
            self.is_muted = True
            self.saved_volume = self.vol_slider.value()
            self.btn_mute.setText("🔇")
            self.vol_slider.setValue(0)

    def _on_volume_changed(self, value: int):
        self.lbl_volume.setText(f"{value}%")
        if value > 100:
            self.lbl_volume.setStyleSheet("color: #F59E0B; font-weight: bold;")
        else:
            self.lbl_volume.setStyleSheet("color: #F8FAFC; font-weight: bold;")

        if value > 0 and self.is_muted:
            self.is_muted = False
            self.btn_mute.setText("🔊")

        if self.streamer:
            self.streamer.set_volume(value / 100.0)

    def _copy_forward_command(self):
        port = self.port_spin.value()
        cmd = f"adb forward tcp:{port} tcp:{port}"
        QApplication.clipboard().setText(cmd)
        self.btn_copy_cmd.setText("✓ Copied!")
        QTimer.singleShot(1500, lambda: self.btn_copy_cmd.setText("📋 Copy Forward Command"))

    # Wireless ADB Handlers
    def _auto_switch_usb_to_wifi(self):
        devices = self.adb.list_devices()
        usb_devices = [d for d in devices if ":" not in d.serial and d.state == "device"]
        if not usb_devices:
            QMessageBox.warning(
                self,
                "No USB Device",
                "Please connect your Android phone via USB cable first.\n\n"
                "Once plugged in, this button will automatically switch it to Wireless ADB."
            )
            return

        target_serial = usb_devices[0].serial
        ip = self.adb.get_device_wlan_ip(target_serial)
        if not ip:
            QMessageBox.warning(
                self,
                "Wi-Fi IP Not Found",
                "Could not auto-detect the phone's Wi-Fi IP address.\n\n"
                "Please ensure the phone is connected to Wi-Fi, or switch to the 'Wireless ADB' tab and enter the IP manually."
            )
            return

        ok_tcp, out_tcp = self.adb.enable_tcpip(5555, serial=target_serial)
        if not ok_tcp:
            QMessageBox.critical(self, "Error", f"Failed to enable TCP/IP mode:\n\n{out_tcp}")
            return

        ok_conn, out_conn = self.adb.connect_wireless(ip, 5555)
        if ok_conn:
            self.wifi_ip_input.setText(ip)
            self._save_settings()
            self.refresh_devices()
            QMessageBox.information(
                self,
                "Wireless ADB Connected!",
                f"🎉 Successfully connected to phone wirelessly at {ip}:5555!\n\n"
                f"You can now UNPLUG the USB cable. Audio streaming will work seamlessly over Wi-Fi."
            )
            self.btn_mode_wifi.setChecked(True)
            self.conn_stack.setCurrentIndex(1)
        else:
            QMessageBox.warning(self, "Connection Failed", f"Enabled TCP/IP on phone, but failed to connect to {ip}:5555:\n\n{out_conn}")

    def _connect_wireless_adb(self):
        ip = self.wifi_ip_input.text().strip()
        port = self.wifi_port_spin.value()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter your phone's Wi-Fi IP address.")
            return

        self._save_settings()
        ok, msg = self.adb.connect_wireless(ip, port)
        if ok:
            self.refresh_devices()
            QMessageBox.information(self, "Connected", f"Connected wirelessly to {ip}:{port}!")
        else:
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {ip}:{port}:\n\n{msg}\n\nMake sure Wireless Debugging is on or click 'Guide' for help.")

    def _disconnect_wireless_adb(self):
        ip = self.wifi_ip_input.text().strip()
        port = self.wifi_port_spin.value()
        target = f"{ip}:{port}" if ip else None
        ok, msg = self.adb.disconnect_wireless(target)
        self.refresh_devices()
        QMessageBox.information(self, "Disconnected", f"Wireless device disconnected: {msg}")

    def _open_pair_dialog(self):
        default_ip = self.wifi_ip_input.text().strip()
        dlg = WirelessPairDialog(self.adb, default_ip=default_ip, parent=self)
        dlg.exec()

    def _open_wireless_guide(self):
        dlg = WirelessGuideDialog(self)
        dlg.exec()

    def _on_install_apk_clicked(self):
        selected_serial = self.device_combo.currentData() or None
        if not self.adb.is_available():
            QMessageBox.critical(self, "ADB Error", "ADB executable was not found in PATH.")
            return

        self.btn_install_apk.setEnabled(False)
        self.btn_install_apk.setText("⏳ Installing APK to Phone...")

        self._install_worker = ApkInstallWorker(serial=selected_serial)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.start()

    def _on_install_finished(self, success: bool, msg: str):
        self.btn_install_apk.setEnabled(True)
        self.btn_install_apk.setText("📲  Install & Launch APK on Phone")
        if success:
            QMessageBox.information(self, "Installation Succeeded", msg)
        else:
            QMessageBox.warning(self, "Installation", msg)

    def toggle_streaming(self):
        if self.streamer and self.streamer.is_running:
            self.stop_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        port = self.port_spin.value()
        selected_serial = self.device_combo.currentData() or None

        if self.adb.is_available():
            forward_ok = self.adb.forward_port(local_port=port, remote_port=port, serial=selected_serial)
            if not forward_ok:
                ans = QMessageBox.question(
                    self,
                    "ADB Forward Notice",
                    f"Could not automatically execute 'adb forward tcp:{port} tcp:{port}'.\n\n"
                    f"Ensure device is connected and authorized.\n\n"
                    f"Do you want to continue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    return

        backend_idx = self.backend_combo.currentIndex()
        backend_name = None
        if backend_idx == 1:
            backend_name = "pulse"
        elif backend_idx == 2:
            backend_name = "wasapi"
        elif backend_idx == 3:
            backend_name = "soundcard"

        audio_dev_id = self.source_combo.currentData() or None
        sample_rate = 48000
        channels = 2
        vol = self.vol_slider.value() / 100.0

        self.streamer = AudioStreamer(
            host="127.0.0.1",
            port=port,
            sample_rate=sample_rate,
            channels=channels,
            chunk_frames=self.chunk_frames,
            volume=vol,
            backend=backend_name,
            audio_device_id=audio_dev_id,
            on_stats_update=lambda stats: self.signals.stats_updated.emit(stats),
            on_error=lambda err: self.signals.error_occurred.emit(err),
        )

        try:
            self.streamer.start()
        except Exception as e:
            QMessageBox.critical(self, "Streaming Error", f"Failed to start stream: {e}")
            self.stop_streaming()
            return

        self._save_settings()

        self.status_badge.set_streaming(True)
        self.btn_toggle.setText("■   STOP STREAMING")
        self.btn_toggle.setStyleSheet(
            "background-color: #DC2626; color: #FFFFFF; border-radius: 27px; "
            "font-weight: bold; border: none; letter-spacing: 0.5px;"
        )
        self._set_controls_enabled(False)

    def stop_streaming(self):
        if self.streamer:
            self.streamer.stop()
            self.streamer = None

        self.meter_widget.set_levels(0.0, 0.0, 0.0, 0.0)
        self.status_badge.set_streaming(False)
        self.btn_toggle.setText("▶   START STREAMING")
        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 27px; "
            "font-weight: bold; border: none; letter-spacing: 0.5px;"
        )
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool):
        self.device_combo.setEnabled(enabled)
        self.btn_refresh_devices.setEnabled(enabled)
        self.btn_mode_usb.setEnabled(enabled)
        self.btn_mode_wifi.setEnabled(enabled)
        self.btn_usb_to_wifi.setEnabled(enabled)
        self.btn_wifi_connect.setEnabled(enabled)
        self.btn_wifi_disconnect.setEnabled(enabled)
        self.btn_wifi_pair.setEnabled(enabled)
        self.port_spin.setEnabled(enabled)
        self.backend_combo.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.btn_refresh_sources.setEnabled(enabled)
        self.btn_p10.setEnabled(enabled)
        self.btn_p20.setEnabled(enabled)
        self.btn_p40.setEnabled(enabled)

    def _on_stats_updated(self, stats: dict):
        mb = stats.get("bytes_sent", 0) / (1024.0 * 1024.0)
        self.lbl_total.setText(f"{mb:.1f} MB")

        rate = stats.get("kb_per_sec", 0.0)
        self.lbl_rate.setText(f"{rate:.1f} KB/s")

        uptime = int(stats.get("uptime", 0))
        mins, secs = divmod(uptime, 60)
        self.lbl_uptime.setText(f"{mins:02d}:{secs:02d}")

        l_rms = stats.get("left_rms", stats.get("rms_level", 0.0))
        r_rms = stats.get("right_rms", stats.get("rms_level", 0.0))
        l_peak = stats.get("left_peak", stats.get("peak_level", 0.0))
        r_peak = stats.get("right_peak", stats.get("peak_level", 0.0))

        self.meter_widget.set_levels(l_rms, r_rms, l_peak, r_peak)

    def _on_error_occurred(self, err_msg: str):
        self.stop_streaming()
        self.status_badge.set_error()
        QMessageBox.warning(
            self,
            "Stream Interrupted",
            f"Audio transmission stopped:\n\n{err_msg}\n\n"
            f"Check if Sonopipe app is running on your phone."
        )

    def closeEvent(self, event):
        self._save_settings()
        self.stop_streaming()
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
