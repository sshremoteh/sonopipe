"""
Sonopipe v1.4.0 — Minimalist Studio Desktop GUI.
Designed with anti-slop design principles: clean, focused, purposeful, zero clutter.
"""

from __future__ import annotations
import math
import os
import sys
from typing import Optional

# Suppress noisy Qt Wayland client warnings on Hyprland/Wayland compositors
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland*=false")

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QSettings, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QBrush,
    QPen,
    QLinearGradient,
    QIcon,
    QPixmap,
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
    QFrame,
    QMessageBox,
    QButtonGroup,
    QSizePolicy,
    QDialog,
    QSystemTrayIcon,
    QMenu,
)

from sonopipe.adb.manager import AdbManager
from sonopipe.adb.installer import install_and_launch
from sonopipe.adb.qr_dialog import WirelessQrDialog, WirelessPairDialog
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT
from sonopipe.mic.receiver import MicReceiver, DEFAULT_MIC_PORT
from sonopipe.mic.tester import LocalMicTester
from sonopipe.gui.settings_dialog import SettingsDialog


MODE_SPEAKER = "speaker"
MODE_MIC = "mic"
MODE_DUPLEX = "duplex"


class StreamerSignals(QObject):
    stats_updated = Signal(dict)
    mic_stats_updated = Signal(dict)
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


class MinimalLedMeter(QWidget):
    """
    Sleek, low-profile LED level bar widget with peak hold decay.
    Clean 6px height with smooth gradient (emerald -> amber -> rose).
    """

    def __init__(self, parent=None, is_stereo: bool = False):
        super().__init__(parent)
        self.is_stereo = is_stereo
        self.setFixedHeight(14 if is_stereo else 8)

        self._l_rms = 0.0
        self._r_rms = 0.0
        self._l_peak = 0.0
        self._r_peak = 0.0

        self._l_hold = 0.0
        self._r_hold = 0.0

        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(30)
        self._decay_timer.timeout.connect(self._decay)
        self._decay_timer.start()

    def set_levels(self, l_rms: float, r_rms: float = 0.0, l_peak: float = 0.0, r_peak: float = 0.0):
        self._l_rms = max(0.0, min(1.0, l_rms))
        self._r_rms = max(0.0, min(1.0, r_rms))
        self._l_peak = max(0.0, min(1.0, l_peak))
        self._r_peak = max(0.0, min(1.0, r_peak))

        if self._l_peak > self._l_hold:
            self._l_hold = self._l_peak
        if self._r_peak > self._r_hold:
            self._r_hold = self._r_peak

        self.update()

    def _decay(self):
        decay = 0.03
        changed = False
        if self._l_hold > 0.0:
            self._l_hold = max(0.0, self._l_hold - decay)
            changed = True
        if self._r_hold > 0.0:
            self._r_hold = max(0.0, self._r_hold - decay)
            changed = True

        if changed or self._l_rms > 0 or self._r_rms > 0:
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        track_bg = QColor("#191C24")

        def draw_bar(y_pos: float, h_bar: float, rms_val: float, hold_val: float):
            # Background track
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(track_bg))
            p.drawRoundedRect(QRectF(0, y_pos, w, h_bar), h_bar / 2, h_bar / 2)

            fill_w = max(0.0, min(w, w * rms_val))
            if fill_w > 1.0:
                grad = QLinearGradient(0, 0, w, 0)
                grad.setColorAt(0.0, QColor("#10B981"))
                grad.setColorAt(0.7, QColor("#F59E0B"))
                grad.setColorAt(0.95, QColor("#EF4444"))
                p.setBrush(QBrush(grad))
                p.drawRoundedRect(QRectF(0, y_pos, fill_w, h_bar), h_bar / 2, h_bar / 2)

            # Peak hold dot
            if hold_val > 0.02:
                dot_x = max(2.0, min(w - 3.0, w * hold_val))
                p.setBrush(QBrush(QColor("#FFFFFF")))
                p.drawEllipse(QRectF(dot_x - 1.5, y_pos, 3.0, h_bar))

        if self.is_stereo:
            draw_bar(0, 5, self._l_rms, self._l_hold)
            draw_bar(7, 5, self._r_rms, self._r_hold)
        else:
            draw_bar(1, 6, self._l_rms, self._l_hold)


class MainWindow(QMainWindow):
    """Refined minimalist studio interface for Sonopipe."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonopipe — Audio & Mic over ADB")
        self.setFixedSize(450, 560)

        self.adb = AdbManager()
        self.streamer: Optional[AudioStreamer] = None
        self.mic_receiver: Optional[MicReceiver] = None

        self.signals = StreamerSignals()
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.mic_stats_updated.connect(self._on_mic_stats_updated)
        self.signals.error_occurred.connect(self._on_error_occurred)

        self.settings = QSettings("Sonopipe", "Sonopipe")

        self.current_mode = MODE_SPEAKER
        self.chunk_frames = 960
        self.is_muted = False
        self.is_mic_muted = False
        self.saved_volume = 100
        self.saved_mic_gain = 100

        self.mic_tester = LocalMicTester()
        self.mic_test_timer = QTimer(self)
        self.mic_test_timer.setInterval(1000)
        self.mic_test_countdown = 5
        self.mic_test_timer.timeout.connect(self._on_mic_test_tick)

        self.tray_icon: Optional[QSystemTrayIcon] = None

        # Hidden background widgets for settings persistence & dialog synchronization
        self.wifi_ip_input = QLineEdit()
        self.wifi_port_spin = QSpinBox()
        self.wifi_port_spin.setRange(1024, 65535)
        self.wifi_port_spin.setValue(5555)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(DEFAULT_PORT)

        self.mic_port_spin = QSpinBox()
        self.mic_port_spin.setRange(1024, 65535)
        self.mic_port_spin.setValue(DEFAULT_MIC_PORT)

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Auto", "Pulse", "WASAPI", "Soundcard"])
        self.source_combo = QComboBox()

        self._init_ui()
        self._apply_theme()
        self._load_saved_settings()
        self._init_tray_icon()
        self.refresh_devices()

    def _init_ui(self):
        container = QWidget(self)
        self.setCentralWidget(container)

        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(14)

        # 1. TOP BAR: Title & Status + Settings
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        # Pulse indicator dot
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("sans-serif", 12))
        self.status_dot.setStyleSheet("color: #64748B;")
        top_bar.addWidget(self.status_dot)

        app_title = QLabel("Sonopipe")
        app_title.setFont(QFont("sans-serif", 15, QFont.Bold))
        app_title.setStyleSheet("color: #F8FAFC; letter-spacing: -0.3px;")
        top_bar.addWidget(app_title)

        ver_badge = QLabel("v1.4.0")
        ver_badge.setFont(QFont("sans-serif", 9, QFont.Bold))
        ver_badge.setStyleSheet("color: #64748B; background-color: #171A21; padding: 2px 6px; border-radius: 4px;")
        top_bar.addWidget(ver_badge)

        top_bar.addStretch()

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(34, 30)
        self.btn_settings.setToolTip("Advanced Settings (Wi-Fi, Latency, APK, Ports)")
        self.btn_settings.setStyleSheet(
            "background-color: #161A22; color: #94A3B8; border: 1px solid #222634; border-radius: 6px; font-size: 14px;"
        )
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        top_bar.addWidget(self.btn_settings)

        root_layout.addLayout(top_bar)

        # 2. CARD: TARGET DEVICE
        dev_card = QFrame()
        dev_card.setStyleSheet("background-color: #13161F; border: 1px solid #1E2330; border-radius: 12px;")
        dev_layout = QHBoxLayout(dev_card)
        dev_layout.setContentsMargins(12, 10, 12, 10)
        dev_layout.setSpacing(10)

        phone_icon = QLabel("📱")
        phone_icon.setFont(QFont("sans-serif", 16))
        dev_layout.addWidget(phone_icon)

        dev_col = QVBoxLayout()
        dev_col.setSpacing(2)

        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.device_combo.setStyleSheet("""
            QComboBox {
                background-color: transparent;
                border: none;
                color: #F8FAFC;
                font-weight: bold;
                font-size: 13px;
                padding: 0;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #13161F;
                color: #F8FAFC;
                selection-background-color: #2563EB;
                border: 1px solid #1E2330;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        dev_col.addWidget(self.device_combo)

        self.lbl_device_status = QLabel("○ Scanning ADB devices...")
        self.lbl_device_status.setStyleSheet("color: #64748B; font-size: 11px;")
        dev_col.addWidget(self.lbl_device_status)
        dev_layout.addLayout(dev_col)

        self.btn_quick_find = QPushButton("⚡ Auto-Find")
        self.btn_quick_find.setToolTip("Auto-discover phone on Wi-Fi via mDNS and connect")
        self.btn_quick_find.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; font-weight: bold; font-size: 11px; "
            "padding: 6px 10px; border: 1px solid #0284C7; border-radius: 6px;"
        )
        self.btn_quick_find.clicked.connect(self._auto_find_and_connect)
        dev_layout.addWidget(self.btn_quick_find)

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setFixedSize(30, 28)
        self.btn_refresh.setToolTip("Refresh connected ADB devices")
        self.btn_refresh.setStyleSheet(
            "background-color: #181C26; color: #94A3B8; border: 1px solid #222634; border-radius: 6px;"
        )
        self.btn_refresh.clicked.connect(self.refresh_devices)
        dev_layout.addWidget(self.btn_refresh)

        root_layout.addWidget(dev_card)

        # 3. SEGMENTED MODE SELECTOR (Speaker / Mic / Headset)
        mode_frame = QFrame()
        mode_frame.setStyleSheet("background-color: #0E1017; border: 1px solid #1E2330; border-radius: 8px;")
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(3, 3, 3, 3)
        mode_layout.setSpacing(3)

        self.btn_mode_spk = QPushButton("🔊  Speaker")
        self.btn_mode_mic = QPushButton("🎙  Microphone")
        self.btn_mode_dup = QPushButton("🎧  Headset")

        mode_group = QButtonGroup(self)
        for idx, btn in enumerate((self.btn_mode_spk, self.btn_mode_mic, self.btn_mode_dup)):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setFont(QFont("sans-serif", 11, QFont.Bold))
            mode_group.addButton(btn, idx)
            mode_layout.addWidget(btn)

        self.btn_mode_spk.setChecked(True)
        self.btn_mode_spk.clicked.connect(lambda: self._set_mode(MODE_SPEAKER))
        self.btn_mode_mic.clicked.connect(lambda: self._set_mode(MODE_MIC))
        self.btn_mode_dup.clicked.connect(lambda: self._set_mode(MODE_DUPLEX))

        root_layout.addWidget(mode_frame)

        # 4. CARD: AUDIO DECK (Unified Studio Slider & LED Levels)
        self.deck_card = QFrame()
        self.deck_card.setStyleSheet("background-color: #13161F; border: 1px solid #1E2330; border-radius: 12px;")
        self.deck_layout = QVBoxLayout(self.deck_card)
        self.deck_layout.setContentsMargins(14, 14, 14, 14)
        self.deck_layout.setSpacing(12)

        # Speaker Block
        self.spk_widget = QWidget()
        spk_l = QVBoxLayout(self.spk_widget)
        spk_l.setContentsMargins(0, 0, 0, 0)
        spk_l.setSpacing(6)

        spk_header = QHBoxLayout()
        lbl_spk = QLabel("OUTPUT (PC → PHONE)")
        lbl_spk.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        spk_header.addWidget(lbl_spk)
        spk_header.addStretch()

        self.btn_mute_spk = QPushButton("🔊")
        self.btn_mute_spk.setFixedSize(26, 22)
        self.btn_mute_spk.setStyleSheet("background: transparent; border: none; font-size: 13px;")
        self.btn_mute_spk.clicked.connect(self._toggle_mute)
        spk_header.addWidget(self.btn_mute_spk)

        self.lbl_vol_val = QLabel("100%")
        self.lbl_vol_val.setFont(QFont("monospace", 10, QFont.Bold))
        self.lbl_vol_val.setStyleSheet("color: #F8FAFC;")
        spk_header.addWidget(self.lbl_vol_val)
        spk_l.addLayout(spk_header)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        spk_l.addWidget(self.vol_slider)

        self.spk_meter = MinimalLedMeter(is_stereo=True)
        spk_l.addWidget(self.spk_meter)

        self.deck_layout.addWidget(self.spk_widget)

        # Divider between Speaker and Mic (visible in Duplex mode)
        self.deck_divider = QFrame()
        self.deck_divider.setFrameShape(QFrame.HLine)
        self.deck_divider.setStyleSheet("color: #1E2330; margin: 2px 0;")
        self.deck_layout.addWidget(self.deck_divider)

        # Microphone Block
        self.mic_widget = QWidget()
        mic_l = QVBoxLayout(self.mic_widget)
        mic_l.setContentsMargins(0, 0, 0, 0)
        mic_l.setSpacing(6)

        mic_header = QHBoxLayout()
        lbl_mic = QLabel("INPUT (PHONE MIC → PC)")
        lbl_mic.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        mic_header.addWidget(lbl_mic)
        mic_header.addStretch()

        self.btn_mic_mute = QPushButton("🎙")
        self.btn_mic_mute.setFixedSize(26, 22)
        self.btn_mic_mute.setStyleSheet("background: transparent; border: none; font-size: 13px;")
        self.btn_mic_mute.clicked.connect(self._toggle_mic_mute)
        mic_header.addWidget(self.btn_mic_mute)

        self.lbl_mic_gain = QLabel("100%")
        self.lbl_mic_gain.setFont(QFont("monospace", 10, QFont.Bold))
        self.lbl_mic_gain.setStyleSheet("color: #F8FAFC;")
        mic_header.addWidget(self.lbl_mic_gain)
        mic_l.addLayout(mic_header)

        self.mic_gain_slider = QSlider(Qt.Horizontal)
        self.mic_gain_slider.setRange(0, 200)
        self.mic_gain_slider.setValue(100)
        self.mic_gain_slider.valueChanged.connect(self._on_mic_gain_changed)
        mic_l.addWidget(self.mic_gain_slider)

        self.mic_meter = MinimalLedMeter(is_stereo=False)
        mic_l.addWidget(self.mic_meter)

        # Mic Tools Sub-Row (Gate & Local Test)
        mic_tools = QHBoxLayout()
        mic_tools.setContentsMargins(0, 4, 0, 0)
        mic_tools.setSpacing(8)

        lbl_gate = QLabel("Gate:")
        lbl_gate.setStyleSheet("color: #64748B; font-size: 11px;")
        mic_tools.addWidget(lbl_gate)

        self.combo_noise_gate = QComboBox()
        self.combo_noise_gate.addItem("Off", 0.0)
        self.combo_noise_gate.addItem("Low (-42 dB)", 0.008)
        self.combo_noise_gate.addItem("Med (-36 dB)", 0.016)
        self.combo_noise_gate.addItem("High (-24 dB)", 0.060)
        self.combo_noise_gate.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.combo_noise_gate.currentIndexChanged.connect(self._on_noise_gate_changed)
        mic_tools.addWidget(self.combo_noise_gate)

        mic_tools.addStretch()

        self.btn_mic_test = QPushButton("🎧 Test Mic")
        self.btn_mic_test.setToolTip("Listen to your phone's microphone locally in PC headphones for 5 seconds")
        self.btn_mic_test.setStyleSheet("background-color: #1E293B; color: #38BDF8; font-weight: bold; font-size: 11px; padding: 3px 8px;")
        self.btn_mic_test.clicked.connect(self._toggle_mic_test)
        mic_tools.addWidget(self.btn_mic_test)

        mic_l.addLayout(mic_tools)

        self.deck_layout.addWidget(self.mic_widget)

        root_layout.addWidget(self.deck_card)

        # 5. HERO PRIMARY BUTTON & STATUS
        hero_box = QVBoxLayout()
        hero_box.setSpacing(8)

        self.btn_toggle = QPushButton("▶   START STREAMING")
        self.btn_toggle.setFixedHeight(48)
        self.btn_toggle.setFont(QFont("sans-serif", 13, QFont.Bold))
        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 10px; border: 1px solid #3B82F6; letter-spacing: 0.5px;"
        )
        self.btn_toggle.clicked.connect(self.toggle_streaming)
        hero_box.addWidget(self.btn_toggle)

        # Live telemetry line (visible when streaming)
        self.lbl_telemetry = QLabel("Ready • Press Start Streaming")
        self.lbl_telemetry.setAlignment(Qt.AlignCenter)
        self.lbl_telemetry.setFont(QFont("monospace", 10))
        self.lbl_telemetry.setStyleSheet("color: #64748B;")
        hero_box.addWidget(self.lbl_telemetry)

        root_layout.addLayout(hero_box)

        # Initialize view state for the default mode
        self._set_mode(MODE_SPEAKER)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0B0D12;
            }
            QWidget {
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QPushButton[checkable="true"] {
                background-color: transparent;
                color: #8E95A2;
                border: none;
                border-radius: 6px;
            }
            QPushButton[checkable="true"]:checked {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #1E2330;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #3B82F6;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #3B82F6;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QComboBox {
                background-color: #161A22;
                color: #F8FAFC;
                border: 1px solid #222634;
                border-radius: 6px;
                padding: 4px 8px;
            }
        """)

    def _set_mode(self, mode: str):
        self.current_mode = mode
        if mode == MODE_SPEAKER:
            self.spk_widget.setVisible(True)
            self.deck_divider.setVisible(False)
            self.mic_widget.setVisible(False)
            self.btn_toggle.setText("▶   START SPEAKER STREAM")
        elif mode == MODE_MIC:
            self.spk_widget.setVisible(False)
            self.deck_divider.setVisible(False)
            self.mic_widget.setVisible(True)
            self.btn_toggle.setText("▶   START MICROPHONE")
        else:  # MODE_DUPLEX
            self.spk_widget.setVisible(True)
            self.deck_divider.setVisible(True)
            self.mic_widget.setVisible(True)
            self.btn_toggle.setText("▶   START HEADSET DUPLEX")

    def refresh_devices(self):
        self.device_combo.clear()
        if not self.adb.is_available():
            self.device_combo.addItem("⚠ ADB not found in PATH", "")
            self.lbl_device_status.setText("Install android-tools or check PATH")
            self.status_dot.setStyleSheet("color: #EF4444;")
            return

        devices = self.adb.list_devices()
        if not devices:
            self.device_combo.addItem("○ No devices connected", "")
            self.lbl_device_status.setText("Plug in USB cable or click ⚡ Auto-Find for Wi-Fi")
            self.status_dot.setStyleSheet("color: #64748B;")
            return

        active_count = 0
        for dev in devices:
            is_wifi = ":" in dev.serial
            tag = " [Wi-Fi]" if is_wifi else " [USB]"
            name = dev.model or ("Wireless Device" if is_wifi else "Android Device")
            state_warning = f" — ⚠ {dev.state.upper()}" if dev.state != "device" else ""
            label = f"{name}{tag} ({dev.serial}){state_warning}"
            self.device_combo.addItem(label, dev.serial)
            if dev.state == "device":
                active_count += 1

        selected_serial = self.device_combo.currentData() or ""
        if ":" in selected_serial:
            self.lbl_device_status.setText(f"Connected wirelessly via Wi-Fi ({selected_serial})")
        elif selected_serial:
            self.lbl_device_status.setText(f"Connected via USB cable ({selected_serial})")
        else:
            self.lbl_device_status.setText(f"Detected {len(devices)} device(s)")

        if active_count > 0:
            self.status_dot.setStyleSheet("color: #10B981;" if (self.streamer or self.mic_receiver) else "color: #38BDF8;")
        else:
            self.status_dot.setStyleSheet("color: #F59E0B;")

    def _auto_find_and_connect(self):
        """Discovers phone on Wi-Fi via mDNS and establishes connection immediately."""
        self.lbl_device_status.setText("Scanning Wi-Fi network via mDNS...")
        QApplication.processEvents()

        services = self.adb.discover_mdns_services()
        if not services:
            # Fallback to USB switch if phone is connected via USB
            devices = self.adb.list_devices()
            usb_devs = [d for d in devices if ":" not in d.serial and d.state == "device"]
            if usb_devs:
                self._auto_switch_usb_to_wifi()
                return

            QMessageBox.information(
                self,
                "Auto-Find via Wi-Fi",
                "No Wireless ADB devices found on local Wi-Fi.\n\n"
                "1. Make sure phone is on the same Wi-Fi network.\n"
                "2. Ensure 'Wireless Debugging' is ON in Developer options.\n"
                "3. Or click ⚙ Settings → Pair with QR Code."
            )
            self.refresh_devices()
            return

        srv_name, _, ip_port = services[0]
        if ":" in ip_port:
            host, port_str = ip_port.split(":", 1)
            port = int(port_str)
        else:
            host, port = ip_port, 5555

        self.wifi_ip_input.setText(host)
        self.wifi_port_spin.setValue(port)
        ok, msg = self.adb.connect_wireless(host, port)
        self.refresh_devices()
        if ok:
            self.lbl_device_status.setText(f"Connected to {srv_name} ({ip_port})")
        else:
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {ip_port}:\n\n{msg}")

    def _auto_switch_usb_to_wifi(self):
        devices = self.adb.list_devices()
        usb_devices = [d for d in devices if ":" not in d.serial and d.state == "device"]
        if not usb_devices:
            QMessageBox.warning(self, "No USB Device", "Please connect phone via USB first.")
            return

        target_serial = usb_devices[0].serial
        ip = self.adb.get_device_wlan_ip(target_serial)
        if not ip:
            QMessageBox.warning(self, "IP Not Found", "Could not detect phone Wi-Fi IP.")
            return

        self.adb.enable_tcpip(5555, serial=target_serial)
        ok, _ = self.adb.connect_wireless(ip, 5555)
        self.refresh_devices()
        if ok:
            QMessageBox.information(self, "Wireless Connected", f"🎉 Connected wirelessly to {ip}:5555!\nYou can now unplug USB.")

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def toggle_streaming(self):
        is_active = (self.streamer and self.streamer.is_running) or (self.mic_receiver and self.mic_receiver.is_running)
        if is_active:
            self.stop_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        port = self.port_spin.value()
        mic_port = self.mic_port_spin.value()
        selected_serial = self.device_combo.currentData() or None

        if not selected_serial:
            QMessageBox.warning(
                self,
                "No Device Selected",
                "Please connect an Android phone via USB or Wireless ADB before starting the stream.",
            )
            return

        for dev in self.adb.list_devices():
            if dev.serial == selected_serial and dev.state != "device":
                QMessageBox.warning(
                    self,
                    "Device Offline or Unauthorized",
                    f"Selected device '{selected_serial}' is currently {dev.state.upper()}.\n\n"
                    "• If using Wireless ADB, make sure phone screen is awake and reconnect.\n"
                    "• If prompt appears on phone, tap 'Allow debugging'.",
                )
                return

        # 1. Forward ports via ADB
        if self.adb.is_available():
            if self.current_mode in (MODE_SPEAKER, MODE_DUPLEX):
                self.adb.forward_port(local_port=port, remote_port=port, serial=selected_serial)
            if self.current_mode in (MODE_MIC, MODE_DUPLEX):
                self.adb.forward_port(local_port=mic_port, remote_port=mic_port, serial=selected_serial)

        # 2. Start Speaker Streamer
        if self.current_mode in (MODE_SPEAKER, MODE_DUPLEX):
            vol = self.vol_slider.value() / 100.0
            self.streamer = AudioStreamer(
                host="127.0.0.1",
                port=port,
                sample_rate=48000,
                channels=2,
                chunk_frames=self.chunk_frames,
                volume=vol,
                backend="auto",
                on_stats_update=lambda st: self.signals.stats_updated.emit(st),
                on_error=lambda err: self.signals.error_occurred.emit(err),
            )
            try:
                self.streamer.start()
            except Exception as e:
                QMessageBox.critical(self, "Speaker Error", f"Failed to start stream: {e}")
                self.stop_streaming()
                return

        # 3. Start Microphone Receiver
        if self.current_mode in (MODE_MIC, MODE_DUPLEX):
            gain = self.mic_gain_slider.value() / 100.0
            self.mic_receiver = MicReceiver(
                host="127.0.0.1",
                port=mic_port,
                gain=gain,
                on_stats_update=lambda st: self.signals.mic_stats_updated.emit(st),
                on_error=lambda err: self.signals.error_occurred.emit(err),
            )
            gate_val = self.combo_noise_gate.currentData()
            if gate_val is not None:
                self.mic_receiver.set_noise_gate(float(gate_val))

            try:
                self.mic_receiver.start()
            except Exception as e:
                QMessageBox.critical(self, "Microphone Error", f"Failed to start microphone: {e}")
                self.stop_streaming()
                return

        self._save_settings()

        self.btn_toggle.setText("■   STOP STREAMING")
        self.btn_toggle.setStyleSheet(
            "background-color: #DC2626; color: #FFFFFF; border-radius: 10px; "
            "border: 1px solid #EF4444; font-weight: bold; letter-spacing: 0.5px;"
        )
        self.status_dot.setStyleSheet("color: #10B981;")

        if self.tray_icon:
            self.tray_icon.setIcon(self._create_app_icon(True))
            self.tray_icon.setToolTip(f"Sonopipe: Streaming ({self.current_mode.upper()})")
            if hasattr(self, 'tray_act_stream'):
                self.tray_act_stream.setText("Stop Streaming")

    def stop_streaming(self):
        self._stop_mic_test()

        if self.streamer:
            self.streamer.stop()
            self.streamer = None

        if self.mic_receiver:
            self.mic_receiver.stop()
            self.mic_receiver = None

        self.spk_meter.set_levels(0.0, 0.0, 0.0, 0.0)
        self.mic_meter.set_levels(0.0, 0.0, 0.0, 0.0)

        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 10px; "
            "border: 1px solid #3B82F6; font-weight: bold; letter-spacing: 0.5px;"
        )
        self._set_mode(self.current_mode)
        self.status_dot.setStyleSheet("color: #38BDF8;")
        self.lbl_telemetry.setText("Ready • Press Start Streaming")

        if self.tray_icon:
            self.tray_icon.setIcon(self._create_app_icon(False))
            self.tray_icon.setToolTip("Sonopipe: Idle")
            if hasattr(self, 'tray_act_stream'):
                self.tray_act_stream.setText("Start Streaming")

    def _on_stats_updated(self, stats: dict):
        l_rms = stats.get("left_rms", stats.get("rms_level", 0.0))
        r_rms = stats.get("right_rms", stats.get("rms_level", 0.0))
        l_peak = stats.get("left_peak", stats.get("peak_level", 0.0))
        r_peak = stats.get("right_peak", stats.get("peak_level", 0.0))
        self.spk_meter.set_levels(l_rms, r_rms, l_peak, r_peak)

        rate = stats.get("kb_per_sec", 0.0)
        uptime = int(stats.get("uptime", 0))
        mins, secs = divmod(uptime, 60)
        self.lbl_telemetry.setText(f"● Live  •  {rate:5.1f} KB/s  •  ~20 ms  •  {mins:02d}:{secs:02d}")

    def _on_mic_stats_updated(self, stats: dict):
        mic_rms = stats.get("mic_rms", 0.0)
        mic_peak = stats.get("mic_peak", 0.0)
        self.mic_meter.set_levels(mic_rms, 0.0, mic_peak, 0.0)

        if self.current_mode == MODE_MIC:
            rate = stats.get("mic_kb_per_sec", 0.0)
            self.lbl_telemetry.setText(f"● Live Mic  •  {rate:5.1f} KB/s  •  PipeWire monitor")

    def _on_error_occurred(self, err_msg: str):
        self.stop_streaming()
        self.status_dot.setStyleSheet("color: #EF4444;")
        QMessageBox.warning(self, "Stream Interrupted", f"Transmission stopped:\n\n{err_msg}")

    def _on_volume_changed(self, value: int):
        self.lbl_vol_val.setText(f"{value}%")
        if self.streamer:
            self.streamer.volume = value / 100.0

    def _toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            self.btn_mute_spk.setText("🔊")
            self.vol_slider.setValue(self.saved_volume)
        else:
            self.saved_volume = self.vol_slider.value()
            self.is_muted = True
            self.btn_mute_spk.setText("🔇")
            self.vol_slider.setValue(0)

    def _on_mic_gain_changed(self, value: int):
        self.lbl_mic_gain.setText(f"{value}%")
        if self.mic_receiver:
            self.mic_receiver.set_gain(value / 100.0)

    def _toggle_mic_mute(self):
        if self.is_mic_muted:
            self.is_mic_muted = False
            self.btn_mic_mute.setText("🎙")
            self.mic_gain_slider.setValue(self.saved_mic_gain)
        else:
            self.saved_mic_gain = self.mic_gain_slider.value()
            self.is_mic_muted = True
            self.btn_mic_mute.setText("🔇")
            self.mic_gain_slider.setValue(0)

    def _on_noise_gate_changed(self, idx: int):
        val = self.combo_noise_gate.currentData()
        if self.mic_receiver and val is not None:
            self.mic_receiver.set_noise_gate(float(val))

    def _toggle_mic_test(self):
        if self.mic_tester.is_active:
            self._stop_mic_test()
        else:
            if not self.mic_receiver or not self.mic_receiver.is_running:
                QMessageBox.information(
                    self,
                    "Mic Not Streaming",
                    "Please start streaming in Mic or Headset mode first to test your microphone."
                )
                return

            if self.mic_tester.start():
                self.mic_receiver.set_loopback(True, self.mic_tester.write_chunk)
                self.mic_test_countdown = 6
                self.btn_mic_test.setText(f"⏹ ({self.mic_test_countdown}s)")
                self.btn_mic_test.setStyleSheet("background-color: #991B1B; color: #FCA5A5; font-weight: bold;")
                self.mic_test_timer.start()

    def _on_mic_test_tick(self):
        self.mic_test_countdown -= 1
        if self.mic_test_countdown <= 0:
            self._stop_mic_test()
        else:
            self.btn_mic_test.setText(f"⏹ ({self.mic_test_countdown}s)")

    def _stop_mic_test(self):
        self.mic_test_timer.stop()
        self.mic_tester.stop()
        if self.mic_receiver:
            self.mic_receiver.set_loopback(False)
        self.btn_mic_test.setText("🎧 Test Mic")
        self.btn_mic_test.setStyleSheet("background-color: #1E293B; color: #38BDF8; font-weight: bold; font-size: 11px; padding: 3px 8px;")

    def _on_preset_changed(self, frames: int):
        self.chunk_frames = frames

    def _connect_wireless_adb(self):
        text = self.wifi_ip_input.text().strip()
        port = self.wifi_port_spin.value()
        if not text:
            return
        if ":" in text:
            host, port_str = text.split(":", 1)
            try:
                port = int(port_str)
                self.wifi_ip_input.setText(host)
                self.wifi_port_spin.setValue(port)
            except ValueError:
                pass
        else:
            host = text

        self._save_settings()
        ok, msg = self.adb.connect_wireless(host, port)
        self.refresh_devices()
        if ok:
            QMessageBox.information(self, "Connected", f"Connected wirelessly to {host}:{port}!")
        else:
            QMessageBox.warning(self, "Failed", f"Could not connect to {host}:{port}:\n\n{msg}")

    def _disconnect_wireless_adb(self):
        text = self.wifi_ip_input.text().strip()
        port = self.wifi_port_spin.value()
        target = f"{text}:{port}" if text else None
        self.adb.disconnect_wireless(target)
        self.refresh_devices()

    def _copy_forward_command(self):
        port = self.port_spin.value()
        mic_port = self.mic_port_spin.value()
        cmd = f"adb forward tcp:{port} tcp:{port} && adb forward tcp:{mic_port} tcp:{mic_port}"
        QApplication.clipboard().setText(cmd)
        QMessageBox.information(self, "Copied", f"Command copied to clipboard:\n\n{cmd}")

    def _on_install_apk_clicked(self):
        selected_serial = self.device_combo.currentData() or None
        self.apk_worker = ApkInstallWorker(serial=selected_serial)
        self.apk_worker.finished.connect(lambda ok, msg: QMessageBox.information(self, "APK Install", msg) if ok else QMessageBox.warning(self, "APK Install", msg))
        self.apk_worker.start()

    def _open_wireless_guide(self):
        from sonopipe.gui.main_window import WirelessGuideDialog
        dlg = WirelessGuideDialog(self)
        dlg.exec()

    def _create_app_icon(self, is_streaming: bool = False) -> QIcon:
        pix = QPixmap(32, 32)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        bg_col = QColor("#0284C7") if not is_streaming else QColor("#10B981")
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(2, 2, 28, 28, 8, 8)
        p.setPen(QPen(QColor("#FFFFFF"), 2.5))
        p.drawLine(10, 16, 10, 16)
        p.drawLine(16, 11, 16, 21)
        p.drawLine(22, 7, 22, 25)
        p.end()
        return QIcon(pix)

    def _init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self._create_app_icon(False), self)
        self.tray_icon.setToolTip("Sonopipe: Idle")

        menu = QMenu()
        self.tray_act_toggle_win = menu.addAction("Show Sonopipe")
        self.tray_act_toggle_win.triggered.connect(self._toggle_window_visibility)

        menu.addSeparator()
        self.tray_act_stream = menu.addAction("Start Streaming")
        self.tray_act_stream.triggered.connect(self.toggle_streaming)

        self.tray_act_mute_spk = menu.addAction("Mute Speaker")
        self.tray_act_mute_spk.triggered.connect(self._toggle_mute)

        self.tray_act_mute_mic = menu.addAction("Mute Mic")
        self.tray_act_mute_mic.triggered.connect(self._toggle_mic_mute)

        menu.addSeparator()
        act_quit = menu.addAction("Quit Sonopipe")
        act_quit.triggered.connect(self._quit_app)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_window_visibility()

    def _toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
            if hasattr(self, 'tray_act_toggle_win'):
                self.tray_act_toggle_win.setText("Show Sonopipe")
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            if hasattr(self, 'tray_act_toggle_win'):
                self.tray_act_toggle_win.setText("Hide Sonopipe")

    def _quit_app(self):
        self._stop_mic_test()
        self._save_settings()
        self.stop_streaming()
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Sonopipe",
                "Sonopipe minimized to system tray. Click to restore.",
                QSystemTrayIcon.Information,
                2000
            )
            if hasattr(self, 'tray_act_toggle_win'):
                self.tray_act_toggle_win.setText("Show Sonopipe")
            event.ignore()
        else:
            self._stop_mic_test()
            self._save_settings()
            self.stop_streaming()
            event.accept()

    def _save_settings(self):
        self.settings.setValue("mode", self.current_mode)
        self.settings.setValue("volume", self.vol_slider.value())
        self.settings.setValue("mic_gain", self.mic_gain_slider.value())
        self.settings.setValue("chunk_frames", self.chunk_frames)
        self.settings.setValue("wifi_ip", self.wifi_ip_input.text().strip())
        self.settings.setValue("wifi_port", self.wifi_port_spin.value())

    def _load_saved_settings(self):
        saved_mode = self.settings.value("mode", MODE_SPEAKER)
        if saved_mode == MODE_MIC:
            self.btn_mode_mic.setChecked(True)
            self._set_mode(MODE_MIC)
        elif saved_mode == MODE_DUPLEX:
            self.btn_mode_dup.setChecked(True)
            self._set_mode(MODE_DUPLEX)
        else:
            self.btn_mode_spk.setChecked(True)
            self._set_mode(MODE_SPEAKER)

        vol = int(self.settings.value("volume", 100))
        self.vol_slider.setValue(vol)

        gain = int(self.settings.value("mic_gain", 100))
        self.mic_gain_slider.setValue(gain)

        frames = int(self.settings.value("chunk_frames", 960))
        self.chunk_frames = frames

        ip = str(self.settings.value("wifi_ip", ""))
        if ip:
            self.wifi_ip_input.setText(ip)

        port = int(self.settings.value("wifi_port", 5555))
        self.wifi_port_spin.setValue(port)


def run_gui() -> int:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland*=false")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
