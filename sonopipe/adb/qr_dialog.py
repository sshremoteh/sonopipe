"""
QR Code Dialog for Android Wireless ADB pairing and Wi-Fi connection.
"""

from __future__ import annotations
import io
import random
import socket
from typing import Optional

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QMessageBox,
)

from sonopipe.adb.manager import AdbManager


def get_local_lan_ip() -> str:
    """Determine the PC's primary LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually send data
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generate_qr_pixmap(data: str, size: int = 220) -> QPixmap:
    """Generate a clean QPixmap containing the QR code for given string data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qimg = QImage()
    qimg.loadFromData(buf.getvalue())
    return QPixmap.fromImage(qimg).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class WirelessQrDialog(QDialog):
    """
    Material Design 3 dialog displaying QR codes for Wireless ADB pairing
    and local network quick connection.
    """

    def __init__(self, adb: AdbManager, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.setWindowTitle("Wireless ADB QR Pairing")
        self.resize(500, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F1116;
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QTabWidget::pane {
                border: 1px solid #262934;
                border-radius: 12px;
                background-color: #171A21;
                padding: 16px;
            }
            QTabBar::tab {
                background-color: #12141A;
                color: #94A3B8;
                padding: 8px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background-color: #1E3A8A;
                color: #60A5FA;
                border-bottom: 2px solid #3B82F6;
            }
            QLabel {
                color: #CBD5E1;
            }
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 9px 18px;
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
        h_lbl = QLabel("📷 Wireless ADB QR Pairing")
        h_lbl.setFont(QFont("sans-serif", 16, QFont.Bold))
        h_lbl.setStyleSheet("color: #F8FAFC;")
        layout.addWidget(h_lbl)

        sub = QLabel("Scan the QR code with your phone to pair or configure Wireless ADB.")
        sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(sub)

        # Tabs
        tabs = QTabWidget()

        # Tab 1: Android 11+ System QR Pairing
        tab1 = QWidget()
        l1 = QVBoxLayout(tab1)
        l1.setSpacing(10)
        l1.setAlignment(Qt.AlignCenter)

        desc1 = QLabel("1. On Phone: Settings → Developer options → Wireless debugging\n2. Tap 'Pair device with QR code' and scan this:")
        desc1.setStyleSheet("color: #94A3B8; font-size: 11px;")
        desc1.setAlignment(Qt.AlignCenter)
        l1.addWidget(desc1)

        # Generate standard AOSP Wi-Fi ADB QR string: WIFI:T:ADB;S:Sonopipe;P:<code_6_digits>;;
        self.pairing_code = f"{random.randint(100000, 999999)}"
        qr_string_adb = f"WIFI:T:ADB;S:Sonopipe;P:{self.pairing_code};;"

        qr_label1 = QLabel()
        qr_label1.setPixmap(generate_qr_pixmap(qr_string_adb, size=210))
        qr_label1.setAlignment(Qt.AlignCenter)
        qr_label1.setStyleSheet("background-color: white; padding: 10px; border-radius: 12px;")
        l1.addWidget(qr_label1)

        code_lbl = QLabel(f"Pairing Password: {self.pairing_code}")
        code_lbl.setFont(QFont("monospace", 12, QFont.Bold))
        code_lbl.setStyleSheet("color: #38BDF8;")
        code_lbl.setAlignment(Qt.AlignCenter)
        l1.addWidget(code_lbl)

        tabs.addTab(tab1, "Android 11+ System QR")

        # Tab 2: Wi-Fi Quick Connect info
        tab2 = QWidget()
        l2 = QVBoxLayout(tab2)
        l2.setSpacing(10)
        l2.setAlignment(Qt.AlignCenter)

        local_ip = get_local_lan_ip()
        connect_str = f"sonopipe://connect?ip={local_ip}&port=5555"

        desc2 = QLabel(f"PC Local IP: {local_ip}\nUse your phone camera or QR scanner to copy address:")
        desc2.setStyleSheet("color: #94A3B8; font-size: 11px;")
        desc2.setAlignment(Qt.AlignCenter)
        l2.addWidget(desc2)

        qr_label2 = QLabel()
        qr_label2.setPixmap(generate_qr_pixmap(connect_str, size=210))
        qr_label2.setAlignment(Qt.AlignCenter)
        qr_label2.setStyleSheet("background-color: white; padding: 10px; border-radius: 12px;")
        l2.addWidget(qr_label2)

        l2.addWidget(QLabel(f"Target: adb connect {local_ip}:5555"))

        tabs.addTab(tab2, "LAN Connect QR")
        layout.addWidget(tabs)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(38)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class WirelessPairDialog(QDialog):
    """Dialog to pair devices using Android 11+ Wireless Pairing Code."""

    def __init__(self, adb: AdbManager, default_ip: str = "", parent=None):
        super().__init__(parent)
        self.adb = adb
        self.setWindowTitle("Android 11+ Wireless Pairing")
        self.resize(420, 260)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0D12;
                color: #F8FAFC;
            }
            QLabel {
                color: #94A3B8;
                font-size: 12px;
            }
            QLineEdit, QSpinBox {
                background-color: #13161F;
                color: #F8FAFC;
                border: 1px solid #1E2330;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 6px;
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
        btn_cancel.setStyleSheet("background-color: #1E2330; color: #94A3B8;")
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
            QMessageBox.information(
                self,
                "Pairing Successful",
                f"Successfully paired with {host}:{port}!\n\nNow enter the main connection port and click Connect Wi-Fi.",
            )
            self.accept()
        else:
            QMessageBox.warning(self, "Pairing Failed", f"Could not pair:\n\n{msg}")

