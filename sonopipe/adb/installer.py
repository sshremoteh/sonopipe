"""
Helper for building, locating, and installing the Android APK onto connected devices.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from typing import Callable, Optional, Tuple

from sonopipe.adb.manager import AdbManager


def get_project_root() -> str:
    """Return the root directory of the adbsound project."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def find_apk_file() -> Optional[str]:
    """Search for the compiled APK in known build directories."""
    root = get_project_root()
    candidates = [
        os.path.join(root, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
        os.path.join(root, "android", "app", "build", "outputs", "apk", "release", "app-release-unsigned.apk"),
        os.path.join(root, "apk", "app-debug.apk"),
        os.path.join(root, "app-debug.apk"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 10000:
            return c
    return None


def build_apk(
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Execute Gradle to build the debug APK."""
    root = get_project_root()
    android_dir = os.path.join(root, "android")

    gradlew = os.path.join(android_dir, "gradlew" + (".bat" if sys.platform == "win32" else ""))
    if not os.path.isfile(gradlew):
        return False, f"Gradle wrapper not found in {android_dir}"

    env = os.environ.copy()
    # Check for Java 17 if current is newer or unset
    if "JAVA_HOME" not in env:
        for candidate_jvm in [
            "/usr/lib/jvm/java-17-openjdk",
            "/usr/lib/jvm/java-21-openjdk",
            "/usr/lib/jvm/default",
        ]:
            if os.path.isdir(candidate_jvm):
                env["JAVA_HOME"] = candidate_jvm
                break

    # Check for Android SDK
    if "ANDROID_HOME" not in env:
        for candidate_sdk in [
            os.path.expanduser("~/Android/Sdk"),
            os.path.expanduser("~/.android/sdk"),
            "/opt/android-sdk",
        ]:
            if os.path.isdir(candidate_sdk):
                env["ANDROID_HOME"] = candidate_sdk
                break

    if progress_cb:
        progress_cb("Starting Gradle APK build (assembleDebug)...")

    cmd = [gradlew, "assembleDebug"]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=android_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        lines = []
        for line in proc.stdout:
            lines.append(line)
            clean_l = line.strip()
            if clean_l and progress_cb and (clean_l.startswith("> Task") or "Building" in clean_l):
                progress_cb(clean_l)

        proc.wait()
        full_output = "".join(lines)
        if proc.returncode == 0:
            apk_path = find_apk_file()
            if apk_path:
                return True, apk_path
            return False, "Build succeeded, but APK was not found in outputs folder."
        else:
            return False, f"Gradle build failed with code {proc.returncode}:\n{full_output[-1500:]}"
    except Exception as e:
        return False, f"Failed to execute Gradle: {e}"


def install_and_launch(
    serial: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Find or build the APK, install it to device via ADB, and launch the app."""
    adb = AdbManager()
    if not adb.is_available():
        return False, "ADB is not installed or not found in PATH."

    devices = adb.list_devices()
    if not devices:
        return False, "No Android devices connected via ADB. Please connect your phone with USB debugging enabled."

    target_serial = serial or devices[0].serial

    # 1. Check if APK is already built
    apk_path = find_apk_file()
    if not apk_path:
        if progress_cb:
            progress_cb("APK not found, building APK with Gradle...")
        ok, res = build_apk(progress_cb)
        if not ok:
            return False, f"Failed to build APK: {res}"
        apk_path = res

    # 2. Install APK via ADB
    if progress_cb:
        progress_cb(f"Installing APK onto device {target_serial}...")
    success, output = adb.install_apk(apk_path, serial=target_serial)
    if not success:
        return False, f"Failed to install APK: {output}"

    # 3. Launch App on phone
    if progress_cb:
        progress_cb("Launching ADBSound on device...")
    launch_ok, launch_out = adb.launch_app(serial=target_serial)

    return True, f"ADBSound APK successfully installed and launched on {target_serial}!"
