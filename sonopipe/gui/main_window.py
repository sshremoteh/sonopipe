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
from sonopipe.adb.wifi_store import WifiDeviceStore
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT
from sonopipe.mic.receiver import MicReceiver, DEFAULT_MIC_PORT
from sonopipe.mic.tester import LocalMicTester
from sonopipe.gui.settings_dialog import SettingsDialog
from sonopipe.gui.theme import MD3, md3_base_stylesheet
from sonopipe.gui.wifi_dialog import (
    WifiConnectDialog,
    WifiConnectWorker,
    WifiScanWorker,
    WirelessGuideDialog,
)


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


class AutoReconnectWorker(QThread):
    """Background worker that reconnects to remembered Wi-Fi devices on launch."""

    finished = Signal(str)

    def __init__(self, adb: AdbManager, candidates: list[dict]):
        super().__init__()
        self.adb = adb
        self.candidates = candidates

    def run(self):
        for dev in self.candidates:
            host = dev.get("host", "")
            port = int(dev.get("port", 5555))
            if not host:
                continue
            ok, _ = self.adb.connect_wireless(host, port)
            if ok:
                self.finished.emit(f"{host}:{port}")
                return
        self.finished.emit("")


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
        self.setFixedSize(460, 610)

        self.adb = AdbManager()
        self.streamer: Optional[AudioStreamer] = None
        self.mic_receiver: Optional[MicReceiver] = None
        self._wifi_scan_worker: Optional[WifiScanWorker] = None
        self._wifi_conn_worker: Optional[WifiConnectWorker] = None
        self._auto_reconn_worker: Optional[AutoReconnectWorker] = None

        self.signals = StreamerSignals()
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.mic_stats_updated.connect(self._on_mic_stats_updated)
        self.signals.error_occurred.connect(self._on_error_occurred)

        self.settings = QSettings("Sonopipe", "Sonopipe")
        self.wifi_store = WifiDeviceStore(self.settings)

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
        QTimer.singleShot(250, self._auto_reconnect_saved_wifi)

    def _init_ui(self):
        c = MD3
        container = QWidget(self)
        self.setCentralWidget(container)

        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(14)

        # 1. MD3 TOP APP BAR: Status + Title + Wi-Fi Pill + MD3 Overflow Menu
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("sans-serif", 11))
        self.status_dot.setStyleSheet(f"color: {c['muted']};")
        top_bar.addWidget(self.status_dot)

        app_title = QLabel("Sonopipe")
        app_title.setFont(QFont("sans-serif", 16, QFont.Bold))
        app_title.setStyleSheet(f"color: {c['on_surface']}; letter-spacing: -0.3px;")
        top_bar.addWidget(app_title)

        ver_badge = QLabel("v1.5")
        ver_badge.setFont(QFont("sans-serif", 9, QFont.Bold))
        ver_badge.setStyleSheet(
            f"color: {c['on_secondary_container']}; background-color: {c['secondary_container']}; "
            "padding: 2px 8px; border-radius: 10px;"
        )
        top_bar.addWidget(ver_badge)

        top_bar.addStretch()

        self.btn_wifi_menu = QPushButton("📶  Wi-Fi")
        self.btn_wifi_menu.setFixedHeight(34)
        self.btn_wifi_menu.setToolTip("Manage & connect saved Wi-Fi devices")
        self.btn_wifi_menu.setStyleSheet(
            f"QPushButton {{ background-color: {c['primary_container']}; color: {c['on_primary_container']}; "
            "border: none; border-radius: 17px; padding: 0 14px; font-weight: 700; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {c['primary']}; color: {c['on_primary']}; }}"
        )
        self.btn_wifi_menu.clicked.connect(self._open_wifi_dialog)
        top_bar.addWidget(self.btn_wifi_menu)

        self.btn_menu = QPushButton("⋮")
        self.btn_menu.setFixedSize(34, 34)
        self.btn_menu.setToolTip("Menu")
        self.btn_menu.setStyleSheet(
            f"QPushButton {{ background-color: {c['surface_container_high']}; color: {c['on_surface']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 17px; font-size: 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {c['surface_container_highest']}; }}"
        )
        self._build_md3_menu()
        self.btn_menu.clicked.connect(self._show_md3_menu)
        top_bar.addWidget(self.btn_menu)

        root_layout.addLayout(top_bar)

        # 2. MD3 CARD: TARGET DEVICE + QUICK SAVED WI-FI CHIPS
        dev_card = QFrame()
        dev_card.setStyleSheet(
            f"background-color: {c['surface_container']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 18px;"
        )
        dev_card_layout = QVBoxLayout(dev_card)
        dev_card_layout.setContentsMargins(14, 12, 14, 12)
        dev_card_layout.setSpacing(8)

        dev_layout = QHBoxLayout()
        dev_layout.setSpacing(10)

        phone_badge = QLabel("📱")
        phone_badge.setFixedSize(36, 36)
        phone_badge.setAlignment(Qt.AlignCenter)
        phone_badge.setStyleSheet(
            f"background-color: {c['surface_container_high']}; border-radius: 18px; font-size: 16px; border: none;"
        )
        dev_layout.addWidget(phone_badge)

        dev_col = QVBoxLayout()
        dev_col.setSpacing(2)

        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.device_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: transparent;
                border: none;
                color: {c['on_surface']};
                font-weight: 700;
                font-size: 13px;
                padding: 0;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {c['surface_container_high']};
                color: {c['on_surface']};
                selection-background-color: {c['primary_container']};
                selection-color: {c['on_primary_container']};
                border: 1px solid {c['outline_variant']};
                border-radius: 12px;
                padding: 6px;
            }}
        """)
        dev_col.addWidget(self.device_combo)

        self.lbl_device_status = QLabel("○ Scanning ADB devices...")
        self.lbl_device_status.setStyleSheet(f"color: {c['on_surface_variant']}; font-size: 11px; border: none;")
        dev_col.addWidget(self.lbl_device_status)
        dev_layout.addLayout(dev_col)

        self.btn_quick_find = QPushButton("⚡ Auto")
        self.btn_quick_find.setFixedHeight(32)
        self.btn_quick_find.setToolTip("Auto-discover phone on Wi-Fi via mDNS and connect")
        self.btn_quick_find.setStyleSheet(
            f"QPushButton {{ background-color: {c['secondary_container']}; color: {c['on_secondary_container']}; "
            "font-weight: 700; font-size: 11px; padding: 0 12px; border: none; border-radius: 16px; }}"
            f"QPushButton:hover {{ background-color: {c['primary_container']}; color: {c['on_primary_container']}; }}"
        )
        self.btn_quick_find.clicked.connect(self._auto_find_and_connect)
        dev_layout.addWidget(self.btn_quick_find)

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setToolTip("Refresh connected ADB devices")
        self.btn_refresh.setStyleSheet(
            f"QPushButton {{ background-color: {c['surface_container_high']}; color: {c['on_surface_variant']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 16px; font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: {c['surface_container_highest']}; color: {c['on_surface']}; }}"
        )
        self.btn_refresh.clicked.connect(lambda: self.refresh_devices())
        dev_layout.addWidget(self.btn_refresh)

        dev_card_layout.addLayout(dev_layout)

        # Quick-connect chips row for remembered Wi-Fi devices
        self.quick_wifi_bar = QWidget()
        self.quick_wifi_bar.setStyleSheet("border: none; background: transparent;")
        self.quick_wifi_layout = QHBoxLayout(self.quick_wifi_bar)
        self.quick_wifi_layout.setContentsMargins(0, 2, 0, 0)
        self.quick_wifi_layout.setSpacing(6)
        self.quick_wifi_bar.setVisible(False)
        dev_card_layout.addWidget(self.quick_wifi_bar)

        root_layout.addWidget(dev_card)

        # 3. MD3 SEGMENTED MODE SELECTOR (Speaker / Mic / Headset)
        mode_frame = QFrame()
        mode_frame.setStyleSheet(
            f"background-color: {c['surface_container_low']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 20px;"
        )
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(4, 4, 4, 4)
        mode_layout.setSpacing(4)

        self.btn_mode_spk = QPushButton("🔊  Speaker")
        self.btn_mode_mic = QPushButton("🎙  Microphone")
        self.btn_mode_dup = QPushButton("🎧  Headset")

        mode_group = QButtonGroup(self)
        for idx, btn in enumerate((self.btn_mode_spk, self.btn_mode_mic, self.btn_mode_dup)):
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setFont(QFont("sans-serif", 11, QFont.Bold))
            mode_group.addButton(btn, idx)
            mode_layout.addWidget(btn)

        self.btn_mode_spk.setChecked(True)
        self.btn_mode_spk.clicked.connect(lambda: self._set_mode(MODE_SPEAKER))
        self.btn_mode_mic.clicked.connect(lambda: self._set_mode(MODE_MIC))
        self.btn_mode_dup.clicked.connect(lambda: self._set_mode(MODE_DUPLEX))

        root_layout.addWidget(mode_frame)

        # 4. MD3 CARD: AUDIO DECK (Unified Studio Slider & LED Levels)
        self.deck_card = QFrame()
        self.deck_card.setStyleSheet(
            f"background-color: {c['surface_container']}; "
            f"border: 1px solid {c['outline_variant']}; border-radius: 18px;"
        )
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

        # 5. MD3 HERO PILL BUTTON & STATUS
        hero_box = QVBoxLayout()
        hero_box.setSpacing(8)

        c = MD3
        self.btn_toggle = QPushButton("▶   START STREAMING")
        self.btn_toggle.setFixedHeight(48)
        self.btn_toggle.setFont(QFont("sans-serif", 13, QFont.Bold))
        self.btn_toggle.setStyleSheet(
            f"QPushButton {{ background-color: {c['primary']}; color: {c['on_primary']}; "
            "border-radius: 24px; border: none; letter-spacing: 0.4px; }}"
            f"QPushButton:hover {{ background-color: {c['on_primary_container']}; }}"
        )
        self.btn_toggle.clicked.connect(self.toggle_streaming)
        hero_box.addWidget(self.btn_toggle)

        # Live telemetry line (visible when streaming)
        self.lbl_telemetry = QLabel("Ready • Press Start Streaming")
        self.lbl_telemetry.setAlignment(Qt.AlignCenter)
        self.lbl_telemetry.setFont(QFont("monospace", 10))
        self.lbl_telemetry.setStyleSheet(f"color: {c['muted']};")
        hero_box.addWidget(self.lbl_telemetry)

        root_layout.addLayout(hero_box)

        # Initialize view state for the default mode
        self._set_mode(MODE_SPEAKER)

    def _apply_theme(self):
        c = MD3
        self.setStyleSheet(
            md3_base_stylesheet()
            + f"""
            QPushButton[checkable="true"] {{
                background-color: transparent;
                color: {c['on_surface_variant']};
                border: none;
                border-radius: 16px;
            }}
            QPushButton[checkable="true"]:hover {{
                background-color: {c['surface_container_high']};
            }}
            QPushButton[checkable="true"]:checked {{
                background-color: {c['secondary_container']};
                color: {c['on_secondary_container']};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {c['surface_container_highest']};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {c['primary']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {c['primary']};
                border: 2px solid {c['on_primary']};
                width: 16px;
                height: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 9px;
            }}
            """
        )

    def _build_md3_menu(self):
        self.md3_menu = QMenu(self)
        act_wifi = self.md3_menu.addAction("📶  Wi-Fi Devices & Pairing")
        act_wifi.triggered.connect(self._open_wifi_dialog)

        act_find = self.md3_menu.addAction("⚡  Auto-Find Phone (mDNS)")
        act_find.triggered.connect(self._auto_find_and_connect)

        act_usb = self.md3_menu.addAction("🔌  Switch USB → Wi-Fi")
        act_usb.triggered.connect(self._auto_switch_usb_to_wifi)

        self.md3_menu.addSeparator()

        act_settings = self.md3_menu.addAction("⚙  Audio & Advanced Settings")
        act_settings.triggered.connect(self._open_settings_dialog)

        act_apk = self.md3_menu.addAction("📲  Install Companion APK")
        act_apk.triggered.connect(self._on_install_apk_clicked)

        act_guide = self.md3_menu.addAction("📖  Wireless Setup Guide")
        act_guide.triggered.connect(self._open_wireless_guide)

        self.md3_menu.addSeparator()

        act_quit = self.md3_menu.addAction("✕  Quit Sonopipe")
        act_quit.triggered.connect(self._quit_app)

    def _show_md3_menu(self):
        pos = self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomRight())
        pos.setX(pos.x() - self.md3_menu.sizeHint().width())
        pos.setY(pos.y() + 6)
        self.md3_menu.exec(pos)

    def _open_wifi_dialog(self):
        dlg = WifiConnectDialog(self)
        dlg.exec()
        self.refresh_devices()

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

    def refresh_devices(self, select_serial: Optional[str] = None):
        c = MD3
        prev_serial = select_serial or (self.device_combo.currentData() or "")
        self.device_combo.clear()
        if not self.adb.is_available():
            self.device_combo.addItem("⚠ ADB not found in PATH", "")
            self.lbl_device_status.setText("Install android-tools or check PATH")
            self.status_dot.setStyleSheet(f"color: {c['error']};")
            self._refresh_quick_wifi_bar()
            return

        devices = self.adb.list_devices()
        if not devices:
            self.device_combo.addItem("○ No devices connected", "")
            self.lbl_device_status.setText("Plug in USB, click ⚡ Auto, or tap a saved Wi-Fi chip")
            self.status_dot.setStyleSheet(f"color: {c['muted']};")
            self._refresh_quick_wifi_bar()
            return

        active_count = 0
        select_idx = 0
        for idx, dev in enumerate(devices):
            is_wifi = ":" in dev.serial
            tag = " [Wi-Fi]" if is_wifi else " [USB]"
            name = dev.model or ("Wireless Device" if is_wifi else "Android Device")
            state_warning = f" — ⚠ {dev.state.upper()}" if dev.state != "device" else ""
            label = f"{name}{tag} ({dev.serial}){state_warning}"
            self.device_combo.addItem(label, dev.serial)
            if prev_serial and dev.serial == prev_serial:
                select_idx = idx
            if dev.state == "device":
                active_count += 1
                # Automatically remember any connected Wi-Fi device
                if is_wifi:
                    host, p_str = dev.serial.rsplit(":", 1)
                    try:
                        port = int(p_str)
                    except ValueError:
                        port = 5555
                    self.wifi_store.save_device(host, port, model=dev.model)

        self.device_combo.setCurrentIndex(select_idx)
        selected_serial = self.device_combo.currentData() or ""
        if ":" in selected_serial:
            self.lbl_device_status.setText(f"Connected wirelessly via Wi-Fi ({selected_serial})")
        elif selected_serial:
            self.lbl_device_status.setText(f"Connected via USB cable ({selected_serial})")
        else:
            self.lbl_device_status.setText(f"Detected {len(devices)} device(s)")

        if active_count > 0:
            self.status_dot.setStyleSheet(
                f"color: {c['success']};" if (self.streamer or self.mic_receiver) else f"color: {c['primary']};"
            )
        else:
            self.status_dot.setStyleSheet(f"color: {c['warning']};")

        self._refresh_quick_wifi_bar()

    def _refresh_quick_wifi_bar(self):
        """Show 1-click MD3 chips for remembered Wi-Fi devices not currently connected."""
        c = MD3
        while self.quick_wifi_layout.count():
            item = self.quick_wifi_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        active_serials = {
            self.device_combo.itemData(i)
            for i in range(self.device_combo.count())
            if self.device_combo.itemData(i)
        }
        saved = [
            d for d in self.wifi_store.list_devices()
            if d.get("serial") not in active_serials
        ]

        if not saved:
            self.quick_wifi_bar.setVisible(False)
            return

        lbl = QLabel("Saved:")
        lbl.setStyleSheet(f"color: {c['muted']}; font-size: 11px; font-weight: 600; border: none;")
        self.quick_wifi_layout.addWidget(lbl)

        for dev in saved[:2]:
            host = dev["host"]
            port = int(dev.get("port", 5555))
            name = dev.get("model") or host
            short_name = name if len(name) <= 16 else name[:15] + "…"
            chip = QPushButton(f"📶 {short_name}")
            chip.setFixedHeight(26)
            chip.setToolTip(f"Connect to {name} ({host}:{port})")
            chip.setStyleSheet(
                f"QPushButton {{ background-color: {c['surface_container_high']}; color: {c['primary']}; "
                f"border: 1px solid {c['outline_variant']}; border-radius: 13px; "
                "padding: 0 10px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: {c['primary_container']}; color: {c['on_primary_container']}; }}"
            )
            chip.clicked.connect(lambda _, h=host, p=port: self._quick_connect_saved(h, p))
            self.quick_wifi_layout.addWidget(chip)

        self.quick_wifi_layout.addStretch()
        self.quick_wifi_bar.setVisible(True)

    def _quick_connect_saved(self, host: str, port: int):
        self.lbl_device_status.setText(f"Connecting to {host}:{port}...")
        self._wifi_conn_worker = WifiConnectWorker(self.adb, host, port)
        self._wifi_conn_worker.finished.connect(self._on_quick_wifi_connected)
        self._wifi_conn_worker.start()

    def _on_quick_wifi_connected(self, ok: bool, msg: str, host: str, port: int):
        if ok:
            self.wifi_ip_input.setText(host)
            self.wifi_port_spin.setValue(port)
            self.wifi_store.save_device(host, port)
            self.refresh_devices(select_serial=f"{host}:{port}")
        else:
            self.refresh_devices()
            QMessageBox.warning(self, "Connection Failed", f"Could not connect to {host}:{port}:\n\n{msg}")

    def _auto_reconnect_saved_wifi(self):
        """Silently reconnect to remembered auto-connect Wi-Fi devices on startup."""
        devices = self.adb.list_devices()
        if any(":" in d.serial and d.state == "device" for d in devices):
            return
        candidates = self.wifi_store.get_auto_connect_devices()
        if not candidates:
            return
        self.lbl_device_status.setText("Reconnecting to remembered Wi-Fi device...")
        self._auto_reconn_worker = AutoReconnectWorker(self.adb, candidates)
        self._auto_reconn_worker.finished.connect(self._on_auto_reconnect_finished)
        self._auto_reconn_worker.start()

    def _on_auto_reconnect_finished(self, connected_serial: str):
        if connected_serial:
            host, p_str = connected_serial.rsplit(":", 1)
            self.wifi_ip_input.setText(host)
            self.wifi_port_spin.setValue(int(p_str))
            self.refresh_devices(select_serial=connected_serial)
        else:
            self.refresh_devices()

    def _auto_find_and_connect(self):
        """Discovers phone on Wi-Fi via mDNS in the background and connects immediately."""
        self.lbl_device_status.setText("Scanning Wi-Fi network via mDNS...")
        self.btn_quick_find.setEnabled(False)
        self._wifi_scan_worker = WifiScanWorker(self.adb)
        self._wifi_scan_worker.finished.connect(self._on_auto_find_finished)
        self._wifi_scan_worker.start()

    def _on_auto_find_finished(self, services: list):
        self.btn_quick_find.setEnabled(True)
        if not services:
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
                "3. Or click 📶 Wi-Fi → QR Pair / 6-Digit Code."
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
        self._quick_connect_saved(host, port)

    # Alias for compatibility with settings dialog
    _auto_find_mdns = _auto_find_and_connect

    def _auto_switch_usb_to_wifi(self):
        devices = self.adb.list_devices()
        usb_devices = [d for d in devices if ":" not in d.serial and d.state == "device"]
        if not usb_devices:
            QMessageBox.warning(self, "No USB Device", "Please connect phone via USB first.")
            return

        target_dev = usb_devices[0]
        target_serial = target_dev.serial
        ip = self.adb.get_device_wlan_ip(target_serial)
        if not ip:
            QMessageBox.warning(self, "IP Not Found", "Could not detect phone Wi-Fi IP.")
            return

        self.adb.enable_tcpip(5555, serial=target_serial)
        ok, _ = self.adb.connect_wireless(ip, 5555)
        if ok:
            self.wifi_ip_input.setText(ip)
            self.wifi_port_spin.setValue(5555)
            self.wifi_store.save_device(ip, 5555, model=target_dev.model)
            self.refresh_devices(select_serial=f"{ip}:5555")
            QMessageBox.information(
                self,
                "Wireless Connected",
                f"Connected wirelessly to {ip}:5555 and remembered this device!\nYou can now unplug USB.",
            )
        else:
            self.refresh_devices()

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

        c = MD3
        self.btn_toggle.setText("■   STOP STREAMING")
        self.btn_toggle.setStyleSheet(
            f"QPushButton {{ background-color: {c['error_container']}; color: {c['on_error_container']}; "
            "border-radius: 24px; border: none; font-weight: bold; letter-spacing: 0.4px; }}"
            f"QPushButton:hover {{ background-color: {c['error']}; color: {c['error_container']}; }}"
        )
        self.status_dot.setStyleSheet(f"color: {c['success']};")

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

        c = MD3
        self.btn_toggle.setStyleSheet(
            f"QPushButton {{ background-color: {c['primary']}; color: {c['on_primary']}; "
            "border-radius: 24px; border: none; font-weight: bold; letter-spacing: 0.4px; }}"
            f"QPushButton:hover {{ background-color: {c['on_primary_container']}; }}"
        )
        self._set_mode(self.current_mode)
        self.status_dot.setStyleSheet(f"color: {c['primary']};")
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
        if ok:
            self.wifi_store.save_device(host, port)
            self.refresh_devices(select_serial=f"{host}:{port}")
            QMessageBox.information(self, "Connected", f"Connected wirelessly to {host}:{port}!")
        else:
            self.refresh_devices()
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
