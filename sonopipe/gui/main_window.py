"""
Sonopipe v1.1.0 — Modern PySide6 Desktop GUI.
Designed with dark aesthetic, dual-channel stereo VU meter,
quality presets, settings persistence, and intuitive controls.
"""

from __future__ import annotations
import math
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QSettings, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QBrush, QPen, QLinearGradient, QClipboard
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
    QSlider,
    QGroupBox,
    QFrame,
    QMessageBox,
    QButtonGroup,
)

from sonopipe.adb.manager import AdbManager, AdbDevice
from sonopipe.adb.installer import install_and_launch
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.capture.base import AudioDeviceInfo
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS


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


class StereoVuMeterWidget(QWidget):
    """
    Professional dual-channel (Left / Right) stereo LED peak & RMS level meter
    with smooth peak decay and dB-scale markings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(44)
        self.setMaximumHeight(52)

        self._l_rms = 0.0
        self._r_rms = 0.0
        self._l_peak = 0.0
        self._r_peak = 0.0

        # Peak hold values with gravity decay
        self._l_peak_hold = 0.0
        self._r_peak_hold = 0.0

        # Decay timer for smooth meter physics (30 FPS)
        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(33)
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
        decay_step = 0.03
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
        h = self.height()

        label_w = 18
        bar_x = label_w + 4
        bar_w = w - bar_x - 8
        bar_h = 10
        gap = 6

        # Draw dB scale ticks at top
        db_y = 9
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

        # Draw Channel L
        l_y = 15
        self._draw_bar(painter, "L", bar_x, l_y, bar_w, bar_h, self._l_rms, self._l_peak_hold)

        # Draw Channel R
        r_y = l_y + bar_h + gap
        self._draw_bar(painter, "R", bar_x, r_y, bar_w, bar_h, self._r_rms, self._r_peak_hold)

    def _draw_bar(self, painter: QPainter, label: str, x: int, y: int, w: int, h: int, rms: float, peak_hold: float):
        # Channel label
        painter.setFont(QFont("sans-serif", 9, QFont.Bold))
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(2, y + h - 1, label)

        # Track background
        painter.setBrush(QBrush(QColor("#16181E")))
        painter.setPen(QPen(QColor("#262932"), 1))
        painter.drawRoundedRect(x, y, w, h, 3, 3)

        # Active RMS level gradient
        fill_w = int(w * rms)
        if fill_w > 0:
            grad = QLinearGradient(x, y, x + w, y)
            grad.setColorAt(0.0, QColor("#10B981"))   # Safe green
            grad.setColorAt(0.65, QColor("#3B82F6"))  # Clean cyan/blue
            grad.setColorAt(0.85, QColor("#F59E0B"))  # Warning amber
            grad.setColorAt(0.98, QColor("#EF4444"))  # Peak clip red

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x + 1, y + 1, max(1, fill_w - 2), h - 2, 2, 2)

        # Peak hold tick
        if peak_hold > 0.02:
            pk_x = min(x + w - 2, int(x + peak_hold * w))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawLine(pk_x, y, pk_x, y + h - 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonopipe v1.1.0 — PC Audio to Android Speaker")
        self.resize(560, 740)
        self.setMinimumWidth(500)
        self.setMinimumHeight(680)

        self.adb = AdbManager()
        self.streamer: Optional[AudioStreamer] = None
        self.signals = StreamerSignals()
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.error_occurred.connect(self._on_error_occurred)

        self.settings = QSettings("Sonopipe", "Sonopipe")

        # Preset chunk frames: 480 (10ms), 960 (20ms), 1920 (40ms)
        self.chunk_frames = 960
        self.is_muted = False
        self.saved_volume = 100

        self._init_ui()
        self._apply_theme()
        self._load_saved_settings()
        self.refresh_devices()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(22, 20, 22, 20)
        main_layout.setSpacing(14)

        # 1. HEADER BAR
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)

        # Brand / Title
        brand_col = QVBoxLayout()
        brand_col.setSpacing(2)

        brand_row = QHBoxLayout()
        title_lbl = QLabel("Sonopipe")
        title_lbl.setFont(QFont("sans-serif", 18, QFont.Bold))
        title_lbl.setStyleSheet("color: #F8FAFC;")
        brand_row.addWidget(title_lbl)

        ver_badge = QLabel("v1.1.0")
        ver_badge.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; font-size: 11px; "
            "font-weight: bold; padding: 2px 7px; border-radius: 9px; border: 1px solid #0284C7;"
        )
        brand_row.addWidget(ver_badge)
        brand_row.addStretch()
        brand_col.addLayout(brand_row)

        sub_lbl = QLabel("Ultra-low latency audio stream over USB")
        sub_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        brand_col.addWidget(sub_lbl)
        header_layout.addLayout(brand_col)

        header_layout.addStretch()

        # Status Pill Badge
        self.status_pill = QLabel("○  DISCONNECTED")
        self.status_pill.setStyleSheet(
            "background-color: #181A20; color: #94A3B8; font-size: 12px; "
            "font-weight: bold; padding: 6px 14px; border-radius: 14px; border: 1px solid #2B2F3A;"
        )
        header_layout.addWidget(self.status_pill)
        main_layout.addLayout(header_layout)

        # 2. CARD: ADB & PHONE CONNECTION
        conn_group = QGroupBox("📱 Android Connection (ADB)")
        conn_layout = QGridLayout(conn_group)
        conn_layout.setContentsMargins(14, 14, 14, 14)
        conn_layout.setSpacing(10)

        conn_layout.addWidget(QLabel("Target Device:"), 0, 0)
        self.device_combo = QComboBox()
        conn_layout.addWidget(self.device_combo, 0, 1)

        self.btn_refresh_devices = QPushButton("↻ Refresh")
        self.btn_refresh_devices.setToolTip("Rescan connected ADB USB devices")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        conn_layout.addWidget(self.btn_refresh_devices, 0, 2)

        # Port & Quick Commands
        conn_layout.addWidget(QLabel("TCP Port:"), 1, 0)
        port_row = QHBoxLayout()
        port_row.setSpacing(8)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        self.port_spin.setFixedWidth(90)
        port_row.addWidget(self.port_spin)

        self.btn_copy_cmd = QPushButton("📋 Copy Forward Command")
        self.btn_copy_cmd.setToolTip("Copy 'adb forward tcp:PORT tcp:PORT' to clipboard")
        self.btn_copy_cmd.clicked.connect(self._copy_forward_command)
        port_row.addWidget(self.btn_copy_cmd)
        port_row.addStretch()

        conn_layout.addLayout(port_row, 1, 1, 1, 2)

        # Direct APK Install Button
        self.btn_install_apk = QPushButton("📲  Install & Launch APK on Phone")
        self.btn_install_apk.setToolTip("Install the latest Sonopipe APK to the connected device via ADB")
        self.btn_install_apk.setStyleSheet(
            "background-color: #172554; color: #60A5FA; border: 1px solid #2563EB; "
            "font-weight: bold; padding: 7px; border-radius: 6px;"
        )
        self.btn_install_apk.clicked.connect(self._on_install_apk_clicked)
        conn_layout.addWidget(self.btn_install_apk, 2, 0, 1, 3)

        main_layout.addWidget(conn_group)

        # 3. CARD: AUDIO CAPTURE & LATENCY ENGINE
        audio_group = QGroupBox("🔊 Audio Capture Engine")
        audio_layout = QGridLayout(audio_group)
        audio_layout.setContentsMargins(14, 14, 14, 14)
        audio_layout.setSpacing(10)

        audio_layout.addWidget(QLabel("Audio Source:"), 0, 0)
        self.source_combo = QComboBox()
        audio_layout.addWidget(self.source_combo, 0, 1)

        self.btn_refresh_sources = QPushButton("↻ Refresh")
        self.btn_refresh_sources.clicked.connect(self.refresh_audio_sources)
        audio_layout.addWidget(self.btn_refresh_sources, 0, 2)

        audio_layout.addWidget(QLabel("Capture Backend:"), 1, 0)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Auto (Recommended)", "PipeWire / PulseAudio", "WASAPI (Windows)", "Soundcard"])
        def_idx = 1 if get_default_backend_name() == "pulse" else (2 if get_default_backend_name() == "wasapi" else 0)
        self.backend_combo.setCurrentIndex(def_idx)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        audio_layout.addWidget(self.backend_combo, 1, 1, 1, 2)

        # Latency Preset Pills
        audio_layout.addWidget(QLabel("Latency Preset:"), 2, 0)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)

        self.preset_group = QButtonGroup(self)

        self.btn_preset_10 = QPushButton("⚡ Low (10ms)")
        self.btn_preset_10.setCheckable(True)
        self.btn_preset_10.setToolTip("480 frames. Lowest possible delay for gaming and real-time audio.")
        self.preset_group.addButton(self.btn_preset_10, 480)
        preset_row.addWidget(self.btn_preset_10)

        self.btn_preset_20 = QPushButton("⚖ Balanced (20ms)")
        self.btn_preset_20.setCheckable(True)
        self.btn_preset_20.setChecked(True)
        self.btn_preset_20.setToolTip("960 frames. Recommended balance of low latency and rock-solid stability.")
        self.preset_group.addButton(self.btn_preset_20, 960)
        preset_row.addWidget(self.btn_preset_20)

        self.btn_preset_40 = QPushButton("🛡 Reliable (40ms)")
        self.btn_preset_40.setCheckable(True)
        self.btn_preset_40.setToolTip("1920 frames. Extra buffer against audio underruns or busy CPU.")
        self.preset_group.addButton(self.btn_preset_40, 1920)
        preset_row.addWidget(self.btn_preset_40)

        self.preset_group.idClicked.connect(self._on_preset_changed)
        audio_layout.addLayout(preset_row, 2, 1, 1, 2)

        main_layout.addWidget(audio_group)

        # 4. CARD: MASTER VOLUME & STEREO VU METER
        vol_group = QGroupBox("🎚 Master Output & Live Levels")
        vol_layout = QVBoxLayout(vol_group)
        vol_layout.setContentsMargins(14, 14, 14, 14)
        vol_layout.setSpacing(10)

        # Volume row
        vol_row = QHBoxLayout()
        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedSize(34, 30)
        self.btn_mute.setToolTip("Toggle Mute")
        self.btn_mute.clicked.connect(self._toggle_mute)
        vol_row.addWidget(self.btn_mute)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self.vol_slider)

        self.lbl_volume = QLabel("100%")
        self.lbl_volume.setFixedWidth(46)
        self.lbl_volume.setFont(QFont("monospace", 10, QFont.Bold))
        self.lbl_volume.setStyleSheet("color: #F8FAFC;")
        vol_row.addWidget(self.lbl_volume)
        vol_layout.addLayout(vol_row)

        # Stereo VU Meter
        self.meter_widget = StereoVuMeterWidget()
        vol_layout.addWidget(self.meter_widget)

        main_layout.addWidget(vol_group)

        # 5. CARD: LIVE TELEMETRY TILES
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet(
            "background-color: #14161C; border: 1px solid #23262E; border-radius: 8px;"
        )
        t_layout = QGridLayout(telemetry_frame)
        t_layout.setContentsMargins(12, 10, 12, 10)
        t_layout.setSpacing(12)

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
        t4, self.lbl_delay = make_tile("BUFFER DELAY", "~20 ms", "#10B981")

        t_layout.addWidget(t1, 0, 0)
        t_layout.addWidget(t2, 0, 1)
        t_layout.addWidget(t3, 0, 2)
        t_layout.addWidget(t4, 0, 3)

        main_layout.addWidget(telemetry_frame)

        main_layout.addStretch()

        # 6. ACTION BUTTON (START / STOP STREAMING)
        self.btn_toggle = QPushButton("▶  START STREAMING")
        self.btn_toggle.setFixedHeight(54)
        self.btn_toggle.setFont(QFont("sans-serif", 14, QFont.Bold))
        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 10px; font-weight: bold; border: none;"
        )
        self.btn_toggle.clicked.connect(self.toggle_streaming)
        main_layout.addWidget(self.btn_toggle)

    def _apply_theme(self):
        style = """
        QMainWindow, QWidget {
            background-color: #0F1115;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }
        QGroupBox {
            background-color: #181A20;
            border: 1px solid #262932;
            border-radius: 10px;
            margin-top: 10px;
            padding-top: 14px;
            font-weight: bold;
            color: #94A3B8;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 14px;
            padding: 0 4px;
        }
        QComboBox, QSpinBox {
            background-color: #20232B;
            color: #F8FAFC;
            border: 1px solid #333844;
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 22px;
        }
        QComboBox:hover, QSpinBox:hover {
            border-color: #4B5563;
        }
        QComboBox:focus, QSpinBox:focus {
            border-color: #3B82F6;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton {
            background-color: #262932;
            color: #F8FAFC;
            border: 1px solid #373C48;
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #323743;
            border-color: #4B5563;
        }
        QPushButton:pressed {
            background-color: #1F222A;
        }
        QPushButton:checked {
            background-color: #1E3A8A;
            color: #60A5FA;
            border-color: #2563EB;
            font-weight: bold;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #20232B;
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

        saved_preset = self.settings.value("preset", 960, type=int)
        if saved_preset == 480:
            self.btn_preset_10.setChecked(True)
            self._on_preset_changed(480)
        elif saved_preset == 1920:
            self.btn_preset_40.setChecked(True)
            self._on_preset_changed(1920)
        else:
            self.btn_preset_20.setChecked(True)
            self._on_preset_changed(960)

    def _save_settings(self):
        self.settings.setValue("port", self.port_spin.value())
        self.settings.setValue("volume", self.vol_slider.value())
        self.settings.setValue("preset", self.chunk_frames)

    def refresh_devices(self):
        self.device_combo.clear()
        if not self.adb.is_available():
            self.device_combo.addItem("⚠ ADB not found in PATH", "")
            return

        devices = self.adb.list_devices()
        if not devices:
            self.device_combo.addItem("○ No ADB devices connected via USB", "")
            return

        for dev in devices:
            name = dev.model or "Android Device"
            label = f"{name} ({dev.serial})"
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

        # 1. Automatic ADB Port Forwarding
        if self.adb.is_available():
            forward_ok = self.adb.forward_port(local_port=port, remote_port=port, serial=selected_serial)
            if not forward_ok:
                ans = QMessageBox.question(
                    self,
                    "ADB Forward Notice",
                    f"Could not automatically execute 'adb forward tcp:{port} tcp:{port}'.\n\n"
                    f"Ensure USB debugging is authorized on your phone.\n\n"
                    f"Do you want to continue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    return

        # 2. Extract options
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

        # 3. Create and launch AudioStreamer
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

        # Update UI state to Live
        self.status_pill.setText("●  LIVE STREAMING")
        self.status_pill.setStyleSheet(
            "background-color: #064E3B; color: #34D399; font-size: 12px; "
            "font-weight: bold; padding: 6px 14px; border-radius: 14px; border: 1px solid #059669;"
        )
        self.btn_toggle.setText("■  STOP STREAMING")
        self.btn_toggle.setStyleSheet(
            "background-color: #DC2626; color: #FFFFFF; border-radius: 10px; font-weight: bold; border: none;"
        )
        self._set_controls_enabled(False)

    def stop_streaming(self):
        if self.streamer:
            self.streamer.stop()
            self.streamer = None

        self.meter_widget.set_levels(0.0, 0.0, 0.0, 0.0)
        self.status_pill.setText("○  DISCONNECTED")
        self.status_pill.setStyleSheet(
            "background-color: #181A20; color: #94A3B8; font-size: 12px; "
            "font-weight: bold; padding: 6px 14px; border-radius: 14px; border: 1px solid #2B2F3A;"
        )
        self.btn_toggle.setText("▶  START STREAMING")
        self.btn_toggle.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; border-radius: 10px; font-weight: bold; border: none;"
        )
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool):
        self.device_combo.setEnabled(enabled)
        self.btn_refresh_devices.setEnabled(enabled)
        self.port_spin.setEnabled(enabled)
        self.backend_combo.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.btn_refresh_sources.setEnabled(enabled)
        self.btn_preset_10.setEnabled(enabled)
        self.btn_preset_20.setEnabled(enabled)
        self.btn_preset_40.setEnabled(enabled)

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
