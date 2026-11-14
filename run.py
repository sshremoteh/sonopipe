#!/usr/bin/env python3
"""
Convenience launcher for ADBSound.
"""
import os
import sys

# Suppress noisy Qt Wayland client textinput warnings on Hyprland/Wayland
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland*=false")

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sonopipe.main import main

if __name__ == "__main__":
    main()
