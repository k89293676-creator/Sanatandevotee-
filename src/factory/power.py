"""Power/battery policy and sleep inhibit."""
from __future__ import annotations
import shutil, subprocess, sys
from .config import load_config
from .logging_setup import setup_logging

log = setup_logging("power")
cfg = load_config()


def is_on_battery() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            st = SYSTEM_POWER_STATUS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st))
            return st.ACLineStatus == 0
        except Exception:
            return False
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
            return "Battery Power" in r.stdout
        except Exception:
            return False
    # linux
    try:
        from pathlib import Path
        st = Path("/sys/class/power_supply/BAT0/status")
        if st.exists():
            return st.read_text().strip() != "Charging" and "Discharging" in st.read_text()
    except Exception:
        pass
    return False


def battery_pct() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            class SPS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            st = SPS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st))
            return int(st.BatteryLifePercent)
        except Exception:
            return 100
    return 100


def can_render() -> bool:
    lc = cfg["laptop"]
    if not lc.get("render_on_battery", False) and is_on_battery():
        if battery_pct() < lc.get("min_battery_pct", 50):
            return False
    return True


def max_threads() -> int:
    return 2