"""
PySide6 GUI Main Window for ADBSound.
"""

from __future__ import annotations
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QBrush, QPen
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
    QProgressBar,
    QGroupBox,
    QFrame,
    QMessageBox,
)

from sonopipe.adb.manager import AdbManager, AdbDevice
from sonopipe.adb.installer import install_and_launch
from sonopipe.capture.factory import list_audio_devices, get_default_backend_name
from sonopipe.capture.base import AudioDeviceInfo
from sonopipe.stream.sender import AudioStreamer
from sonopipe.stream.protocol import DEFAULT_PORT, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS


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


class StreamerSignals(QObject):
    stats_updated = Signal(dict)
    error_occurred = Signal(str)


class LevelMeterWidget(QWidget):
    """Custom low-latency horizontal peak/RMS level meter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(14)
        self.setMaximumHeight(18)
        self._level = 0.0
        self._peak = 0.0

    def set_levels(self, level: float, peak: float):
        self._level = max(0.0, min(1.0, level))
        self._peak = max(0.0, min(1.0, peak))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Background track
        painter.setBrush(QBrush(QColor("#1F2228")))
        painter.setPen(QPen(QColor("#2E323B"), 1))
        painter.drawRoundedRect(0, 0, width, height, 4, 4)

        # Active fill width
        fill_w = int(width * self._level)
        if fill_w > 0:
            if self._level > 0.85:
                bar_color = QColor("#EF4444")
            elif self._level > 0.65:
                bar_color = QColor("#F59E0B")
            else:
                bar_color = QColor("#3B82F6")

            painter.setBrush(QBrush(bar_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(1, 1, fill_w - 2, height - 2, 3, 3)

        # Peak indicator line
        if self._peak > 0.01:
            peak_x = min(width - 2, int(width * self._peak))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawLine(peak_x, 1, peak_x, height - 2)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonopipe — PC Audio to Android Speaker")
        self.resize(540, 680)
        self.setMinimumWidth(480)

        self.adb = AdbManager()
        self.streamer: Optional[AudioStreamer] = None
        self.signals = StreamerSignals()
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.error_occurred.connect(self._on_error_occurred)

        self._init_ui()
        self._apply_dark_theme()
        self.refresh_devices()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 1. Header (Title + Status Indicator)
        header_layout = QHBoxLayout()
        title_label = QLabel("Sonopipe")
        title_label.setFont(QFont("sans-serif", 16, QFont.Bold))
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #EF4444; font-size: 16px;")
        header_layout.addWidget(self.status_dot)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: #9CA3AF; font-weight: bold;")
        header_layout.addWidget(self.status_label)
        main_layout.addLayout(header_layout)

        # 2. ADB Settings Group
        adb_group = QGroupBox("ADB Connection")
        adb_layout = QGridLayout(adb_group)
        adb_layout.setSpacing(10)

        adb_layout.addWidget(QLabel("Target Device:"), 0, 0)
        self.device_combo = QComboBox()
        adb_layout.addWidget(self.device_combo, 0, 1)

        self.btn_refresh_devices = QPushButton("Refresh")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        adb_layout.addWidget(self.btn_refresh_devices, 0, 2)

        adb_layout.addWidget(QLabel("TCP Port:"), 1, 0)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        adb_layout.addWidget(self.port_spin, 1, 1)

        self.btn_copy_cmd = QPushButton("Copy Forward Command")
        self.btn_copy_cmd.setToolTip("Copies 'adb forward tcp:PORT tcp:PORT' to clipboard")
        self.btn_copy_cmd.clicked.connect(self._copy_forward_command)
        adb_layout.addWidget(self.btn_copy_cmd, 1, 2)

        self.btn_install_apk = QPushButton("📱 Install APK to Phone")
        self.btn_install_apk.setToolTip("Install and launch the ADBSound app on the connected phone via ADB")
        self.btn_install_apk.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; border: 1px solid #0284C7; font-weight: bold; padding: 6px;"
        )
        self.btn_install_apk.clicked.connect(self._on_install_apk_clicked)
        adb_layout.addWidget(self.btn_install_apk, 2, 0, 1, 3)

        main_layout.addWidget(adb_group)

        # 3. Audio Capture Settings Group
        audio_group = QGroupBox("Audio Capture")
        audio_layout = QGridLayout(audio_group)
        audio_layout.setSpacing(10)

        audio_layout.addWidget(QLabel("Backend:"), 0, 0)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Auto", "Pulse/PipeWire", "WASAPI (Windows)", "Soundcard"])
        def_idx = 1 if get_default_backend_name() == "pulse" else (2 if get_default_backend_name() == "wasapi" else 0)
        self.backend_combo.setCurrentIndex(def_idx)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        audio_layout.addWidget(self.backend_combo, 0, 1, 1, 2)

        audio_layout.addWidget(QLabel("Audio Source:"), 1, 0)
        self.source_combo = QComboBox()
        audio_layout.addWidget(self.source_combo, 1, 1)

        self.btn_refresh_sources = QPushButton("Refresh")
        self.btn_refresh_sources.clicked.connect(self.refresh_audio_sources)
        audio_layout.addWidget(self.btn_refresh_sources, 1, 2)

        audio_layout.addWidget(QLabel("Sample Rate:"), 2, 0)
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["48000 Hz", "44100 Hz"])
        audio_layout.addWidget(self.rate_combo, 2, 1)

        audio_layout.addWidget(QLabel("Channels:"), 2, 2)
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(["Stereo (2)", "Mono (1)"])
        audio_layout.addWidget(self.channels_combo, 2, 3)

        main_layout.addWidget(audio_group)

        # 4. Volume & Audio Level Meter
        vol_group = QGroupBox("Volume & Live Meter")
        vol_layout = QVBoxLayout(vol_group)
        vol_layout.setSpacing(10)

        slider_row = QHBoxLayout()
        self.lbl_volume = QLabel("Volume: 100%")
        slider_row.addWidget(self.lbl_volume)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        slider_row.addWidget(self.vol_slider)
        vol_layout.addLayout(slider_row)

        vol_layout.addWidget(QLabel("Audio Activity:"))
        self.meter_widget = LevelMeterWidget()
        vol_layout.addWidget(self.meter_widget)

        main_layout.addWidget(vol_group)

        # 5. Live Transmission Stats
        stats_group = QGroupBox("Transmission Stats")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(8)

        stats_layout.addWidget(QLabel("Bitrate / Throughput:"), 0, 0)
        self.lbl_rate = QLabel("0.0 KB/s")
        self.lbl_rate.setStyleSheet("color: #3B82F6; font-weight: bold;")
        stats_layout.addWidget(self.lbl_rate, 0, 1)

        stats_layout.addWidget(QLabel("Transferred Data:"), 0, 2)
        self.lbl_total = QLabel("0.0 MB")
        stats_layout.addWidget(self.lbl_total, 0, 3)

        stats_layout.addWidget(QLabel("Session Uptime:"), 1, 0)
        self.lbl_uptime = QLabel("00:00")
        stats_layout.addWidget(self.lbl_uptime, 1, 1)

        stats_layout.addWidget(QLabel("Audio Delay / Buffer:"), 1, 2)
        self.lbl_buffer = QLabel("~20 ms")
        self.lbl_buffer.setStyleSheet("color: #10B981;")
        stats_layout.addWidget(self.lbl_buffer, 1, 3)

        main_layout.addWidget(stats_group)

        main_layout.addStretch()

        # 6. Action Button (Start / Stop)
        self.btn_toggle = QPushButton("Start Streaming")
        self.btn_toggle.setFixedHeight(50)
        self.btn_toggle.setFont(QFont("sans-serif", 13, QFont.Bold))
        self.btn_toggle.setStyleSheet(
            "background-color: #3B82F6; color: white; border-radius: 8px; font-weight: bold;"
        )
        self.btn_toggle.clicked.connect(self.toggle_streaming)
        main_layout.addWidget(self.btn_toggle)

    def _apply_dark_theme(self):
        style = """
        QMainWindow, QWidget {
            background-color: #121316;
            color: #F3F4F6;
            font-size: 13px;
        }
        QGroupBox {
            background-color: #1B1D22;
            border: 1px solid #2E323B;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 14px;
            font-weight: bold;
            color: #9CA3AF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 4px;
        }
        QComboBox, QSpinBox {
            background-color: #23262D;
            color: #F3F4F6;
            border: 1px solid #374151;
            border-radius: 6px;
            padding: 5px 8px;
            min-height: 22px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton {
            background-color: #2E323B;
            color: #F3F4F6;
            border: 1px solid #374151;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #374151;
        }
        QPushButton:pressed {
            background-color: #1F2937;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #23262D;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #3B82F6;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #FFFFFF;
            width: 14px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 7px;
        }
        """
        self.setStyleSheet(style)

    def refresh_devices(self):
        self.device_combo.clear()
        if not self.adb.is_available():
            self.device_combo.addItem("ADB not found in PATH", "")
            return

        devices = self.adb.list_devices()
        if not devices:
            self.device_combo.addItem("No ADB devices connected", "")
            return

        for dev in devices:
            label = f"{dev.serial} ({dev.model or 'Device'})"
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

    def _on_volume_changed(self, value: int):
        self.lbl_volume.setText(f"Volume: {value}%")
        if self.streamer:
            self.streamer.set_volume(value / 100.0)

    def _copy_forward_command(self):
        port = self.port_spin.value()
        cmd = f"adb forward tcp:{port} tcp:{port}"
        QApplication.clipboard().setText(cmd)
        QMessageBox.information(self, "Copied", f"Command copied to clipboard:\n\n{cmd}")

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
        self.btn_install_apk.setText("📱 Install APK to Phone")
        if success:
            QMessageBox.information(self, "Installation Succeeded", msg)
        else:
            QMessageBox.warning(self, "Installation Failed", msg)

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
                    "ADB Forward Warning",
                    f"Failed to automatically execute 'adb forward tcp:{port} tcp:{port}'.\n\n"
                    f"Is your phone connected with USB debugging turned on?\n\n"
                    f"Do you want to continue anyway?",
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
        sample_rate = 48000 if self.rate_combo.currentIndex() == 0 else 44100
        channels = 2 if self.channels_combo.currentIndex() == 0 else 1
        vol = self.vol_slider.value() / 100.0

        # 3. Create and launch AudioStreamer
        self.streamer = AudioStreamer(
            host="127.0.0.1",
            port=port,
            sample_rate=sample_rate,
            channels=channels,
            chunk_frames=960,
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

        self.status_dot.setStyleSheet("color: #10B981; font-size: 16px;")
        self.status_label.setText("Streaming Active")
        self.status_label.setStyleSheet("color: #10B981; font-weight: bold;")
        self.btn_toggle.setText("Stop Streaming")
        self.btn_toggle.setStyleSheet(
            "background-color: #EF4444; color: white; border-radius: 8px; font-weight: bold;"
        )
        self._set_controls_enabled(False)

    def stop_streaming(self):
        if self.streamer:
            self.streamer.stop()
            self.streamer = None

        self.meter_widget.set_levels(0.0, 0.0)
        self.status_dot.setStyleSheet("color: #EF4444; font-size: 16px;")
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: #9CA3AF; font-weight: bold;")
        self.btn_toggle.setText("Start Streaming")
        self.btn_toggle.setStyleSheet(
            "background-color: #3B82F6; color: white; border-radius: 8px; font-weight: bold;"
        )
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool):
        self.device_combo.setEnabled(enabled)
        self.btn_refresh_devices.setEnabled(enabled)
        self.port_spin.setEnabled(enabled)
        self.backend_combo.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.btn_refresh_sources.setEnabled(enabled)
        self.rate_combo.setEnabled(enabled)
        self.channels_combo.setEnabled(enabled)

    def _on_stats_updated(self, stats: dict):
        mb = stats.get("bytes_sent", 0) / (1024.0 * 1024.0)
        self.lbl_total.setText(f"{mb:.1f} MB")

        rate = stats.get("kb_per_sec", 0.0)
        self.lbl_rate.setText(f"{rate:.1f} KB/s")

        uptime = int(stats.get("uptime", 0))
        mins, secs = divmod(uptime, 60)
        self.lbl_uptime.setText(f"{mins:02d}:{secs:02d}")

        rms = stats.get("rms_level", 0.0)
        peak = stats.get("peak_level", 0.0)
        self.meter_widget.set_levels(rms, peak)

    def _on_error_occurred(self, err_msg: str):
        self.stop_streaming()
        QMessageBox.warning(
            self,
            "Connection Error",
            f"Audio transmission encountered an error:\n\n{err_msg}\n\n"
            f"Make sure the ADBSound app is running on your phone with the receiver turned on."
        )

    def closeEvent(self, event):
        self.stop_streaming()
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
